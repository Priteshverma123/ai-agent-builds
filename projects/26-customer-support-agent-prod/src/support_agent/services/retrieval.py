"""Policy RAG: split policy docs by heading, score chunks with BM25, return citable hits.

Each chunk gets a stable id like ``refunds.md#refund-window`` so an answer can cite it and a
reviewer can click straight to the paragraph that justified it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = frozenset(
    "a an and are be can do for from how i if in is it its my of on or the to we what when "
    "where which who will with you your me this that have has".split()
)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    title: str
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w.rstrip("s") if len(w) > 3 else w for w in words if w not in STOPWORDS]


def slugify(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def chunk_markdown(name: str, markdown: str) -> list[Chunk]:
    """One chunk per '## ' section; the section heading is part of the searchable text."""
    chunks: list[Chunk] = []
    for section in re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]:
        heading, _, body = section.partition("\n")
        body = " ".join(body.split())
        chunks.append(Chunk(f"{name}#{slugify(heading)}", heading.strip(), body))
    return chunks


class PolicyIndex:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75) -> None:
        self.chunks = chunks
        self._k1, self._b = k1, b
        self._docs = [Counter(tokenize(c.title + " " + c.title + " " + c.text)) for c in chunks]
        self._avg_len = sum(sum(d.values()) for d in self._docs) / max(len(self._docs), 1)
        df = Counter(term for doc in self._docs for term in doc)
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @classmethod
    def from_dir(cls, folder: Path) -> "PolicyIndex":
        chunks: list[Chunk] = []
        for path in sorted(folder.glob("*.md")):
            chunks.extend(chunk_markdown(path.name, path.read_text(encoding="utf-8")))
        return cls(chunks)

    def search(self, query: str, k: int = 3) -> list[Hit]:
        terms = tokenize(query)
        hits = []
        for chunk, doc in zip(self.chunks, self._docs):
            length = sum(doc.values())
            score = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    norm = tf * (self._k1 + 1) / (tf + self._k1 * (1 - self._b + self._b * length / self._avg_len))
                    score += self._idf[t] * norm
            if score > 0:
                hits.append(Hit(chunk, round(score, 3)))
        return sorted(hits, key=lambda h: h.score, reverse=True)[:k]

    def get(self, chunk_id: str) -> Chunk | None:
        return next((c for c in self.chunks if c.chunk_id == chunk_id), None)
