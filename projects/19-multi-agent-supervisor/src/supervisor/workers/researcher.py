"""Researcher: retrieves documents from a local knowledge base and extracts rules and examples.

No model needed: retrieval + parsing is cheaper, faster and cannot hallucinate a rule that isn't
in the docs. (Swap in an LLM extractor when your docs are messier than ours.)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from ..messages import Example, ResearchNotes, WorkerResult
from ..state import SharedState

_WORD = re.compile(r"[a-z0-9]+")
_EXAMPLE = re.compile(r'^- "(.*)" -> "(.*)"$')


@dataclass
class Doc:
    slug: str
    title: str
    tags: set[str]
    body: str


class KnowledgeBase:
    """A folder of markdown files with a ``tags:`` line, searchable by keyword overlap."""

    def __init__(self, folder: Path) -> None:
        self.docs = [self._parse(p) for p in sorted(Path(folder).glob("*.md"))]

    @staticmethod
    def _parse(path: Path) -> Doc:
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        tags = re.search(r"^tags:\s*(.+)$", text, flags=re.MULTILINE)
        return Doc(path.stem, title, {t.strip() for t in tags.group(1).split(",")} if tags else set(), text)

    def search(self, query: str, k: int = 1) -> list[Doc]:
        """Rank by overlap with tags (weight 2) and title words (weight 1)."""
        words = set(_WORD.findall(query.lower()))
        scored = []
        for doc in self.docs:
            score = 2 * len(words & doc.tags) + len(words & set(_WORD.findall(doc.title.lower())))
            if score:
                scored.append((score, doc.slug, doc))
        return [doc for _, _, doc in sorted(scored, key=lambda s: (-s[0], s[1]))[:k]]


def extract_notes(doc: Doc) -> ResearchNotes:
    """Bullets under '## Rules' become rules; '- "a" -> "b"' lines become examples."""
    rules: list[str] = []
    examples: list[Example] = []
    section = ""
    for line in doc.body.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
        elif (m := _EXAMPLE.match(line)):
            examples.append(Example(given=m.group(1), expected=m.group(2)))
        elif section == "rules" and line.startswith("- "):
            rules.append(line[2:].strip())
    return ResearchNotes(rules=rules, examples=examples, sources=[doc.slug])


class Researcher:
    name = "researcher"
    description = "Looks things up in the team knowledge base; returns rules, examples and sources."
    parallel_safe = True

    def __init__(self, kb: KnowledgeBase, latency_s: float = 0.05) -> None:
        self.kb = kb
        self.latency_s = latency_s  # stands in for a slow search API; makes the parallel speed-up visible

    async def run(self, instruction: str, state: SharedState) -> WorkerResult:
        await asyncio.sleep(self.latency_s)
        docs = self.kb.search(instruction)
        if not docs:
            return WorkerResult(worker="researcher", instruction=instruction, ok=False,
                                summary="no matching documents")
        notes = extract_notes(docs[0])
        return WorkerResult(worker="researcher", instruction=instruction, research=notes,
                            summary=f"{docs[0].slug}: {len(notes.rules)} rules, {len(notes.examples)} examples")
