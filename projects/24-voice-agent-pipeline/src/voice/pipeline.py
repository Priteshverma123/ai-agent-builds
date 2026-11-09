"""The voice agent: ears -> brain -> mouth, as concurrent asyncio tasks connected by queues.

Two response modes make the latency lesson concrete:

* ``batch``: wait for the whole LLM reply, synthesise it all, then play (simple, slow);
* ``streaming``: phrases flow to TTS while the LLM is still writing, and audio starts after the
  *first* phrase (what production voice agents do).

And two conversational behaviours:

* **barge-in**: if the user starts talking while the agent speaks, cancel the whole response
  (LLM, TTS, speaker) at once and remember only the words the user actually heard;
* **filler**: if the model hasn't produced a token by ``filler_after_ms``, say a short
  pre-recorded phrase so the user isn't left in silence.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Literal

from .audio import AudioFrame, MockMicrophone
from .brain import History, StreamingLLM
from .budget import TurnMetrics
from .clock import Clock
from .ears import Ears, FinalTranscript, Hearing, SpeechStarted
from .mouth import AudioChunk, MockTTS, PhraseChunker, Speaker

Mode = Literal["streaming", "batch"]


@dataclass
class Timeline:
    """Timestamped events in clock time; ``echo`` prints them live."""

    clock: Clock
    echo: bool = False
    events: list[tuple[float, str, str]] = field(default_factory=list)

    def log(self, actor: str, message: str) -> None:
        self.events.append((self.clock.now_ms, actor, message))
        if self.echo:
            print(f"  {self.clock.now_ms / 1000:7.3f}s  {actor:<8}| {message}")


class VoiceAgent:
    def __init__(self, clock: Clock, llm: StreamingLLM, tts: MockTTS, *, mode: Mode = "streaming",
                 filler_after_ms: float | None = 450, filler_text: str = "One moment.",
                 timeline: Timeline | None = None) -> None:
        self.clock = clock
        self.llm = llm
        self.tts = tts
        self.mode = mode
        self.filler_after_ms = filler_after_ms
        self.filler = AudioChunk(filler_text, tts.duration(filler_text))  # pre-synthesised at startup
        self.timeline = timeline or Timeline(clock)
        self.speaker = Speaker(clock)
        self.history: History = []
        self.turns: list[TurnMetrics] = []
        self._response: asyncio.Task[None] | None = None
        self._current: TurnMetrics | None = None

    async def run(self, mic: MockMicrophone) -> list[TurnMetrics]:
        frames: asyncio.Queue[AudioFrame | None] = asyncio.Queue()
        hearing: asyncio.Queue[Hearing | None] = asyncio.Queue()
        background = [asyncio.ensure_future(mic.stream(frames)),
                      asyncio.ensure_future(Ears(self.clock).listen(frames, hearing))]
        while (event := await hearing.get()) is not None:
            if isinstance(event, SpeechStarted):
                self.timeline.log("user", "starts speaking")
                if self._response and not self._response.done():
                    await self._barge_in(event)
            elif isinstance(event, FinalTranscript):
                self._start_turn(event)
        if self._response:
            await self._response
        await asyncio.gather(*background)
        return self.turns

    # ------------------------------------------------------------------ turn management

    def _start_turn(self, heard: FinalTranscript) -> None:
        turn = TurnMetrics(len(self.turns) + 1, heard.text, heard.speech_end_ms, heard.endpoint_ms, heard.t_ms)
        self.turns.append(turn)
        self._current = turn
        self.timeline.log("stt", f'final "{heard.text}"  (endpoint +{turn.stages["endpoint"]:.0f} ms, '
                                 f'stt +{turn.stages["stt"]:.0f} ms)')
        self.history.append(("user", heard.text))
        self._response = asyncio.ensure_future(self._respond(turn))

    async def _barge_in(self, event: SpeechStarted) -> None:
        """Stop everything for the current answer, right now."""
        turn = self._current
        self._response.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._response
        # The user's voice began (start_frames x 20 ms) before the VAD was sure it was speech.
        turn.interrupted_at_ms = event.t_ms - 20
        turn.stopped_at_ms = self.clock.now_ms
        self.timeline.log("barge-in", f"user talked over the agent -> stopped after "
                                      f"{turn.barge_in_reaction_ms:.0f} ms; user heard: \"{turn.heard}\"")

    async def _respond(self, turn: TurnMetrics) -> None:
        try:
            if self.mode == "streaming":
                await asyncio.gather(self._stream_answer(turn), self._filler_guard(turn))
            else:
                await asyncio.gather(self._batch_answer(turn), self._filler_guard(turn))
            turn.done_ms = self.clock.now_ms
        except asyncio.CancelledError:
            turn.heard = self.speaker.take_heard()
            self.history.append(("assistant", f"{turn.heard} [interrupted]"))
            raise
        turn.heard = self.speaker.take_heard()
        self.history.append(("assistant", turn.heard))

    # ------------------------------------------------------------------ the two modes

    async def _stream_answer(self, turn: TurnMetrics) -> None:
        phrases: asyncio.Queue[str | None] = asyncio.Queue()
        chunks: asyncio.Queue[AudioChunk | None] = asyncio.Queue()

        async def think() -> None:
            chunker = PhraseChunker()
            async for token in self.llm.stream(self.history):
                self._first_token(turn)
                if phrase := chunker.push(token):
                    await phrases.put(phrase)
            if rest := chunker.flush():
                await phrases.put(rest)
            await phrases.put(None)

        async def synthesise() -> None:
            while (phrase := await phrases.get()) is not None:
                await chunks.put(await self.tts.synth(phrase))
            await chunks.put(None)

        async def speak() -> None:
            while (chunk := await chunks.get()) is not None:
                await self._play(turn, chunk)

        await asyncio.gather(think(), synthesise(), speak())

    async def _batch_answer(self, turn: TurnMetrics) -> None:
        tokens = []
        async for token in self.llm.stream(self.history):
            self._first_token(turn)
            tokens.append(token)
        await self._play(turn, await self.tts.synth("".join(tokens).strip()))

    # ------------------------------------------------------------------ helpers

    def _first_token(self, turn: TurnMetrics) -> None:
        if turn.first_token_ms is None:
            turn.first_token_ms = self.clock.now_ms
            self.timeline.log("llm", f"first token  (+{turn.stages['llm']:.0f} ms after transcript)")

    async def _play(self, turn: TurnMetrics, chunk: AudioChunk, filler: bool = False) -> None:
        def on_start() -> None:  # runs once the speaker is free, so the timestamps are exact
            note = ""
            if turn.first_audio_ms is None:
                turn.first_audio_ms = self.clock.now_ms
                note = f"  <- voice-to-voice {turn.perceived_ms:.0f} ms"
            if not filler and turn.answer_audio_ms is None:
                turn.answer_audio_ms = self.clock.now_ms
            self.timeline.log("speaker", f'{"filler " if filler else ""}"{chunk.text}" '
                                         f'({chunk.duration_ms:.0f} ms){note}')

        await self.speaker.play(chunk, on_start)

    async def _filler_guard(self, turn: TurnMetrics) -> None:
        if self.filler_after_ms is None:
            return
        await self.clock.sleep(self.filler_after_ms)
        if turn.first_token_ms is None:
            turn.filler = True
            await self._play(turn, self.filler, filler=True)
