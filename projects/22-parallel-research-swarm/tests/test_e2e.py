"""End-to-end: the demo flow (plan -> parallel workers -> dedup -> cited report) as a learner runs it."""

import os
import subprocess
import sys
from pathlib import Path

from swarm.cli import main
from swarm.config import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_demo_script_runs_offline_and_prints_a_cited_report():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # force the offline mocks
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for expected in ("4 sub-questions: cost, lifespan, safety, savings", "FAILED slow-blog",
                     "# What should a homeowner know before buying a home battery?", "## Sources",
                     "corroborated by", "18 raw -> 16 after dedup", "+-- SWARM STATS"):
        assert expected in out


def test_cli_writes_the_report_file(tmp_path, capsys):
    out_file = tmp_path / "report.md"
    assert main(["--out", str(out_file)]) == 0
    report = out_file.read_text(encoding="utf-8")
    assert report.startswith("# What should a homeowner know") and report in capsys.readouterr().out


def test_settings_from_env():
    assert load_settings({}) == Settings()
    s = load_settings({"LLM_PROVIDER": "OPENAI", "SWARM_CONCURRENCY": "8", "FETCH_RETRIES": "0", "LLM_MODEL": ""})
    assert (s.llm_provider, s.llm_model, s.concurrency, s.fetch_retries, s.use_mock) == ("openai", None, 8, 0, False)
