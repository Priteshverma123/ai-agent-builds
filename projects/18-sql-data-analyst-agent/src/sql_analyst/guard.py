"""Static checks on model-written SQL, *before* it touches the database.

Two kinds of problems, two kinds of response:

* :class:`UnsafeSQL` - the query tries to change something (or smuggle a second statement).
  The agent **refuses** and never asks the model to "repair" it into something else.
* :class:`InvalidSQL` - the query is harmless but wrong (unknown table). The agent feeds the
  error back to the model and lets it try again.

The guard also caps result size by enforcing a ``LIMIT``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import Schema

FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "replace", "attach", "detach",
    "pragma", "vacuum", "reindex", "truncate", "grant", "begin", "commit", "rollback",
    "savepoint", "release",
)
# Functions that reach outside the database (files, native code) are never allowed.
FORBIDDEN_FUNCTIONS = ("load_extension", "readfile", "writefile", "fts3_tokenizer")


class UnsafeSQL(ValueError):
    """The query could modify data or escape the sandbox. Refuse, do not retry."""


class InvalidSQL(ValueError):
    """The query is read-only but references something that does not exist. Safe to retry."""


@dataclass
class SafeQuery:
    sql: str
    tables: list[str]
    notes: list[str] = field(default_factory=list)


def _mask(sql: str) -> str:
    """Blank out comments and string literals so keywords inside them can't fool the checks."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str, schema: Schema, max_rows: int = 200) -> SafeQuery:
    """Validate one model-written statement and return a version that is safe to execute."""
    text = sql.strip().rstrip(";").strip()
    if not text:
        raise InvalidSQL("empty query")
    masked = _mask(text).lower()

    if ";" in masked:
        raise UnsafeSQL("multiple statements are not allowed")
    first_word = masked.split(None, 1)[0]
    if first_word not in ("select", "with"):
        raise UnsafeSQL(f"only SELECT queries are allowed, got {first_word.upper()}")
    for keyword in FORBIDDEN_KEYWORDS:
        # `replace(` is the harmless string function; `REPLACE INTO` is a write.
        if re.search(rf"\b{keyword}\b(?!\s*\()", masked):
            raise UnsafeSQL(f"forbidden keyword: {keyword.upper()}")
    for function in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{function}\s*\(", masked):
            raise UnsafeSQL(f"forbidden function: {function}()")

    cte_names = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", masked))
    referenced = re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", masked)
    unknown = sorted({t for t in referenced if t not in schema.tables and t not in cte_names})
    if unknown:
        raise InvalidSQL(f"unknown table(s): {', '.join(unknown)}; known: {', '.join(sorted(schema.tables))}")

    notes: list[str] = []
    has_limit = re.search(r"\blimit\s+\d+\s*$", masked) is not None
    limit = re.search(r"\blimit\s+(\d+)\s*$", text, flags=re.IGNORECASE) if has_limit else None
    if limit is None:
        text = f"SELECT * FROM (\n{text}\n) LIMIT {max_rows}"
        notes.append(f"added LIMIT {max_rows}")
    elif int(limit.group(1)) > max_rows:
        text = text[: limit.start(1)] + str(max_rows)
        notes.append(f"clamped LIMIT to {max_rows}")
    tables = sorted({t for t in referenced if t in schema.tables})
    return SafeQuery(text, tables, notes)
