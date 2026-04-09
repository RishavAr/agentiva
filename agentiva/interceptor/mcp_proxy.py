from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agentiva.interceptor.core import Agentiva


class MCPRequest(BaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    agent_id: str = "mcp-agent"
    # Optional upstream selector. Only honored when proxy is started with
    # multi-upstream routing enabled and the alias is explicitly configured.
    upstream: Optional[str] = None


def _parse_upstream_aliases(items: list[str] | None) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for raw in items or []:
        s = (raw or "").strip()
        if not s:
            continue
        if "=" not in s:
            raise SystemExit(f"Invalid --upstream-alias {raw!r} (expected NAME=host:port)")
        name, target = s.split("=", 1)
        name = name.strip()
        target = target.strip()
        if not name or not target:
            raise SystemExit(f"Invalid --upstream-alias {raw!r} (expected NAME=host:port)")
        aliases[name] = target
    return aliases


def create_mcp_proxy_app(
    *,
    upstream: str,
    shield: Agentiva,
    upstream_aliases: dict[str, str] | None = None,
    allow_request_upstream: bool = False,
) -> FastAPI:
    app = FastAPI(title="Agentiva MCP Proxy")
    aliases = dict(upstream_aliases or {})

    @app.post("/mcp/call")
    async def mcp_call(req: MCPRequest):
        chosen_upstream = upstream
        chosen_alias = ""
        if req.upstream:
            if not allow_request_upstream:
                raise HTTPException(status_code=400, detail="Request upstream selection is disabled on this proxy.")
            alias = str(req.upstream).strip()
            if alias not in aliases:
                raise HTTPException(status_code=400, detail=f"Unknown upstream alias: {alias}")
            chosen_upstream = aliases[alias]
            chosen_alias = alias

        action, negotiation = await shield.intercept_with_negotiation(
            req.tool_name,
            req.arguments,
            req.agent_id,
            context={
                "mcp_upstream": chosen_upstream,
                "mcp_upstream_alias": chosen_alias,
                "mcp_route": "/mcp/call",
            },
        )
        if action.decision == "block":
            return {
                "blocked": True,
                "decision": action.decision,
                "risk_score": action.risk_score,
                "negotiation": negotiation.to_dict() if negotiation else None,
            }

        try:
            async with httpx.AsyncClient(base_url=f"http://{chosen_upstream}") as client:
                resp = await client.post(
                    "/mcp/call",
                    json={
                        "tool_name": req.tool_name,
                        "arguments": req.arguments,
                        "agent_id": req.agent_id,
                    },
                )
            return {"blocked": False, "upstream_status": resp.status_code, "upstream_response": resp.json()}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Upstream MCP error: {exc}") from exc

    return app


def run_proxy(
    *,
    upstream: str,
    port: int,
    upstream_aliases: dict[str, str] | None = None,
    allow_request_upstream: bool = False,
) -> None:
    import uvicorn

    shield = Agentiva(mode="shadow", policy_path="policies/default.yaml")
    app = create_mcp_proxy_app(
        upstream=upstream,
        shield=shield,
        upstream_aliases=upstream_aliases,
        allow_request_upstream=allow_request_upstream,
    )
    uvicorn.run(app, host="0.0.0.0", port=port)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", default="localhost:3001")
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument(
        "--upstream-alias",
        action="append",
        default=[],
        help="Additional upstreams by alias, e.g. --upstream-alias prod=mcp.prod:3001 (repeatable)",
    )
    parser.add_argument(
        "--multi-upstream",
        action="store_true",
        help="Allow requests to select an upstream via MCPRequest.upstream alias",
    )
    args = parser.parse_args()
    aliases = _parse_upstream_aliases(args.upstream_alias)
    run_proxy(
        upstream=args.upstream,
        port=args.port,
        upstream_aliases=aliases,
        allow_request_upstream=bool(args.multi_upstream),
    )


if __name__ == "__main__":
    main()
