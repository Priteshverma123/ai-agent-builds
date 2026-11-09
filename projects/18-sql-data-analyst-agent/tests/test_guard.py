"""The guard must refuse every way of writing, and only every way of writing."""

import pytest

from sql_analyst.guard import InvalidSQL, UnsafeSQL, check_sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "UPDATE products SET price = 0",
    "INSERT INTO customers VALUES (9, 'x', 'y', 'z')",
    "DROP TABLE orders",
    "SELECT 1; DROP TABLE orders",
    "PRAGMA writable_schema = 1",
    "ATTACH DATABASE 'evil.db' AS evil",
    "WITH x AS (SELECT 1) DELETE FROM orders",
    "REPLACE INTO products VALUES (1, 'a', 'b', 1)",
    "SELECT load_extension('evil')",
])
def test_refuses_writes_and_escapes(db, sql):
    with pytest.raises(UnsafeSQL):
        check_sql(sql, db.schema)


def test_keywords_inside_strings_and_comments_are_ignored(db):
    safe = check_sql("SELECT name FROM customers WHERE name = 'drop table' -- delete me", db.schema)
    assert safe.tables == ["customers"]


def test_replace_function_is_allowed(db):
    check_sql("SELECT replace(name, ' ', '_') AS slug FROM products", db.schema)


def test_unknown_table_is_invalid_not_unsafe(db):
    with pytest.raises(InvalidSQL, match="invoices"):
        check_sql("SELECT * FROM invoices", db.schema)


def test_cte_names_are_known(db):
    safe = check_sql("WITH t AS (SELECT id FROM orders) SELECT COUNT(*) AS n FROM t", db.schema)
    assert safe.tables == ["orders"]


def test_limit_is_added_or_clamped(db):
    assert check_sql("SELECT * FROM orders", db.schema, max_rows=50).sql.endswith("LIMIT 50")
    clamped = check_sql("SELECT * FROM orders LIMIT 100000", db.schema, max_rows=50)
    assert clamped.sql.endswith("LIMIT 50") and clamped.notes == ["clamped LIMIT to 50"]
    assert check_sql("SELECT * FROM orders LIMIT 5", db.schema).notes == []
