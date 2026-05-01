"""Точка входа браузерного MCP ([ma-pony/mcp-playwright](https://github.com/ma-pony/mcp-playwright)) в том же venv, что и stack-mcp.

Браузеры:

- По умолчанию — кэш пользователя после ``playwright install chromium``.
- **Рядом с проектом** — каталог ``playwright-browsers/`` в корне репозитория (рядом с ``pyproject.toml``) или в **текущей рабочей директории**; если не пустой, выставляется ``PLAYWRIGHT_BROWSERS_PATH`` до импорта Playwright (важно для офлайн-переноса).
- Явно: ``export PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers`` (задайте **до** запуска процесса).

Запуск: ``stack-mcp-playwright`` — Streamable HTTP, по умолчанию ``0.0.0.0:8770``, путь ``/mcp``.
"""
from __future__ import annotations

import os
from pathlib import Path


def _ensure_local_playwright_browsers_path() -> None:
    """Если PLAYWRIGHT_BROWSERS_PATH не задан — пробуем ./playwright-browsers и <repo>/playwright-browsers."""
    if (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip():
        return
    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.append(cwd / "playwright-browsers")
    here = Path(__file__).resolve()
    # editable: .../src/stack_mcp/playwright_http.py → repo root
    if here.parent.name == "stack_mcp" and here.parent.parent.name == "src":
        candidates.append(here.parent.parent.parent / "playwright-browsers")
    for p in candidates:
        try:
            if p.is_dir() and any(p.iterdir()):
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(p.resolve())
                return
        except OSError:
            continue


def main() -> None:
    _ensure_local_playwright_browsers_path()
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        print(f"PLAYWRIGHT_BROWSERS_PATH={os.environ['PLAYWRIGHT_BROWSERS_PATH']}", flush=True)

    from mcp_playwright.server import mcp

    host = (os.environ.get("MCP_PLAYWRIGHT_HOST") or "0.0.0.0").strip()
    port = int((os.environ.get("MCP_PLAYWRIGHT_PORT") or "8770").strip())
    mcp.settings.host = host
    mcp.settings.port = port
    path = getattr(mcp.settings, "streamable_http_path", "/mcp")
    print(f"stack-mcp-playwright (mcp-playwright): http://{host}:{port}{path}", flush=True)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
