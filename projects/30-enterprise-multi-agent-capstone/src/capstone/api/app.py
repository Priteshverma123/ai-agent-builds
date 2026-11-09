"""FastAPI front door (recap of 26): /ask, /mcp (JSON-RPC), /tools, /traces/{id}, /healthz."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from capstone.container import System, build
from capstone.domain.models import AskRequest, AskResponse


def create_app(system: System | None = None) -> FastAPI:
    system = system or build()
    app = FastAPI(title="exe_404 Enterprise Assistant", version="1.0.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "tools": len(system.tool_server.tools)}

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest) -> AskResponse:
        response, _ = system.orchestrator.ask(body.question)
        return response

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        """Expose the same tools to any MCP-style client over HTTP."""
        reply = system.tool_server.handle_raw((await request.body()).decode("utf-8"))
        if reply is None:
            return Response(status_code=204)
        return Response(content=reply, media_type="application/json")

    @app.get("/tools")
    def tools() -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in system.tool_server.tools.values()]

    @app.get("/traces/{trace_id}")
    def trace(trace_id: str) -> JSONResponse:
        found = system.traces.get(trace_id)
        if found is None:
            raise HTTPException(404, f"trace '{trace_id}' not found")
        return JSONResponse({"trace_id": trace_id, "spans": found.to_dicts(), "tree": found.render()})

    return app
