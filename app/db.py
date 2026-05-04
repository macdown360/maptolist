"""
PostgreSQL connection helper.
Provides a sqlite3-compatible interface so application code can use
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
instead of sqlite3.connect(DB_PATH).
"""
import os
import re
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras




class _CursorProxy:
    """Thin wrapper around a psycopg2 cursor exposing fetchone/fetchall/rowcount."""

    def __init__(self, cur: Any) -> None:
        self._cur = cur

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount  # type: ignore[return-value]

    def fetchone(self) -> Any:
        return self._cur.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cur.fetchall()

    def __iter__(self) -> Any:
        return iter(self._cur)


class _ConnProxy:
    """
    Wraps a psycopg2 connection and exposes a sqlite3-compatible
    conn.execute(sql, params) interface.

    - Automatically converts '?' placeholders to '%s'.
    - Uses DictCursor so rows support both row['col'] and row[0] access.
    - dict(row) and row["col"] both work.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    def execute(self, sql: str, params: Any = None) -> _CursorProxy:
        pg_sql = re.sub(r"\?", "%s", sql)
        if params is not None:
            self._cur.execute(pg_sql, params)
        else:
            self._cur.execute(pg_sql)
        return _CursorProxy(self._cur)

    def _close(self) -> None:
        self._cur.close()


@contextmanager  # type: ignore[misc]
def get_connection() -> Any:
    """
    Context manager that yields a _ConnProxy.
    Commits on success, rolls back on exception, always closes the connection.

    Usage:
        with get_connection() as conn:
            rows = conn.execute("SELECT ...", (param,)).fetchall()
    """
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL が設定されていません。"
            "Supabase の接続文字列を environment variable に設定してください。"
        )
    raw = psycopg2.connect(database_url, connect_timeout=10)
    proxy = _ConnProxy(raw)
    try:
        yield proxy
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        proxy._close()
        raw.close()
