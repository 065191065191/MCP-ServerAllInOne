from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdocs_mcp.config import load_config
from sdocs_mcp.config_yaml_patch import patch_modules_s3_mcp


def test_patch_modules_s3_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "mcp.conf"
    cfg.write_text(
        "modules:\n  postgres:\n    enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    out = patch_modules_s3_mcp(allow_put=True, allow_delete=False)
    assert out["allow_put"] is True
    assert out["allow_delete"] is False
    loaded = load_config()
    assert loaded.modules.s3_mcp.allow_put is True
    assert loaded.modules.s3_mcp.allow_delete is False
