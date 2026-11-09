"""A streaming voice-agent pipeline (VAD/STT -> LLM -> TTS) with barge-in and a latency budget, on mock audio."""

from .budget import LatencyBudget, TurnMetrics
from .clock import RealClock, VirtualClock
from .pipeline import Timeline, VoiceAgent

__version__ = "0.2.0"

__all__ = ["LatencyBudget", "TurnMetrics", "RealClock", "VirtualClock", "Timeline", "VoiceAgent"]
