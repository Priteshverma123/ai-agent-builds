"""Database helpers for the shop."""

import sqlite3


def connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path)


def get_user(conn: sqlite3.Connection, user_id: int):
    cur = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def count_users(conn: sqlite3.Connection) -> int:
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except:
        return 0
