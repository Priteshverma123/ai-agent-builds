"""Span-based tracing for agents: tracer, instrumentation, JSONL export, terminal + HTML viewers."""

from .exporters import JSONLExporter, read_jsonl, summarise
from .spans import SimClock, Span, Tracer
from .viewer_html import render_html, write_html
from .viewer_terminal import render_trace

__version__ = "0.1.0"

__all__ = ["JSONLExporter", "SimClock", "Span", "Tracer", "read_jsonl", "render_html", "render_trace",
           "summarise", "write_html", "__version__"]
