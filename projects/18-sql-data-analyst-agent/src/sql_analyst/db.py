"""A database handle that physically cannot write.

Prompt instructions ("only write SELECT") are a request, not a control. We enforce read-only at
three independent layers, so a bug in any one of them is not a data-loss incident:

1. the connection is opened with ``mode=ro`` (SQLite refuses writes at the file level),
2. ``PRAGMA query_only = ON`` (SQLite refuses writes at the statement level),
3. an *authorizer* callback that only allows reading tables and calling functions.

The SQL guard in ``guard.py`` is a fourth, friendlier layer that explains *why* a query was refused.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .schema import Schema, introspect

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    getattr(sqlite3, "SQLITE_FUNCTION", 31),
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    elapsed_ms: float


class QueryTimeout(sqlite3.OperationalError):
    """Raised when a query runs longer than the configured budget."""


def build_demo_db(path: Path, seed_sql: Path) -> Path:
    """Create (or recreate) the sample database from a ``.sql`` seed file."""
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(seed_sql.read_text(encoding="utf-8"))
    conn.close()
    return path


class ReadOnlyDatabase:
    """Open an existing SQLite file for analysis only."""

    def __init__(self, path: Path, timeout_ms: int = 2000) -> None:
        self.path = Path(path)
        self.timeout_ms = timeout_ms
        self.conn = sqlite3.connect(f"file:{self.path.resolve().as_posix()}?mode=ro", uri=True)
        self.conn.execute("PRAGMA query_only = ON")
        self.schema: Schema = introspect(self.conn)  # PRAGMAs are needed here, before the authorizer.
        self.conn.set_authorizer(self._authorize)

    @staticmethod
    def _authorize(action: int, arg1: str | None, arg2: str | None, db: str | None, src: str | None) -> int:
        return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY

    def run(self, sql: str) -> QueryResult:
        """Execute one SELECT with a wall-clock budget enforced by a progress handler."""
        deadline = time.perf_counter() + self.timeout_ms / 1000
        self.conn.set_progress_handler(lambda: int(time.perf_counter() > deadline), 10_000)
        start = time.perf_counter()
        try:
            cursor = self.conn.execute(sql)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise QueryTimeout(f"query exceeded {self.timeout_ms} ms") from exc
            raise
        finally:
            self.conn.set_progress_handler(None, 0)
        columns = [d[0] for d in cursor.description or []]
        return QueryResult(columns, rows, (time.perf_counter() - start) * 1000)

    def close(self) -> None:
        self.conn.close()
