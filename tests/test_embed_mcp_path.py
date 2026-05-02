from __future__ import annotations

import pytest

from stack_mcp.config import AppConfig
from stack_mcp.server import build_mcp


def test_build_mcp_accepts_streamable_http_path() -> None:
    m = build_mcp(AppConfig(), streamable_http_path="/")
    assert m.settings.streamable_http_path == "/"


def test_build_mcp_default_streamable_path() -> None:
    m = build_mcp(AppConfig())
    assert m.settings.streamable_http_path == "/mcp"


def test_build_mcp_stateless_http_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STACK_MCP_STATELESS_HTTP", "true")
    m = build_mcp(AppConfig())
    assert m.settings.stateless_http is True


def test_build_mcp_stateless_http_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STACK_MCP_STATELESS_HTTP", raising=False)
    m = build_mcp(AppConfig())
    assert m.settings.stateless_http is False
