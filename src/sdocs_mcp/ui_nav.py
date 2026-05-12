"""Единая верхняя навигация веб-UI (дашборд, консоль, метрики)."""

from __future__ import annotations

from typing import Literal

from sdocs_mcp.ui_paths import normalize_ui_base_path

NavPage = Literal["dash", "ops", "status"]

_NAV_LINKS: tuple[tuple[NavPage, str, str], ...] = (
    ("dash", "/", "Дашборд"),
    ("ops", "/ops", "Консоль"),
    ("status", "/status-page", "Статус и /metrics"),
)

TOP_NAV_STYLES = """
    nav.sdocs-mcp-topnav {
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
    nav.sdocs-mcp-topnav a {
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
    nav.sdocs-mcp-topnav a:hover {
      opacity: 1;
      text-decoration: underline;
      text-underline-offset: 3px;
    }
    nav.sdocs-mcp-topnav a.is-active {
      opacity: 1;
      font-weight: 650;
      cursor: default;
      pointer-events: none;
      background: color-mix(in srgb, currentColor 12%, transparent);
      border-color: color-mix(in srgb, currentColor 22%, transparent);
    }
    nav.sdocs-mcp-topnav .sdocs-mcp-nav-sep {
      opacity: 0.35;
      user-select: none;
      font-size: 0.7rem;
      padding: 0 0.1rem;
    }
"""


def _abs_href(ui_base: str, path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return (ui_base + path) if ui_base else path


def render_top_nav(current: NavPage, ui_base: str = "") -> str:
    parts: list[str] = [
        '<nav class="sdocs-mcp-topnav" aria-label="Разделы веб-интерфейса sdocs-mcp">'
    ]
    for i, (pid, href, label) in enumerate(_NAV_LINKS):
        if i:
            parts.append('<span class="sdocs-mcp-nav-sep" aria-hidden="true">·</span>')
        full = _esc(_abs_href(ui_base, href))
        if pid == current:
            parts.append(
                f'<a href="{full}" class="is-active" aria-current="page">{_esc(label)}</a>'
            )
        else:
            parts.append(f'<a href="{full}">{_esc(label)}</a>')
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
    base = normalize_ui_base_path()
    out = html_fragment.replace("{{TOPNAV}}", render_top_nav(current, base))
    out = out.replace("{{TOPNAV_STYLES}}", TOP_NAV_STYLES)
    return out


# Те же токены и поведение, что у главного дашборда (executive_dashboard_html), плюс алиасы для старых имён переменных в /ops.
SUBPAGE_SKIN_STYLES = """
    nav.sdocs-mcp-topnav {
      border-color: var(--border-light);
      background: var(--bg-card-light);
    }
    nav.sdocs-mcp-topnav a:not(.is-active) { color: var(--accent-green); }
    nav.sdocs-mcp-topnav a.is-active { color: var(--text-primary); }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    :root {
      --bg-primary: #020304;
      --bg-card: #080b10;
      --bg-card-light: #0d0f16;
      --border-color: #171b23;
      --border-light: #1a1e28;
      --text-primary: #eef3ff;
      --text-secondary: #8d99ab;
      --text-muted: #5a6675;
      --accent-green: #10b981;
      --accent-gold: #f0b90b;
      --accent-green-glow: #10b98130;
      --bg: var(--bg-primary);
      --surface: var(--bg-card);
      --surface2: var(--bg-card-light);
      --text: var(--text-primary);
      --muted: var(--text-secondary);
      --border: var(--border-color);
      --accent: var(--accent-green);
      --accent-soft: rgba(16, 185, 129, 0.14);
      --ok: #10b981;
      --ok-bg: rgba(16, 185, 129, 0.12);
      --bad: #f97316;
      --bad-bg: rgba(249, 115, 22, 0.12);
      --skip: #6b7280;
      --skip-bg: rgba(107, 114, 128, 0.15);
      --radius: 20px;
      --radius-sm: 12px;
      font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    body.light {
      --bg-primary: #f5f7fc;
      --bg-card: #ffffff;
      --bg-card-light: #f8f9fe;
      --border-color: #e2e8f0;
      --border-light: #e2edf2;
      --text-primary: #1a202c;
      --text-secondary: #4a5568;
      --text-muted: #718096;
      --accent-green: #059669;
      --accent-gold: #b45309;
      --accent-green-glow: #05966920;
      --bg: var(--bg-primary);
      --surface: var(--bg-card);
      --surface2: var(--bg-card-light);
      --text: var(--text-primary);
      --muted: var(--text-secondary);
      --border: var(--border-color);
      --accent: var(--accent-green);
      --accent-soft: rgba(5, 150, 105, 0.12);
      --ok-bg: rgba(5, 150, 105, 0.12);
      --bad-bg: rgba(234, 88, 12, 0.12);
      --skip-bg: rgba(100, 116, 139, 0.12);
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.55;
      padding: 32px 40px;
      font-family: inherit;
      transition: background 0.2s, color 0.2s;
    }
    @media (max-width: 640px) {
      body { padding: 20px 16px; }
    }
    .dashboard { max-width: 1600px; margin: 0 auto; }
    .subpage-content { max-width: 1120px; }
    .dashboard-footer {
      margin-top: 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 20px;
      border-top: 0.5px solid var(--border-light);
      font-size: 11px;
      color: var(--text-muted);
      flex-wrap: wrap;
      gap: 12px;
    }
    .theme-switch {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--bg-card-light);
      padding: 4px 12px;
      border-radius: 40px;
      cursor: pointer;
    }
    .theme-switch .toggle-track {
      width: 36px;
      height: 18px;
      background: var(--border-light);
      border-radius: 30px;
      position: relative;
      transition: 0.2s;
    }
    .theme-switch .toggle-track .toggle-thumb {
      width: 14px;
      height: 14px;
      background: var(--text-primary);
      border-radius: 14px;
      position: absolute;
      top: 2px;
      left: 2px;
      transition: 0.2s;
    }
    body.light .theme-switch .toggle-track .toggle-thumb { left: 20px; }
    .skip-link {
      position: absolute;
      left: -9999px;
      z-index: 999;
      padding: 0.5rem 1rem;
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      text-decoration: none;
    }
    .skip-link:focus { left: 1rem; top: 1rem; }
"""


def inject_subpage(html_fragment: str, current: NavPage) -> str:
    """Дашборд-скин + topnav для вспомогательных HTML-страниц ({{SUBPAGE_SKIN}}, {{TOPNAV}}, {{TOPNAV_STYLES}})."""
    b = normalize_ui_base_path()
    out = (
        html_fragment.replace("{{SUBPAGE_SKIN}}", SUBPAGE_SKIN_STYLES)
        .replace("{{UI_BASE_PATH}}", b)
    )
    return inject_top_nav(out, current)
