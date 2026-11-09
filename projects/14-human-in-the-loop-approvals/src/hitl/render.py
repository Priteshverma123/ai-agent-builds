"""Plain-ASCII rendering for the trace, approval cards and the audit log."""

from __future__ import annotations

import textwrap

from .approvals import ApprovalRequest

WIDTH = 78
MARKS = {"propose": "[model]  ", "pause": "[PAUSE]  ", "approved": "[human+] ", "rejected": "[human-] ",
         "execute": "[tool]   ", "done": "[done]   "}


def box(title: str, lines: list[str], width: int = WIDTH) -> str:
    inner = width - 4
    out = [f"+-- {title} " + "-" * max(0, width - len(title) - 6) + "+"]
    if not lines:
        return out[0]
    for line in lines:
        for piece in textwrap.wrap(line, inner, subsequent_indent="    ") or [""]:
            out.append(f"| {piece:<{inner}} |")
    out.append("+" + "-" * (width - 2) + "+")
    return "\n".join(out)


def print_event(kind: str, title: str, lines: list[str]) -> None:
    print(f"{MARKS.get(kind, '[?]      ')}{title}")
    for line in lines:
        print(" " * 12 + line)


def approval_card(request: ApprovalRequest) -> str:
    risk = request.risk
    votes = sum(1 for d in request.decisions if d.approve)
    lines = [
        f"action      : {request.action.describe()}",
        f"risk        : {risk.level.value} ({risk.score}/100)",
        *[f"  - {reason}" for reason in risk.reasons],
        f"needs       : {risk.required_approvals} approver(s){', written reason' if risk.needs_reason else ''}"
        f"   [{votes}/{risk.required_approvals} so far]",
        f"requested by: {request.requested_by} (cannot approve own run)",
        f"fingerprint : {request.fingerprint}",
    ]
    return box(f"APPROVAL NEEDED  {request.id}  ({request.run_id})", lines)


def audit_table(entries: list[dict]) -> str:
    rows = [f"{'seq':>3}  {'event':<19} {'detail':<38} {'hash':<16}", "-" * WIDTH]
    for e in entries:
        data = e["data"]
        detail = (data.get("approver") or data.get("action", {}).get("tool") or data.get("request")
                  or data.get("status") or data.get("task", ""))
        if e["event"] == "executed":
            detail = str(data.get("result", ""))
        rows.append(f"{e['seq']:>3}  {e['event']:<19} {str(detail)[:38]:<38} {e['hash']}")
    return "\n".join(rows)
