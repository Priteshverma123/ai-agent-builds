"""Input and output guards: the checks at the two doors of the agent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .detectors import detect

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "api_token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    "password": re.compile(r"(?i)\bpassword\s*[:=]\s*\S+"),
}


@dataclass
class GuardResult:
    ok: bool
    text: str
    notes: list[str] = field(default_factory=list)


def check_input(text: str, max_chars: int = 4000) -> GuardResult:
    """Refuse oversized input and direct jailbreak attempts before they reach the model."""
    if len(text) > max_chars:
        return GuardResult(False, text, [f"input is {len(text)} chars (limit {max_chars})"])
    verdict = detect(text)
    if verdict.flagged:
        return GuardResult(False, text, [f"jailbreak score {verdict.score:.2f} ({', '.join(verdict.rules)})"])
    return GuardResult(True, text)


def redact_secrets(text: str) -> tuple[str, list[str]]:
    found = []
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            found.append(name)
            text = pattern.sub(f"[REDACTED:{name}]", text)
    return text, found


def check_output(text: str, canary: str) -> GuardResult:
    """Block system-prompt leaks (canary token) and redact anything that looks like a secret."""
    if canary and canary in text:
        return GuardResult(False, "I can't share that.", ["canary token found: the system prompt was leaking"])
    clean, found = redact_secrets(text)
    return GuardResult(True, clean, [f"redacted {name}" for name in found])
