"""Speaking: phrase chunking, text-to-speech (TTS) and an interruptible speaker.

Streaming TTS is the trick that makes voice agents feel fast: don't wait for the whole answer -
cut the token stream into short phrases and synthesise the first one while the model is still
writing the rest. The speaker plays chunks in order and can be stopped mid-word (barge-in); it
remembers exactly which words the user actually heard.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from .clock import Clock

PHRASE_END = (".", ",", "!", "?", ";", ":")


class PhraseChunker:
    """Group streamed tokens into speakable phrases: break on punctuation or every ``max_words``."""

    def __init__(self, max_words: int = 6) -> None:
        self.max_words = max_words
        self._words: list[str] = []

    def push(self, token: str) -> str | None:
        self._words.append(token.strip())
        if token.strip().endswith(PHRASE_END) or len(self._words) >= self.max_words:
            return self.flush()
        return None

    def flush(self) -> str | None:
        phrase, self._words = " ".join(w for w in self._words if w), []
        return phrase or None


@dataclass(frozen=True)
class AudioChunk:
    text: str
    duration_ms: float


class MockTTS:
    """Synthesis takes ``first_byte_ms`` per request plus ``synth_ms_per_word``; audio lasts ``ms_per_word``."""

    def __init__(self, clock: Clock, first_byte_ms: float = 120, synth_ms_per_word: float = 10,
                 ms_per_word: float = 300) -> None:
        self.clock = clock
        self.first_byte_ms = first_byte_ms
        self.synth_ms_per_word = synth_ms_per_word
        self.ms_per_word = ms_per_word

    def duration(self, text: str) -> float:
        return len(text.split()) * self.ms_per_word

    async def synth(self, text: str) -> AudioChunk:
        await self.clock.sleep(self.first_byte_ms + self.synth_ms_per_word * len(text.split()))
        return AudioChunk(text, self.duration(text))


@dataclass
class Speaker:
    """Plays one chunk at a time. If cancelled, records the words that were already audible."""

    clock: Clock
    heard: list[str] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def play(self, chunk: AudioChunk, on_start: Callable[[], None] | None = None) -> None:
        """Wait for the speaker to be free, call ``on_start`` (for timing), then play the chunk."""
        async with self.lock:
            if on_start:
                on_start()
            start = self.clock.now_ms
            words = chunk.text.split()
            try:
                await self.clock.sleep(chunk.duration_ms)
            except asyncio.CancelledError:
                played = (self.clock.now_ms - start) / chunk.duration_ms if chunk.duration_ms else 1.0
                self.heard += words[: int(len(words) * played)]
                raise
            self.heard += words

    def take_heard(self) -> str:
        text, self.heard = " ".join(self.heard), []
        return text
