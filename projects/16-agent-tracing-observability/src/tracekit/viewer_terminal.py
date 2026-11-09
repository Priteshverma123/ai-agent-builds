"""Terminal waterfall: the span tree with a time bar per span (plain ASCII)."""

from __future__ import annotations

from .exporters import summarise
from .spans import Span

BAR = 34
NAME = 30


def ordered_tree(spans: list[Span]) -> list[tuple[int, Span]]:
    """Depth-first (depth, span) pairs, children in start order."""
    children: dict[str | None, list[Span]] = {}
    for s in spans:
        children.setdefault(s.parent_id, []).append(s)
    for kids in children.values():
        kids.sort(key=lambda s: (s.start_ms, s.span_id))
    out: list[tuple[int, Span]] = []

    def visit(span: Span, depth: int) -> None:
        out.append((depth, span))
        for child in children.get(span.span_id, []):
            visit(child, depth + 1)

    for root in children.get(None, []):
        visit(root, 0)
    return out


def _bar(span: Span, t0: float, total: float) -> str:
    start = int((span.start_ms - t0) / total * BAR) if total else 0
    width = max(1, round(span.duration_ms / total * BAR)) if total else 1
    fill = "!" if span.status == "error" else "#"
    return (" " * start + fill * width)[:BAR].ljust(BAR)


def render_trace(spans: list[Span]) -> str:
    s = summarise(spans)
    root = next(sp for sp in spans if sp.parent_id is None)
    lines = [
        f"TRACE {s.trace_id}  \"{s.name[:44]}\"",
        f"  total {s.total_ms:,.0f} ms | llm {s.llm_calls} calls {s.llm_ms:,.0f} ms | tools {s.tool_calls} calls "
        f"{s.tool_ms:,.0f} ms | tokens {s.input_tokens:,} in / {s.output_tokens:,} out | ${s.cost_usd:.4f}"
        f" | errors {s.errors}",
        f"  {'span':<{NAME}} {'start':>6} {'dur ms':>7}  |{'waterfall':<{BAR}}|",
    ]
    for depth, span in ordered_tree(spans):
        label = ("  " * depth + span.name)[:NAME]
        lines.append(f"  {label:<{NAME}} {span.start_ms - root.start_ms:>6.0f} {span.duration_ms:>7.0f}  "
                     f"|{_bar(span, root.start_ms, root.duration_ms)}|")
        for event in span.events:
            detail = event.get("type") or event.get("reason") or ""
            lines.append(f"  {'  ' * (depth + 1)}* {event['name']}: {detail} {event.get('message', '')}".rstrip())
    lines.append(f"  slowest: {s.slowest}")
    return "\n".join(lines)
