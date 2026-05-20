from __future__ import annotations

import time
from pathlib import Path

import pytest

from sdocs_mcp.config import load_config
from sdocs_mcp.embedded_mcp import (
    EmbeddedMcpHolder,
    config_file_fingerprint,
    config_reload_interval_seconds,
    config_wait_seconds,
)


def test_config_fingerprint_changes_when_file_touched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "mcp.conf"
    cfg.write_text("modules:\n  postgres:\n    enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    a = config_file_fingerprint()
    time.sleep(0.05)
    cfg.write_text("modules:\n  postgres:\n    enabled: false\n", encoding="utf-8")
    b = config_file_fingerprint()
    assert a is not None and b is not None
    assert a != b


def test_holder_rebuild_picks_up_enabled_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text("modules:\n  redis:\n    enabled: true\n    url: redis://127.0.0.1:6379/0\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    monkeypatch.setenv("SDOCS_MCP_CONFIG_WAIT_SECONDS", "0")
    holder = EmbeddedMcpHolder(streamable_http_path="/")
    import anyio

    anyio.run(lambda: holder.rebuild(force=True))
    assert holder.mcp is not None
    app_cfg = load_config()
    assert app_cfg.modules.redis.enabled is True


def test_config_wait_and_reload_env_defaults() -> None:
    assert config_wait_seconds() >= 0
    assert config_reload_interval_seconds() >= 0
