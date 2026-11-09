"""Command line: `demo` (teaching trace), `run` (batch job), `eval` (golden-set acceptance gate)."""

from __future__ import annotations

import argparse
import os
import textwrap
from pathlib import Path

from .adapters.providers import build_llm
from .adapters.storage import OutputWriter, load_inbox, load_posted_keys, load_vendors
from .config import ClientConfig, Settings
from .domain.models import DocumentResult, Status
from .domain.vendors import VendorMaster
from .services.evaluate import EvalReport, evaluate, load_golden
from .services.pipeline import IntakePipeline, RunOutput, write_outputs
from .services.report import render_markdown, stats

WIDTH = 96


def run_pipeline(inbox: Path, client: Path, master: Path, out: Path, provider: str | None = None,
                 settings: Settings | None = None) -> RunOutput:
    cfg = ClientConfig.load(client)
    llm = build_llm(provider, settings)
    pipeline = IntakePipeline(cfg, VendorMaster(load_vendors(master / "vendors.json")),
                              load_posted_keys(master / "posted_invoices.json"), llm)
    run = pipeline.run(load_inbox(inbox))
    return write_outputs(run, OutputWriter(out), render_markdown(run, cfg, llm.name))


def render_document(r: DocumentResult) -> str:
    title = f"+-- {r.doc_id} [{r.status.value.upper()}] "
    lines = [title + "-" * (WIDTH - len(title) - 1) + "+"]
    for event in r.trace:
        mark = " " if event.ok else "!"
        body = textwrap.wrap(event.detail, WIDTH - 15) or [""]
        lines.append(f"| {mark}{event.stage:<9} {body[0]:<{WIDTH - 15}} |")
        lines += [f"|  {'':<9} {more:<{WIDTH - 15}} |" for more in body[1:]]
    lines.append("+" + "-" * (WIDTH - 2) + "+")
    return "\n".join(lines)


def render_summary(run: RunOutput) -> str:
    s = stats(run)
    rows = [
        ("documents processed", f"{s['documents']} in {run.duration_ms} ms"),
        ("invoices", str(s["invoices"])),
        ("straight-through (posted to ERP)", f"{s['approved']}  ({s['stp_rate']:.0%})  USD {s['approved_amount']:,.2f}"),
        ("held in exceptions queue", f"{s['exceptions']} documents, USD {s['held_amount']:,.2f} of invoices"),
    ]
    rows += [(f"  {r.doc_id}", f"-> {r.owner}: {', '.join(i.code for i in r.blocking)}")
             for r in run.by_status(Status.EXCEPTION)]
    rows += [(name, os.path.relpath(path)) for name, path in run.files.items()]
    return "\n".join(f"  {k:<34} {v}" for k, v in rows)


def render_eval(report: EvalReport) -> str:
    lines = [f"  {'metric':<26} {'value':>7}  {'target':>7}  result"]
    for name, value in report.metrics.items():
        target = report.thresholds.get(name)
        verdict = "" if target is None else ("PASS" if value >= target else "FAIL")
        lines.append(f"  {name:<26} {value:>7.3f}  {'' if target is None else f'{target:.3f}':>7}  {verdict}")
    lines += [f"  ! {m}" for m in report.mismatches]
    lines.append(f"  ACCEPTANCE: {'PASS' if report.passed else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Document intake pipeline (AI Agent Builds #27)")
    parser.add_argument("command", choices=["demo", "run", "eval"])
    parser.add_argument("--inbox", type=Path, default=settings.inbox)
    parser.add_argument("--client", type=Path, default=settings.client)
    parser.add_argument("--master", type=Path, default=settings.master)
    parser.add_argument("--golden", type=Path, default=settings.golden)
    parser.add_argument("--out", type=Path, default=settings.out_dir)
    parser.add_argument("--provider", default=None, help="mock | anthropic | openai (default: $LLM_PROVIDER or mock)")
    args = parser.parse_args(argv)

    run = run_pipeline(args.inbox, args.client, args.master, args.out, args.provider, settings)
    if args.command == "demo":
        refs = run.by_status(Status.REFERENCE)
        print(f"== Reference documents ({len(refs)}) kept for 3-way matching ==")
        for r in refs:
            print(f"  {r.doc_id:<16} {r.doc_type.value:<15} {r.trace[1].detail}")
        print()
        for result in run.results:
            if result.status is not Status.REFERENCE:
                print(render_document(result))
        print("\n== Run summary ==")
        print(render_summary(run))
    if args.command == "run":
        print(render_summary(run))
    if args.command in ("demo", "eval"):
        report = evaluate(run.results, load_golden(args.golden), ClientConfig.load(args.client).acceptance)
        print("\n== Golden-set acceptance ==")
        print(render_eval(report))
        return 0 if report.passed else 1
    return 0
