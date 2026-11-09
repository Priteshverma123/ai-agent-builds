"""The journal: a SQLite file that outlives any worker process.

Durability comes from one rule: **a step is done when its result is committed to the journal**,
not when its code finished running. On restart, the engine replays committed results instead of
re-running the steps. The journal also holds a *lease* per run, so two workers can never execute
the same run at the same time - and a crashed worker's lease simply expires.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    workflow    TEXT NOT NULL,
    input       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    owner       TEXT,
    lease_until REAL NOT NULL DEFAULT 0,
    result      TEXT,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    run_id   TEXT NOT NULL REFERENCES runs(run_id),
    step     TEXT NOT NULL,
    status   TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    attempts INTEGER NOT NULL,
    result   TEXT,
    error    TEXT,
    PRIMARY KEY (run_id, step)
);
"""


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    workflow: str
    input: dict
    status: str
    owner: str | None
    lease_until: float
    result: Any
    error: str | None


class LeaseHeld(RuntimeError):
    """Another worker owns this run and its lease has not expired."""


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        # Autocommit mode: every statement is durable as soon as it returns, which is the point.
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL")
        # WAL + NORMAL survives any *process* crash; only a power cut can lose the last commits.
        # Use synchronous = FULL if you need that too (slower: one fsync per commit).
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.executescript(SCHEMA)

    def create_run(self, workflow: str, input: dict) -> str:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        self.conn.execute("INSERT INTO runs (run_id, workflow, input, status) VALUES (?, ?, ?, 'pending')",
                          (run_id, workflow, json.dumps(input)))
        return run_id

    def get_run(self, run_id: str) -> RunRecord:
        row = self.conn.execute("SELECT run_id, workflow, input, status, owner, lease_until, result, error "
                                "FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunRecord(row[0], row[1], json.loads(row[2]), row[3], row[4], row[5],
                         json.loads(row[6]) if row[6] else None, row[7])

    def claim(self, run_id: str, owner: str, lease_s: float, now: float | None = None) -> None:
        """Atomically take (or renew) the lease. Fails if someone else holds a live lease."""
        now = time.time() if now is None else now
        cursor = self.conn.execute(
            "UPDATE runs SET owner = ?, lease_until = ?, status = 'running' "
            "WHERE run_id = ? AND status IN ('pending', 'running') AND (owner IS NULL OR owner = ? OR lease_until < ?)",
            (owner, now + lease_s, run_id, owner, now))
        if cursor.rowcount == 0:
            run = self.get_run(run_id)
            if run.status in ("completed", "failed"):
                return
            raise LeaseHeld(f"{run_id} is leased by {run.owner} for another {run.lease_until - now:.1f}s")

    def get_step(self, run_id: str, step: str) -> tuple[bool, Any]:
        """Return ``(found, result)`` for a *completed* step."""
        row = self.conn.execute("SELECT result FROM steps WHERE run_id = ? AND step = ? AND status = 'completed'",
                                (run_id, step)).fetchone()
        return (True, json.loads(row[0])) if row else (False, None)

    def complete_step(self, run_id: str, step: str, result: Any, attempts: int) -> None:
        payload = json.dumps(result)  # fails loudly on results that can't be replayed
        self.conn.execute("INSERT OR REPLACE INTO steps (run_id, step, status, attempts, result) "
                          "VALUES (?, ?, 'completed', ?, ?)", (run_id, step, attempts, payload))

    def fail_step(self, run_id: str, step: str, error: str, attempts: int) -> None:
        self.conn.execute("INSERT OR REPLACE INTO steps (run_id, step, status, attempts, error) "
                          "VALUES (?, ?, 'failed', ?, ?)", (run_id, step, attempts, error))

    def finish(self, run_id: str, result: Any) -> None:
        self.conn.execute("UPDATE runs SET status = 'completed', result = ?, owner = NULL WHERE run_id = ?",
                          (json.dumps(result), run_id))

    def fail(self, run_id: str, error: str) -> None:
        self.conn.execute("UPDATE runs SET status = 'failed', error = ?, owner = NULL WHERE run_id = ?",
                          (error, run_id))

    def steps(self, run_id: str) -> list[tuple[str, str, int]]:
        """``(step, status, attempts)`` in the order they were journaled."""
        return self.conn.execute("SELECT step, status, attempts FROM steps WHERE run_id = ? ORDER BY rowid",
                                 (run_id,)).fetchall()

    def close(self) -> None:
        self.conn.close()
