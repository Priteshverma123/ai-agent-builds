"""Span-based tracing (recap of 16). One Trace per request; spans nest via a stack."""
from __future__ import annotations

import itertools
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class Span:
    id: int
    parent: int | None
    name: str
    kind: str                 # request | guard | plan | agent | tool | llm
    start: float
    end: float = 0.0
    status: str = "ok"
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def ms(self) -> float:
        return round((self.end - self.start) * 1000, 2)

    def set(self, **attrs: Any) -> None:
        self.attrs.update(attrs)


class Trace:
    def __init__(self, trace_id: str) -> None:
        self.id = trace_id
        self.spans: list[Span] = []
        self._stack: list[Span] = []
        self._ids = itertools.count(1)

    @contextmanager
    def span(self, name: str, kind: str, **attrs: Any) -> Iterator[Span]:
        s = Span(next(self._ids), self._stack[-1].id if self._stack else None, name, kind, time.perf_counter(),
                 attrs=dict(attrs))
        self.spans.append(s)
        self._stack.append(s)
        try:
            yield s
        except Exception as exc:
            s.status = f"error: {type(exc).__name__}"
            raise
        finally:
            s.end = time.perf_counter()
            self._stack.pop()

    def to_dicts(self) -> list[dict[str, Any]]:
        return [{**asdict(s), "trace_id": self.id, "ms": s.ms} for s in self.spans]

    def render(self, show_ms: bool = True) -> str:
        """ASCII tree, children indented under parents."""
        children: dict[int | None, list[Span]] = {}
        for s in self.spans:
            children.setdefault(s.parent, []).append(s)
        lines: list[str] = []

        def walk(parent: int | None, depth: int) -> None:
            for s in children.get(parent, []):
                attrs = " ".join(f"{k}={v}" for k, v in s.attrs.items())
                timing = f"{s.ms:>7.2f}ms " if show_ms else ""
                flag = "" if s.status == "ok" else f" [{s.status}]"
                lines.append(f"{timing}{'  ' * depth}{s.kind:<7} {s.name}{flag}  {attrs}".rstrip())
                walk(s.id, depth + 1)

        walk(None, 0)
        return "\n".join(lines)


class TraceStore:
    """Keeps recent traces for GET /traces/{id}; optionally appends them to a JSONL file."""

    def __init__(self, path: Path | None = None, keep: int = 200) -> None:
        self._traces: dict[str, Trace] = {}
        self._path, self._keep = path, keep
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def new(self) -> Trace:
        with self._lock:
            return Trace(f"tr_{next(self._ids):05d}")

    def save(self, trace: Trace) -> None:
        with self._lock:
            self._traces[trace.id] = trace
            while len(self._traces) > self._keep:
                self._traces.pop(next(iter(self._traces)))
            if self._path:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    for row in trace.to_dicts():
                        fh.write(json.dumps(row, default=str) + "\n")

    def get(self, trace_id: str) -> Trace | None:
        return self._traces.get(trace_id)
