"""Typed messages for a debate: what each agent says, and what the judge concludes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Stance = Literal["for", "against", "conditional"]


class Argument(BaseModel):
    """What we require from a debater's model reply. Anything else is a failed turn."""

    stance: Stance
    confidence: float = Field(ge=0.0, le=1.0)
    claims: list[str] = Field(min_length=1)
    changed_because: str = ""

    @field_validator("claims")
    @classmethod
    def _claims_have_topics(cls, claims: list[str]) -> list[str]:
        """Claims are written ``topic: text`` so the judge can find where sides actually clash."""
        for claim in claims:
            if ":" not in claim:
                raise ValueError(f"claim must look like 'topic: text', got {claim!r}")
        return claims


class Position(BaseModel):
    """One agent's turn in one round (an abstention has ``argument=None``)."""

    agent: str
    round: int
    argument: Argument | None = None
    error: str = ""

    @property
    def abstained(self) -> bool:
        return self.argument is None


class Shift(BaseModel):
    agent: str
    round: int
    before: Stance
    after: Stance
    because: str

    @property
    def unexplained(self) -> bool:
        return not self.because.strip()


class Crux(BaseModel):
    """A topic where agents on different sides made claims - the real disagreement."""

    topic: str
    sides: dict[str, list[str]]  # stance -> agents who argued that topic


class Verdict(BaseModel):
    question: str
    consensus: bool
    decision: Stance | Literal["no consensus"]
    agreement: float
    tally: dict[str, float]
    dissent: list[str]
    cruxes: list[Crux]
    shifts: list[Shift]
    abstained: list[str]
    rounds: int
