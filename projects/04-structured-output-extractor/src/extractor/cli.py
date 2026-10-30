"""CLI: extract structured data from the example documents (or your own file) and show every attempt.

Used by `demo.py`, `python -m extractor` and the `extractor` console script.

    python demo.py
    python demo.py path/to/email.txt --schema ticket
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .extract import Extraction, extract
from .llm import LLM, make_llm
from .schemas import SCHEMAS
from .ui import banner, box

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DEMO_FILES = [("invoice_acme.txt", "invoice"), ("email_late_order.txt", "ticket"), ("invoice_bad_total.txt", "invoice")]


def report(path: Path, schema_name: str, llm: LLM, max_attempts: int = 3) -> Extraction:
    schema = SCHEMAS[schema_name]
    result = extract(path.read_text(encoding="utf-8"), schema, llm, max_attempts=max_attempts)
    rows: list[tuple[str, str]] = []
    for attempt in result.attempts:
        status = "valid" if not attempt.errors else f"invalid ({len(attempt.errors)} error(s))"
        rows.append((f"attempt {attempt.number}", status))
        rows += [("", f"- {error}") for error in attempt.errors]
    if result.ok:
        rows.append(("result", f"OK: a validated {schema.__name__} after {len(result.attempts)} attempt(s)"))
    else:
        rows.append(("result", "FAILED: send to a human for review (bad data in, no valid data out)"))
    print(box(f"{path.name} -> {schema.__name__}", rows))
    if result.data is not None:
        print(result.data.model_dump_json(indent=2))
    print()
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Messy text -> validated JSON with repair retries.")
    parser.add_argument("file", nargs="?", type=Path, help="a text file to extract from")
    parser.add_argument("--schema", choices=sorted(SCHEMAS), default="invoice")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    llm = make_llm(settings)
    model = type(llm).__name__
    print(banner(f"04 - Structured output extractor | model: {model} | max {settings.max_attempts} attempts"))
    jobs = [(args.file, args.schema)] if args.file else [(EXAMPLES / name, kind) for name, kind in DEMO_FILES]
    results = [report(path, kind, llm, settings.max_attempts) for path, kind in jobs]
    valid = sum(r.ok for r in results)
    print(f"Valid: {valid}/{len(results)} documents. Routed to human review: {len(results) - valid}.")


if __name__ == "__main__":
    main()
