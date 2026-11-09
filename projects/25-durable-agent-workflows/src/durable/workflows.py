"""The example job: a weekly account digest agent.

fetch tickets (flaky tool) -> summarise (LLM) -> draft email (LLM) -> send email (side effect)
-> add CRM note (side effect). Every line that touches the world goes through ``ctx.step``.
The workflow body itself must be deterministic: same inputs and step results -> same steps.
"""

from __future__ import annotations

import asyncio
import json

from .engine import Context, Workflow
from .llm import LLM, extract_json
from .world import World

SUMMARY_PROMPT = "You summarise support tickets for account managers. Reply with JSON only: " \
                 '{"summary": "<one sentence>", "needs_attention": true|false}'
EMAIL_PROMPT = "You write short, friendly customer emails. Reply with JSON only: " \
               '{"subject": "...", "body": "..."}'


def make_workflows(world: World, llm: LLM) -> dict[str, Workflow]:
    async def ask(system: str, prompt: str) -> dict:
        return extract_json(await asyncio.to_thread(llm.complete, system, prompt))

    async def weekly_digest(ctx: Context, account: str, recipient: str) -> dict:
        tickets = await ctx.step("fetch_tickets", lambda s: world.fetch_tickets(account))
        summary = await ctx.step("summarize", lambda s: ask(
            SUMMARY_PROMPT, f"TASK: summarize\nACCOUNT: {account}\nTICKETS:{json.dumps(tickets)}"))
        email = await ctx.step("draft_email", lambda s: ask(
            EMAIL_PROMPT, f"TASK: draft\nACCOUNT: {account}\nSUMMARY: {summary['summary']}"))
        receipt = await ctx.step("send_email", lambda s: world.send_email(
            recipient, email["subject"], email["body"], idempotency_key=s.idempotency_key))
        if receipt["duplicate"]:
            ctx.log("DEDUP", f"email service recognised the idempotency key -> original receipt "
                             f"{receipt['message_id']}, no second email")
        crm = await ctx.step("update_crm", lambda s: world.add_crm_note(
            account, f"Digest sent ({receipt['message_id']}): {summary['summary']}", idempotency_key=s.idempotency_key))
        return {"account": account, "message_id": receipt["message_id"], "summary": summary["summary"],
                "crm_duplicate": crm["duplicate"]}

    return {"weekly_digest": weekly_digest}


STEPS = ["fetch_tickets", "summarize", "draft_email", "send_email", "update_crm"]
