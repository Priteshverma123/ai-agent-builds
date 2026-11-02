"""A tiny offline "web": pages on disk, a BM25 search engine, and fetch().

Each page in ``examples/web/`` is a text file with a small header, a blank line and a body:

    URL: https://energy.example.org/heat-pump-basics
    Title: How heat pumps work
    Type: guide

    A heat pump moves heat ...

Swapping this class for a real search API (and a real HTTP fetch) is the only change
needed to point the agent at the real web.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how in is it its of on or "
    "that the their this to was were what when which who why will with worth".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase words, drop stopwords, and strip a plural 's' (a naive stemmer)."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOPWORDS]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    body: str
    kind: str = "web"  # guide | study | news | opinion ...


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    score: float


class PageNotFound(LookupError):
    """Raised by fetch() for an unknown URL (the offline 404)."""


class LocalWeb:
    """Search and fetch over a fixed set of pages using BM25 ranking."""

    def __init__(self, pages: list[Page], k1: float = 1.5, b: float = 0.75) -> None:
        self.pages = {p.url: p for p in pages}
        self.k1, self.b = k1, b
        # Titles count twice: a match in the title is a strong relevance signal.
        self._terms = {p.url: Counter(tokenize(f"{p.title} {p.title} {p.body}")) for p in pages}
        self._lengths = {url: sum(c.values()) for url, c in self._terms.items()}
        self._avg_len = sum(self._lengths.values()) / max(len(pages), 1)
        self._df = Counter(term for c in self._terms.values() for term in c)

    @classmethod
    def from_dir(cls, folder: str | Path) -> "LocalWeb":
        return cls([parse_page(path.read_text(encoding="utf-8")) for path in sorted(Path(folder).glob("*.txt"))])

    def _idf(self, term: str) -> float:
        n, df = len(self.pages), self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _bm25(self, url: str, query_terms: list[str]) -> float:
        tf, length = self._terms[url], self._lengths[url]
        score = 0.0
        for term in query_terms:
            f = tf.get(term, 0)
            if f:
                norm = f + self.k1 * (1 - self.b + self.b * length / self._avg_len)
                score += self._idf(term) * f * (self.k1 + 1) / norm
        return score

    def search(self, query: str, k: int = 3) -> list[SearchResult]:
        """Return the top-k pages for ``query`` with a short snippet."""
        terms = tokenize(query)
        scored = [(self._bm25(url, terms), url) for url in self.pages]
        top = sorted((s for s in scored if s[0] > 0), reverse=True)[:k]
        return [
            SearchResult(url, self.pages[url].title, _snippet(self.pages[url].body, terms), round(score, 2))
            for score, url in top
        ]

    def fetch(self, url: str) -> Page:
        try:
            return self.pages[url]
        except KeyError:
            raise PageNotFound(url) from None


def parse_page(raw: str) -> Page:
    header, _, body = raw.strip().partition("\n\n")
    meta = dict(line.split(":", 1) for line in header.splitlines() if ":" in line)
    meta = {k.strip().lower(): v.strip() for k, v in meta.items()}
    return Page(url=meta["url"], title=meta["title"], body=" ".join(body.split()), kind=meta.get("type", "web"))


def _snippet(body: str, terms: list[str], limit: int = 110) -> str:
    """The sentence sharing the most words with the query, trimmed for display."""
    wanted = set(terms)
    best = max(split_sentences(body), key=lambda s: len(wanted & set(tokenize(s))), default="")
    return best if len(best) <= limit else best[: limit - 3] + "..."
