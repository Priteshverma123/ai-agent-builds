"""Turn a result table into chart-ready output.

An analyst agent is more useful when it answers "what does this look like?", not just "here are
rows". We pick a chart type from the *shape* of the result (no LLM needed), emit a small JSON spec
any frontend can render, and draw an ASCII preview for the terminal.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .db import QueryResult

ChartKind = Literal["kpi", "bar", "line", "table"]
_PERIOD = re.compile(r"^\d{4}(-\d{2}){0,2}$")  # 2026, 2026-03, 2026-03-14


class ChartSpec(BaseModel):
    kind: ChartKind
    title: str
    x: str | None = None
    y: str | None = None
    data: list[dict]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def infer_chart(title: str, result: QueryResult) -> ChartSpec:
    """Choose kpi / line / bar / table from the result's columns and values."""
    data = [dict(zip(result.columns, row)) for row in result.rows]
    cols, rows = result.columns, result.rows
    if len(cols) == 1 and len(rows) == 1 and _is_number(rows[0][0]):
        return ChartSpec(kind="kpi", title=title, y=cols[0], data=data)
    if len(cols) == 2 and rows and all(_is_number(r[1]) for r in rows):
        labels = [str(r[0]) for r in rows]
        kind: ChartKind = "line" if all(_PERIOD.match(label) for label in labels) else "bar"
        return ChartSpec(kind=kind, title=title, x=cols[0], y=cols[1], data=data)
    return ChartSpec(kind="table", title=title, data=data)


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def render_ascii(spec: ChartSpec, width: int = 30) -> list[str]:
    """A terminal preview: big number, horizontal bars, or an aligned table."""
    if spec.kind == "kpi":
        return [f"{spec.y} = {_fmt(spec.data[0][spec.y])}"]
    if spec.kind in ("bar", "line"):
        values = [row[spec.y] for row in spec.data]
        top = max(values) or 1
        label_w = max(len(str(row[spec.x])) for row in spec.data)
        mark = "#" if spec.kind == "bar" else "*"
        return [
            f"{str(row[spec.x]).ljust(label_w)} | {(mark * max(1, round(width * row[spec.y] / top))).ljust(width)} {_fmt(row[spec.y])}"
            for row in spec.data
        ]
    if not spec.data:
        return ["(no rows)"]
    headers = list(spec.data[0])
    widths = [max(len(h), *(len(_fmt(r[h])) for r in spec.data)) for h in headers]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths))]
    lines += ["  ".join(_fmt(r[h]).ljust(w) for h, w in zip(headers, widths)) for r in spec.data[:10]]
    return lines
