"""A2A client: fetch an agent card, send messages, poll tasks. Works over any httpx.Client."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .models import AgentCard, Message, Task, TaskState, TextPart, new_id

CARD_PATH = "/.well-known/agent-card.json"


class A2AError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class A2AClient:
    def __init__(self, base_url: str, http: httpx.Client | None = None,
                 on_wire: Callable[[str, str], None] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=10.0)
        self.on_wire = on_wire or (lambda direction, text: None)
        self.card: AgentCard | None = None

    def get_card(self) -> AgentCard:
        self.on_wire("-->", f"GET {self.base_url}{CARD_PATH}")
        response = self.http.get(self.base_url + CARD_PATH)
        response.raise_for_status()
        self.card = AgentCard.model_validate(response.json())
        self.on_wire("<--", f"card: {self.card.name} v{self.card.version}, skills: "
                            f"{', '.join(s.id for s in self.card.skills)}")
        return self.card

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        url = (self.card.url if self.card else self.base_url).rstrip("/") + "/"
        response = self.http.post(url, json={"jsonrpc": "2.0", "id": new_id(), "method": method, "params": params})
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise A2AError(body["error"]["code"], body["error"]["message"])
        return body["result"]

    def send(self, text: str, task_id: str | None = None, context_id: str | None = None,
             blocking: bool = True) -> Task:
        message = Message(role="user", parts=[TextPart(text=text)], taskId=task_id, contextId=context_id)
        mode = "blocking" if blocking else "non-blocking"
        self.on_wire("-->", f"message/send ({mode}{', task ' + task_id if task_id else ''}): {text}")
        task = Task.model_validate(self._rpc("message/send", {
            "message": message.model_dump(mode="json", exclude_none=True),
            "configuration": {"blocking": blocking},
        }))
        self._report(task)
        return task

    def get_task(self, task_id: str) -> Task:
        return Task.model_validate(self._rpc("tasks/get", {"id": task_id}))

    def cancel(self, task_id: str) -> Task:
        return Task.model_validate(self._rpc("tasks/cancel", {"id": task_id}))

    def wait(self, task_id: str, interval: float = 0.1, timeout: float = 10.0) -> Task:
        """Poll ``tasks/get`` until the task is final or needs input from us."""
        deadline = time.monotonic() + timeout
        polls = 0
        while True:
            task = self.get_task(task_id)
            polls += 1
            if task.status.state.is_final or task.status.state == TaskState.input_required:
                self.on_wire("<--", f"tasks/get x{polls} -> task {task.id}: {task.status.state.value}"
                                    f"{': ' + task.status.message.text if task.status.message else ''}")
                return task
            if time.monotonic() > deadline:
                raise TimeoutError(f"task {task_id} still {task.status.state.value} after {timeout}s")
            time.sleep(interval)

    def _report(self, task: Task) -> None:
        note = f": {task.status.message.text}" if task.status.message else ""
        self.on_wire("<--", f"task {task.id} [{task.status.state.value}]{note}")
