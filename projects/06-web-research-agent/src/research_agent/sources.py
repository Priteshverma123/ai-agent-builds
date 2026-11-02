"""Source tracking: every fact the agent keeps is tied to the page it came from.

The tracker hands out stable citation numbers ([1], [2], ...) and later checks that
the final brief only cites sources that were really read. That check is what stops
an LLM from inventing a "[7]" that points nowhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .corpus import Page

CITATION = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Note:
    """One claim extracted from one source."""

    source_id: int
    claim: str


class SourceTracker:
    def __init__(self) -> None:
        self._ids: dict[str, int] = {}
        self.pages: dict[int, Page] = {}
        self.visited: list[str] = []  # every URL fetched, cited or not

    def visit(self, url: str) -> bool:
        """Record a fetch. Returns False if the URL was already read (skip duplicates)."""
        if url in self.visited:
            return False
        self.visited.append(url)
        return True

    def cite(self, page: Page) -> int:
        """Return the citation number for ``page``, assigning the next one if new."""
        if page.url not in self._ids:
            self._ids[page.url] = len(self._ids) + 1
            self.pages[self._ids[page.url]] = page
        return self._ids[page.url]

    def unknown_citations(self, text: str) -> set[int]:
        """Citation numbers used in ``text`` that do not belong to any tracked source."""
        return {int(n) for n in CITATION.findall(text)} - set(self.pages)

    def remove_unverified_lines(self, text: str) -> tuple[str, int]:
        """Drop lines that cite a source we never read. Returns (clean_text, lines_dropped)."""
        kept, dropped = [], 0
        for line in text.splitlines():
            if self.unknown_citations(line):
                dropped += 1
            else:
                kept.append(line)
        return "\n".join(kept), dropped

    def bibliography(self) -> list[str]:
        return [f"[{sid}] {p.title} ({p.kind}) {p.url}" for sid, p in sorted(self.pages.items())]
