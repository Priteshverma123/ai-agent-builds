"""Demo: research a homeowner question with a swarm of parallel workers over a local 'web'."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from .config import Settings, load_settings
from .corpus import Fetcher, SearchIndex, load_corpus
from .llm import MockExtractor, MockPlanner, llm_from_env
from .report import render_markdown, render_stats
from .swarm import Swarm

QUESTION = "What should a homeowner know before buying a home battery?"


def build_swarm(corpus: Path | None = None, *, concurrency: int | None = None, timeout_s: float | None = None,
                log=None, settings: Settings | None = None) -> Swarm:
    """Wire index, fetcher and both models from settings (env); explicit arguments win."""
    s = settings or load_settings()
    docs = load_corpus(corpus or s.corpus_dir)
    fetcher = Fetcher(docs, max_concurrency=concurrency or s.concurrency,
                      timeout_s=timeout_s or s.fetch_timeout_s, retries=s.fetch_retries)
    return Swarm(SearchIndex(docs), fetcher, llm_from_env(MockPlanner(), s), llm_from_env(MockExtractor(), s),
                 docs_per_worker=s.docs_per_worker, log=log)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Parallel research swarm with dedup and a merged report")
    parser.add_argument("question", nargs="*", help=f"default: {QUESTION!r}")
    parser.add_argument("--concurrency", type=int, default=settings.concurrency, help="max requests in flight")
    parser.add_argument("--out", type=Path, help="also write the report to this markdown file")
    args = parser.parse_args(argv)

    t0 = time.perf_counter()

    def log(who: str, msg: str) -> None:
        print(f"[{time.perf_counter() - t0:5.2f}s] {who:<9}| {msg}")

    swarm = build_swarm(concurrency=args.concurrency, log=log)
    question = " ".join(args.question) or QUESTION
    print(f"QUESTION: {question}\n")
    report = asyncio.run(swarm.run(question))
    markdown = render_markdown(report)
    print("\n" + markdown + "\n")
    print(render_stats(report, swarm.fetcher))
    if args.out:
        args.out.write_text(markdown, encoding="utf-8")
    return 0
