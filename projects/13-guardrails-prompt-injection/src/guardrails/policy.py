"""Tool-call policy: the layer that still holds when the detector is fooled.

Detection is probabilistic; policy is deterministic. Before any tool runs we ask three questions:

1. Is this tool on the session's allow-list at all?
2. Are the arguments inside their allow-list (e.g. email only to our own domains)?
3. Taint rule: has untrusted content entered the context, and is this a *sensitive* tool the user
   never asked for? Then the request most likely came from the content, not the user. Deny.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Words in the user's own request that show they really wanted a sensitive tool.
INTENT_WORDS: dict[str, tuple[str, ...]] = {
    "send_email": ("email", "e-mail", "mail", "send"),
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


ALLOW = Decision(True, "allowed")


@dataclass(frozen=True)
class ToolPolicy:
    allowed_tools: frozenset[str]
    email_domains: frozenset[str] = frozenset()
    sensitive_tools: frozenset[str] = field(default_factory=lambda: frozenset({"send_email"}))

    def check(self, tool: str, args: dict[str, Any], *, tainted: bool, user_request: str) -> Decision:
        if tool not in self.allowed_tools:
            return Decision(False, f"tool '{tool}' is not on this session's allow-list")
        if tool == "send_email":
            domain = str(args.get("to", "")).rpartition("@")[2].lower()
            if domain not in self.email_domains:
                return Decision(False, f"recipient domain '{domain}' is not on the email allow-list")
        if tainted and tool in self.sensitive_tools and not user_asked_for(tool, user_request):
            return Decision(False, f"'{tool}' requested after reading untrusted content; the user never asked for it")
        return ALLOW


def user_asked_for(tool: str, user_request: str) -> bool:
    words = INTENT_WORDS.get(tool, (tool,))
    lowered = user_request.lower()
    return any(w in lowered for w in words)
