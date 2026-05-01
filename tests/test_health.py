from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_ok() -> None:
    from stack_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.text == "ok"


def test_ready_without_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STACK_MCP_CONFIG", raising=False)
    from stack_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code == 503


def test_cron_page_ok() -> None:
    from stack_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/cron-page")
        assert r.status_code == 200
        assert "allowlisted_query" in r.text or "allowlist" in r.text
        r2 = client.get("/cron")
        assert r2.status_code == 200


def test_ready_with_valid_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "test.yaml"
    cfg.write_text("modules: {}\n", encoding="utf-8")
    monkeypatch.setenv("STACK_MCP_CONFIG", str(cfg))
    # Import app after env is set so middleware and routes see consistent env for ready()
    from stack_mcp.info_app import app

    with TestClient(app) as client:
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json().get("status") == "ready"
