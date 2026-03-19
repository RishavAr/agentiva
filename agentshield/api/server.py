import logging
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from agentshield.db.database import (
    add_approval_log,
    add_negotiation_log,
    add_policy_history,
    enqueue_approval,
    health_check_db,
    init_db,
    list_negotiations,
    log_action,
    touch_agent_registry,
)
from agentshield.interceptor.core import AgentShield

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agentshield.api")


class InterceptRequest(BaseModel):
    tool_name: str = Field(
        ..., min_length=1, max_length=256, description="Name of the tool being called"
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool call arguments"
    )
    agent_id: str = Field(
        default="default", max_length=128, description="Identifier for the agent"
    )

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name cannot be empty")
        return value.strip()


class InterceptResponse(BaseModel):
    action_id: str
    tool_name: str
    arguments: Dict[str, Any]
    agent_id: str
    decision: str
    risk_score: float
    mode: str
    timestamp: str


class AuditEntry(BaseModel):
    action_id: str
    tool_name: str
    arguments: Dict[str, Any]
    agent_id: str
    decision: str
    risk_score: float
    mode: str
    timestamp: str


class ShadowReport(BaseModel):
    total_actions: int
    by_tool: Dict[str, int]
    by_decision: Dict[str, int]
    avg_risk_score: float


class PolicyUpdateRequest(BaseModel):
    policy_yaml: str = Field(..., min_length=1, description="YAML policy content")


class HealthResponse(BaseModel):
    status: str
    version: str
    mode: str
    total_actions_intercepted: int
    uptime_seconds: float


class MetricsResponse(BaseModel):
    total_requests: int
    avg_latency_ms: float
    error_rate: float


class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    reason: str = ""


class ApprovalSubmitRequest(BaseModel):
    action_id: str
    reason: str = ""
    requested_by: str = "agent"


class RetryRequest(BaseModel):
    modified_arguments: Dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(default="agent", max_length=128)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected total=%d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("websocket_disconnected total=%d", len(self.active_connections))

    async def broadcast(self, message: Dict[str, Any]) -> None:
        disconnected: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for connection in disconnected:
            self.disconnect(connection)


_shield: Optional[AgentShield] = None
_manager = ConnectionManager()
_start_time: Optional[datetime] = None
_pending_approvals: Dict[str, bool] = {}
_request_counts_by_agent: Dict[str, Deque[float]] = {}
_rate_limit_per_minute = int(os.getenv("AGENTSHIELD_RATE_LIMIT_PER_MINUTE", "100"))
_metrics: Dict[str, float] = {
    "total_requests": 0,
    "total_errors": 0,
    "total_latency_ms": 0.0,
}
_retry_chain: Dict[str, Dict[str, Any]] = {}


def get_shield() -> AgentShield:
    if _shield is None:
        raise HTTPException(status_code=500, detail="AgentShield not initialized")
    return _shield


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _shield, _start_time
    _start_time = datetime.now(timezone.utc)
    mode = os.getenv("AGENTSHIELD_MODE", "shadow")
    policy_path = "policies/default.yaml" if os.path.exists("policies/default.yaml") else None
    await init_db()
    if not await health_check_db():
        raise RuntimeError("Database health check failed at startup")
    if policy_path:
        with open(policy_path, encoding="utf-8") as handle:
            yaml.safe_load(handle)
    _shield = AgentShield(mode=mode, policy_path=policy_path)
    logger.info("agentshield_started mode=%s policy=%s", mode, policy_path)
    try:
        yield
    finally:
        logger.info("agentshield_stopping")


app = FastAPI(
    title="AgentShield",
    description="Preview deployments for AI agents. Intercept, preview, approve, and rollback agent actions.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()
    _metrics["total_requests"] += 1
    try:
        response = await call_next(request)
    except Exception as exc:
        _metrics["total_errors"] += 1
        logger.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_server_error",
                    "message": "Unexpected server error",
                    "request_id": request_id,
                }
            },
        )
    latency_ms = (time.perf_counter() - start) * 1000
    _metrics["total_latency_ms"] += latency_ms
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request request_id=%s method=%s path=%s status=%s latency_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )
    return response


def _rate_limit_allow(agent_id: str) -> bool:
    now = time.time()
    bucket = _request_counts_by_agent.setdefault(agent_id, deque())
    while bucket and (now - bucket[0]) > 60:
        bucket.popleft()
    if len(bucket) >= _rate_limit_per_minute:
        return False
    bucket.append(now)
    return True


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    shield = get_shield()
    if _start_time is None:
        raise HTTPException(status_code=500, detail="Server start time unavailable")
    elapsed = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        mode=shield.mode,
        total_actions_intercepted=len(shield.audit_log),
        uptime_seconds=round(elapsed, 2),
    )


