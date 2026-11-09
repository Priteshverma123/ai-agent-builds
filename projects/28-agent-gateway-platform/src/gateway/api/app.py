"""FastAPI front door. Thin on purpose: parse, call the service, map errors to HTTP."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from gateway.container import Container, build
from gateway.domain.errors import Forbidden, GatewayError
from gateway.domain.models import ChatRequest, ChatResponse, Tenant


def _api_key(authorization: str | None = Header(default=None),
             x_api_key: str | None = Header(default=None)) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return x_api_key


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build()
    service = container.service
    app = FastAPI(title="exe_404 Agent Gateway", version="1.0.0")

    @app.exception_handler(GatewayError)
    def _gateway_error(_: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, headers=exc.headers,
                            content={"error": {"code": exc.code, "message": exc.message}})

    def tenant_of(key: str | None = Depends(_api_key)) -> Tenant:
        return service.keys.authenticate(key)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/v1/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, key: str | None = Depends(_api_key)) -> JSONResponse:
        response = service.chat(key, body)
        tenant = service.keys.authenticate(key)
        return JSONResponse(content=response.model_dump(), headers={
            "X-RateLimit-Remaining": str(service.limiter.remaining(tenant)),
            "X-Cache": "HIT" if response.cached else "MISS",
            "X-Model": response.model})

    @app.get("/v1/usage")
    def usage(tenant: str | None = None, caller: Tenant = Depends(tenant_of)) -> dict:
        return service.usage(caller, tenant)

    @app.get("/v1/audit")
    def audit(caller: Tenant = Depends(tenant_of)) -> dict:
        if not caller.is_admin:
            raise Forbidden("audit log requires an admin key")
        ok, bad = service.audit.verify()
        return {"verified": ok, "first_bad_seq": bad, "entries": service.audit.entries()}

    return app
