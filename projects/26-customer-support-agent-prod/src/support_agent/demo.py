"""Terminal demo: real HTTP calls (via TestClient) to the FastAPI app, each turn rendered from its trace."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from fastapi.testclient import TestClient

from .api import create_app
from .config import Settings
from .evals import DEMO_TODAY

WIDTH = 92
SCENARIOS: list[tuple[str, str, list[str]]] = [
    ("Shipping status", "C-100", ["Where is my order ORD-1002?"]),
    ("Refund across two turns (state)", "C-100", ["I want a refund", "It's ORD-1001"]),
    ("Big refund -> human approval", "C-200", ["I want a refund for my laptop, order ORD-2001"]),
    ("Policy question (RAG + citation)", "C-100", ["How long do I have to return something?"]),
    ("Angry customer -> escalation", "C-300", ["This is the third time I'm asking about ORD-3002, this is ridiculous"]),
]


def _row(label: str, text: str) -> list[str]:
    body = textwrap.wrap(text, WIDTH - 12) or [""]
    return [f"| {label:<7} {body[0]:<{WIDTH - 12}} |"] + [f"| {'':<7} {line:<{WIDTH - 12}} |" for line in body[1:]]


def render_turn(user: str, chat: dict[str, Any], trace: dict[str, Any]) -> str:
    head = f"+-- trace {trace['trace_id']} ({trace['total_ms']:.1f} ms) "
    lines = [head + "-" * (WIDTH - len(head) - 1) + "+"]
    lines += _row("USER", user)
    for span in trace["spans"]:
        attrs = span["attrs"]
        if span["name"] == "llm.complete" and attrs.get("thought"):
            lines += _row("THINK", attrs["thought"])
        elif span["name"].startswith("tool."):
            status = "ok" if attrs.get("ok") else "FAIL"
            lines += _row("TOOL", f"{span['name'][5:]}({json.dumps(attrs['args'])}) -> {status}: {attrs['summary']}")
        elif span["name"] == "guard.citations" and attrs.get("dropped"):
            lines += _row("GUARD", f"dropped invented citations {attrs['dropped']}")
    lines += _row("REPLY", chat["reply"])
    for c in chat["citations"]:
        lines += _row("CITE", f"{c['chunk_id']}  ({c['title']})")
    if chat["ticket_id"]:
        lines += _row("TICKET", f"{chat['ticket_id']}  escalated={chat['escalated']}")
    lines.append("+" + "-" * (WIDTH - 2) + "+")
    return "\n".join(lines)


def main() -> None:
    client = TestClient(create_app(Settings(today=DEMO_TODAY, log_level="WARNING")))
    health = client.get("/health").json()
    print(f"GET /health -> {health}\n")
    for title, customer, turns in SCENARIOS:
        print(f"=== {title}  (customer {customer}) ===")
        conversation_id = None
        for text in turns:
            chat = client.post("/chat", json={"customer_id": customer, "message": text,
                                              "conversation_id": conversation_id}).json()
            conversation_id = chat["conversation_id"]
            trace = client.get(f"/traces/{chat['trace_id']}").json()
            print(render_turn(text, chat, trace))
        print()
    print("=== Human queue ===")
    for t in client.get("/queue", params={"status": "open"}).json():
        print(f"  {t['ticket_id']}  {t['kind']:<16} {t['customer_id']}  {t['reason'][:50]}")
    ticket = next(t for t in client.get("/queue").json() if t["kind"] == "refund_approval")
    done = client.post(f"/queue/{ticket['ticket_id']}/resolve", json={"approve": True, "agent": "maria"}).json()
    print(f"\nPOST /queue/{ticket['ticket_id']}/resolve -> {done['status']} by {done['resolved_by']}, "
          f"refund {done['payload']['refund_id']} for ${done['payload']['amount']:.2f}")


if __name__ == "__main__":
    main()