@app.post("/api/v1/intercept", response_model=InterceptResponse)
async def intercept_action(request: InterceptRequest) -> InterceptResponse:
    shield = get_shield()
    if not _rate_limit_allow(request.agent_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for agent_id")
    try:
        action = await shield.intercept(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_id=request.agent_id,
        )
        await log_action(
            {
                "id": action.id,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
                "agent_id": action.agent_id,
                "decision": action.decision,
                "risk_score": action.risk_score,
                "mode": action.mode,
                "simulation_result": (action.result or {}).get("simulation"),
                "rollback_plan": action.rollback_plan,
            }
        )
        await touch_agent_registry(request.agent_id)
    except Exception as exc:
        _metrics["total_errors"] += 1
        logger.exception("interception_failed tool=%s", request.tool_name)
        raise HTTPException(status_code=500, detail=f"Interception failed: {exc}") from exc

    response = InterceptResponse(
        action_id=action.id,
        tool_name=action.tool_name,
        arguments=action.arguments,
        agent_id=action.agent_id,
        decision=action.decision,
        risk_score=action.risk_score,
        mode=action.mode,
        timestamp=action.timestamp,
    )

    await _manager.broadcast(response.model_dump())
    logger.info(
        "action_intercepted tool=%s decision=%s risk=%.2f agent=%s",
        action.tool_name,
        action.decision,
        action.risk_score,
        action.agent_id,
    )
    return response


@app.post("/api/v1/negotiate/{action_id}")
async def negotiate_action(action_id: str) -> Dict[str, Any]:
    shield = get_shield()
    action = next((a for a in shield.audit_log if a.id == action_id), None)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.decision not in {"block", "shadow"}:
        return {
            "action_id": action.id,
            "status": "skipped",
            "explanation": {
                "decision": action.decision,
                "reason": "not_blocked",
                "risk_score": action.risk_score,
                "risk_factors": [],
                "human_readable": "Negotiation is intended for blocked or shadowed actions.",
            },
            "suggestions": [],
            "proposed_safe_action": {},
            "escalation_available": False,
            "retry_endpoint": "",
        }

    negotiation = await shield.negotiator.negotiate(action, None)
    await add_negotiation_log(
        action_id=action.id,
        agent_id=action.agent_id,
        status=negotiation.status,
        explanation=negotiation.explanation,
        suggestions=negotiation.suggestions,
        proposed_safe_action=negotiation.proposed_safe_action,
    )
    return negotiation.to_dict()


@app.post("/api/v1/request-approval")
async def request_approval(request: ApprovalSubmitRequest) -> Dict[str, Any]:
    _pending_approvals[request.action_id] = False
    queue_id = await enqueue_approval(
        action_id=request.action_id,
        requested_by=request.requested_by,
        reason=request.reason,
    )
    await add_approval_log(
        action_id=request.action_id,
        approved=False,
        reason=request.reason,
        approved_by=request.requested_by,
    )
    await _manager.broadcast(
        {
            "event": "approval_requested",
            "queue_id": queue_id,
            "action_id": request.action_id,
            "requested_by": request.requested_by,
            "reason": request.reason,
            "status": "pending",
        }
    )
    return {
        "status": "requested",
        "queue_id": queue_id,
        "action_id": request.action_id,
        "requested_by": request.requested_by,
    }


@app.get("/api/v1/negotiation-history")
async def negotiation_history() -> List[Dict[str, Any]]:
    shield = get_shield()
    return shield.negotiator.get_history()


@app.get("/api/v1/negotiations")
async def negotiations(limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)) -> List[Dict[str, Any]]:
    rows = await list_negotiations(limit=limit, offset=offset)
    return [
        {
            "id": row.id,
            "action_id": row.action_id,
            "agent_id": row.agent_id,
            "status": row.status,
            "explanation": row.explanation,
            "suggestions": row.suggestions,
            "proposed_safe_action": row.proposed_safe_action,
            "timestamp": row.timestamp.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/v1/retry/{action_id}")
async def retry_action(action_id: str, request: RetryRequest) -> Dict[str, Any]:
    shield = get_shield()
    original = next((a for a in shield.audit_log if a.id == action_id), None)
    if original is None:
        raise HTTPException(status_code=404, detail="Original action not found")

    retried_action, negotiation = await shield.intercept_with_negotiation(
        tool_name=original.tool_name,
        arguments=request.modified_arguments,
        agent_id=original.agent_id,
    )
    _retry_chain[action_id] = {
        "original_action_id": action_id,
        "retried_action_id": retried_action.id,
        "original_decision": original.decision,
        "retried_decision": retried_action.decision,
        "modified_arguments": request.modified_arguments,
        "requested_by": request.requested_by,
    }
    await add_negotiation_log(
        action_id=retried_action.id,
        agent_id=retried_action.agent_id,
        status="retry",
        explanation={
            "decision": retried_action.decision,
            "reason": "retry_flow",
            "risk_score": retried_action.risk_score,
            "risk_factors": [],
            "human_readable": "Action retried after negotiation guidance.",
        },
        suggestions=(negotiation.suggestions if negotiation else []),
        proposed_safe_action=(negotiation.proposed_safe_action if negotiation else {}),
    )
    return {
        "status": "retried",
        "chain": _retry_chain[action_id],
        "action": {
            "id": retried_action.id,
            "decision": retried_action.decision,
            "risk_score": retried_action.risk_score,
        },
        "negotiation": negotiation.to_dict() if negotiation else None,
    }


@app.get("/api/v1/audit", response_model=List[AuditEntry])
async def get_audit_log(
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    decision: Optional[str] = Query(None, description="Filter by decision"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    min_risk: Optional[float] = Query(None, ge=0, le=1, description="Minimum risk score"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> List[AuditEntry]:
    shield = get_shield()
    entries = shield.audit_log

    if tool_name:
        entries = [a for a in entries if a.tool_name == tool_name]
    if decision:
        entries = [a for a in entries if a.decision == decision]
    if agent_id:
        entries = [a for a in entries if a.agent_id == agent_id]
    if min_risk is not None:
        entries = [a for a in entries if a.risk_score >= min_risk]

    paged = entries[offset : offset + limit]
    return [
        AuditEntry(
            action_id=a.id,
            tool_name=a.tool_name,
            arguments=a.arguments,
            agent_id=a.agent_id,
            decision=a.decision,
            risk_score=a.risk_score,
            mode=a.mode,
            timestamp=a.timestamp,
        )
        for a in paged
    ]


@app.get("/api/v1/report", response_model=ShadowReport)
async def get_shadow_report() -> ShadowReport:
    shield = get_shield()
    report = shield.get_shadow_report()
    return ShadowReport(**report)


@app.post("/api/v1/approve")
async def approve_action(request: ApprovalRequest) -> Dict[str, Any]:
    if request.action_id not in _pending_approvals:
        raise HTTPException(status_code=404, detail="No pending approval for this action")
    _pending_approvals[request.action_id] = request.approved
    await add_approval_log(
        action_id=request.action_id,
        approved=request.approved,
        reason=request.reason,
        approved_by="api",
    )
    return {"status": "processed", "action_id": request.action_id, "approved": request.approved}


@app.post("/api/v1/mode/{new_mode}")
async def change_mode(new_mode: str) -> Dict[str, str]:
    if new_mode not in ("shadow", "live", "approval"):
        raise HTTPException(status_code=400, detail="Mode must be: shadow, live, or approval")
    shield = get_shield()
    shield.mode = new_mode
    logger.info("mode_changed mode=%s", new_mode)
    return {"status": "ok", "mode": new_mode}


@app.post("/api/v1/policies")
async def update_policy(payload: PolicyUpdateRequest) -> Dict[str, str]:
    policy_yaml = payload.policy_yaml
    try:
        yaml.safe_load(policy_yaml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}") from exc

    policy_path = os.getenv("AGENTSHIELD_POLICY_PATH", "policies/default.yaml")
    os.makedirs(os.path.dirname(policy_path), exist_ok=True)
    with open(policy_path, "w", encoding="utf-8") as handle:
        handle.write(policy_yaml)
    await add_policy_history(policy_yaml=policy_yaml, applied_by="api")
    return {"status": "ok", "policy_path": policy_path}


@app.get("/api/v1/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    total_requests = int(_metrics["total_requests"])
    total_errors = int(_metrics["total_errors"])
    avg_latency = (_metrics["total_latency_ms"] / total_requests) if total_requests else 0.0
    error_rate = (total_errors / total_requests) if total_requests else 0.0
    return MetricsResponse(
        total_requests=total_requests,
        avg_latency_ms=round(avg_latency, 4),
        error_rate=round(error_rate, 4),
    )


@app.websocket("/ws/actions")
async def websocket_actions(websocket: WebSocket):
    await _manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _manager.disconnect(websocket)
    except Exception:
        _manager.disconnect(websocket)
        logger.exception("websocket_error")


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
