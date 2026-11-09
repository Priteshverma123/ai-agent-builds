"""End-to-end: the demo flow (CLI -> schema grounding -> draft -> guard -> read-only DB -> repair -> chart)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sql_analyst.cli import main
from sql_analyst.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = ("LLM_PROVIDER", "LLM_MODEL", "SQL_DB_PATH", "SQL_SEED", "SQL_QUESTIONS", "SQL_MAX_ATTEMPTS",
            "SQL_MAX_ROWS", "SQL_TIMEOUT_MS")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SQL_DB_PATH", str(tmp_path / "shop.db"))


def test_demo_answers_repairs_and_refuses(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "database: shop.db (read-only)" in out
    assert "ERROR    | sqlite: no such column: o.total" in out
    assert "OK after 2 attempt(s)" in out and "Germany | ############################## 218.25" in out
    assert "customers = 8" in out
    assert "BLOCKED  | only SELECT queries are allowed, got DELETE - refusing, no retry" in out
    assert "REFUSED after 1 attempt(s)" in out


def test_own_question_with_chart_json(capsys):
    assert main(["--json", "How", "many", "customers", "do", "we", "have?"]) == 0
    out = capsys.readouterr().out
    spec = json.loads(out[out.index("{"):])
    assert spec["kind"] == "kpi" and "Q: How many customers do we have?" in out


def test_max_attempts_setting_limits_repairs(capsys, monkeypatch):
    monkeypatch.setenv("SQL_MAX_ATTEMPTS", "1")
    main(["What is the average order value by country?"])
    assert "OK after" not in capsys.readouterr().out  # the broken first draft gets no repair attempt


def test_demo_script_runs_as_a_subprocess(tmp_path):
    env = {**os.environ, "LLM_PROVIDER": "mock", "SQL_DB_PATH": str(tmp_path / "sub.db")}
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "REFUSED after 1 attempt(s)" in proc.stdout and (tmp_path / "sub.db").exists()


def test_settings_read_from_env():
    s = Settings.from_env({"SQL_MAX_ROWS": "50", "SQL_TIMEOUT_MS": "500", "LLM_PROVIDER": ""})
    assert (s.max_rows, s.timeout_ms, s.llm_provider) == (50, 500, "mock")
    assert Settings.from_env({}) == Settings()
