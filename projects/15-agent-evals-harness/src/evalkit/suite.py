"""Suite format, validated with pydantic so a typo in a suite fails loudly instead of silently passing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

GraderType = Literal["exact", "contains", "regex", "numeric", "json_fields", "rubric", "llm_judge"]


class GraderSpec(BaseModel):
    type: GraderType
    params: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(default=1.0, gt=0)


class Case(BaseModel):
    id: str
    input: str
    tags: list[str] = Field(default_factory=list)
    graders: list[GraderSpec] = Field(min_length=1)


class Suite(BaseModel):
    name: str
    version: str
    pass_threshold: float = Field(default=0.8, ge=0, le=1, description="minimum share of cases that must pass")
    cases: list[Case] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def unique_ids(cls, cases: list[Case]) -> list[Case]:
        ids = [c.id for c in cases]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate case ids: {sorted(duplicates)}")
        return cases


def load_suite(path: Path) -> Suite:
    return Suite.model_validate(json.loads(path.read_text(encoding="utf-8")))
