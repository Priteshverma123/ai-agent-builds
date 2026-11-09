"""Schema grounding: read the real schema and show the model only what it needs.

Hallucinated column names are the #1 failure of text-to-SQL. The fix is to *ground* the model:
introspect the live database, then hand it a compact "schema card" with column types, foreign
keys and a few example values for low-cardinality text columns (so it knows status is 'paid',
not 'PAID' or 'complete').
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

_SAMPLE_LIMIT = 6  # text columns with at most this many distinct values get their values listed


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_key: bool = False


@dataclass
class Table:
    name: str
    columns: list[Column]
    foreign_keys: list[tuple[str, str, str]] = field(default_factory=list)  # (column, ref_table, ref_column)
    row_count: int = 0
    samples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def column_names(self) -> set[str]:
        return {c.name for c in self.columns}


@dataclass
class Schema:
    tables: dict[str, Table]

    def card(self, names: list[str] | None = None) -> str:
        """Render a compact, model-friendly description of (some of) the tables."""
        lines: list[str] = []
        for name in names or sorted(self.tables):
            t = self.tables[name]
            cols = ", ".join(f"{c.name} {c.type}{' PK' if c.primary_key else ''}" for c in t.columns)
            lines.append(f"TABLE {t.name} ({t.row_count} rows): {cols}")
            for col, ref_table, ref_col in t.foreign_keys:
                lines.append(f"  FK {t.name}.{col} -> {ref_table}.{ref_col}")
            for col, values in t.samples.items():
                lines.append(f"  {t.name}.{col} values: {', '.join(repr(v) for v in values)}")
        return "\n".join(lines)

    def relevant_tables(self, question: str) -> list[str]:
        """Pick the tables a question is probably about, plus the tables needed to join them.

        Scoring is deliberately simple: a table matches if the question mentions its name (or
        singular), one of its columns, or one of its sample values. Then we add "bridge" tables
        whose foreign keys connect two matched tables, so the model can actually write the JOIN.
        """
        words = set(re.findall(r"[a-z_]+", question.lower()))
        hits: set[str] = set()
        for t in self.tables.values():
            names = {t.name, t.name.rstrip("s")}
            columns = {c.name for c in t.columns} | {part for c in t.columns for part in c.name.split("_")}
            values = {v.lower() for vs in t.samples.values() for v in vs}
            if words & (names | columns | values):
                hits.add(t.name)
        if {"revenue", "sales", "spend", "sold", "value"} & words:  # money lives in order lines
            hits |= {"orders", "order_items"} & set(self.tables)
        if not hits:
            return sorted(self.tables)
        # Bridge tables: include a table if it links two tables we already need.
        for t in self.tables.values():
            linked = {ref for _, ref, _ in t.foreign_keys}
            if len(linked & hits) >= 2:
                hits.add(t.name)
        return sorted(hits)


def introspect(conn: sqlite3.Connection) -> Schema:
    """Build a :class:`Schema` from a live SQLite connection."""
    tables: dict[str, Table] = {}
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    for name in names:
        columns = [Column(r[1], r[2] or "ANY", bool(r[5])) for r in conn.execute(f'PRAGMA table_info("{name}")')]
        fks = [(r[3], r[2], r[4]) for r in conn.execute(f'PRAGMA foreign_key_list("{name}")')]
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        table = Table(name, columns, fks, row_count)
        for col in columns:
            if col.type.upper() != "TEXT" or col.name.endswith(("name", "date")):
                continue
            values = [r[0] for r in conn.execute(
                f'SELECT DISTINCT "{col.name}" FROM "{name}" ORDER BY 1 LIMIT {_SAMPLE_LIMIT + 1}'
            )]
            if len(values) <= _SAMPLE_LIMIT:
                table.samples[col.name] = [str(v) for v in values]
        tables[name] = table
    return Schema(tables)
