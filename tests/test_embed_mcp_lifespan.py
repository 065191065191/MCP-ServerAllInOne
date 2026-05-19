from __future__ import annotations

import importlib

import pytest
from starlette.testclient import TestClient


def test_embed_mcp_initialize_no_task_group_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Встроенный MCP: session_manager.run() в lifespan FastAPI, не 500 Task group."""
    monkeypatch.setenv("SDOCS_MCP_EMBED_MCP", "true")
    import sdocs_mcp.info_app as ia

    importlib.reload(ia)
    assert ia._embedded_mcp is not None
    mcp_url = f"{ia.UI_BASE}/mcp/" if ia.UI_BASE else "/mcp/"

    with TestClient(ia.app) as client:
        r = client.post(
            mcp_url,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )

    assert r.status_code == 200, r.text
    assert "mcp-session-id" in {k.lower() for k in r.headers.keys()}

    monkeypatch.setenv("SDOCS_MCP_EMBED_MCP", "false")
    importlib.reload(ia)  # сброс для остальных тестов (session_manager.run() — один раз на инстанс)
