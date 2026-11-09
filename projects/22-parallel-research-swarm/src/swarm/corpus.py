"""A local stand-in for the web: search, plus a fetcher with latency, flakiness and single-flight.

Real web research is slow and unreliable, so the fake web is too: each document has a latency,
some fail on the first try, one never answers in time. The :class:`Fetcher` adds the three things
a swarm needs on top: a concurrency limit, retries with backoff, and *single-flight* - if two
workers ask for the same URL at the same time, only one request goes out.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections import Counter
from pathlib import Path

from .models import Doc

_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]*")


def stem(word: str) -> str:
    """Tiny plural stemmer: batteries -> battery, cycles -> cycle, glass stays glass."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def terms(text: str) -> list[str]:
    return [stem(t) for t in _TOKEN.findall(text.lower().replace(",", ""))]


def load_corpus(folder: Path) -> dict[str, Doc]:
    """Each file: ``key: value`` header lines, a ``---`` line, then the body."""
    docs: dict[str, Doc] = {}
    for path in sorted(Path(folder).glob("*.md")):
        header, body = path.read_text(encoding="utf-8").split("\n---\n", 1)
        meta = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        docs[path.stem] = Doc(id=path.stem, title=meta["title"], url=meta["url"], body=body.strip(),
                              latency_ms=int(meta.get("latency_ms", 50)), flaky=meta.get("flaky") == "true")
    return docs


class SearchIndex:
    """TF-IDF over titles and bodies. Search is instant; *fetching* is what costs time."""

    def __init__(self, docs: dict[str, Doc]) -> None:
        self.docs = docs
        self.tf = {d.id: Counter(terms(d.title + " " + d.body)) for d in docs.values()}
        df = Counter(t for counts in self.tf.values() for t in counts)
        self.idf = {t: math.log((1 + len(docs)) / (1 + n)) + 1 for t, n in df.items()}

    def search(self, keywords: list[str], k: int = 3) -> list[str]:
        wanted = [stem(w.lower()) for w in keywords]
        scored = [(sum(self.tf[doc_id][t] * self.idf.get(t, 0) for t in wanted), doc_id) for doc_id in self.tf]
        return [doc_id for score, doc_id in sorted(scored, key=lambda s: (-s[0], s[1])) if score > 0][:k]


class TransientFetchError(RuntimeError):
    """The kind of error worth retrying (timeouts, 503s, resets)."""


class Fetcher:
    def __init__(self, docs: dict[str, Doc], max_concurrency: int = 3, timeout_s: float = 0.3,
                 retries: int = 1, backoff_s: float = 0.02) -> None:
        self.docs = docs
        self.limit = asyncio.Semaphore(max_concurrency)
        self.timeout_s = timeout_s
        self.retries = retries
        self.backoff_s = backoff_s
        self.inflight: dict[str, asyncio.Task[Doc]] = {}
        self.attempts: Counter[str] = Counter()
        self.network_calls = 0
        self.deduplicated_requests = 0
        self.fetch_ms_total = 0.0
        self.peak_concurrency = 0
        self._active = 0

    async def fetch(self, doc_id: str) -> Doc:
        """Single-flight: concurrent callers for the same doc share one task (and its result)."""
        if doc_id in self.inflight:
            self.deduplicated_requests += 1
        else:
            self.inflight[doc_id] = asyncio.ensure_future(self._fetch_with_retries(doc_id))
        return await asyncio.shield(self.inflight[doc_id])

    async def _fetch_with_retries(self, doc_id: str) -> Doc:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            # Take a concurrency slot first, *then* start the timeout clock: time spent queueing
            # behind other requests must not count as the server being slow.
            async with self.limit:
                try:
                    return await asyncio.wait_for(self._request(doc_id), self.timeout_s)
                except (TransientFetchError, TimeoutError) as exc:
                    last = exc
            await asyncio.sleep(self.backoff_s * 2 ** attempt)  # back off without holding a slot
        raise TransientFetchError(f"gave up after {self.retries + 1} attempts ({type(last).__name__})")

    async def _request(self, doc_id: str) -> Doc:
        """The pretend HTTP request: waits for the document's latency, sometimes fails."""
        self._active += 1
        self.peak_concurrency = max(self.peak_concurrency, self._active)
        self.network_calls += 1
        self.attempts[doc_id] += 1
        doc = self.docs[doc_id]
        start = time.perf_counter()
        try:
            await asyncio.sleep(doc.latency_ms / 1000)
            if doc.flaky and self.attempts[doc_id] == 1:
                raise TransientFetchError("503 Service Unavailable")
            return doc
        finally:
            self.fetch_ms_total += (time.perf_counter() - start) * 1000
            self._active -= 1
