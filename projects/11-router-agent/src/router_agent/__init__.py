"""11 - Router agent: rules + LLM intent classifier with confidence, dispatch and fallback."""

__version__ = "1.0.0"

from .agent import EvalReport, Response, RouterAgent, evaluate, load_labelled, print_report
from .config import Settings
from .llm import MockRouterLLM, make_llm
from .router import FALLBACK, Intent, RouteDecision, Router
from .specialists import BillingAgent, FallbackAgent, SalesAgent, TechSupportAgent
from .trace import Trace

__all__ = [
    "FALLBACK", "BillingAgent", "EvalReport", "FallbackAgent", "Intent", "MockRouterLLM", "Response",
    "RouteDecision", "Router", "RouterAgent", "SalesAgent", "Settings", "TechSupportAgent", "Trace", "evaluate",
    "load_labelled", "make_llm", "print_report",
]
