"""Diff-aware code review agent: static checks + an LLM pass with guardrails."""

from .agent import ReviewAgent, ReviewResult
from .findings import Finding, Severity

__version__ = "0.1.0"

__all__ = ["Finding", "ReviewAgent", "ReviewResult", "Severity", "__version__"]
