"""HTTP-контекст для аудита MCP tools: кто вызвал (заголовок, IP) через ContextVar."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from stack_mcp.config import OpenSearchToolCallAuditConfig

_var: ContextVar[_HttpCallerHints | None] = ContextVar("stack_mcp_tool_audit_http_hints", default=None)


@dataclass(frozen=True, slots=True)
class _HttpCallerHints:
    header_caller: str
    client_host: str


def current_http_caller_hints() -> _HttpCallerHints:
    h = _var.get()
    if h is None:
        return _HttpCallerHints(header_caller="", client_host="")
    return h


@contextmanager
def http_caller_hints_override(header_caller: str = "", client_host: str = ""):
    """Для тестов: временно подставить значения, как из ASGI middleware."""
    token = _var.set(_HttpCallerHints(header_caller=header_caller, client_host=client_host))
    try:
        yield
    finally:
        _var.reset(token)


class ToolAuditCallerMiddleware:
    """ASGI: для запросов к MCP сохраняет в ContextVar имя из заголовка и client host."""

    def __init__(
        self,
        app,
        audit_cfg: OpenSearchToolCallAuditConfig,
        path_prefix: str | None = None,
    ) -> None:
        self.app = app
        self.audit_cfg = audit_cfg
        self.path_prefix = path_prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if self.path_prefix is not None and not path.startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        hdr_val = ""
        header_name = (self.audit_cfg.caller_http_header or "").strip()
        if header_name:
            want = header_name.lower().encode("ascii")
            for k, v in scope.get("headers") or []:
                if k.lower() == want:
                    hdr_val = v.decode("latin-1", errors="replace").strip()
                    break

        client_host = ""
        client = scope.get("client")
        if isinstance(client, (list, tuple)) and client and client[0]:
            client_host = str(client[0]).strip()

        token = _var.set(_HttpCallerHints(header_caller=hdr_val, client_host=client_host))
        try:
            await self.app(scope, receive, send)
        finally:
            _var.reset(token)
