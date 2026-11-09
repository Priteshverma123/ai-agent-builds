"""End-to-end: the scripted story (CLI -> agent -> approvals -> executor -> audit) and the manual subcommands."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hitl.audit import AuditLog
from hitl.cli import main
from hitl.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = ("LLM_PROVIDER", "LLM_MODEL", "HITL_STATE_DIR", "AGENT_MAX_STEPS", "RISK_COMPANY_DOMAINS",
            "RISK_LARGE_AMOUNT", "RISK_VERY_LARGE_AMOUNT")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_full_story(tmp_path, capsys):
    main(["--state", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[refused] sam -> sam started this run and cannot approve it" in out
    assert "refund rf_0001 of 1249.00 issued for A-1042" in out
    assert "[human-] req-4 rejected by bob" in out
    assert "close_account: rejected." in out
    assert "verify(): audit chain intact" in out
    assert "verify() after someone edits bob's rejection: entry 19 was modified" in out
    assert AuditLog(tmp_path / "audit.jsonl").verify() == (True, "audit chain intact")


def test_manual_subcommands_pause_approve_resume(tmp_path, capsys):
    state = ["--state", str(tmp_path)]
    main([*state, "start", "--by", "sam"])
    run_id = next((tmp_path / "runs").glob("*.json")).stem
    main([*state, "pending"])
    assert "1 run(s) waiting" in capsys.readouterr().out
    main([*state, "approve", run_id, "--by", "alice", "--comment", "ledger checked"])
    assert "req-2 is now approved" in capsys.readouterr().out
    main([*state, "resume", run_id])
    assert "refund rf_0001" in capsys.readouterr().out


def test_demo_script_respects_state_dir_env(tmp_path):
    """demo.py wiring + HITL_STATE_DIR, using the cheap `pending` subcommand (the story is tested above)."""
    env = {**os.environ, "LLM_PROVIDER": "mock", "HITL_STATE_DIR": str(tmp_path)}
    proc = subprocess.run([sys.executable, "demo.py", "pending"], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "0 run(s) waiting" in proc.stdout
    assert (tmp_path / "runs").is_dir()


def test_settings_read_from_env():
    s = Settings.from_env({"RISK_COMPANY_DOMAINS": "a.example, B.example", "RISK_LARGE_AMOUNT": "50"})
    assert s.company_domains == ("a.example", "b.example") and s.large_amount == 50.0
    assert Settings.from_env({}) == Settings()
