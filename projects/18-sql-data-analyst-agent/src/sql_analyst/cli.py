"""Command line: ask the sample shop database the demo questions (one must be refused), or your own.

    python demo.py                                   # the demo question set
    python demo.py "How many customers do we have?"  # your own question
    python demo.py --json                            # also print the chart-ready JSON spec
"""

from __future__ import annotations

import argparse

from .agent import SQLAnalyst
from .chart import render_ascii
from .config import load_settings
from .db import ReadOnlyDatabase, build_demo_db
from .llm import MockSQLWriter, llm_from_env
from .trace import Tracer, box


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Natural language -> safe, read-only SQL")
    parser.add_argument("question", nargs="*", help="ask your own question instead of the demo set")
    parser.add_argument("--json", action="store_true", help="also print the chart-ready JSON spec")
    args = parser.parse_args(argv)

    settings = load_settings()
    db_path = build_demo_db(settings.db_path, settings.seed_sql)
    db = ReadOnlyDatabase(db_path, timeout_ms=settings.timeout_ms)
    llm = llm_from_env(MockSQLWriter())
    questions = [" ".join(args.question)] if args.question else \
        settings.questions.read_text(encoding="utf-8").splitlines()

    print(box("SQL DATA ANALYST", [
        f"model: {llm.name}   database: shop.db (read-only)",
        "tables: " + ", ".join(f"{t.name}({t.row_count})" for t in db.schema.tables.values()),
    ]))
    for question in filter(None, questions):
        print(f"\nQ: {question}")
        analyst = SQLAnalyst(db, llm, max_attempts=settings.max_attempts, max_rows=settings.max_rows,
                             tracer=Tracer(echo=True))
        answer = analyst.ask(question)
        body = [answer.summary]
        if answer.chart:
            body += ["", *render_ascii(answer.chart)]
        print(box(f"{answer.status.upper()} after {answer.attempts} attempt(s)", body))
        if args.json and answer.chart:
            print(answer.chart.model_dump_json(indent=2))
    db.close()
    return 0
