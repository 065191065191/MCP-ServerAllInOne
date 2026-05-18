from __future__ import annotations

import logging
from datetime import datetime, timezone
from logging.handlers import WatchedFileHandler
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from sdocs_mcp.config import AccessLogConfig

_ACCESS_LOGGER = "sdocs_mcp.access"


def setup_http_access_logging(cfg: AccessLogConfig) -> logging.Logger:
    log = logging.getLogger(_ACCESS_LOGGER)
    log.setLevel(logging.INFO)
    log.propagate = False
    if log.handlers:
        return log
    fmt = logging.Formatter("%(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    log_dir = Path(cfg.directory).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = WatchedFileHandler(log_dir / cfg.filename, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return log


def nginx_combined_line(request: Request, status: int, body_bytes: int) -> str:
    client = request.client.host if request.client else "-"
    now = datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S +0000")
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    proto = f"HTTP/{request.scope.get('http_version', '1.1')}"
    referer = request.headers.get("referer") or "-"
    ua = request.headers.get("user-agent") or "-"
    return (
        f'{client} - - [{now}] "{request.method} {path} {proto}" '
        f"{status} {body_bytes} \"{referer}\" \"{ua}\""
    )


def _response_size(response: Response) -> int:
    cl = response.headers.get("content-length")
    if cl and cl.isdigit():
        return int(cl)
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)):
        return len(body)
    return 0


class NginxAccessLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._log = logging.getLogger(_ACCESS_LOGGER)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        self._log.info(nginx_combined_line(request, response.status_code, _response_size(response)))
        return response


def install_access_logging(app: ASGIApp, cfg: AccessLogConfig) -> None:
    if not cfg.enabled:
        return
    setup_http_access_logging(cfg)
    app.add_middleware(NginxAccessLogMiddleware)
