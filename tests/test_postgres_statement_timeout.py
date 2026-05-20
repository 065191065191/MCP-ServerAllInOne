from __future__ import annotations

from unittest.mock import MagicMock, patch

from psycopg import sql

from sdocs_mcp.config import PostgresModuleConfig
from sdocs_mcp.postgres_tools import _connect


def test_connect_set_statement_timeout_without_bind_params() -> None:
    """PostgreSQL отклоняет SET ... = $1; используем sql.Literal."""
    captured: list[tuple[object, object | None]] = []

    class FakeCursor:
        def execute(self, query, params=None) -> None:
            captured.append((query, params))

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = FakeCursor()

    cfg = PostgresModuleConfig(enabled=True, dsn="postgresql://u:p@localhost:5432/postgres")
    with patch("sdocs_mcp.postgres_tools.psycopg.connect", return_value=fake_conn):
        _connect(cfg)

    assert len(captured) == 1
    query, params = captured[0]
    assert params is None
    assert isinstance(query, sql.Composed)
    rendered = query.as_string(None)
    assert "25000" in rendered
    assert "$1" not in rendered
