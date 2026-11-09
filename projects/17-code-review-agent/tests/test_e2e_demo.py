"""End-to-end: the demo flow (CLI -> diff -> static checks -> LLM pass -> guard -> rank -> verdict -> render)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from reviewer.cli import main
from reviewer.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = ("LLM_PROVIDER", "LLM_MODEL", "REVIEW_DIFF", "REVIEW_BASE", "REVIEW_FORMAT", "REVIEW_FAIL_ON",
            "REVIEW_STATIC_ONLY")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_demo_trace_shows_every_stage_and_the_verdict(capsys):
    main([])
    out = capsys.readouterr().out
    assert "[parse]   4 files, +42 lines" in out
    assert "[static]  11 findings from 9 rules" in out
    assert "[GUARD]   refused to dismiss CRITICAL hardcoded-secret@shop/api.py:10" in out
    assert "dropped LLM finding 'connection-pooling'" in out
    assert "VERDICT: REQUEST_CHANGES" in out
    assert out.index("hardcoded-secret       static") < out.index("sql-injection          static")  # ranked


def test_static_only_from_env_skips_the_llm(capsys, monkeypatch):
    monkeypatch.setenv("REVIEW_STATIC_ONLY", "true")
    monkeypatch.setenv("REVIEW_FORMAT", "json")
    main([])
    report = json.loads(capsys.readouterr().out)
    assert all(f["source"] == "static" for f in report["findings"]) and report["summaries"] == []


def test_demo_script_reviews_a_diff_from_stdin_as_markdown():
    env = {**os.environ, "LLM_PROVIDER": "mock"}
    diff = (ROOT / "examples" / "change.diff").read_text(encoding="utf-8")
    args = ["demo.py", "--diff", "-", "--format", "markdown", "--fail-on", "critical"]
    proc = subprocess.run([sys.executable, *args],
                          cwd=ROOT, env=env, input=diff, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1, proc.stderr  # CRITICAL findings fail the build
    assert "## Automated review: Changes requested" in proc.stdout and "| 1 | CRITICAL | `shop/api.py:10`" in proc.stdout


def test_settings_validate_env_values():
    assert Settings.from_env({"REVIEW_FAIL_ON": "High"}).fail_on == "high"
    assert Settings.from_env({}) == Settings()
    with pytest.raises(ValueError):
        Settings.from_env({"REVIEW_FORMAT": "pdf"})
