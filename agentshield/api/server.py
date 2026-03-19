import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

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


class ApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    reason: str = ""


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
    try:
        action = await shield.intercept(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_id=request.agent_id,
        )
    except Exception as exc:
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
    return {"status": "processed", "action_id": request.action_id, "approved": request.approved}


@app.post("/api/v1/mode/{new_mode}")
async def change_mode(new_mode: str) -> Dict[str, str]:
    if new_mode not in ("shadow", "live", "approval"):
        raise HTTPException(status_code=400, detail="Mode must be: shadow, live, or approval")
    shield = get_shield()
    shield.mode = new_mode
    logger.info("mode_changed mode=%s", new_mode)
    return {"status": "ok", "mode": new_mode}


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
