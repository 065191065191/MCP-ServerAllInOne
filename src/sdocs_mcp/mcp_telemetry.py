from __future__ import annotations

import threading

_lock = threading.Lock()
_mcp_http_requests: int = 0


def inc_mcp_http_request() -> None:
    global _mcp_http_requests
    with _lock:
        _mcp_http_requests += 1


def mcp_http_requests_total() -> int:
    with _lock:
        return _mcp_http_requests


class McpHttpMetricsMiddleware:
    """Счётчик HTTP-запросов к MCP (Streamable HTTP / SSE), без /api/* UI."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http":
            inc_mcp_http_request()
        await self.app(scope, receive, send)


def wrap_mcp_http_app(app):
    return McpHttpMetricsMiddleware(app)
