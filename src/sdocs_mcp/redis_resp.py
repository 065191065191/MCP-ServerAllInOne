"""Минимальный клиент Redis по RESP2 (без пакета redis). Поддержка redis:// и rediss:// + опциональный mTLS."""
from __future__ import annotations

import socket
import ssl
from typing import Any
from urllib.parse import unquote, urlparse

from sdocs_mcp.backend_tls import resolve_client_mtls
from sdocs_mcp.config import RedisModuleConfig


class RedisRespError(RuntimeError):
    pass


def _encode_command(parts: list[bytes]) -> bytes:
    out = bytearray()
    out.extend(f"*{len(parts)}\r\n".encode())
    for p in parts:
        out.extend(f"${len(p)}\r\n".encode())
        out.extend(p)
        out.extend(b"\r\n")
    return bytes(out)


class RedisRawClient:
    def __init__(self, sock: socket.socket, timeout: float) -> None:
        self._sock = sock
        self._sock.settimeout(timeout)
        self._buf = bytearray()

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def _read_more(self) -> None:
        chunk = self._sock.recv(65536)
        if not chunk:
            raise RedisRespError("connection closed by server")
        self._buf.extend(chunk)

    def _read_line(self) -> bytes:
        while True:
            idx = self._buf.find(b"\r\n")
            if idx != -1:
                line = bytes(self._buf[:idx])
                del self._buf[: idx + 2]
                return line
            self._read_more()

    def _read_bulk(self, length: int) -> bytes | None:
        if length < 0:
            return None
        need = length + 2
        while len(self._buf) < need:
            self._read_more()
        data = bytes(self._buf[:length])
        if self._buf[length : length + 2] != b"\r\n":
            raise RedisRespError("invalid bulk CRLF")
        del self._buf[:need]
        return data

    def read_value(self) -> Any:
        line = self._read_line()
        if not line:
            raise RedisRespError("empty response line")
        prefix = line[:1]
        rest = line[1:]
        if prefix == b"+":
            return rest.decode("utf-8", errors="replace")
        if prefix == b"-":
            raise RedisRespError(rest.decode("utf-8", errors="replace"))
        if prefix == b":":
            return int(rest)
        if prefix == b"$":
            n = int(rest)
            body = self._read_bulk(n)
            if body is None:
                return None
            return body.decode("utf-8", errors="replace")
        if prefix == b"*":
            n = int(rest)
            if n < 0:
                return None
            return [self.read_value() for _ in range(n)]
        raise RedisRespError(f"unknown RESP prefix: {prefix!r}")

    def execute(self, *parts: str | bytes | int) -> Any:
        bparts: list[bytes] = []
        for p in parts:
            if isinstance(p, bytes):
                bparts.append(p)
            else:
                bparts.append(str(p).encode("utf-8"))
        self._sock.sendall(_encode_command(bparts))
        return self.read_value()


def _parse_redis_url(url: str) -> tuple[bool, str, int, str | None, str | None, int]:
    u = urlparse(url)
    if u.scheme not in ("redis", "rediss"):
        raise ValueError("redis url must start with redis:// or rediss://")
    use_tls = u.scheme == "rediss"
    host = u.hostname or "localhost"
    port = u.port or (6380 if use_tls else 6379)
    user = unquote(u.username) if u.username else None
    password = unquote(u.password) if u.password else None
    db = 0
    if u.path and u.path not in ("/", ""):
        path_db = u.path.lstrip("/")
        if path_db.isdigit():
            db = int(path_db)
    return use_tls, host, port, user, password, db


def connect_redis(cfg: RedisModuleConfig) -> RedisRawClient:
    use_tls, host, port, user, url_password, db = _parse_redis_url(cfg.url.strip())
    mtls = resolve_client_mtls(cfg)
    if mtls and not use_tls:
        raise ValueError("redis mtls_* requires rediss:// in url")
    raw = socket.create_connection((host, port), timeout=cfg.socket_timeout_seconds)
    try:
        if use_tls:
            if mtls:
                ctx = ssl.create_default_context()
                ctx.load_verify_locations(mtls.ca)
                ctx.load_cert_chain(mtls.cert, mtls.key, mtls.key_password)
                ctx.verify_mode = ssl.CERT_REQUIRED
            else:
                ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=host)
    except Exception:
        raw.close()
        raise

    client = RedisRawClient(raw, timeout=float(cfg.socket_timeout_seconds))
    try:
        if url_password is not None:
            if user:
                client.execute("AUTH", user, url_password)
            else:
                client.execute("AUTH", url_password)
        if db:
            client.execute("SELECT", db)
    except Exception:
        client.close()
        raise
    return client


def parse_info_bulk(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            out[k] = v
    return out
