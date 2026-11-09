"""The analyst loop: ground -> draft -> guard -> execute -> (repair) -> chart -> answer."""

from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import BaseModel, ValidationError

from .chart import ChartSpec, infer_chart
from .db import QueryResult, ReadOnlyDatabase
from .guard import InvalidSQL, UnsafeSQL, check_sql
from .llm import LLM, extract_json
from .trace import Tracer

SYSTEM_PROMPT = """You are a careful data analyst who writes SQLite queries.
Rules:
- Write exactly ONE read-only SELECT (CTEs with WITH are fine). Never modify data.
- Use only the tables and columns in the schema card. Revenue counts only orders with status = 'paid'.
- Give every computed column a short alias.
Reply with JSON only: {"sql": "<query>", "rationale": "<one sentence>"}"""


class Draft(BaseModel):
    """What we require back from the model. Anything else is a failed attempt."""

    sql: str
    rationale: str = ""


class Answer(BaseModel):
    question: str
    status: Literal["ok", "refused", "failed"]
    sql: str | None = None
    attempts: int = 0
    columns: list[str] = []
    rows: list[list] = []
    chart: ChartSpec | None = None
    summary: str = ""


class SQLAnalyst:
    """Answers questions about a SQLite database with model-written, guard-checked SQL."""

    def __init__(self, db: ReadOnlyDatabase, llm: LLM, *, max_attempts: int = 3, max_rows: int = 200,
                 tracer: Tracer | None = None) -> None:
        self.db = db
        self.llm = llm
        self.max_attempts = max_attempts
        self.max_rows = max_rows
        self.trace = tracer or Tracer()

    def ask(self, question: str) -> Answer:
        tables = self.db.schema.relevant_tables(question)
        card = self.db.schema.card(tables)
        self.trace.log("GROUND", f"tables: {', '.join(tables)}")
        feedback: str | None = None

        for attempt in range(1, self.max_attempts + 1):
            draft = self._draft(question, card, feedback)
            if draft is None or not draft.sql.strip():
                self.trace.log("GIVE UP", "model returned no usable SQL")
                return Answer(question=question, status="failed", attempts=attempt,
                              summary="I couldn't map that question to this database.")
            self.trace.log("DRAFT" if attempt == 1 else "REPAIR", draft.rationale, draft.sql)

            try:
                safe = check_sql(draft.sql, self.db.schema, self.max_rows)
            except UnsafeSQL as exc:
                self.trace.log("BLOCKED", f"{exc} - refusing, no retry")
                return Answer(question=question, status="refused", sql=draft.sql, attempts=attempt,
                              summary=f"Refused: this agent is read-only ({exc}).")
            except InvalidSQL as exc:
                feedback = self._feedback(draft.sql, str(exc))
                self.trace.log("INVALID", str(exc))
                continue
            self.trace.log("GUARD", "read-only: ok" + (f"; {'; '.join(safe.notes)}" if safe.notes else ""))

            try:
                result = self.db.run(safe.sql)
            except sqlite3.Error as exc:
                feedback = self._feedback(draft.sql, str(exc))
                self.trace.log("ERROR", f"sqlite: {exc}")
                continue
            self.trace.log("EXECUTE", f"{len(result.rows)} row(s) x {len(result.columns)} col(s) in {result.elapsed_ms:.1f} ms")

            chart = infer_chart(question, result)
            summary = summarize(result)
            axes = ", ".join(f"{k}={v}" for k, v in (("x", chart.x), ("y", chart.y)) if v)
            self.trace.log("CHART", f"{chart.kind} ({axes})" if axes else chart.kind)
            return Answer(question=question, status="ok", sql=draft.sql, attempts=attempt,
                          columns=result.columns, rows=[list(r) for r in result.rows],
                          chart=chart, summary=summary)

        self.trace.log("GIVE UP", f"no valid query after {self.max_attempts} attempts")
        return Answer(question=question, status="failed", attempts=self.max_attempts,
                      summary="I couldn't produce a working query.")

    def _draft(self, question: str, card: str, feedback: str | None) -> Draft | None:
        prompt = f"SCHEMA:\n{card}\n\nQUESTION: {question}"
        if feedback:
            prompt += f"\n\n{feedback}"
        try:
            return Draft.model_validate(extract_json(self.llm.complete(SYSTEM_PROMPT, prompt)))
        except (ValueError, ValidationError):
            return None

    @staticmethod
    def _feedback(sql: str, error: str) -> str:
        """The repair prompt: show the model its own query and the exact database error."""
        return f"PREVIOUS ATTEMPT FAILED\nSQL:\n{sql}\nERROR: {error}\nFix the query using only the schema above."


def summarize(result: QueryResult) -> str:
    """A deterministic one-line answer. Numbers come from the database, never from the model."""
    if not result.rows:
        return "The query returned no rows."
    if len(result.columns) == 1 and len(result.rows) == 1:
        return f"{result.columns[0]}: {result.rows[0][0]}"
    first = result.rows[0]
    return (f"{len(result.rows)} rows. First: {result.columns[0]} = {first[0]}"
            + (f", {result.columns[1]} = {first[1]}" if len(first) > 1 else "") + ".")
