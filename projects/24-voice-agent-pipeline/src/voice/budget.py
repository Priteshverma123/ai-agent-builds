"""Latency accounting: where did the milliseconds go between "user stops" and "agent speaks"?

Voice-to-voice latency is what users feel. Conversations feel natural under roughly a second; past
that people start repeating themselves. We split it into four stages, each with its own budget,
so a regression points straight at the guilty component.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TurnMetrics:
    index: int
    user_text: str
    speech_end_ms: float      # user's last voiced frame
    endpoint_ms: float        # VAD decided the turn ended
    final_ms: float           # STT final transcript ready
    first_token_ms: float | None = None
    first_audio_ms: float | None = None   # any audio, including a filler phrase
    answer_audio_ms: float | None = None  # first audio of the actual answer
    done_ms: float | None = None
    filler: bool = False
    interrupted_at_ms: float | None = None
    stopped_at_ms: float | None = None
    heard: str = ""

    @property
    def perceived_ms(self) -> float | None:
        """What the user experiences: silence from their last word to the agent's first sound."""
        return None if self.first_audio_ms is None else self.first_audio_ms - self.speech_end_ms

    @property
    def stages(self) -> dict[str, float | None]:
        def gap(a: float | None, b: float | None) -> float | None:
            return None if a is None or b is None else b - a

        return {
            "endpoint": self.endpoint_ms - self.speech_end_ms,
            "stt": self.final_ms - self.endpoint_ms,
            "llm": gap(self.final_ms, self.first_token_ms),
            "tts": gap(self.first_token_ms, self.answer_audio_ms),
        }

    @property
    def barge_in_reaction_ms(self) -> float | None:
        if self.interrupted_at_ms is None or self.stopped_at_ms is None:
            return None
        return self.stopped_at_ms - self.interrupted_at_ms


@dataclass(frozen=True)
class LatencyBudget:
    total_ms: float = 1000
    endpoint_ms: float = 320
    stt_ms: float = 130
    llm_ms: float = 300
    tts_ms: float = 250

    def stage_limits(self) -> dict[str, float]:
        return {"endpoint": self.endpoint_ms, "stt": self.stt_ms, "llm": self.llm_ms, "tts": self.tts_ms}

    def check(self, turn: TurnMetrics) -> tuple[bool, list[str]]:
        """Return (within budget?, list of human-readable violations)."""
        problems = [f"{stage} {actual:.0f} ms > {limit:.0f} ms"
                    for stage, limit in self.stage_limits().items()
                    if (actual := turn.stages[stage]) is not None and actual > limit]
        perceived = turn.perceived_ms
        ok = perceived is not None and perceived <= self.total_ms
        if perceived is None:
            problems.insert(0, "agent never spoke")
        elif not ok:
            problems.insert(0, f"total {perceived:.0f} ms > {self.total_ms:.0f} ms")
        return ok, problems
