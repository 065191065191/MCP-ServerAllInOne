from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from stack_mcp.config import AppConfig, PostgresAllowlistedQuery
from stack_mcp.postgres_allowlist_sql import normalize_and_validate_allowlisted_sql
from stack_mcp.postgres_tools import postgres_allowlisted_query, postgres_allowlisted_query_catalog


def test_validate_allowlisted_sql_accepts_select() -> None:
    normalize_and_validate_allowlisted_sql("SELECT 1 AS x")


def test_validate_allowlisted_sql_accepts_with() -> None:
    normalize_and_validate_allowlisted_sql("WITH t AS (SELECT 1 AS a) SELECT * FROM t")


def test_validate_rejects_insert() -> None:
    with pytest.raises(ValueError, match="SELECT or WITH"):
        normalize_and_validate_allowlisted_sql("INSERT INTO t VALUES (1)")


def test_validate_rejects_delete_after_with() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        normalize_and_validate_allowlisted_sql("WITH x AS (SELECT 1) DELETE FROM t")


def test_validate_rejects_semicolon_in_middle() -> None:
    with pytest.raises(ValueError, match="unquoted semicolon"):
        normalize_and_validate_allowlisted_sql("SELECT 1; SELECT 2")


def test_validate_accepts_semicolon_inside_string_literal() -> None:
    normalize_and_validate_allowlisted_sql("SELECT ';' AS semi")


def test_validate_accepts_semicolon_inside_quoted_identifier() -> None:
    normalize_and_validate_allowlisted_sql('SELECT 1 AS "x;y"')


def test_validate_rejects_into() -> None:
    with pytest.raises(ValueError, match="INTO"):
        normalize_and_validate_allowlisted_sql("SELECT 1 INTO tmp")


def test_duplicate_allowlist_id_in_config(tmp_path: Path) -> None:
    data = {
        "modules": {
            "postgres": {
                "enabled": True,
                "allowlisted_queries": [
                    {"id": "a", "sql": "SELECT 1"},
                    {"id": "a", "sql": "SELECT 2"},
                ],
            }
        }
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(Exception, match="duplicate id"):
        AppConfig.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))


def test_postgres_allowlisted_query_rejects_malformed_id() -> None:
    from stack_mcp.config import PostgresModuleConfig

    cfg = PostgresModuleConfig(
        enabled=True,
        allowlisted_queries=[
            PostgresAllowlistedQuery(id="ok-id", sql="SELECT 1", description="", max_rows=1),
        ],
    )
    with pytest.raises(ValueError, match="pattern"):
        postgres_allowlisted_query(cfg, "'; DROP--")


def test_allowlisted_query_catalog_json() -> None:
    from stack_mcp.config import PostgresModuleConfig

    cfg = PostgresModuleConfig(
        enabled=True,
        allowlisted_queries=[
            PostgresAllowlistedQuery(id="cron-ping", sql="SELECT 1", description="ping", max_rows=3),
        ],
    )
    out = json.loads(postgres_allowlisted_query_catalog(cfg))
    assert out["queries"] == [{"id": "cron-ping", "description": "ping", "max_rows": 3}]
