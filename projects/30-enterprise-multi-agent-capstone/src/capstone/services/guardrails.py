"""Three guardrail checkpoints (recap of 13): user input, tool output, final answer.

Rules are deliberately simple regexes so you can read every one. Real systems layer a classifier on top,
but keep rules like these as a cheap, explainable first line.
"""
from __future__ import annotations

import re

from capstone.domain.models import GuardVerdict

INJECTION = [
    (re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.I), "instruction override"),
    (re.compile(r"(reveal|print|show) (me )?(your |the )?system prompt", re.I), "system prompt extraction"),
    (re.compile(r"\byou are now\b|\bact as (an? )?(unfiltered|jailbroken)", re.I), "role hijack"),
    (re.compile(r"disable (the |all )?(guardrails|safety|filters)", re.I), "guardrail tampering"),
    (re.compile(r"send .{0,40}(customer|password|key|list).{0,40}(to|@)", re.I), "data exfiltration"),
]

PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
    (re.compile(r"\+?\d{1,3}[ -]?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b(sk|pk|ghp)[-_][A-Za-z0-9_-]{8,}\b"), "[SECRET]"),
]

CITATION = re.compile(r"\[\d+\]")


def redact(text: str) -> tuple[str, list[str]]:
    notes = []
    for pattern, label in PII:
        text, n = pattern.subn(label, text)
        if n:
            notes.append(f"redacted {n} {label}")
    return text, notes


def injection_reasons(text: str) -> list[str]:
    return [label for pattern, label in INJECTION if pattern.search(text)]


def check_input(question: str) -> GuardVerdict:
    """Block prompt injection; redact PII so it never reaches the LLM, tools or traces."""
    reasons = injection_reasons(question)
    if reasons:
        return GuardVerdict(False, question, tuple(f"blocked input: {r}" for r in reasons))
    clean, notes = redact(question)
    return GuardVerdict(True, clean, tuple(notes))


def check_tool_output(text: str) -> GuardVerdict:
    """Retrieved documents are untrusted. Text that tries to give orders is quarantined, not obeyed."""
    reasons = injection_reasons(text)
    return GuardVerdict(not reasons, text, tuple(f"quarantined tool output: {r}" for r in reasons))


def check_output(answer: str, needs_citation: bool) -> GuardVerdict:
    clean, notes = redact(answer)
    reasons = list(notes)
    if needs_citation and not CITATION.search(clean):
        clean += "\n(Note: no supporting source was found; treat this answer as unverified.)"
        reasons.append("uncited answer flagged")
    return GuardVerdict(True, clean, tuple(reasons))
