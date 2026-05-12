"""Префикс путей веб-UI (reverse proxy / занятый /api на другом сервисе)."""

from __future__ import annotations

import os


def normalize_ui_base_path() -> str:
    """
    SDOCS_MCP_UI_BASE_PATH: префикс перед /api/status, /health и т.д.
    Пусто или "/" — без префикса (как раньше).
    Пример: /mcp-server → маршруты /mcp-server/api/status, /mcp-server/health.
    """
    raw = (os.environ.get("SDOCS_MCP_UI_BASE_PATH") or "").strip()
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or ""
