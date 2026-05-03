from __future__ import annotations

import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo


@dataclass(frozen=True)
class ClientMtlsPaths:
    cert: str
    key: str
    ca: str
    key_password: str | None


def validate_client_mtls_triplet_files(
    cert_file: str | None,
    key_file: str | None,
    root_ca_file: str | None,
) -> None:
    """Либо все три пути заданы и файлы существуют, либо ни одного — иначе ValueError."""
    c = (cert_file or "").strip()
    k = (key_file or "").strip()
    r = (root_ca_file or "").strip()
    n = sum(1 for x in (c, k, r) if x)
    if n == 0:
        return
    if n != 3:
        raise ValueError(
            "mtls_cert_file, mtls_key_file, mtls_root_ca_file: укажите все три или оставьте все пустыми"
        )
    for label, p in (
        ("mtls_cert_file", c),
        ("mtls_key_file", k),
        ("mtls_root_ca_file", r),
    ):
        path = Path(p).expanduser()
        if not path.is_file():
            raise ValueError(f"{label}: файл не найден: {p}")


def resolve_client_mtls(cfg: Any) -> ClientMtlsPaths | None:
    c = (getattr(cfg, "mtls_cert_file", None) or "").strip()
    k = (getattr(cfg, "mtls_key_file", None) or "").strip()
    r = (getattr(cfg, "mtls_root_ca_file", None) or "").strip()
    if not c and not k and not r:
        return None
    validate_client_mtls_triplet_files(c, k, r)
    pwd = (getattr(cfg, "mtls_key_password", None) or "").strip() or None
    return ClientMtlsPaths(
        cert=str(Path(c).expanduser().resolve()),
        key=str(Path(k).expanduser().resolve()),
        ca=str(Path(r).expanduser().resolve()),
        key_password=pwd,
    )


def make_postgres_conninfo(cfg: Any) -> str:
    info = conninfo_to_dict(cfg.dsn)
    m = resolve_client_mtls(cfg)
    if m:
        info["sslmode"] = "verify-full"
        info["sslcert"] = m.cert
        info["sslkey"] = m.key
        info["sslrootcert"] = m.ca
        if m.key_password:
            info["sslpassword"] = m.key_password
    return make_conninfo(**info)


def opensearch_client_kwargs(cfg: Any) -> dict[str, Any]:
    m = resolve_client_mtls(cfg)
    if not m:
        return {}
    if m.key_password:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(m.ca)
        ctx.load_cert_chain(m.cert, m.key, m.key_password)
        return {
            "use_ssl": True,
            "verify_certs": True,
            "ssl_context": ctx,
        }
    return {
        "use_ssl": True,
        "verify_certs": True,
        "client_cert": m.cert,
        "client_key": m.key,
        "ca_certs": m.ca,
    }


def kafka_apply_mtls(conf: dict[str, Any], cfg: Any) -> None:
    m = resolve_client_mtls(cfg)
    if not m:
        return
    conf["ssl_cafile"] = m.ca
    conf["ssl_certfile"] = m.cert
    conf["ssl_keyfile"] = m.key
    if m.key_password:
        conf["ssl_password"] = m.key_password
    proto = (getattr(cfg, "security_protocol", None) or "PLAINTEXT").strip()
    if proto == "PLAINTEXT":
        conf["security_protocol"] = "SSL"


def prometheus_httpx_verify_and_cert(cfg: Any) -> tuple[Any, Any]:
    m = resolve_client_mtls(cfg)
    if not m:
        return getattr(cfg, "verify_tls", True), None
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(m.ca)
    ctx.load_cert_chain(m.cert, m.key, m.key_password)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx, None
