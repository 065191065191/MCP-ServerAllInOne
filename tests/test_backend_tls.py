from __future__ import annotations

import pytest

from sdocs_mcp.backend_tls import resolve_client_mtls, validate_client_mtls_triplet_files
from sdocs_mcp.config import RedisModuleConfig


def test_mtls_incomplete_raises() -> None:
    with pytest.raises(ValueError, match="все три"):
        validate_client_mtls_triplet_files("/a", "/b", None)


def test_redis_mtls_requires_rediss(tmp_path) -> None:
    a, b, c = tmp_path / "a.pem", tmp_path / "b.pem", tmp_path / "ca.pem"
    for p in (a, b, c):
        p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="rediss"):
        RedisModuleConfig(
            url="redis://localhost:6379/0",
            mtls_cert_file=str(a),
            mtls_key_file=str(b),
            mtls_root_ca_file=str(c),
        )


def test_resolve_simple_obj(tmp_path) -> None:
    a, b, c = tmp_path / "a.pem", tmp_path / "b.pem", tmp_path / "ca.pem"
    for p in (a, b, c):
        p.write_text("x", encoding="utf-8")

    class MtlsHolder:
        mtls_cert_file = str(a)
        mtls_key_file = str(b)
        mtls_root_ca_file = str(c)
        mtls_key_password = None

    m = resolve_client_mtls(MtlsHolder())
    assert m is not None
    assert m.cert.endswith("a.pem")
