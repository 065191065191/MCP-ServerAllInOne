from __future__ import annotations

from pathlib import Path

import pytest

from sdocs_mcp.config import load_config


def test_load_config_health_ping_without_sql_gets_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "mcp.conf"
    cfg_path.write_text(
        "modules:\n  postgres:\n    enabled: true\n    dsn: postgresql://u:p@h:5432/ms-eda\n"
        "    allowlisted_queries:\n      - id: health-ping\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg_path))
    app = load_config()
    assert len(app.modules.postgres.allowlisted_queries) == 1
    assert app.modules.postgres.allowlisted_queries[0].id == "health-ping"
    assert "current_database" in app.modules.postgres.allowlisted_queries[0].sql


def test_load_config_skips_query_without_sql(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "mcp.conf"
    cfg_path.write_text(
        "modules:\n  postgres:\n    enabled: true\n    dsn: postgresql://u:p@h:5432/db\n"
        "    allowlisted_queries:\n      - id: broken\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg_path))
    app = load_config()
    assert app.modules.postgres.allowlisted_queries == []
