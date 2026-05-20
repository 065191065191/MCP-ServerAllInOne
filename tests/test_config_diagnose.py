from __future__ import annotations

from pathlib import Path

import pytest

from sdocs_mcp.config import config_yaml_diagnose, load_config


def test_diagnose_misplaced_postgres_at_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "mcp.conf"
    cfg.write_text("postgres:\n  enabled: true\n  dsn: postgresql://x\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    d = config_yaml_diagnose()
    assert d["file_found"] is True
    assert "postgres" in d["top_level_keys"]
    assert d["modules_keys"] == []
    assert d["hints"]
    assert load_config().modules.postgres.enabled is False


def test_diagnose_enabled_under_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "mcp.conf"
    cfg.write_text("modules:\n  redis:\n    enabled: true\n    url: redis://127.0.0.1\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    d = config_yaml_diagnose()
    assert d["enabled_true_in_yaml"] == ["redis"]
    assert load_config().modules.redis.enabled is True
