from __future__ import annotations

import pytest
import yaml

from sdocs_mcp.config import AppConfig, PostgresModuleConfig
from sdocs_mcp.postgres_tools import _ensure_db_allowed


def test_postgres_allowed_databases_explicit() -> None:
    cfg = PostgresModuleConfig(
        enabled=True,
        dsn="postgresql://u:p@localhost:5432/mydb",
        allowed_databases=["other"],
    )
    with pytest.raises(PermissionError, match="mydb"):
        _ensure_db_allowed(cfg)


def test_postgres_allowed_prefixes() -> None:
    cfg = PostgresModuleConfig(
        enabled=True,
        dsn="postgresql://u:p@localhost:5432/tenant_01",
        allowed_database_prefixes=["tenant_"],
    )
    _ensure_db_allowed(cfg)


def test_postgres_allowed_regex() -> None:
    cfg = PostgresModuleConfig(
        enabled=True,
        dsn="postgresql://u:p@localhost:5432/app_42",
        allowed_database_regex=r"^app_[0-9]+$",
    )
    _ensure_db_allowed(cfg)


def test_postgres_list_and_prefix_mutually_exclusive(tmp_path) -> None:
    data = {
        "modules": {
            "postgres": {
                "enabled": True,
                "allowed_databases": ["a"],
                "allowed_database_prefixes": ["b"],
            }
        }
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(Exception, match="allowed_databases"):
        AppConfig.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
