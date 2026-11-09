"""Guardrails against prompt injection: detect, sanitise, enforce policy, guard the doors."""

from .agent import GuardConfig, GuardedAgent
from .detectors import detect, sanitise
from .policy import ToolPolicy

__version__ = "0.1.0"

__all__ = ["GuardConfig", "GuardedAgent", "ToolPolicy", "__version__", "detect", "sanitise"]
