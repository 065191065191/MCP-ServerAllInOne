from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_ok() -> None:
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/sdocs/health")
        assert r.status_code == 200
        assert r.text == "ok"


def test_ready_without_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDOCS_MCP_CONFIG", raising=False)
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/sdocs/ready")
        assert r.status_code == 200
        assert r.json().get("status") == "ready"


def test_host_root_not_sdocs() -> None:
    """Корень / хоста не занят SDocsMCP (другие сервисы на том же origin)."""
    from sdocs_mcp.info_app import UI_BASE, app

    assert UI_BASE == "/sdocs"
    with TestClient(app) as client:
        assert client.get("/").status_code == 404


def test_sdocs_landing_points_to_mcp() -> None:
    from sdocs_mcp.info_app import UI_PAGES, app

    assert UI_PAGES == "/console"
    with TestClient(app) as client:
        r = client.get("/sdocs/")
        assert r.status_code == 200
        assert "/sdocs/mcp" in r.text
        assert "sdocs_mcp_status" in r.text
        assert "dashboard-stats" not in r.text


def test_executive_dashboard_under_sdocs_console() -> None:
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/sdocs/console/dashboard")
        assert r.status_code == 200
        assert "dashboard-stats" in r.text
        redir = client.get("/sdocs/dashboard", follow_redirects=False)
        assert redir.status_code == 302
        assert redir.headers["location"].endswith("/sdocs/console/dashboard")


def test_dashboard_stats_json(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "test.yaml"
    cfg.write_text("modules: {}\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/sdocs/api/dashboard-stats")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "modules" in data
        assert data["summary"]["mcp_enabled_count"] == 0


def test_ready_with_valid_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "test.yaml"
    cfg.write_text("modules: {}\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/sdocs/ready")
        assert r.status_code == 200
