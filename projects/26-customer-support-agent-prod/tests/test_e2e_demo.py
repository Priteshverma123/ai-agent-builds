"""End-to-end: the documented demo command and the CLI entry point, exactly as learners run them."""

import subprocess
import sys
from pathlib import Path

from support_agent.cli import main
from support_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_run_py_demo_walks_all_five_scenarios_over_http():
    proc = subprocess.run([sys.executable, "run.py", "demo"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert "GET /health -> {'status': 'ok'" in out
    for title in ("Shipping status", "Refund across two turns", "Big refund -> human approval",
                  "Policy question (RAG + citation)", "Angry customer -> escalation"):
        assert f"=== {title}" in out
    assert "TOOL    issue_refund" in out and "CITE" in out
    assert "=== Human queue ===" in out
    assert "-> approved by maria" in out


def test_cli_evals_gate_passes(capsys):
    assert main(["evals"]) == 0
    assert "passed (100%)" in capsys.readouterr().out


def test_settings_read_every_documented_variable(monkeypatch):
    env = {"LLM_PROVIDER": "OpenAI", "LLM_MODEL": "m", "REFUND_WINDOW_DAYS": "14",
           "REFUND_AUTO_APPROVE_LIMIT": "50", "MAX_AGENT_STEPS": "3", "SUPPORT_API_KEY": "k",
           "SUPPORT_TODAY": "2026-01-02", "SUPPORT_DATA_DIR": "/d", "TRACE_CAPACITY": "7", "LOG_LEVEL": "DEBUG"}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    s = Settings.from_env()
    assert (s.llm_provider, s.llm_model, s.refund_window_days, s.refund_auto_approve_limit, s.max_agent_steps,
            s.api_key, str(s.today), s.data_dir, s.trace_capacity, s.log_level) == (
        "openai", "m", 14, 50.0, 3, "k", "2026-01-02", Path("/d"), 7, "DEBUG")
