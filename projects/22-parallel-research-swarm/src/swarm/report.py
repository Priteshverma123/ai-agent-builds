"""Render the merged report: sections, citations, corroboration, and the swarm's own stats."""

from __future__ import annotations

import textwrap

from .corpus import Fetcher
from .models import Report

WIDTH = 78


def render_markdown(report: Report) -> str:
    """The deliverable: a cited brief. Each claim lists every source that said it."""
    number = {s.doc_id: i for i, s in enumerate(report.sources, start=1)}
    out = [f"# {report.question}", ""]
    for sq in report.plan.subquestions:
        out += [f"## {sq.question}", ""]
        clusters = report.sections.get(sq.id, [])
        if not clusters:
            out += ["_No usable findings._", ""]
            continue
        for c in clusters:
            cites = "".join(f"[{number[d]}]" for d in c.doc_ids)
            tag = f" (corroborated by {c.corroboration} sources)" if c.corroboration > 1 else ""
            out.append(f"- {c.claim} {cites}{tag}")
        out.append("")
    out += ["## Sources", ""] + [f"[{number[s.doc_id]}] {s.title} - {s.url}" for s in report.sources]
    failed = {d: r for w in report.workers for d, r in w.failed.items()}
    if failed:
        out += ["", "## Not included", ""] + [f"- {d}: {r}" for d, r in failed.items()]
    return "\n".join(out)


def render_stats(report: Report, fetcher: Fetcher) -> str:
    lines = [
        f"workers          : {len(report.workers)} in parallel",
        f"findings         : {report.raw_findings} raw -> {sum(len(v) for v in report.sections.values())} after dedup",
        f"network requests : {fetcher.network_calls} (peak {fetcher.peak_concurrency} at once)",
        f"retried / shared : {fetcher.network_calls - len(fetcher.inflight)} retried, "
        f"{fetcher.deduplicated_requests} fetches shared via single-flight",
        f"wall time        : {report.wall_ms:7.0f} ms",
        f"time in requests : {report.fetch_ms_total:7.0f} ms  (what a one-at-a-time crawler would wait)",
    ]
    inner = WIDTH - 4
    top = "+-- SWARM STATS " + "-" * (WIDTH - 17) + "+"
    body = [f"| {chunk.ljust(inner)} |" for line in lines for chunk in textwrap.wrap(line, inner)]
    return "\n".join([top, *body, "+" + "-" * (WIDTH - 2) + "+"])
