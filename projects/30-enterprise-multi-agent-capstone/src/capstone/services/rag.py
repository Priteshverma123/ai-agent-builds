"""RAG over a folder of Markdown files: chunk by section, TF-IDF vectors, cosine retrieval (recap of 05)."""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from capstone.domain.models import Chunk, Hit

STOP = set("a an the and or of to in on for is are be by with what whats how can i my me we our it this that "
           "do does at as from per any if not your you".split())


SUFFIXES = ("ing", "ed", "es", "s", "e")


def stem(word: str) -> str:
    """Tiny suffix stripper so 'acknowledged' and 'acknowledge' meet at 'acknowledg'."""
    for suffix in SUFFIXES:
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


def chunk_markdown(source: str, text: str) -> list[Chunk]:
    """One chunk per '## Section' paragraph block. Sections are natural citation units."""
    chunks, section, buf = [], "Intro", []
    title = source

    def flush() -> None:
        body = " ".join(buf).strip()
        if body:
            chunks.append(Chunk(f"{source}#{len(chunks) + 1}", source, f"{title} > {section}", body))
        buf.clear()

    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section = line[3:].strip()
        elif line.strip():
            buf.append(line.strip())
    flush()
    return chunks


class DocIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        docs = [Counter(tokenize(c.section + " " + c.text)) for c in chunks]
        df = Counter(t for d in docs for t in d)
        n = len(chunks)
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items()}
        self.vectors = [self._vec(d) for d in docs]

    def _vec(self, counts: Counter) -> dict[str, float]:
        v = {t: c * self.idf.get(t, 0.0) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, query: str, k: int = 3, min_score: float = 0.12) -> list[Hit]:
        q = self._vec(Counter(tokenize(query)))
        scored = [Hit(c, round(sum(q.get(t, 0.0) * w for t, w in v.items()), 3))
                  for c, v in zip(self.chunks, self.vectors)]
        return [h for h in sorted(scored, key=lambda h: -h.score)[:k] if h.score >= min_score]

    @classmethod
    def from_folder(cls, folder: Path) -> "DocIndex":
        chunks: list[Chunk] = []
        for path in sorted(Path(folder).glob("*.md")):
            chunks += chunk_markdown(path.name, path.read_text(encoding="utf-8"))
        return cls(chunks)
