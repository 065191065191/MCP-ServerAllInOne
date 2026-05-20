"""Встроенный MCP: ожидание конфига при старте и пересборка tools при смене файла на диске."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sdocs_mcp.config import AppConfig, load_config, resolve_config_path
from sdocs_mcp.config_runtime import record_config_loaded
from sdocs_mcp.http_access_log import install_access_logging
from sdocs_mcp.mcp_telemetry import wrap_mcp_http_app
from sdocs_mcp.server import build_mcp

_log = logging.getLogger("sdocs_mcp.embedded_mcp")


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def config_wait_seconds() -> float:
    """SDOCS_MCP_CONFIG_WAIT_SECONDS — ждать появления файла конфига при старте (0 = не ждать)."""
    return max(0.0, _env_float("SDOCS_MCP_CONFIG_WAIT_SECONDS", 120.0))


def config_reload_interval_seconds() -> float:
    """SDOCS_MCP_CONFIG_RELOAD_INTERVAL — опрос mtime конфига (0 = только при старте)."""
    return max(0.0, _env_float("SDOCS_MCP_CONFIG_RELOAD_INTERVAL", 30.0))


def config_file_fingerprint() -> tuple[float, int] | None:
    """(mtime_ns, size) для обнаружения замены Secret / правки YAML."""
    path, _ = resolve_config_path()
    if path is None or not path.is_file():
        return None
    st = path.stat()
    return (st.st_mtime_ns, st.st_size)


def _modules_summary(cfg: AppConfig) -> str:
    m = cfg.modules
    parts = [
        f"postgres={m.postgres.enabled}",
        f"redis={m.redis.enabled}",
        f"kafka={m.kafka.enabled}",
        f"prometheus={m.prometheus.enabled}",
        f"mail={m.mail.enabled}",
        f"opensearch={m.opensearch.enabled}",
        f"ssh={m.ssh.enabled}",
    ]
    return ", ".join(parts)


class EmbeddedMcpHolder:
    """
    Текущий FastMCP + ASGI для mount(/mcp).
    session_manager.run() крутится в lifespan; при смене конфига — выход из run(), rebuild, снова run().
    """

    def __init__(self, *, streamable_http_path: str = "/") -> None:
        self._streamable_http_path = streamable_http_path
        self._mcp: FastMCP | None = None
        self._asgi: ASGIApp | None = None
        self._fingerprint: tuple[float, int] | None = None
        self._reload_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def mcp(self) -> FastMCP | None:
        return self._mcp

    def config_changed_on_disk(self) -> bool:
        return config_file_fingerprint() != self._fingerprint

    def _build_unlocked(self) -> FastMCP:
        try:
            cfg = load_config()
            record_config_loaded(cfg)
        except Exception as e:
            record_config_loaded(None, error=str(e))
            raise
        mcp = build_mcp(cfg, streamable_http_path=self._streamable_http_path)
        asgi = wrap_mcp_http_app(mcp.streamable_http_app())
        install_access_logging(asgi, cfg.logging)
        self._mcp = mcp
        self._asgi = asgi
        self._fingerprint = config_file_fingerprint()
        path, source = resolve_config_path()
        _log.info(
            "Embedded MCP rebuilt (%s): %s; config=%s",
            source,
            _modules_summary(cfg),
            path,
        )
        return mcp

    async def rebuild(self, *, force: bool = False) -> bool:
        async with self._lock:
            if not force and not self.config_changed_on_disk():
                return False
            self._build_unlocked()
            return True

    async def wait_for_config_file(self) -> bool:
        max_wait = config_wait_seconds()
        path, source = resolve_config_path()
        if config_file_fingerprint() is not None:
            _log.info("Config file present at startup: %s (%s)", path, source)
            return True
        if max_wait <= 0:
            _log.warning("Config file missing at startup (%s); modules disabled until file appears.", source)
            return False
        deadline = asyncio.get_running_loop().time() + max_wait
        interval = min(5.0, max(1.0, max_wait / 12))
        while asyncio.get_running_loop().time() < deadline:
            _log.info("Waiting for config file (%s), next check in %.0fs…", source, interval)
            await asyncio.sleep(interval)
            if config_file_fingerprint() is not None:
                _log.info("Config file appeared: %s (%s)", path, source)
                return True
        _log.warning(
            "Config file still missing after %.0fs (%s); MCP uses empty modules until reload picks up the file.",
            max_wait,
            source,
        )
        return False

    async def run_session_manager_loop(self, stop: asyncio.Event) -> None:
        await self.wait_for_config_file()
        await self.rebuild(force=True)
        interval = config_reload_interval_seconds()
        while not stop.is_set():
            assert self._mcp is not None
            poll_task = asyncio.create_task(self._poll_config_or_stop(stop, interval))
            try:
                async with self._mcp.session_manager.run():
                    await poll_task
            except asyncio.CancelledError:
                raise
            if stop.is_set():
                break
            changed = poll_task.result() if not poll_task.cancelled() else False
            self._reload_event.clear()
            if changed:
                await self.rebuild(force=True)
            else:
                break

    async def _poll_config_or_stop(self, stop: asyncio.Event, interval: float) -> bool:
        """Завершается True, когда пора выйти из session_manager.run() и пересобрать MCP."""
        while not stop.is_set():
            if interval > 0 and self.config_changed_on_disk():
                _log.info("Config file changed on disk — reloading embedded MCP tools")
                return True
            # interval=0: без частого reload, но раз в 5 с проверяем появление/смену файла (Secret mount).
            wait = interval if interval > 0 else 5.0
            try:
                await asyncio.wait_for(self._reload_event.wait(), timeout=wait)
                return True
            except asyncio.TimeoutError:
                continue
        return False

    async def asgi_app(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            if self._asgi is not None:
                await self._asgi(scope, receive, send)
            return
        async with self._lock:
            if self._asgi is None:
                await self.rebuild(force=True)
            app = self._asgi
        if app is None:
            await JSONResponse(
                {"error": "mcp_not_ready", "detail": "Конфиг отсутствует — повторите после монтирования Secret"},
                status_code=503,
            )(scope, receive, send)
            return
        await app(scope, receive, send)
