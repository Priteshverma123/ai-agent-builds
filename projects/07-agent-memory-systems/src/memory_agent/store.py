"""Long-term memory in SQLite: facts that survive restarts, ranked by relevance.

Three ideas worth remembering:
- **Slots** make updates explicit: "lives in Berlin" replaces "lives in London" because
  both fill the ``city`` slot. Without slots, memory fills up with contradictions.
- **Dedup**: a near-identical fact is not stored twice, it just gets "touched".
- **Recall score** = similarity + importance + recency. Similarity alone would forget
  that an allergy matters more than a favourite colour.

Time is measured in conversation turns (a deterministic clock that is easy to test).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .vectors import cosine, embed

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,
    slot TEXT UNIQUE,
    importance REAL NOT NULL,
    created_turn INTEGER NOT NULL,
    last_used_turn INTEGER NOT NULL,
    embedding TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@dataclass(frozen=True)
class Fact:
    """A candidate memory proposed by the extractor."""

    text: str
    kind: str = "note"  # profile | preference | goal | episode | note
    slot: str | None = None
    importance: float = 0.5


@dataclass(frozen=True)
class Memory:
    id: int
    text: str
    kind: str
    slot: str | None
    importance: float
    last_used_turn: int


@dataclass(frozen=True)
class Recall:
    memory: Memory
    score: float
    similarity: float
    recency: float


@dataclass(frozen=True)
class WriteResult:
    action: str  # added | updated | duplicate
    memory: Memory
    previous: str | None = None


class LongTermMemory:
    def __init__(self, path: str | Path = ":memory:", duplicate_threshold: float = 0.9, half_life: int = 20) -> None:
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        self.duplicate_threshold = duplicate_threshold
        self.half_life = half_life  # turns until recency weight halves

    # -- the clock -----------------------------------------------------------
    @property
    def turn(self) -> int:
        row = self.db.execute("SELECT value FROM meta WHERE key = 'turn'").fetchone()
        return int(row[0]) if row else 0

    def tick(self) -> int:
        """Advance the conversation clock by one turn and persist it."""
        turn = self.turn + 1
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('turn', ?)", (str(turn),))
        self.db.commit()
        return turn

    # -- writing -------------------------------------------------------------
    def write(self, fact: Fact) -> WriteResult:
        vector = embed(fact.text)
        if fact.slot and (old := self._by_slot(fact.slot)):
            if old.text == fact.text:
                return WriteResult("duplicate", self._touch(old.id))
            self.db.execute(
                "UPDATE memories SET text=?, importance=?, last_used_turn=?, embedding=? WHERE id=?",
                (fact.text, fact.importance, self.turn, json.dumps(vector), old.id),
            )
            self.db.commit()
            return WriteResult("updated", self._get(old.id), previous=old.text)
        for memory, other in self._all_with_vectors():
            if cosine(vector, other) >= self.duplicate_threshold:
                return WriteResult("duplicate", self._touch(memory.id))
        cursor = self.db.execute(
            "INSERT INTO memories (text, kind, slot, importance, created_turn, last_used_turn, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fact.text, fact.kind, fact.slot, fact.importance, self.turn, self.turn, json.dumps(vector)),
        )
        self.db.commit()
        return WriteResult("added", self._get(cursor.lastrowid))

    # -- reading -------------------------------------------------------------
    def recall(self, query: str, k: int = 3, min_similarity: float = 0.3) -> list[Recall]:
        """Top-k memories for ``query``, scored by similarity, importance and recency."""
        q, now, hits = embed(query), self.turn, []
        for memory, vector in self._all_with_vectors():
            similarity = cosine(q, vector)
            if similarity < min_similarity:
                continue
            recency = 0.5 ** ((now - memory.last_used_turn) / self.half_life)
            score = 0.6 * similarity + 0.25 * memory.importance + 0.15 * recency
            hits.append(Recall(memory, round(score, 3), round(similarity, 3), round(recency, 3)))
        top = sorted(hits, key=lambda r: r.score, reverse=True)[:k]
        for hit in top:
            self._touch(hit.memory.id)  # being used keeps a memory fresh
        return top

    def all(self) -> list[Memory]:
        return [m for m, _ in self._all_with_vectors()]

    # -- helpers -------------------------------------------------------------
    _COLUMNS = "id, text, kind, slot, importance, last_used_turn"

    def _get(self, memory_id: int) -> Memory:
        return Memory(*self.db.execute(f"SELECT {self._COLUMNS} FROM memories WHERE id=?", (memory_id,)).fetchone())

    def _by_slot(self, slot: str) -> Memory | None:
        row = self.db.execute(f"SELECT {self._COLUMNS} FROM memories WHERE slot=?", (slot,)).fetchone()
        return Memory(*row) if row else None

    def _touch(self, memory_id: int) -> Memory:
        self.db.execute("UPDATE memories SET last_used_turn=? WHERE id=?", (self.turn, memory_id))
        self.db.commit()
        return self._get(memory_id)

    def _all_with_vectors(self) -> list[tuple[Memory, list[float]]]:
        rows = self.db.execute(f"SELECT {self._COLUMNS}, embedding FROM memories ORDER BY id").fetchall()
        return [(Memory(*row[:-1]), json.loads(row[-1])) for row in rows]

    def close(self) -> None:
        self.db.close()
