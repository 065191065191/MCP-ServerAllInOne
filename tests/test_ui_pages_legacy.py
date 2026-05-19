"""Изолированный импорт: префиксы сняты — страницы и API на корне хоста (локальная отладка)."""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_at_host_root(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SDOCS_MCP_UI_BASE_PATH", "")
    monkeypatch.setenv("SDOCS_MCP_UI_PAGES_PREFIX", "")
    for name in list(sys.modules):
        if name == "sdocs_mcp.info_app" or name.startswith("sdocs_mcp.info_app."):
            del sys.modules[name]
    import sdocs_mcp.info_app as ia

    importlib.reload(ia)
    yield ia.app
    for name in list(sys.modules):
        if name == "sdocs_mcp.info_app" or name.startswith("sdocs_mcp.info_app."):
            del sys.modules[name]


def test_dashboard_at_root_without_prefixes(app_at_host_root) -> None:
    with TestClient(app_at_host_root) as client:
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "dashboard-stats" in r.text
        root = client.get("/")
        assert root.status_code == 200
        assert "dashboard-stats" in root.text
