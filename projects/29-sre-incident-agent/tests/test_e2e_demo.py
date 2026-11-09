"""End-to-end: `python demo.py` exactly as learners run it, plus the settings that drive it."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sre_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_demo_triages_mitigates_with_approval_and_writes_postmortem(tmp_path: Path) -> None:
    env = {**os.environ, "SRE_OUT_DIR": str(tmp_path), "LLM_PROVIDER": "mock"}
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=60)
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert "ACT     detect_anomalies()" in out
    assert "DENIED  by on-call (alex)" in out                      # the human said no to the restart
    assert "rollback_deploy(" in out and "approved by on-call (alex)" in out
    assert "within SLO" in out and "FINISH  status=mitigated" in out
    assert "blameless lint: PASS (0 issues)" in out
    postmortem = (tmp_path / "postmortem.md").read_text(encoding="utf-8")
    assert "ALERT-5521" in postmortem


def test_settings_read_every_documented_variable() -> None:
    s = Settings.from_env({"LLM_PROVIDER": "Anthropic", "LLM_MODEL": "", "ANTHROPIC_API_KEY": "a",
                           "OPENAI_API_KEY": "o", "SRE_EXAMPLES_DIR": "ex", "SRE_OUT_DIR": "o",
                           "SRE_MAX_STEPS": "4"})
    assert (s.llm_provider, s.model, s.anthropic_api_key, s.openai_api_key) == (
        "anthropic", "claude-sonnet-4-5", "a", "o")
    assert (s.examples_dir, s.out_dir, s.max_steps) == (Path("ex"), Path("o"), 4)
    assert Settings.from_env({}) == Settings()
