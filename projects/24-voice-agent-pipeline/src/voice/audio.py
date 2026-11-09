"""Mock audio: a microphone that emits 20 ms frames of "energy" with the words riding along.

Real audio is a stream of PCM samples. For learning the *pipeline* we only need two properties of
it: how loud each 20 ms frame is (for voice activity detection) and what was said (which a real
STT model would recover from the samples). So a frame is ``(t_ms, energy, word)``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .clock import Clock

FRAME_MS = 20
SPEECH_ENERGY = 0.7
SILENCE_ENERGY = 0.02


@dataclass(frozen=True)
class AudioFrame:
    t_ms: float
    energy: float
    word: str | None = None  # set on the first frame of each spoken word


@dataclass(frozen=True)
class Utterance:
    start_ms: float
    text: str
    ms_per_word: float = 280

    @property
    def end_ms(self) -> float:
        return self.start_ms + len(self.text.split()) * self.ms_per_word


class MockMicrophone:
    """Plays a script of utterances in (virtual) real time into a queue, one frame per 20 ms."""

    def __init__(self, clock: Clock, script: list[Utterance], tail_ms: float = 1500) -> None:
        self.clock = clock
        self.script = sorted(script, key=lambda u: u.start_ms)
        self.duration_ms = max(u.end_ms for u in self.script) + tail_ms

    def frame_at(self, t: float) -> AudioFrame:
        for u in self.script:
            if u.start_ms <= t < u.end_ms:
                index, offset = divmod(t - u.start_ms, u.ms_per_word)
                word = u.text.split()[int(index)] if offset < FRAME_MS else None
                return AudioFrame(t, SPEECH_ENERGY, word)
        return AudioFrame(t, SILENCE_ENERGY)

    async def stream(self, out: asyncio.Queue[AudioFrame | None]) -> None:
        t = 0.0
        while t < self.duration_ms:
            await self.clock.sleep(FRAME_MS)
            await out.put(self.frame_at(t))
            t += FRAME_MS
        await out.put(None)  # end of stream
