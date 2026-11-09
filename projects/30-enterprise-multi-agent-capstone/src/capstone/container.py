"""Composition root: builds the whole system. The only module that knows every concrete class."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from capstone.adapters.llm import LLM, default_llm
from capstone.adapters.mcp import InProcessTransport, McpClient, McpServer, Transport
from capstone.config import Settings
from capstone.services.agents import default_specialists
from capstone.services.orchestrator import Orchestrator
from capstone.services.rag import DocIndex
from capstone.services.toolkit import TicketDesk, build_tool_server
from capstone.services.tracing import TraceStore

DOCS = Settings.from_env().docs_dir


@dataclass
class System:
    orchestrator: Orchestrator
    tool_server: McpServer
    desk: TicketDesk
    traces: TraceStore


def build(docs: Path | None = None, llm: LLM | None = None, transport: Transport | None = None,
          trace_path: Path | None = None, settings: Settings | None = None) -> System:
    """Wire the system. Explicit arguments win over `Settings` (which defaults to the environment)."""
    settings = settings or Settings.from_env()
    desk = TicketDesk()
    server = build_tool_server(DocIndex.from_folder(docs or settings.docs_dir), desk)
    client = McpClient(transport or InProcessTransport(server))
    client.initialize()
    traces = TraceStore(trace_path)
    orchestrator = Orchestrator(llm or default_llm(settings), client, default_specialists(), traces,
                                max_steps=settings.max_steps)
    return System(orchestrator, server, desk, traces)
