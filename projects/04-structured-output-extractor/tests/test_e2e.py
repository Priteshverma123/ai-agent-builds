"""End-to-end: the demo flow (cli -> extract() -> MockLLM -> pydantic schemas -> repair loop) and config."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from extractor.cli import main
from extractor.config import Settings
from extractor.llm import MockLLM, make_llm

PROJECT = Path(__file__).resolve().parents[1]
SETTINGS_ENV = ("LLM_PROVIDER", "LLM_MODEL", "EXTRACT_MAX_ATTEMPTS")


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_demo_extracts_repairs_and_routes_to_review(capsys):
    main([])
    out = capsys.readouterr().out
    assert "model: MockLLM | max 3 attempts" in out
    assert "OK: a validated Invoice after 2 attempt(s)" in out
    assert "OK: a validated SupportTicket after 2 attempt(s)" in out
    assert "FAILED: send to a human for review" in out
    assert '"order_id": "ORD-48213"' in out
    assert "Valid: 2/3 documents. Routed to human review: 1." in out


def test_single_file_with_attempts_from_env(monkeypatch, capsys):
    monkeypatch.setenv("EXTRACT_MAX_ATTEMPTS", "1")
    main([str(PROJECT / "examples" / "email_late_order.txt"), "--schema", "ticket"])
    out = capsys.readouterr().out
    assert "max 1 attempts" in out
    assert "Valid: 0/1 documents. Routed to human review: 1." in out  # no repair allowed


def test_valid_output_is_real_json(capsys):
    main([str(PROJECT / "examples" / "invoice_acme.txt")])
    out = capsys.readouterr().out
    body = out[out.index("\n{") + 1 : out.rindex("}") + 1]
    assert json.loads(body)["total"] == "725.75"


def test_settings_defaults_and_validation(monkeypatch):
    settings = Settings.from_env()
    assert settings == Settings(llm_provider="mock", llm_model=None, max_attempts=3)
    assert isinstance(make_llm(settings), MockLLM)
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_demo_script_runs_as_a_subprocess():
    """`python demo.py` works from a clean checkout with no install and no env vars."""
    env = {k: v for k, v in os.environ.items() if k not in SETTINGS_ENV}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "demo.py"], cwd=PROJECT, capture_output=True, text=True, timeout=30, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "Valid: 2/3 documents." in result.stdout
