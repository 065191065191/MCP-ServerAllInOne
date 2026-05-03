"""FastMCP с записью каждого вызова tool в OpenSearch (если включено в конфиге)."""

from __future__ import annotations

import logging
import time
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP

from stack_mcp.config import AppConfig
from stack_mcp.tool_audit_opensearch import audit_log_tool_invocation_sync, audit_should_skip

_log = logging.getLogger("stack_mcp.audit")


class AuditedFastMCP(FastMCP):
    """Тот же FastMCP, но после каждого call_tool пишет событие в OpenSearch (не ломает вызов при сбое записи)."""

    def __init__(self, **kwargs: Any):
        self._stack_mcp_app_config: AppConfig = kwargs.pop("app_config")
        super().__init__(**kwargs)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        cfg = self._stack_mcp_app_config.modules.opensearch
        aud = cfg.tool_call_audit
        skip = not aud.enabled or not cfg.enabled or audit_should_skip(name, aud)
        t0 = time.perf_counter()
        err: str | None = None
        result: Any = None
        try:
            result = await super().call_tool(name, arguments)
            return result
        except BaseException as e:
            err = f"{type(e).__name__}: {e}"
            raise
        finally:
            if not skip:
                duration_ms = (time.perf_counter() - t0) * 1000
                try:
                    await anyio.to_thread.run_sync(
                        audit_log_tool_invocation_sync,
                        cfg,
                        aud,
                        name,
                        arguments,
                        result,
                        err,
                        duration_ms,
                    )
                except Exception as ex:  # noqa: BLE001
                    _log.warning("tool audit scheduling failed: %s", ex)
