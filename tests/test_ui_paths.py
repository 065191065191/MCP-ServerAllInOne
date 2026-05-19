from __future__ import annotations

import pytest

from sdocs_mcp.ui_paths import (
    normalize_ui_base_path,
    normalize_ui_pages_prefix,
    ui_pages_base,
)


@pytest.mark.parametrize(
    ("env_val", "expected"),
    [
        (None, "/sdocs"),
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


@pytest.mark.parametrize(
    ("env_val", "expected"),
    [
        (None, "/console"),
        ("", ""),
        ("   ", ""),
        ("/", ""),
        ("/admin", "/admin"),
        ("admin", "/admin"),
    ],
)
def test_normalize_ui_pages_prefix(monkeypatch: pytest.MonkeyPatch, env_val: str | None, expected: str) -> None:
    if env_val is None:
        monkeypatch.delenv("SDOCS_MCP_UI_PAGES_PREFIX", raising=False)
    else:
        monkeypatch.setenv("SDOCS_MCP_UI_PAGES_PREFIX", env_val)
    assert normalize_ui_pages_prefix() == expected


def test_ui_pages_base_default() -> None:
    assert ui_pages_base() == "/sdocs/console"


def test_ui_pages_base_combines_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDOCS_MCP_UI_BASE_PATH", "/mcp-server")
    monkeypatch.setenv("SDOCS_MCP_UI_PAGES_PREFIX", "/console")
    assert ui_pages_base() == "/mcp-server/console"
