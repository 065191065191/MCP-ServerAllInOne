"""Единая верхняя навигация веб-UI (дашборд, консоль, крон, метрики)."""

from __future__ import annotations

from typing import Literal

NavPage = Literal["dash", "ops", "cron", "status"]

_NAV_LINKS: tuple[tuple[NavPage, str, str], ...] = (
    ("dash", "/", "Дашборд"),
    ("ops", "/ops", "Консоль"),
    ("cron", "/cron-page", "Крон и allowlist Postgres"),
    ("status", "/status-page", "Статус и /metrics"),
)

TOP_NAV_STYLES = """
    nav.stack-mcp-topnav {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.5rem;
      margin: 0 0 0.85rem;
      padding: 0.5rem 0.65rem;
      border-radius: 10px;
      border: 1px solid color-mix(in srgb, currentColor 18%, transparent);
      background: color-mix(in srgb, currentColor 6%, transparent);
      font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
    }
    nav.stack-mcp-topnav a {
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 500;
      padding: 0.28rem 0.65rem;
      border-radius: 7px;
      color: inherit;
      opacity: 0.88;
      border: 1px solid transparent;
      transition: opacity 0.15s, background 0.15s, border-color 0.15s;
    }
    nav.stack-mcp-topnav a:hover {
      opacity: 1;
      text-decoration: underline;
      text-underline-offset: 3px;
    }
    nav.stack-mcp-topnav a.is-active {
      opacity: 1;
      font-weight: 650;
      cursor: default;
      pointer-events: none;
      background: color-mix(in srgb, currentColor 12%, transparent);
      border-color: color-mix(in srgb, currentColor 22%, transparent);
    }
    nav.stack-mcp-topnav .stack-mcp-nav-sep {
      opacity: 0.35;
      user-select: none;
      font-size: 0.7rem;
      padding: 0 0.1rem;
    }
"""


def render_top_nav(current: NavPage) -> str:
    parts: list[str] = [
        '<nav class="stack-mcp-topnav" aria-label="Разделы веб-интерфейса stack-mcp">'
    ]
    for i, (pid, href, label) in enumerate(_NAV_LINKS):
        if i:
            parts.append('<span class="stack-mcp-nav-sep" aria-hidden="true">·</span>')
        if pid == current:
            parts.append(
                f'<a href="{href}" class="is-active" aria-current="page">{_esc(label)}</a>'
            )
        else:
            parts.append(f'<a href="{href}">{_esc(label)}</a>')
    parts.append("</nav>")
    return "".join(parts)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def inject_top_nav(html_fragment: str, current: NavPage) -> str:
    """Подставляет разметку навигации вместо маркера {{TOPNAV}} + добавляет стили {{TOPNAV_STYLES}} в <head>."""
    out = html_fragment.replace("{{TOPNAV}}", render_top_nav(current))
    out = out.replace("{{TOPNAV_STYLES}}", TOP_NAV_STYLES)
    return out
