"""Specialist agents. Each one is small and good at exactly one job.

They are deterministic here (a dictionary lookup each) because the subject of this
project is the *router*. In a real system each specialist would be its own agent with
its own prompt, tools and permissions, and that separation is the main point of routing.
"""

from __future__ import annotations

import re
from typing import Protocol


class Specialist(Protocol):
    name: str
    description: str

    def handle(self, message: str) -> str: ...


INVOICES = {
    "INV-1042": {"amount": "49.00 USD", "date": "2026-10-02", "duplicate": True},
    "INV-0977": {"amount": "49.00 USD", "date": "2026-09-02", "duplicate": False},
}


class BillingAgent:
    name = "billing"
    description = "Invoices, duplicate charges, refunds, payment methods."

    def handle(self, message: str) -> str:
        match = re.search(r"\bINV-\d+\b", message, re.IGNORECASE)
        if match and (invoice := INVOICES.get(match.group(0).upper())):
            if invoice["duplicate"]:
                return (f"{match.group(0).upper()} ({invoice['amount']}, {invoice['date']}) was charged twice. "
                        "I've filed a refund for the duplicate; expect it in 5 business days.")
            return f"{match.group(0).upper()} ({invoice['amount']}) was charged once and is fully paid."
        if "refund" in message.lower():
            return "Refunds are available within 30 days. Reply with your invoice number (INV-....) and I'll start one."
        return "I can help with invoices, refunds and payment methods. What's your invoice number?"


TECH_KB = [
    (r"crash", "Update to app version 4.2.1: older builds crashed on photo uploads over 20 MB."),
    (r"export|csv", "Go to Settings > Data > Export and choose CSV. Large exports arrive by email."),
    (r"password|log ?in|sign ?in", "Use 'Forgot password' on the sign-in page; reset links expire after 30 minutes."),
    (r"sync", "Sign out and back in on both devices, then check Settings > Sync is on for each."),
]


class TechSupportAgent:
    name = "tech_support"
    description = "Bugs, errors, login problems, how-to questions."

    def handle(self, message: str) -> str:
        for pattern, answer in TECH_KB:
            if re.search(pattern, message, re.IGNORECASE):
                return answer
        return "I've opened ticket T-5521 for our engineers. Can you share a screenshot of the problem?"


class SalesAgent:
    name = "sales"
    description = "Pricing, plans, discounts, demos, enterprise deals."

    def handle(self, message: str) -> str:
        text = message.lower()
        if "discount" in text or re.search(r"\b\d{2,} (people|seats|users)\b", text):
            return "Team plan is 12 USD per seat per month, with 15% off from 50 seats. Want a quote?"
        if "demo" in text:
            return "Happy to! Pick a 30-minute slot at example.com/demo and an account executive will join."
        if "enterprise" in text:
            return "Enterprise adds SSO, audit logs and a 99.9% SLA. I'll connect you with our enterprise team."
        return "Plans: Free, Pro (8 USD/month) and Team (12 USD/seat/month). Which fits you best?"


class FallbackAgent:
    """Used when the router is not confident: ask, don't guess."""

    name = "fallback"
    description = "Clarifying question or human handoff."

    def __init__(self, options: list[str]) -> None:
        self.options = options

    def handle(self, message: str, candidates: list[str] | None = None) -> str:
        if candidates and len(candidates) > 1:
            return f"I can help with that. Is this mainly about {' or '.join(candidates)}? I'll start there."
        return f"I'm not sure I can help with that. I can help with: {', '.join(self.options)}."
