"""Structured JSON logs + a tiny span tracer (the shape OpenTelemetry would give you).

Every /chat turn gets a trace_id. Every model call and tool call is a span inside it. The trace is
returned by GET /traces/{id}, and every log line carries the trace_id so logs and traces join up.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Iterator

from pydantic import BaseModel, Field

LOGGER_NAME = "support_agent"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": round(record.created, 3), "level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level.upper())
    return logger


def log_event(event: str, **fields: Any) -> None:
    logging.getLogger(LOGGER_NAME).info(event, extra={"fields": fields})


class Span(BaseModel):
    name: str
    start_ms: float
    duration_ms: float = 0.0
    status: str = "ok"
    attrs: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    trace_id: str
    conversation_id: str
    spans: list[Span] = Field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return round(sum(s.duration_ms for s in self.spans if s.name == "agent.turn"), 2)


class TraceRecorder:
    def __init__(self, conversation_id: str) -> None:
        self.trace = Trace(trace_id=uuid.uuid4().hex[:16], conversation_id=conversation_id)
        self._t0 = time.perf_counter()

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        """Time a block. Callers add attributes by mutating the yielded dict."""
        start = time.perf_counter()
        span = Span(name=name, start_ms=round((start - self._t0) * 1000, 2), attrs=dict(attrs))
        self.trace.spans.append(span)
        try:
            yield span.attrs
        except Exception as exc:
            span.status, span.attrs["error"] = "error", repr(exc)
            raise
        finally:
            span.duration_ms = round((time.perf_counter() - start) * 1000, 2)


class TraceStore:
    """Bounded in-memory store; production would export spans to an OTLP collector instead."""

    def __init__(self, capacity: int = 500) -> None:
        self._capacity = capacity
        self._traces: OrderedDict[str, Trace] = OrderedDict()

    def save(self, trace: Trace) -> None:
        self._traces[trace.trace_id] = trace
        while len(self._traces) > self._capacity:
            self._traces.popitem(last=False)

    def get(self, trace_id: str) -> Trace | None:
        return self._traces.get(trace_id)
