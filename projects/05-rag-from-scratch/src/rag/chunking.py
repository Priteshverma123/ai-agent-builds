"""Step 1 of RAG: split documents into chunks small enough to retrieve precisely.

We pack whole sentences into chunks of at most `max_words`, and repeat the last sentence
of each chunk at the start of the next (overlap), so a fact that straddles a boundary
still appears intact in at least one chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    id: str  # e.g. "shipping.md#1" -- stable, human-readable, citable
    source: str
    text: str


def split_sentences(text: str) -> list[str]:
    sentences = []
    for paragraph in re.split(r"\n\s*\n", text):
        heading = paragraph.lstrip().startswith("#")
        paragraph = " ".join(paragraph.split()).lstrip("#- ").strip()
        if heading and paragraph:
            paragraph += "."  # keep the heading as its own short sentence
        if paragraph:
            sentences += [s for s in _SENTENCE_END.split(paragraph) if s]
    return sentences


def _word_count(sentences: list[str]) -> int:
    return sum(len(s.split()) for s in sentences)


def chunk_document(source: str, text: str, max_words: int = 40, overlap: int = 1) -> list[Chunk]:
    groups: list[list[str]] = []
    current: list[str] = []
    for sentence in split_sentences(text):
        if current and _word_count(current + [sentence]) > max_words:
            groups.append(current)
            carry = current[-overlap:] if overlap else []
            # Only carry the overlap if it leaves room for the new sentence (no duplicate tiny chunks).
            current = carry if _word_count(carry + [sentence]) <= max_words else []
        current.append(sentence)
    if current:
        groups.append(current)
    return [Chunk(f"{source}#{i}", source, " ".join(group)) for i, group in enumerate(groups)]
