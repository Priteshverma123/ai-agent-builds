"""End-to-end behaviour of the analyst loop with the offline model."""

import json

from sql_analyst.agent import SQLAnalyst
from sql_analyst.chart import render_ascii
from sql_analyst.llm import MockSQLWriter
from sql_analyst.trace import Tracer


def ask(db, question):
    tracer = Tracer()
    return SQLAnalyst(db, MockSQLWriter(), tracer=tracer).ask(question), tracer


def test_top_products_answer_and_bar_chart(db):
    answer, _ = ask(db, "Which 3 products bring in the most revenue?")
    assert answer.status == "ok"
    assert answer.rows == [["Noise-Cancelling Headset", 894.0], ["USB-C Dock", 645.0], ["Mechanical Keyboard", 445.0]]
    assert answer.chart.kind == "bar" and answer.chart.x == "product"


def test_monthly_revenue_is_a_line_chart(db):
    answer, _ = ask(db, "Show monthly revenue for 2026")
    assert answer.chart.kind == "line"
    assert sum(row[1] for row in answer.rows) == 2899.0


def test_repairs_a_broken_query_from_the_sqlite_error(db):
    answer, tracer = ask(db, "What is the average order value by country?")
    assert answer.status == "ok" and answer.attempts == 2
    assert tracer.steps().count("ERROR") == 1 and "REPAIR" in tracer.steps()
    assert answer.rows[0] == ["Germany", 218.25]


def test_refuses_write_requests_without_retrying(db):
    answer, tracer = ask(db, "Delete all refunded orders to clean up the data")
    assert answer.status == "refused" and answer.attempts == 1
    assert "REPAIR" not in tracer.steps()
    assert db.run("SELECT COUNT(*) FROM orders WHERE status = 'refunded'").rows == [(2,)]


def test_unmappable_question_fails_gracefully(db):
    answer, _ = ask(db, "What is the meaning of life?")
    assert answer.status == "failed" and answer.rows == []


class AlwaysWrongModel:
    name = "always-wrong"

    def complete(self, system, prompt):
        return json.dumps({"sql": "SELECT nope FROM orders", "rationale": "guessing"})


def test_gives_up_after_max_attempts(db):
    answer = SQLAnalyst(db, AlwaysWrongModel(), max_attempts=2).ask("anything")
    assert answer.status == "failed" and answer.attempts == 2


def test_kpi_chart_renders(db):
    answer, _ = ask(db, "How many customers do we have?")
    assert answer.chart.kind == "kpi"
    assert render_ascii(answer.chart) == ["customers = 8"]
