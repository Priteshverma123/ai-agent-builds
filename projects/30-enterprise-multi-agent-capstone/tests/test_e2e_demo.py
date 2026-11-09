"""End-to-end: `python demo.py` and `python run_evals.py` exactly as learners run them, plus settings."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from capstone.config import Settings
from capstone.container import build

ROOT = Path(__file__).resolve().parents[1]


def run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True, timeout=60)


def test_demo_runs_mcp_discovery_five_requests_and_evals() -> None:
    proc = run("demo.py")
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    assert "initialize  -> server=" in out and "tools/list  -> search_docs" in out
    for n in range(1, 6):
        assert f"| Q{n}. " in out
    assert "plan  steps=research > analyst > writer" in out
    assert "$540 (180 * 3) [1]" in out                     # Q1: RAG + calculator + citation
    assert "I opened ticket" in out                        # Q2: ops agent
    assert "[quarantined]" in out                          # Q3: poisoned vendor doc
    assert "tickets in the Ops desk:" in out
    assert "11/11 passed" in out


def test_run_evals_gate_passes() -> None:
    proc = run("run_evals.py")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "11/11 passed (100%)" in proc.stdout


def test_settings_are_parsed_and_wired_into_build(tmp_path: Path) -> None:
    s = Settings.from_env({"LLM_PROVIDER": "OpenAI", "LLM_MODEL": "", "DOCS_DIR": "d", "EVALS_FILE": "e.json",
                           "TRACE_FILE": "t.jsonl", "ORCHESTRATOR_MAX_STEPS": "2", "HOST": "0.0.0.0",
                           "PORT": "9000", "OPENAI_API_KEY": "k"})
    assert (s.llm_provider, s.model, s.openai_api_key) == ("openai", "gpt-4o-mini", "k")
    assert (s.docs_dir, s.evals_path, s.trace_file) == (Path("d"), Path("e.json"), Path("t.jsonl"))
    assert (s.max_steps, s.host, s.port) == (2, "0.0.0.0", 9000)
    assert Settings.from_env({}) == Settings()
    system = build(settings=Settings(max_steps=2))
    assert system.orchestrator.max_steps == 2
