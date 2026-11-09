"""Spans and a tracer, built on `contextvars`.

A *trace* is one agent run. A *span* is one timed unit of work inside it (the run, a step, a model
call, a tool call). Each span knows its parent, so the run becomes a tree you can draw as a
waterfall. The "current span" lives in a ContextVar, so nested code (and asyncio tasks) gets the
right parent automatically without passing it around.
"""

from __future__ import annotations

import re
import secrets
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterator, Protocol, TypeVar

SENSITIVE_KEY = re.compile(r"key|token|secret|password|authorization", re.IGNORECASE)
SENSITIVE_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b")
MAX_ATTR_CHARS = 500


class Clock(Protocol):
    def now(self) -> float: ...  # milliseconds

    def sleep(self, ms: float) -> None: ...


class RealClock:
    def now(self) -> float:
        return time.perf_counter() * 1000

    def sleep(self, ms: float) -> None:
        return None  # real work takes real time; mocks don't need to pretend


class SimClock:
    """Simulated time: mocks 'sleep' by advancing it, so demo output and tests are deterministic."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, ms: float) -> None:
        self.t += ms


def redact(key: str, value: Any) -> Any:
    """Keep secrets out of traces: traces get copied to dashboards, tickets and chat."""
    if SENSITIVE_KEY.search(key) and not key.startswith(("tokens.", "usage.")):
        return "[REDACTED]"
    if isinstance(value, str):
        value = SENSITIVE_VALUE.sub("[REDACTED]", value)
        return value if len(value) <= MAX_ATTR_CHARS else value[:MAX_ATTR_CHARS] + "...[truncated]"
    return value


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    kind: str  # agent | step | llm | tool | internal
    start_ms: float
    end_ms: float | None = None
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return round((self.end_ms if self.end_ms is not None else self.start_ms) - self.start_ms, 3)

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = redact(key, value)

    def add_event(self, name: str, at_ms: float, **attrs: Any) -> None:
        self.events.append({"name": name, "at_ms": at_ms, **{k: redact(k, v) for k, v in attrs.items()}})

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "duration_ms": self.duration_ms}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Span":
        return cls(**{k: v for k, v in data.items() if k != "duration_ms"})


Exporter = Callable[[Span], None]
F = TypeVar("F", bound=Callable[..., Any])


class Tracer:
    def __init__(self, clock: Clock | None = None, exporters: list[Exporter] | None = None,
                 deterministic_ids: bool = False) -> None:
        self.clock = clock or RealClock()
        self.exporters = exporters or []
        self.finished: list[Span] = []
        self._current: ContextVar[Span | None] = ContextVar("current_span", default=None)
        self._counter = 0
        self._deterministic = deterministic_ids

    def _new_id(self, nbytes: int) -> str:
        if self._deterministic:
            self._counter += 1
            return f"{self._counter:0{nbytes * 2}x}"
        return secrets.token_hex(nbytes)

    @property
    def current(self) -> Span | None:
        return self._current.get()

    @contextmanager
    def span(self, name: str, kind: str = "internal", **attributes: Any) -> Iterator[Span]:
        parent = self._current.get()
        span = Span(
            trace_id=parent.trace_id if parent else self._new_id(8),
            span_id=self._new_id(4), parent_id=parent.span_id if parent else None,
            name=name, kind=kind, start_ms=self.clock.now(),
        )
        for key, value in attributes.items():
            span.set(key, value)
        token = self._current.set(span)
        try:
            yield span
        except BaseException as exc:
            span.status = "error"
            span.add_event("exception", self.clock.now(), type=type(exc).__name__, message=str(exc),
                           stack="".join(traceback.format_exception_only(type(exc), exc)).strip())
            raise
        finally:
            span.end_ms = self.clock.now()
            self._current.reset(token)
            self.finished.append(span)
            for export in self.exporters:
                export(span)

    def traced(self, kind: str = "internal", name: str | None = None) -> Callable[[F], F]:
        """Decorator form: @tracer.traced("tool")"""

        def wrap(fn: F) -> F:
            def inner(*args: Any, **kwargs: Any) -> Any:
                with self.span(name or fn.__name__, kind):
                    return fn(*args, **kwargs)

            inner.__name__, inner.__doc__ = fn.__name__, fn.__doc__
            return inner  # type: ignore[return-value]

        return wrap

    def event(self, name: str, **attrs: Any) -> None:
        """Attach an event (a point in time, not a duration) to the current span."""
        if self.current:
            self.current.add_event(name, self.clock.now(), **attrs)
