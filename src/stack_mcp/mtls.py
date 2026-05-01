from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path
from typing import Any


def resolve_mcp_mtls_uvicorn_kwargs(log: logging.Logger | None = None) -> dict[str, Any] | None:
    """
    mTLS для HTTP-транспорта MCP (streamable-http / sse): нужны все три пути.

    - STACK_MCP_MTLS_CERT_FILE — сертификат сервера (CRT)
    - STACK_MCP_MTLS_KEY_FILE — приватный ключ сервера (KEY)
    - STACK_MCP_MTLS_ROOT_CA_FILE — доверенный CA для проверки клиентских сертификатов (ROOT)

    Опционально: STACK_MCP_MTLS_KEY_PASSWORD — пароль от зашифрованного ключа.

    Если задана только часть переменных или файлы отсутствуют — возвращается None (plain HTTP).
    """
    cert = (os.environ.get("STACK_MCP_MTLS_CERT_FILE") or "").strip()
    key = (os.environ.get("STACK_MCP_MTLS_KEY_FILE") or "").strip()
    ca = (os.environ.get("STACK_MCP_MTLS_ROOT_CA_FILE") or "").strip()

    n = sum(1 for x in (cert, key, ca) if x)
    if n == 0:
        return None
    if n != 3:
        if log:
            log.warning(
                "Неполный mTLS: нужны все три переменные STACK_MCP_MTLS_CERT_FILE, "
                "STACK_MCP_MTLS_KEY_FILE, STACK_MCP_MTLS_ROOT_CA_FILE — слушаем без TLS (HTTP)."
            )
        return None

    paths: list[tuple[str, str]] = [("cert", cert), ("key", key), ("root_ca", ca)]
    resolved: dict[str, str] = {}
    for label, raw in paths:
        p = Path(raw).expanduser()
        if not p.is_file():
            if log:
                log.warning("mTLS: файл %s не найден (%s) — слушаем без TLS (HTTP).", label, raw)
            return None
        resolved[label] = str(p.resolve())

    pwd = (os.environ.get("STACK_MCP_MTLS_KEY_PASSWORD") or "").strip() or None

    out: dict[str, Any] = {
        "ssl_certfile": resolved["cert"],
        "ssl_keyfile": resolved["key"],
        "ssl_ca_certs": resolved["root_ca"],
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }
    if pwd is not None:
        out["ssl_keyfile_password"] = pwd
    return out
