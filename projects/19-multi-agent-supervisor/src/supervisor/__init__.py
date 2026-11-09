"""A supervisor agent delegating to researcher / coder / reviewer workers over typed messages and shared state."""

from .messages import Decision, Delegation, WorkerResult
from .state import SharedState
from .supervisor import Deliverable, Limits, Supervisor

__version__ = "0.2.0"

__all__ = ["Decision", "Delegation", "WorkerResult", "SharedState", "Deliverable", "Limits", "Supervisor"]
