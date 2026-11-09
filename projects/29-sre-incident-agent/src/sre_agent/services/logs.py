"""Turn thousands of log lines into a handful of error signatures.

'db pool timeout after 5000ms (waiting=37)' and '... (waiting=52)' are the same problem. Replacing numbers
with <n> groups them, so the agent (and the human) sees 3 patterns instead of 300 lines.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sre_agent.domain.models import ErrorSignature, LogEvent

_NUMBER = re.compile(r"\d+(\.\d+)?")


def template(message: str) -> str:
    return _NUMBER.sub("<n>", message)


def signatures(events: list[LogEvent], top: int = 5) -> list[ErrorSignature]:
    """Group WARN/ERROR events by (service, template), most frequent first."""
    groups: dict[tuple[str, str], list[LogEvent]] = defaultdict(list)
    for e in events:
        if e.level in ("WARN", "ERROR"):
            groups[(e.service, template(e.message))].append(e)
    sigs = [ErrorSignature(svc, tpl, len(evts), min(e.ts for e in evts)) for (svc, tpl), evts in groups.items()]
    return sorted(sigs, key=lambda s: (-s.count, s.first_seen))[:top]


def keywords(text: str) -> set[str]:
    """Lower-case words of 3+ letters, minus filler. Used to match error text against change descriptions."""
    stop = {"the", "and", "for", "from", "after", "with", "per", "call", "failed", "enable", "raise", "size"}
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in stop}
