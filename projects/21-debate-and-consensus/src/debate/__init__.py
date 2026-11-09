"""Multiple agents argue in rounds; a deterministic judge aggregates and surfaces disagreement."""

from .debate import Debate
from .debater import Debater, make_panel
from .judge import judge
from .messages import Argument, Position, Verdict

__version__ = "0.2.0"

__all__ = ["Debate", "Debater", "make_panel", "judge", "Argument", "Position", "Verdict"]
