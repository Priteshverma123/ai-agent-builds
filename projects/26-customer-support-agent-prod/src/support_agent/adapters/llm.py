"""LLM port + a deterministic, rule-based MockLLM.

The MockLLM behaves like a well-prompted model: it reads the whole transcript, decides on the next
tool call or the final answer, and explains its reasoning in ``thought`` so the trace can teach.
It never decides policy outcomes; it only reports what the tools returned.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from ..domain.models import LLMResponse, Message, ToolCall

ORDER_ID = re.compile(r"\bORD-\d{4}\b", re.IGNORECASE)
AMOUNT = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)|(\d+(?:\.\d{1,2})?)\s*(?:dollars|usd)\b", re.IGNORECASE)
HUMAN = re.compile(r"\b(human|real person|manager|supervisor|representative|live agent)\b", re.I)
ANGRY = re.compile(r"\b(ridiculous|unacceptable|third time|lawyer|scam|furious|worst)\b", re.I)
REFUND = re.compile(r"\b(refund|money back|return|reimburse|\d+ back)\w*", re.I)
SHIPPING = re.compile(r"\b(where is|track|tracking|shipping status|arrive|when will|delivery status|status of)\b", re.I)
QUESTION = re.compile(r"\b(how long|how do|how does|what is|what's|can i|do you|is there|policy|warranty|damaged)\b", re.I)


class LLM(Protocol):
    name: str

    def complete(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        ...


def classify_intent(text: str, has_order_id: bool) -> str | None:
    """Keyword intent detection, ordered by priority (safety first: humans and anger)."""
    if HUMAN.search(text):
        return "human"
    if ANGRY.search(text):
        return "frustrated"
    is_question = bool(QUESTION.search(text))
    if REFUND.search(text) and (has_order_id or not is_question):
        return "refund"
    if SHIPPING.search(text) and (has_order_id or not is_question):
        return "shipping"
    if is_question:
        return "policy"
    return None


def parse_amount(text: str) -> float | None:
    match = AMOUNT.search(text)
    return float(match.group(1) or match.group(2)) if match else None


class MockLLM:
    """Deterministic stand-in for a tool-calling model."""

    name = "mock"

    def __init__(self) -> None:
        self._calls = 0

    def complete(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        last_user = max(i for i, m in enumerate(messages) if m.role == "user")
        user_text = messages[last_user].content
        results = {m.tool_name: json.loads(m.content) for m in messages[last_user + 1:] if m.role == "tool"}
        order_id = self._find_order_id(system, messages[: last_user + 1])
        intent = classify_intent(user_text, ORDER_ID.search(user_text) is not None)
        if intent is None:  # e.g. "It's ORD-1001" -- carry the intent over from earlier turns
            for earlier in reversed(messages[:last_user]):
                if earlier.role == "user" and (intent := classify_intent(earlier.content, True)):
                    break
        if intent in ("human", "frustrated"):
            return self._escalate(intent, results)
        if intent == "policy":
            return self._policy(user_text, results)
        if intent in ("refund", "shipping"):
            if order_id is None:
                return LLMResponse(thought=f"Intent '{intent}' needs an order number; none in context.",
                                   text="I can help with that. What is your order number? It looks like ORD-1234.")
            return self._order_flow(intent, order_id, user_text, results)
        return LLMResponse(thought="No supported intent detected; offer the menu.",
                           text="I can help with order status, shipping, refunds and store policies. "
                                "What can I do for you?")

    # --- flows ----------------------------------------------------------------------------

    def _call(self, name: str, args: dict[str, Any], thought: str) -> LLMResponse:
        self._calls += 1
        return LLMResponse(thought=thought, tool_calls=[ToolCall(call_id=f"call_{self._calls}", name=name, args=args)])

    def _escalate(self, intent: str, results: dict[str, Any]) -> LLMResponse:
        if "escalate_to_human" not in results:
            reason = "customer asked for a human" if intent == "human" else "customer is frustrated"
            return self._call("escalate_to_human", {"reason": reason},
                              f"Intent '{intent}': hand off to a person instead of arguing.")
        ticket = results["escalate_to_human"]["ticket_id"]
        return LLMResponse(thought="Escalation ticket created; tell the customer what happens next.",
                           text=f"I'm sorry for the trouble. I've passed your conversation to a human agent "
                                f"(ticket {ticket}). They can see everything we discussed and will reply here shortly.")

    def _policy(self, question: str, results: dict[str, Any]) -> LLMResponse:
        if "search_policy" not in results:
            return self._call("search_policy", {"query": question}, "Policy question: retrieve before answering.")
        hits = results["search_policy"]["results"]
        if not hits:
            return LLMResponse(thought="Nothing relevant retrieved; do not guess.",
                               text="I couldn't find a policy that covers that. Would you like me to connect "
                                    "you with a human agent?")
        top = hits[0]
        return LLMResponse(thought=f"Answer only from the top chunk {top['chunk_id']} and cite it.",
                           text=f"{top['text']} [{top['chunk_id']}]")

    def _order_flow(self, intent: str, order_id: str, user_text: str, results: dict[str, Any]) -> LLMResponse:
        if "get_order" not in results:
            return self._call("get_order", {"order_id": order_id}, f"Intent '{intent}' on {order_id}: load the order first.")
        order = results["get_order"]
        if "error" in order:
            return LLMResponse(thought="Order lookup failed; ask the customer to double-check.",
                               text=f"I couldn't find order {order_id} on your account. Could you double-check the number?")
        if intent == "shipping":
            return self._shipping(order_id, results)
        return self._refund(order_id, user_text, results)

    def _shipping(self, order_id: str, results: dict[str, Any]) -> LLMResponse:
        if "check_shipping" not in results:
            return self._call("check_shipping", {"order_id": order_id}, "Order found; ask the carrier for status.")
        ship = results["check_shipping"]
        if ship["status"] == "not shipped yet":
            text = f"Order {order_id} hasn't shipped yet. You'll get a tracking number as soon as it leaves our warehouse."
        elif ship["status"] == "delivered":
            text = f"Order {order_id} was delivered on {ship['eta']} ({ship['last_event'].lower()})."
        else:
            text = (f"Order {order_id} is {ship['status']} with {ship['carrier']}. Last scan: {ship['last_event']}. "
                    f"Estimated delivery: {ship['eta']} [shipping.md#tracking]")
        return LLMResponse(thought="Summarise the carrier status for the customer.", text=text)

    def _refund(self, order_id: str, user_text: str, results: dict[str, Any]) -> LLMResponse:
        if "issue_refund" not in results:
            args: dict[str, Any] = {"order_id": order_id, "reason": user_text[:200]}
            amount = parse_amount(user_text)
            if amount is not None:
                args["amount"] = amount
            return self._call("issue_refund", args, "Request the refund; the policy engine decides the outcome.")
        r = results["issue_refund"]
        cite = f"[{r['policy_ref']}]"
        if r["status"] == "approved":
            text = (f"Done. I've refunded ${r['amount']:.2f} for {order_id} (refund {r['refund_id']}). "
                    f"It goes back to your original payment method within 5 to 7 business days {cite}")
        elif r["status"] == "pending_approval":
            text = (f"Your ${r['amount']:.2f} refund for {order_id} is above our automatic limit, so a specialist "
                    f"will review it (ticket {r['ticket_id']}). You'll hear back within one business day {cite}")
        else:
            text = (f"I'm sorry, I can't refund {order_id}. {r['reason']} {cite} "
                    f"If you'd like, I can connect you with a human agent.")
        return LLMResponse(thought=f"Policy said '{r['status']}'; explain it and cite {r['policy_ref']}.", text=text)

    @staticmethod
    def _find_order_id(system: str, messages: list[Message]) -> str | None:
        for message in reversed(messages):
            if message.role == "user" and (m := ORDER_ID.search(message.content)):
                return m.group(0).upper()
        m = re.search(r"Known order: (ORD-\d{4})", system)
        return m.group(1) if m else None
