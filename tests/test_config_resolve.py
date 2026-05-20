from __future__ import annotations

from pathlib import Path

import pytest

from sdocs_mcp.config import load_config, resolve_config_path


def test_resolve_prefers_sdocs_mcp_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "mine.yaml"
    cfg.write_text("modules: {}\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    p, src = resolve_config_path()
    assert p == cfg
    assert "SDOCS_MCP_CONFIG" in src


def test_load_config_maps_posgress_typo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text("modules:\n  posgress:\n    enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    app = load_config()
    assert app.modules.postgres.enabled is True


def test_load_config_merges_posgress_into_existing_postgres(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "modules:\n  postgres:\n    enabled: false\n  posgress:\n    enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    app = load_config()
    assert app.modules.postgres.enabled is True
