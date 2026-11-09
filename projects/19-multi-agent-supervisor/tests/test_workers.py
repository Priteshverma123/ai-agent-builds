"""Each worker on its own: retrieval, prompting and review."""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from supervisor.messages import CodeArtifact, Decision, Example, ResearchNotes, Review
from supervisor.state import SharedState
from supervisor.workers import Coder, KnowledgeBase
from supervisor.workers.researcher import extract_notes
from supervisor.workers.reviewer import Reviewer, run_examples

KB = Path(__file__).resolve().parents[1] / "examples" / "kb"
EXAMPLES = [Example(given="Hello, World!", expected="hello-world")]


def test_knowledge_base_finds_the_right_document():
    kb = KnowledgeBase(KB)
    assert kb.search("URL slug style guide")[0].slug == "url-style-guide"
    assert kb.search("slug examples acceptance tests")[0].slug == "slug-examples"
    assert kb.search("quantum chromodynamics") == []


def test_extracts_rules_and_examples():
    kb = KnowledgeBase(KB)
    notes = extract_notes(kb.search("slug examples")[0])
    assert notes.examples[0] == Example(given="Hello, World!", expected="hello-world")
    assert len(extract_notes(kb.search("style guide")[0]).rules) == 5


def test_research_merge_dedupes():
    a = ResearchNotes(rules=["r1", "r2"], examples=EXAMPLES, sources=["a"])
    b = ResearchNotes(rules=["r2", "r3"], examples=EXAMPLES, sources=["b"])
    merged = a.merge(b)
    assert merged.rules == ["r1", "r2", "r3"] and len(merged.examples) == 1 and merged.sources == ["a", "b"]


def test_reviewer_catches_wrong_output_and_missing_docstring():
    checked, failures = run_examples("def slugify(t):\n    return t.lower()\n", EXAMPLES)
    assert checked == 2 and len(failures) == 2
    assert "expected 'hello-world'" in failures[0] and "docstring" in failures[1]


def test_reviewer_blocks_dangerous_imports():
    _, failures = run_examples("import os\ndef slugify(t):\n    'x'\n    return t\n", EXAMPLES)
    assert "not allowed" in failures[0]


def test_reviewer_only_approves_the_version_it_ran():
    state = SharedState("g", research=ResearchNotes(examples=EXAMPLES),
                        code=CodeArtifact(version=3, source='def slugify(t):\n    """ok"""\n    return "hello-world"\n'))
    result = asyncio.run(Reviewer().run("review", state))
    assert result.review == Review(version=3, passed=True, failures=[], checked=2)


def test_coder_prompt_carries_rules_examples_and_failures():
    state = SharedState("g", research=ResearchNotes(rules=["Lowercase everything."], examples=EXAMPLES),
                        code=CodeArtifact(version=1, source="def slugify(t): ..."),
                        reviews=[Review(version=1, passed=False, failures=["boom"], checked=1)])
    prompt = Coder.build_prompt("fix it", state)
    assert "Lowercase everything." in prompt and "'Hello, World!'" in prompt
    assert "REVIEW FEEDBACK:\n- boom" in prompt


def test_decision_must_finish_or_delegate():
    with pytest.raises(ValidationError):
        Decision()
    with pytest.raises(ValidationError):
        Decision(finish=True, delegations=[{"worker": "coder", "instruction": "write"}])


def test_reviewer_never_approves_without_examples():
    state = SharedState("g", research=ResearchNotes(rules=["r"]),
                        code=CodeArtifact(version=1, source='def slugify(t):\n    """ok"""\n    return t\n'))
    result = asyncio.run(Reviewer().run("review", state))
    assert result.review.passed is False and "no acceptance examples" in result.summary
