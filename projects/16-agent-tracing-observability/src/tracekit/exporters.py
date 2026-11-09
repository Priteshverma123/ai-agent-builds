"""Exporters and trace analysis.

JSONL (one finished span per line) is the simplest durable format: append-only, streamable, and
easy to load into anything later (pandas, a database, an OpenTelemetry collector).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .spans import Span


class JSONLExporter:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def __call__(self, span: Span) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(span.to_dict(), sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[Span]:
    return [Span.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]


def group_traces(spans: list[Span]) -> dict[str, list[Span]]:
    traces: dict[str, list[Span]] = {}
    for span in sorted(spans, key=lambda s: (s.start_ms, s.span_id)):
        traces.setdefault(span.trace_id, []).append(span)
    return traces


@dataclass(frozen=True)
class TraceSummary:
    trace_id: str
    name: str
    total_ms: float
    llm_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    errors: int
    llm_ms: float
    tool_ms: float
    slowest: str


def summarise(spans: list[Span]) -> TraceSummary:
    root = next(s for s in spans if s.parent_id is None)
    llm = [s for s in spans if s.kind == "llm"]
    tools = [s for s in spans if s.kind == "tool"]
    leaf = max(llm + tools, key=lambda s: s.duration_ms, default=root)
    return TraceSummary(
        trace_id=root.trace_id, name=str(root.attributes.get("question", root.name)), total_ms=root.duration_ms,
        llm_calls=len(llm), tool_calls=len(tools),
        input_tokens=sum(int(s.attributes.get("usage.input_tokens", 0)) for s in llm),
        output_tokens=sum(int(s.attributes.get("usage.output_tokens", 0)) for s in llm),
        cost_usd=round(sum(float(s.attributes.get("cost_usd", 0.0)) for s in llm), 6),
        errors=sum(s.status == "error" for s in spans),
        llm_ms=round(sum(s.duration_ms for s in llm), 1), tool_ms=round(sum(s.duration_ms for s in tools), 1),
        slowest=f"{leaf.name} ({leaf.duration_ms:.0f} ms)",
    )
