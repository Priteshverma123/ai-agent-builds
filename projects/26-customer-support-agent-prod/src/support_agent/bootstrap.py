"""Composition root: the one place that wires adapters, services and settings together."""

from __future__ import annotations

from .adapters.human_queue import HumanQueue
from .adapters.llm import LLM
from .adapters.providers import build_llm
from .adapters.repository import OrderRepository, RefundLedger
from .config import Settings
from .domain.policy import RefundPolicy
from .observability import TraceStore
from .services.agent import SupportAgent
from .services.retrieval import PolicyIndex
from .services.tools import SupportTools


def build_agent(settings: Settings, llm: LLM | None = None) -> SupportAgent:
    index = PolicyIndex.from_dir(settings.data_dir / "policies")
    tools = SupportTools(
        repo=OrderRepository.from_json(settings.data_dir / "orders.json"),
        ledger=RefundLedger(),
        queue=HumanQueue(),
        index=index,
        policy=RefundPolicy(settings.refund_window_days, settings.refund_auto_approve_limit),
        clock=settings.current_date,
    )
    return SupportAgent(llm or build_llm(settings), tools, index, TraceStore(settings.trace_capacity), settings)
