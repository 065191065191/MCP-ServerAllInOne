from __future__ import annotations

import pytest

from sdocs_mcp.ui_paths import normalize_ui_base_path


@pytest.mark.parametrize(
    ("env_val", "expected"),
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("/", ""),
        ("/mcp-server", "/mcp-server"),
        ("mcp-server", "/mcp-server"),
        ("/mcp-server/", "/mcp-server"),
    ],
)
def test_normalize_ui_base_path(monkeypatch: pytest.MonkeyPatch, env_val: str | None, expected: str) -> None:
    if env_val is None:
        monkeypatch.delenv("SDOCS_MCP_UI_BASE_PATH", raising=False)
    else:
        monkeypatch.setenv("SDOCS_MCP_UI_BASE_PATH", env_val)
    assert normalize_ui_base_path() == expected
