"""Messy text in, validated object out: prompt -> parse JSON -> validate -> (repair and retry)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .llm import LLM

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class Attempt:
    number: int
    raw: str
    errors: list[str]


@dataclass
class Extraction(Generic[T]):
    data: T | None
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None


def system_prompt(schema: type[BaseModel]) -> str:
    """Show the model the exact JSON Schema we will validate against."""
    return (
        f"You extract a {schema.__name__} from text. Reply with ONE JSON object and nothing else.\n"
        "Rules: dates as YYYY-MM-DD; numbers as plain JSON numbers (no currency symbols or commas); "
        "use null for optional fields that are missing; never invent values.\n\n"
        f"JSON Schema:\n{json.dumps(schema.model_json_schema(), indent=2)}"
    )


def parse_json(raw: str) -> Any:
    """Models love to wrap JSON in ```fences``` and chatty sentences. Dig the object out."""
    fenced = _FENCE.search(raw)
    candidate = fenced.group(1) if fenced else raw
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object found in the reply")
    return json.loads(candidate[start : end + 1])


def describe_errors(exc: ValidationError) -> list[str]:
    """Turn pydantic's errors into short lines the model (and a human) can act on."""
    lines = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"]) or "(whole object)"
        line = f"{where}: {error['msg']}"
        if not isinstance(error["input"], (dict, list)):  # echoing a whole object is just noise
            got = repr(error["input"])
            line += f" (got {got if len(got) <= 40 else got[:37] + '...'})"
        lines.append(line)
    return lines


def extract(text: str, schema: type[T], llm: LLM, max_attempts: int = 3) -> Extraction[T]:
    system = system_prompt(schema)
    messages = [{"role": "user", "content": f"Extract a {schema.__name__} from this text:\n\n{text}"}]
    attempts: list[Attempt] = []

    for number in range(1, max_attempts + 1):
        raw = llm.complete(system, messages)
        try:
            data = schema.model_validate(parse_json(raw))
        except ValidationError as exc:  # check before ValueError: ValidationError is a ValueError
            errors = describe_errors(exc)
        except (json.JSONDecodeError, ValueError) as exc:
            errors = [f"invalid JSON: {exc}"]
        else:
            attempts.append(Attempt(number, raw, []))
            return Extraction(data, attempts)

        attempts.append(Attempt(number, raw, errors))
        # The repair loop: show the model its own output and exactly what was wrong with it.
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": "Your JSON failed validation:\n" + "\n".join(f"- {e}" for e in errors)
            + "\nReturn the corrected JSON object only.",
        })

    return Extraction(None, attempts)  # give up honestly; a human should look at this one
