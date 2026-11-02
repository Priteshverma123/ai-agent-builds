"""Step 3 of RAG: a vector index. Store one vector per chunk; search = rank chunks by cosine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chunking import Chunk, chunk_document
from .embed import TfidfEmbedder, cosine


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class VectorIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.embedder = TfidfEmbedder().fit([c.text for c in chunks])
        self.vectors = [self.embedder.embed(c.text) for c in chunks]

    @classmethod
    def from_folder(cls, folder: Path, max_words: int = 40) -> VectorIndex:
        chunks: list[Chunk] = []
        for path in sorted(folder.glob("*.md")):
            chunks += chunk_document(path.name, path.read_text(encoding="utf-8"), max_words)
        return cls(chunks)

    @property
    def sources(self) -> set[str]:
        return {c.source for c in self.chunks}

    def search(self, query: str, k: int = 3, min_score: float = 0.1) -> list[Hit]:
        """Top-k chunks above a similarity floor. Returning nothing is a valid, useful answer."""
        query_vector = self.embedder.embed(query)
        scored = [Hit(chunk, cosine(query_vector, vector)) for chunk, vector in zip(self.chunks, self.vectors)]
        ranked = sorted((h for h in scored if h.score >= min_score), key=lambda h: h.score, reverse=True)
        return ranked[:k]
