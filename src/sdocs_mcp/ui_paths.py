"""Префикс путей веб-UI (reverse proxy / занятый корень / на другом сервисе)."""

from __future__ import annotations

import os

# По умолчанию всё SDocsMCP под /sdocs (корень хоста свободен для других приложений).
_DEFAULT_UI_BASE_PATH = "/sdocs"
_DEFAULT_UI_PAGES_PREFIX = "/console"


def normalize_ui_base_path() -> str:
    """
    SDOCS_MCP_UI_BASE_PATH: префикс для /health, /api/*, /metrics, /mcp, landing.
    По умолчанию /sdocs — не занимать / на общем хосте.
    Пусто или "/" — без префикса (локальная отладка на отдельном порту).
    """
    raw = os.environ.get("SDOCS_MCP_UI_BASE_PATH")
    if raw is None:
        return _DEFAULT_UI_BASE_PATH
    raw = raw.strip()
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or ""


def normalize_ui_pages_prefix() -> str:
    """
    SDOCS_MCP_UI_PAGES_PREFIX: суффикс HTML-страниц относительно UI_BASE.
    По умолчанию /console → /sdocs/console при базе /sdocs.
    Пусто или "/" — страницы прямо под UI_BASE (/sdocs/).
    """
    raw = os.environ.get("SDOCS_MCP_UI_PAGES_PREFIX")
    if raw is None:
        return _DEFAULT_UI_PAGES_PREFIX
    raw = raw.strip()
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or ""


def ui_pages_base() -> str:
    """Полный префикс HTML: UI_BASE + PAGES (по умолчанию /sdocs/console)."""
    base = normalize_ui_base_path()
    pages = normalize_ui_pages_prefix()
    if not pages:
        return base
    return f"{base}{pages}"
