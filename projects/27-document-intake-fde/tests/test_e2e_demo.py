"""End-to-end: the documented demo command, run exactly as learners run it."""

import os
import subprocess
import sys
from pathlib import Path

from intake.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_run_py_demo_traces_every_document_and_passes_acceptance(tmp_path):
    env = {**os.environ, "INTAKE_OUT_DIR": str(tmp_path / "out"), "LLM_PROVIDER": "mock"}
    proc = subprocess.run([sys.executable, "run.py", "demo"], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=60)
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert "== Reference documents" in out
    assert "+-- INV-1002.txt [EXCEPTION]" in out and "PRICE_VARIANCE" in out
    assert "INV-1008.txt" in out and "DUPLICATE_INVOICE" in out
    assert "== Run summary ==" in out and "straight-through (posted to ERP)" in out
    assert "ACCEPTANCE: PASS" in out
    written = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"erp_invoices.jsonl", "erp_invoice_lines.csv", "exceptions.jsonl", "run_report.md"} <= written


def test_settings_read_every_documented_variable():
    s = Settings.from_env({"LLM_PROVIDER": "Anthropic", "LLM_MODEL": "m", "INTAKE_INBOX": "i",
                           "INTAKE_CLIENT": "c.json", "INTAKE_MASTER": "m", "INTAKE_GOLDEN": "g.json",
                           "INTAKE_OUT_DIR": "o"})
    assert (s.llm_provider, s.llm_model, s.inbox, s.client, s.master, s.golden, s.out_dir) == (
        "anthropic", "m", Path("i"), Path("c.json"), Path("m"), Path("g.json"), Path("o"))
    assert Settings.from_env({}) == Settings()
