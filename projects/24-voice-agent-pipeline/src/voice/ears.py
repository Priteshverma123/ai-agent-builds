"""Listening: voice activity detection (VAD) + streaming speech-to-text (STT).

The VAD answers "is the user talking right now?" from frame energy. It drives two decisions:

* **speech start** (a few loud frames in a row) - used for *barge-in*: stop talking immediately;
* **end of turn** (enough silence after speech) - the "endpoint", when we can start answering.

Endpointing is a trade-off you'll tune in every voice product: wait too little and you cut people
off mid-sentence; wait too long and the agent feels slow. That silence is part of the latency budget.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .audio import FRAME_MS, AudioFrame
from .clock import Clock


@dataclass(frozen=True)
class SpeechStarted:
    t_ms: float


@dataclass(frozen=True)
class FinalTranscript:
    t_ms: float          # when the transcript became available
    text: str
    speech_end_ms: float  # when the user actually stopped talking (end of last loud frame)
    endpoint_ms: float    # when the VAD decided the turn was over


Hearing = SpeechStarted | FinalTranscript


class EnergyVAD:
    def __init__(self, threshold: float = 0.3, start_frames: int = 2, end_silence_ms: float = 300) -> None:
        self.threshold = threshold
        self.start_frames = start_frames
        self.end_silence_ms = end_silence_ms
        self.speaking = False
        self._loud_run = 0
        self.last_voice_end_ms = 0.0

    def feed(self, frame: AudioFrame) -> str | None:
        """Return ``"start"``, ``"end"`` or ``None`` for this frame."""
        if frame.energy >= self.threshold:
            self._loud_run += 1
            self.last_voice_end_ms = frame.t_ms + FRAME_MS
            if not self.speaking and self._loud_run >= self.start_frames:
                self.speaking = True
                return "start"
            return None
        self._loud_run = 0
        if self.speaking and frame.t_ms + FRAME_MS - self.last_voice_end_ms >= self.end_silence_ms:
            self.speaking = False
            return "end"
        return None


class Ears:
    """Consumes mic frames, emits :data:`Hearing` events. STT finalisation takes ``stt_final_ms``."""

    def __init__(self, clock: Clock, vad: EnergyVAD | None = None, stt_final_ms: float = 120) -> None:
        self.clock = clock
        self.vad = vad or EnergyVAD()
        self.stt_final_ms = stt_final_ms
        self._words: list[str] = []
        self._pending: set[asyncio.Task[None]] = set()

    async def listen(self, frames: asyncio.Queue[AudioFrame | None], out: asyncio.Queue[Hearing | None]) -> None:
        while (frame := await frames.get()) is not None:
            if frame.word:
                self._words.append(frame.word)
            change = self.vad.feed(frame)
            if change == "start":
                await out.put(SpeechStarted(frame.t_ms))
            elif change == "end" and self._words:
                text, self._words = " ".join(self._words), []
                task = asyncio.ensure_future(self._finalise(text, self.vad.last_voice_end_ms, frame.t_ms + FRAME_MS, out))
                self._pending.add(task)
                task.add_done_callback(self._pending.discard)
        if self._pending:
            await asyncio.gather(*self._pending)
        await out.put(None)

    async def _finalise(self, text: str, speech_end: float, endpoint: float, out: asyncio.Queue) -> None:
        """The STT model needs a moment to produce its final, punctuated transcript."""
        await self.clock.sleep(self.stt_final_ms)
        await out.put(FinalTranscript(self.clock.now_ms, text, speech_end, endpoint))
