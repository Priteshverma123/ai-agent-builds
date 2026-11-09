"""End-to-end: the demo flow (CLI -> agent -> TracedLLM/TracedTools -> JSONL -> viewers) on the simulated clock."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tracekit.cli import main
from tracekit.config import Settings
from tracekit.exporters import group_traces, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = ("LLM_PROVIDER", "LLM_MODEL", "TRACE_OUT_DIR", "TRACE_QUESTIONS", "TRACE_REAL_CLOCK",
            "AGENT_MAX_STEPS", "AGENT_TOOL_RETRIES")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_demo_traces_every_question_and_writes_both_viewers(tmp_path, capsys):
    main(["--out", str(tmp_path)])
    out = capsys.readouterr().out
    questions = [q for q in (ROOT / "examples" / "questions.txt").read_text(encoding="utf-8").splitlines() if q]
    assert out.count("Q: ") == len(questions)
    assert "exception: TimeoutError search backend did not answer within 1500 ms" in out
    assert "slowest: tool search (1500 ms)" in out
    spans = read_jsonl(tmp_path / "trace.jsonl")
    assert len(group_traces(spans)) == len(questions)
    assert f"{len(spans)} spans exported" in out
    assert (tmp_path / "trace.html").read_text(encoding="utf-8").startswith("<!doctype html>")


def test_view_mode_rerenders_an_existing_trace(tmp_path, capsys):
    main(["--out", str(tmp_path)])
    first = capsys.readouterr().out
    main(["--view", str(tmp_path / "trace.jsonl")])
    second = capsys.readouterr().out
    assert "Q: " not in second
    assert first.split("TRACE", 1)[1] == second.split("TRACE", 1)[1]  # same waterfall, from the export alone


def test_demo_script_subprocess_respects_out_dir_env(tmp_path):
    env = {**os.environ, "LLM_PROVIDER": "mock", "TRACE_OUT_DIR": str(tmp_path)}
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "trace.jsonl").exists() and "spans exported" in proc.stdout


def test_settings_read_from_env():
    s = Settings.from_env({"TRACE_REAL_CLOCK": "yes", "AGENT_TOOL_RETRIES": "0"})
    assert s.real_clock is True and s.tool_retries == 0
    assert Settings.from_env({}) == Settings()
