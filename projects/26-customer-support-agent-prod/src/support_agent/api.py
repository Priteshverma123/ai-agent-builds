"""HTTP layer. Thin on purpose: validate input, call the agent, shape the output."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .adapters.llm import LLM
from .bootstrap import build_agent
from .config import Settings
from .domain.models import Citation, Ticket, TicketStatus, ToolRecord
from .observability import configure_logging
from .services.agent import ConversationForbidden, SupportAgent


class ChatRequest(BaseModel):
    customer_id: str = Field(pattern=r"^C-\d{3,6}$")
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    citations: list[Citation]
    tool_calls: list[ToolRecord]
    escalated: bool
    ticket_id: str | None
    trace_id: str


class ResolveRequest(BaseModel):
    approve: bool
    agent: str = Field(min_length=1, max_length=64)


def create_app(settings: Settings | None = None, llm: LLM | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    agent: SupportAgent = build_agent(settings, llm)
    app = FastAPI(title="Support Agent", version=__version__)
    app.state.agent = agent

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if settings.api_key and x_api_key != settings.api_key:
            raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "llm_provider": agent.llm.name,
                "orders_loaded": len(agent.tools.repo), "policy_chunks": len(agent.index.chunks)}

    @app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_key)])
    def chat(req: ChatRequest) -> ChatResponse:
        try:
            result = agent.handle(req.customer_id, req.message, req.conversation_id)
        except ConversationForbidden:
            raise HTTPException(status_code=403, detail="conversation belongs to another customer")
        return ChatResponse(conversation_id=result.conversation_id, reply=result.reply,
                            citations=result.citations, tool_calls=result.tools, escalated=result.escalated,
                            ticket_id=result.ticket_id, trace_id=result.trace_id)

    @app.get("/traces/{trace_id}", dependencies=[Depends(require_key)])
    def get_trace(trace_id: str) -> dict[str, Any]:
        trace = agent.traces.get(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return trace.model_dump() | {"total_ms": trace.total_ms}

    @app.get("/queue", response_model=list[Ticket], dependencies=[Depends(require_key)])
    def queue(status: TicketStatus | None = None) -> list[Ticket]:
        return agent.tools.queue.list(status)

    @app.post("/queue/{ticket_id}/resolve", response_model=Ticket, dependencies=[Depends(require_key)])
    def resolve(ticket_id: str, req: ResolveRequest) -> Ticket:
        try:
            return agent.resolve_ticket(ticket_id, req.approve, req.agent)
        except KeyError:
            raise HTTPException(status_code=404, detail="ticket not found")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    return app
