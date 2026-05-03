from __future__ import annotations

import logging
import ssl

import pytest

from sdocs_mcp.mtls import resolve_mcp_mtls_uvicorn_kwargs


def test_mtls_none_when_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDOCS_MCP_MTLS_CERT_FILE", raising=False)
    monkeypatch.delenv("SDOCS_MCP_MTLS_KEY_FILE", raising=False)
    monkeypatch.delenv("SDOCS_MCP_MTLS_ROOT_CA_FILE", raising=False)
    assert resolve_mcp_mtls_uvicorn_kwargs() is None


def test_mtls_incomplete_returns_none(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("SDOCS_MCP_MTLS_CERT_FILE", "/x/crt")
    monkeypatch.delenv("SDOCS_MCP_MTLS_KEY_FILE", raising=False)
    monkeypatch.delenv("SDOCS_MCP_MTLS_ROOT_CA_FILE", raising=False)
    caplog.set_level(logging.WARNING)
    log = logging.getLogger("test")
    assert resolve_mcp_mtls_uvicorn_kwargs(log) is None


def test_mtls_ok(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cert = tmp_path / "srv.pem"
    key = tmp_path / "srv.key"
    ca = tmp_path / "ca.pem"
    cert.write_text("x", encoding="utf-8")
    key.write_text("x", encoding="utf-8")
    ca.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SDOCS_MCP_MTLS_CERT_FILE", str(cert))
    monkeypatch.setenv("SDOCS_MCP_MTLS_KEY_FILE", str(key))
    monkeypatch.setenv("SDOCS_MCP_MTLS_ROOT_CA_FILE", str(ca))
    monkeypatch.setenv("SDOCS_MCP_MTLS_KEY_PASSWORD", "secret")
    out = resolve_mcp_mtls_uvicorn_kwargs()
    assert out is not None
    assert out["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert out["ssl_keyfile_password"] == "secret"
