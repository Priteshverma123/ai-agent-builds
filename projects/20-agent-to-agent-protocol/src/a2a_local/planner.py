"""The planner agent: discovers remote agents by their cards, delegates sub-tasks, answers their questions.

Flow:  discover cards -> PLAN (one sub-task per skill) -> send all (non-blocking, in parallel)
       -> poll each task -> if input-required: FOLLOWUP answer on the same task -> SUMMARIZE.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import A2AClient
from .llm import LLM, extract_json
from .models import Task, TaskState, TextPart
from .trace import Trace

PLAN_SYSTEM = """TASK: PLAN
You coordinate remote agents. Split the user's request into sub-tasks, one per skill that is needed.
Only use the skill ids listed. Each sub-task text must make sense on its own to a stranger.
Reply with JSON: {"subtasks": [{"skill": "<skill id>", "text": "<message to send>"}]}"""

FOLLOWUP_SYSTEM = """TASK: FOLLOWUP
A remote agent asked a question about a sub-task. Answer it in a few words, using only facts from the
user's request. Do not invent personal details."""

SUMMARIZE_SYSTEM = """TASK: SUMMARIZE
Write the final answer for the user from the remote agents' results. Be brief and concrete."""


@dataclass
class Delegation:
    skill: str
    agent: str
    client: A2AClient
    text: str
    task: Task | None = None


class Planner:
    def __init__(self, remotes: list[A2AClient], llm: LLM, trace: Trace | None = None, max_followups: int = 2) -> None:
        self.remotes = remotes
        self.llm = llm
        self.trace = trace or Trace(quiet=True)
        self.max_followups = max_followups
        self.directory: dict[str, A2AClient] = {}

    def discover(self) -> dict[str, A2AClient]:
        """Fetch every agent card and index the remote agents by skill id."""
        for client in self.remotes:
            card = client.get_card()
            for skill in card.skills:
                self.directory[skill.id] = client
        return self.directory

    def plan(self, request: str) -> list[Delegation]:
        skills = "\n".join(f"- {s.id} | tags: {', '.join(s.tags)}"
                           for c in self.remotes if c.card for s in c.card.skills)
        raw = self.llm.complete(PLAN_SYSTEM, f"Skills:\n{skills}\n\nRequest: {request}")
        plan = []
        for item in extract_json(raw).get("subtasks", []):
            client = self.directory.get(item["skill"])
            if client is None:
                self.trace.row("skip", f"model asked for unknown skill '{item['skill']}'")
                continue
            plan.append(Delegation(item["skill"], client.card.name, client, item["text"]))
            self.trace.row("plan", f"{item['skill']:<17} -> {client.card.name:<16} \"{item['text']}\"")
        return plan

    def run(self, request: str) -> str:
        self.trace.row("user", request)
        if not self.directory:
            self.discover()
        delegations = self.plan(request)
        for d in delegations:  # fan out: every agent starts working at once
            d.task = d.client.send(d.text, blocking=False)
        for d in delegations:
            d.task = self._finish(d, request)
        results = "\n".join(f"- {d.skill}: {self._result_text(d.task)}" for d in delegations)
        answer = self.llm.complete(SUMMARIZE_SYSTEM, f"Request: {request}\n\nResults:\n{results}")
        self.trace.row("answer", answer)
        return answer

    def _finish(self, d: Delegation, request: str) -> Task:
        task = d.client.wait(d.task.id)
        for _ in range(self.max_followups):
            if task.status.state != TaskState.input_required:
                break
            question = task.status.message.text
            reply = self.llm.complete(FOLLOWUP_SYSTEM, f"Request: {request}\nSub-task: {d.text}\nQuestion: {question}")
            self.trace.row("think", f"{d.agent} needs input. From the request, the answer is: {reply}")
            d.client.send(reply, task_id=task.id, context_id=task.contextId, blocking=False)
            task = d.client.wait(task.id)
        return task

    @staticmethod
    def _result_text(task: Task) -> str:
        if task.status.state != TaskState.completed:
            return f"(not done: {task.status.state.value}: {task.status.message.text if task.status.message else ''})"
        texts = [p.text for a in task.artifacts for p in a.parts if isinstance(p, TextPart)]
        return texts[0] if texts else task.status.message.text
