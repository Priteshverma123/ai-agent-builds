"""The A2A data model: agent cards, messages made of parts, and tasks with a state machine.

Field names follow the public A2A specification (JSON-RPC binding), so the JSON on the wire
looks like what other A2A implementations send.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

PROTOCOL_VERSION = "0.3.0"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    examples: list[str] = []


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False


class AgentCard(BaseModel):
    """The agent's public "business card", served at /.well-known/agent-card.json."""

    protocolVersion: str = PROTOCOL_VERSION
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    preferredTransport: str = "JSONRPC"
    capabilities: AgentCapabilities = AgentCapabilities()
    defaultInputModes: list[str] = ["text/plain"]
    defaultOutputModes: list[str] = ["text/plain", "application/json"]
    skills: list[AgentSkill]


class TextPart(BaseModel):
    kind: Literal["text"] = "text"
    text: str


class DataPart(BaseModel):
    kind: Literal["data"] = "data"
    data: dict[str, Any]


Part = Annotated[Union[TextPart, DataPart], Field(discriminator="kind")]


class Message(BaseModel):
    kind: Literal["message"] = "message"
    role: Literal["user", "agent"]
    parts: list[Part]
    messageId: str = Field(default_factory=new_id)
    taskId: str | None = None
    contextId: str | None = None

    @property
    def text(self) -> str:
        return " ".join(p.text for p in self.parts if isinstance(p, TextPart))


class TaskState(str, Enum):
    submitted = "submitted"
    working = "working"
    input_required = "input-required"
    completed = "completed"
    canceled = "canceled"
    failed = "failed"

    @property
    def is_final(self) -> bool:
        return self in (TaskState.completed, TaskState.canceled, TaskState.failed)


class TaskStatus(BaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: str = Field(default_factory=now)


class Artifact(BaseModel):
    artifactId: str = Field(default_factory=new_id)
    name: str
    parts: list[Part]


class Task(BaseModel):
    kind: Literal["task"] = "task"
    id: str = Field(default_factory=new_id)
    contextId: str = Field(default_factory=new_id)
    status: TaskStatus
    history: list[Message] = []
    artifacts: list[Artifact] = []


class SendConfiguration(BaseModel):
    blocking: bool = True


class MessageSendParams(BaseModel):
    message: Message
    configuration: SendConfiguration = SendConfiguration()


class TaskIdParams(BaseModel):
    id: str


def agent_text(text: str, task: Task | None = None) -> Message:
    return Message(role="agent", parts=[TextPart(text=text)],
                   taskId=task.id if task else None, contextId=task.contextId if task else None)
