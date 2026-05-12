from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_ok() -> None:
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.text == "ok"


def test_ready_without_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDOCS_MCP_CONFIG", raising=False)
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json().get("status") == "ready"


def test_executive_dashboard_page_ok() -> None:
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "dashboard-stats" in r.text


def test_dashboard_stats_json(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "test.yaml"
    cfg.write_text("modules: {}\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/api/dashboard-stats")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "modules" in data
        assert data["summary"]["mcp_enabled_count"] == 0


def test_ready_with_valid_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "test.yaml"
    cfg.write_text("modules: {}\n", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_CONFIG", str(cfg))
    # Import app after env is set so middleware and routes see consistent env for ready()
    from sdocs_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json().get("status") == "ready"
