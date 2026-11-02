"""End-to-end: the demo flow (cli -> VectorIndex.from_folder -> answer() -> MockLLM -> citations) and config."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from rag.cli import main
from rag.config import EXAMPLES_DIR, Settings
from rag.llm import MockLLM, make_llm

PROJECT = Path(__file__).resolve().parents[1]
SETTINGS_ENV = ("LLM_PROVIDER", "LLM_MODEL", "RAG_DOCS_DIR", "RAG_TOP_K", "RAG_CHUNK_WORDS", "RAG_MIN_SCORE")


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_demo_indexes_retrieves_and_cites(capsys):
    main([])
    out = capsys.readouterr().out
    assert "Indexed 4 documents -> 12 chunks -> 118 distinct terms" in out
    assert "shipping.md#1" in out
    assert "International delivery takes 7 to 12 business days" in out
    assert "cites" in out
    assert "no chunk above the similarity floor -> skip the LLM entirely" in out
    assert "I don't know -- nothing in the documents matches that question." in out
    assert "WARNING" not in out


def test_env_settings_change_retrieval(monkeypatch, capsys):
    monkeypatch.setenv("RAG_MIN_SCORE", "0.99")  # nothing is that similar -> the question is refused
    main(["Do you ship to Canada?"])
    assert "skip the LLM entirely" in capsys.readouterr().out


def test_custom_docs_folder(tmp_path, capsys):
    (tmp_path / "pets.md").write_text("# Pets\n\nOur office dog is called Biscuit and loves walks.", encoding="utf-8")
    main(["--docs", str(tmp_path), "What is the office dog called?"])
    out = capsys.readouterr().out
    assert "Indexed 1 documents" in out
    assert "Biscuit" in out and "pets.md#0" in out


def test_settings_defaults_and_validation(monkeypatch):
    settings = Settings.from_env()
    assert settings == Settings(
        llm_provider="mock", llm_model=None, docs_dir=EXAMPLES_DIR / "docs", top_k=3, chunk_words=40, min_score=0.1
    )
    assert isinstance(make_llm(settings), MockLLM)
    monkeypatch.setenv("RAG_MIN_SCORE", "-1")
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
    assert "Indexed 4 documents" in result.stdout
