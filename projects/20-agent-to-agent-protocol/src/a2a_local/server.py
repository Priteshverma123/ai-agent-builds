"""Turn any "skill handler" into an A2A agent served over HTTP (FastAPI).

Endpoints:
  GET  /.well-known/agent-card.json   discovery: who am I, what can I do
  POST /                              JSON-RPC 2.0: message/send, tasks/get, tasks/cancel
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .models import AgentCard, Artifact, MessageSendParams, Task, TaskIdParams, TaskState, TaskStatus, agent_text

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
TASK_NOT_FOUND, TASK_NOT_CANCELABLE = -32001, -32002  # A2A-specific error codes


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Reply:
    """What a skill handler returns: a new state, a message for the caller, and optional artifacts."""

    state: TaskState
    text: str
    artifacts: list[Artifact] = field(default_factory=list)


Handler = Callable[[Task], Reply]  # gets the whole task, including history, so it can do multi-turn


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def get(self, task_id: str) -> Task:
        with self._lock:
            if task_id not in self._tasks:
                raise RpcError(TASK_NOT_FOUND, f"Task not found: {task_id}")
            return self._tasks[task_id].model_copy(deep=True)

    def save(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task.model_copy(deep=True)


def create_agent_app(card: AgentCard, handler: Handler, work_seconds: float = 0.0) -> FastAPI:
    """Build the FastAPI app. ``work_seconds`` simulates a slow agent so polling is visible."""
    app = FastAPI(title=card.name)
    store = TaskStore()
    app.state.store = store

    def run(task: Task) -> Task:
        time.sleep(work_seconds)
        if store.get(task.id).status.state == TaskState.canceled:
            return store.get(task.id)
        try:
            reply = handler(task)
        except Exception as exc:  # a crashing skill becomes a failed task, not a 500
            reply = Reply(TaskState.failed, f"Agent error: {exc}")
        message = agent_text(reply.text, task)
        task.history.append(message)
        task.artifacts += reply.artifacts
        task.status = TaskStatus(state=reply.state, message=message)
        store.save(task)
        return task

    def message_send(params: dict[str, Any]) -> Task:
        request = MessageSendParams.model_validate(params)
        message = request.message
        if message.taskId:  # a follow-up turn on an existing task (e.g. after input-required)
            task = store.get(message.taskId)
            if task.status.state.is_final:
                raise RpcError(INVALID_PARAMS, f"Task {task.id} is already {task.status.state.value}")
        else:
            task = Task(status=TaskStatus(state=TaskState.submitted))
            task.contextId = message.contextId or task.contextId  # join the caller's conversation if given
        message.taskId, message.contextId = task.id, task.contextId
        task.history.append(message)
        task.status = TaskStatus(state=TaskState.working)
        store.save(task)
        if request.configuration.blocking:
            return run(task)
        threading.Thread(target=run, args=(task,), daemon=True).start()
        return task  # returned immediately in "working"; the caller polls tasks/get

    def tasks_cancel(params: dict[str, Any]) -> Task:
        task = store.get(TaskIdParams.model_validate(params).id)
        if task.status.state.is_final:
            raise RpcError(TASK_NOT_CANCELABLE, f"Task {task.id} is {task.status.state.value} and cannot be canceled")
        task.status = TaskStatus(state=TaskState.canceled)
        store.save(task)
        return task

    methods: dict[str, Callable[[dict[str, Any]], Task]] = {
        "message/send": message_send,
        "tasks/get": lambda params: store.get(TaskIdParams.model_validate(params).id),
        "tasks/cancel": tasks_cancel,
    }

    @app.get("/.well-known/agent-card.json")
    def agent_card() -> dict[str, Any]:
        return card.model_dump(mode="json")

    @app.post("/")
    async def json_rpc(request: Request) -> JSONResponse:
        request_id = None
        try:
            try:
                body = await request.json()
            except ValueError:
                raise RpcError(PARSE_ERROR, "Parse error") from None
            if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or "method" not in body:
                raise RpcError(INVALID_REQUEST, "Invalid Request")
            request_id = body.get("id")
            method = methods.get(body["method"])
            if method is None:
                raise RpcError(METHOD_NOT_FOUND, f"Method not found: {body['method']}")
            try:
                task = await run_in_threadpool(method, body.get("params") or {})
            except ValidationError as exc:
                raise RpcError(INVALID_PARAMS, f"Invalid params: {exc.errors()[0]['msg']}") from None
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": task.model_dump(mode="json", exclude_none=True)})
        except RpcError as exc:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}})

    return app
