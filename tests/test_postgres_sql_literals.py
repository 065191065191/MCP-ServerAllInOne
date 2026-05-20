from __future__ import annotations

from psycopg import sql

from sdocs_mcp.postgres_tools import _schema_literals_sql


def test_schema_literals_render_as_string_constants() -> None:
    part = _schema_literals_sql(["public", "audit"])
    rendered = sql.SQL("WHERE n.nspname IN ({})").format(part).as_string(None)
    assert rendered == "WHERE n.nspname IN ('public', 'audit')"


def test_long_running_queries_ilike_escapes_percent_for_psycopg() -> None:
    q = """
      AND query NOT ILIKE '%%pg_stat_activity%%'
    """
    assert "%p" not in q.replace("%%", "")
    assert "%%pg_stat_activity%%" in q
