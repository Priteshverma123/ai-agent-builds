"""End-to-end: the exact command learners run (`python demo.py`) tells the whole crash/resume story."""

import os
import subprocess
import sys
from pathlib import Path

from durable.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_demo_kills_a_worker_and_resumes_with_exactly_once_effects(tmp_path):
    env = {**os.environ, "DURABLE_DATA_DIR": str(tmp_path / "data"), "LLM_PROVIDER": "mock"}
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True,
                          text=True, timeout=60)
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    for act in ("ACT 1", "ACT 2", "ACT 3", "ACT 4"):
        assert act in out
    assert "worker-1 exited with code 137" in out
    assert "[worker-2] REPLAY | summarize" in out
    assert "no second email" in out
    assert "LLM calls made by worker-2: 0" in out
    assert "exactly-once effects: YES" in out
    assert (tmp_path / "data" / "journal.db").exists()  # DURABLE_DATA_DIR was honoured


def test_settings_read_every_documented_variable():
    s = Settings.from_env({"LLM_PROVIDER": " Anthropic ", "LLM_MODEL": "m", "DURABLE_DATA_DIR": "/x",
                           "DURABLE_LEASE_S": "2.5"})
    assert (s.llm_provider, s.llm_model, s.data_dir, s.lease_s) == ("anthropic", "m", Path("/x"), 2.5)
    assert Settings.from_env({}) == Settings()
