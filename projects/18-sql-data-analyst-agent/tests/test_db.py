"""Defence in depth: even SQL that slips past the guard cannot write."""

import sqlite3

import pytest


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "UPDATE products SET price = 0",
    "CREATE TABLE t (x)",
])
def test_database_layer_blocks_writes_even_without_the_guard(db, sql):
    with pytest.raises(sqlite3.Error):
        db.run(sql)
    assert db.run("SELECT COUNT(*) FROM orders").rows == [(18,)]


def test_reads_and_ctes_work(db):
    result = db.run("WITH paid AS (SELECT * FROM orders WHERE status = 'paid') SELECT COUNT(*) AS n FROM paid")
    assert result.columns == ["n"] and result.rows == [(16,)]


def test_schema_card_grounds_the_model(db):
    card = db.schema.card()
    assert "FK orders.customer_id -> customers.id" in card
    assert "orders.status values: 'paid', 'refunded'" in card


def test_relevant_tables_adds_join_bridges(db):
    assert db.schema.relevant_tables("revenue by product") == ["order_items", "orders", "products"]
    assert db.schema.relevant_tables("how many customers?") == ["customers"]


def test_runaway_query_times_out(db):
    db.timeout_ms = 50
    with pytest.raises(sqlite3.OperationalError, match="exceeded"):
        db.run("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n")
