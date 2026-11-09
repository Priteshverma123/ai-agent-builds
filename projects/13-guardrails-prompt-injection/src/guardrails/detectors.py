"""Prompt-injection detection.

Three ideas, in order:

1. **Normalise** before matching. Attackers hide text with zero-width characters, full-width
   letters (NFKC folds them back to ASCII) and base64. Match the text the model would "see".
2. **Score with weighted rules** and combine them with a noisy-OR: each rule is independent
   evidence, so two weak signals together can cross the threshold while one weak signal cannot.
3. **Sanitise, don't just reject.** A web page with one poisoned paragraph is still useful; drop
   the sentences (or hidden comments) that fail and keep the rest.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field

THRESHOLD = 0.5
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


@dataclass(frozen=True)
class Rule:
    name: str
    weight: float
    pattern: re.Pattern[str]
    why: str


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


RULES: tuple[Rule, ...] = (
    Rule("override", 0.9, _rx(
        r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}?\b(previous|prior|above|earlier|all|any|your|the)\b"
        r"[^.\n]{0,25}?\b(instructions?|rules|prompts?|directions|guidelines)\b"),
        "tries to cancel the agent's real instructions"),
    Rule("fake_authority", 0.7, _rx(
        r"(^|\n)\s*(system|assistant|developer)\s*:|<\s*/?\s*(system|im_start|im_end|instructions?)\b[^>]*>"
        r"|\[\s*/?\s*(system|inst)\s*\]"),
        "pretends to be a system or developer message"),
    Rule("role_hijack", 0.6, _rx(
        r"\byou are (now|no longer)\b|\bpretend (to be|you are)\b|\bdeveloper mode\b|\bjailbreak\b|\bdo anything now\b"),
        "tries to change who the agent is"),
    Rule("new_task", 0.45, _rx(r"\b(new|updated|real|actual|important)\s+(instructions?|task|objective|orders)\b\s*[:!-]"),
         "announces replacement instructions"),
    Rule("exfiltration", 0.45, _rx(
        r"\b(send|e-?mail|forward|upload|post|transmit)\b[^.\n]{0,80}?[\w.+-]+@[\w-]+(\.[\w-]+)+"),
        "asks to ship something to an address"),
    Rule("sensitive_object", 0.35, _rx(
        r"\b(conversation|chat) history\b|\buser'?s? (notes|data|files|messages|emails)\b|\bapi[ _-]?keys?\b"
        r"|\bpasswords?\b|\bcredentials\b"),
        "mentions data an attacker would want"),
    Rule("secret_probe", 0.7, _rx(
        r"\b(reveal|print|show|repeat|output|leak|tell me)\b[^.\n]{0,40}?\b(system prompt|hidden instructions"
        r"|api[ _-]?keys?|passwords?|secrets?|credentials)\b"),
        "fishes for secrets or the system prompt"),
    Rule("tool_command", 0.7, _rx(
        r"\b(call|invoke|use|run|execute)\s+(the\s+)?[`'\"]?(send_email|delete_\w+|transfer_\w+|shell|exec|run_code)\b"),
        "orders the agent to use a dangerous tool"),
    Rule("markdown_exfil", 0.7, _rx(r"!\[[^\]]*\]\(\s*https?://[^)\s]*\?[^)\s]*=[^)\s]*\)"),
         "image link that would leak data through its URL"),
)

HIDDEN_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Signal:
    rule: str
    weight: float
    excerpt: str
    why: str


@dataclass
class Verdict:
    score: float
    signals: list[Signal] = field(default_factory=list)
    threshold: float = THRESHOLD

    @property
    def flagged(self) -> bool:
        return self.score >= self.threshold

    @property
    def rules(self) -> list[str]:
        return sorted({s.rule for s in self.signals})


def normalise(text: str) -> str:
    """Fold look-alike characters, drop invisible ones, squeeze spaces (keep newlines)."""
    folded = unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)
    return re.sub(r"[ \t]+", " ", folded)


def _decoded_blobs(text: str) -> list[str]:
    """Decode base64-looking runs that turn out to be readable ASCII."""
    out = []
    for blob in BASE64_BLOB.findall(text):
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True).decode("ascii")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if decoded.isprintable() and " " in decoded:
            out.append(decoded)
    return out


def _match_rules(text: str) -> list[Signal]:
    signals = []
    for rule in RULES:
        found = rule.pattern.search(text)
        if found:
            signals.append(Signal(rule.name, rule.weight, found.group(0).strip()[:60], rule.why))
    return signals


def noisy_or(weights: list[float]) -> float:
    """P(at least one piece of evidence is real) if each weight is an independent probability."""
    miss = 1.0
    for w in weights:
        miss *= 1.0 - w
    return round(1.0 - miss, 3)


def detect(text: str, threshold: float = THRESHOLD) -> Verdict:
    """Score `text` for prompt-injection. Higher = more likely an attack."""
    clean = normalise(text)
    signals = _match_rules(clean)
    if any(ord(ch) in ZERO_WIDTH for ch in text):
        signals.append(Signal("invisible_chars", 0.3, "zero-width characters", "hides words from humans"))
    for decoded in _decoded_blobs(clean):
        inner = _match_rules(decoded)
        if inner:
            signals.append(Signal("encoded_payload", 0.3, decoded[:60], "instructions smuggled as base64"))
            signals.extend(inner)
    # One signal per rule: repeating the same trick does not make it more convincing evidence.
    best: dict[str, Signal] = {}
    for s in signals:
        best.setdefault(s.rule, s)
    unique = list(best.values())
    return Verdict(noisy_or([s.weight for s in unique]), unique, threshold)


@dataclass
class Sanitised:
    text: str
    removed: list[str]
    verdict: Verdict


def sanitise(text: str, threshold: float = THRESHOLD) -> Sanitised:
    """Remove flagged hidden comments and sentences; return what is left plus what was cut."""
    removed: list[str] = []

    def drop_comment(match: re.Match[str]) -> str:
        if detect(match.group(0), threshold).flagged:
            removed.append(match.group(0))
            return ""
        return match.group(0)

    without_comments = HIDDEN_COMMENT.sub(drop_comment, text)
    kept_lines = []
    for line in without_comments.splitlines():
        kept = []
        for sentence in SENTENCE_SPLIT.split(line):
            if sentence.strip() and detect(sentence, threshold).flagged:
                removed.append(sentence.strip())
            else:
                kept.append(sentence)
        kept_lines.append(" ".join(kept))
    return Sanitised("\n".join(kept_lines).strip(), removed, detect(text, threshold))
