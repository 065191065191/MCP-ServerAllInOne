from __future__ import annotations

from stack_mcp.config import AppConfig
from stack_mcp.server import build_mcp


def test_build_mcp_accepts_streamable_http_path() -> None:
    m = build_mcp(AppConfig(), streamable_http_path="/")
    assert m.settings.streamable_http_path == "/"


def test_build_mcp_default_streamable_path() -> None:
    m = build_mcp(AppConfig())
    assert m.settings.streamable_http_path == "/mcp"
