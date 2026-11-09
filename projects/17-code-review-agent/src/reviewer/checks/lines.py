"""Line checks: regexes over *added* lines only. Fast, language-agnostic, a little noisy."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..context import ReviewContext
from ..findings import Finding, Severity


@dataclass(frozen=True)
class LineRule:
    rule: str
    severity: Severity
    confidence: float
    pattern: re.Pattern[str]
    message: str
    suggestion: str
    python_only: bool = False


LINE_RULES = (
    LineRule("hardcoded-secret", Severity.CRITICAL, 0.95,
             re.compile(r"\b(sk-(live|test)-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,})\b"
                        r"|(?i:\b(api_?key|secret|password|token)\s*=\s*[\"'][^\"']{12,}[\"'])"),
             "Credential committed to source control.",
             "Load it from the environment or a secret manager, and rotate the leaked key."),
    LineRule("debug-print", Severity.LOW, 0.6, re.compile(r"^\s*(print\(|breakpoint\(\)|import pdb)"),
             "Debug output left in the change.", "Use the logging module or remove it.", python_only=True),
    LineRule("todo-marker", Severity.LOW, 0.5, re.compile(r"#\s*(TODO|FIXME|XXX)\b"),
             "Unfinished work marker added.", "Open a ticket and link it, or finish the work."),
    LineRule("tls-verify-off", Severity.HIGH, 0.9, re.compile(r"verify\s*=\s*False"),
             "TLS certificate verification disabled.", "Remove verify=False; fix the CA bundle instead."),
)


def check_lines(ctx: ReviewContext) -> list[Finding]:
    findings = []
    for f in ctx.files:
        for line_no, text in f.added.items():
            for rule in LINE_RULES:
                if rule.python_only and not f.is_python:
                    continue
                if rule.pattern.search(text):
                    findings.append(Finding(rule.rule, rule.severity, rule.confidence, f.path, line_no,
                                            rule.message, rule.suggestion))
    return findings
