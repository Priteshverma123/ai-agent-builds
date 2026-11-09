"""Configuration, in two kinds.

* ``Settings``: process settings from environment variables (provider, model, default paths).
  The single source of truth for everything the code reads from the environment.
* ``ClientConfig``: per-client business configuration. Onboarding a new customer means writing one
  of these JSON files, not changing code. See examples/clients/northwind.json and the README
  "Customer onboarding".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"


@dataclass(frozen=True)
class Settings:
    """Environment settings with offline defaults. CLI flags override the path defaults."""

    llm_provider: str = "mock"                  # mock | anthropic | openai
    llm_model: str = ""                         # provider default when empty (openai: required)
    inbox: Path = EXAMPLES / "inbox"
    client: Path = EXAMPLES / "clients" / "northwind.json"
    master: Path = EXAMPLES / "master"
    golden: Path = EXAMPLES / "golden" / "expected.json"
    out_dir: Path = PROJECT_ROOT / "out"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        d = cls()

        def path(name: str, default: Path) -> Path:
            return Path(env[name]) if env.get(name) else default

        return cls(
            llm_provider=(env.get("LLM_PROVIDER") or d.llm_provider).strip().lower(),
            llm_model=env.get("LLM_MODEL", d.llm_model),
            inbox=path("INTAKE_INBOX", d.inbox),
            client=path("INTAKE_CLIENT", d.client),
            master=path("INTAKE_MASTER", d.master),
            golden=path("INTAKE_GOLDEN", d.golden),
            out_dir=path("INTAKE_OUT_DIR", d.out_dir),
        )


class Tolerances(BaseModel):
    price_pct: float = 0.02     # invoice unit price may differ from PO by this fraction
    amount_abs: float = 0.02    # rounding slack for line/subtotal/total arithmetic
    tax_abs: float = 0.05       # slack between stated tax and vendor tax rate x subtotal


class ErpMapping(BaseModel):
    header: dict[str, str]      # ERP column -> source path (e.g. "vendor.gl_code")
    line: dict[str, str]
    date_format: str = "%Y-%m-%d"


class Acceptance(BaseModel):
    """The numbers the customer signed off on. `python run.py eval` checks them."""

    classification_accuracy: float = 1.0
    field_accuracy: float = 0.98
    decision_accuracy: float = 1.0
    exception_recall: float = 0.95


class ClientConfig(BaseModel):
    client_name: str
    as_of: date | None = None                     # pinned "today" for reproducible runs
    require_po: bool = True
    min_classification_confidence: float = 0.8
    date_formats: list[str] = Field(default_factory=lambda: ["%Y-%m-%d"])
    tolerances: Tolerances = Field(default_factory=Tolerances)
    exception_routing: dict[str, str] = Field(default_factory=dict)  # issue code -> owner team
    default_owner: str = "ap_clerk"
    erp_mapping: ErpMapping
    acceptance: Acceptance = Field(default_factory=Acceptance)

    @classmethod
    def load(cls, path: Path) -> "ClientConfig":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def today(self) -> date:
        return self.as_of or date.today()

    def owner_for(self, codes: list[str]) -> str:
        for code in codes:
            if code in self.exception_routing:
                return self.exception_routing[code]
        return self.default_owner
