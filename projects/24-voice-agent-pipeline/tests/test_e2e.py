"""End-to-end: the demo flow (three-turn call, barge-in, filler, latency table) as a learner runs it."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from voice.cli import main
from voice.config import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_demo_script_runs_the_whole_call_on_the_virtual_clock():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # force the offline mock
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for expected in ("clock=virtual", "voice-to-voice 800 ms", "stopped after 40 ms", 'filler "One moment."',
                     "PASS via filler", "Monday to [interrupted]",
                     "same call in batch mode -> first turn heard after 2160 ms (vs 800 ms in streaming mode)"):
        assert expected in out


def test_cli_batch_mode_and_tight_budget_from_settings(monkeypatch, capsys):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LATENCY_BUDGET_MS", "850")
    assert main(["--mode", "batch"]) == 0
    out = capsys.readouterr().out
    assert "budget: total 850 ms" in out and "FAIL (total 2160 ms > 850 ms)" in out
    assert "same call in streaming mode" in out


def test_settings_from_env():
    assert load_settings({}) == Settings()
    s = load_settings({"VOICE_MODE": "Batch", "FILLER_AFTER_MS": "off", "LLM_PROVIDER": "openai"})
    assert (s.mode, s.filler_after_ms, s.use_mock) == ("batch", None, False)
    with pytest.raises(ValueError):
        load_settings({"VOICE_MODE": "telepathy"})
