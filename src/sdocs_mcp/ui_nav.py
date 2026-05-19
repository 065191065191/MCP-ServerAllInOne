"""Единая верхняя навигация веб-UI (дашборд, консоль, метрики)."""

from __future__ import annotations

from typing import Literal

from sdocs_mcp.ui_paths import normalize_ui_base_path, ui_pages_base

NavPage = Literal["dash", "ops", "status", "cron", "alerts"]

_NAV_LINKS: tuple[tuple[NavPage, str, str], ...] = (
    ("dash", "/", "Дашборд"),
    ("ops", "/ops", "Консоль"),
    ("status", "/status-page", "Статус и /metrics"),
    ("cron", "/cron-page", "Cron"),
    ("alerts", "/alerts-page", "Alert"),
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
    out = html_fragment.replace("{{TOPNAV}}", render_top_nav(current, ui_pages_base()))
    out = out.replace("{{TOPNAV_STYLES}}", TOP_NAV_STYLES)
    return out


# Те же токены и поведение, что у главного дашборда (executive_dashboard_html), плюс алиасы для старых имён переменных в /ops.
SUBPAGE_SKIN_STYLES = """
    nav.sdocs-mcp-topnav {
      border-color: var(--border);
      background: var(--card-bg);
    }
    nav.sdocs-mcp-topnav a:not(.is-active) { color: var(--accent); }
    nav.sdocs-mcp-topnav a.is-active { color: var(--text-primary); }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    :root {
      --bg-gradient: linear-gradient(165deg, #0b0f14 0%, #121826 50%, #0d1219 100%);
      --accent: #e8c07d;
      --accent-dim: rgba(232, 192, 125, 0.22);
      --accent-gradient: linear-gradient(rgba(232, 192, 125, 0.14), #121826 92%);
      --text-primary: #f4f1ea;
      --text-muted: rgba(244, 241, 234, 0.72);
      --card-bg: rgba(18, 24, 38, 0.65);
      --border: rgba(232, 192, 125, 0.22);
      --success: rgba(100, 200, 100, 0.8);
      --danger: rgba(200, 100, 100, 0.8);
      --warning: rgba(232, 192, 125, 0.6);
      --bg-primary: #0b0f14;
      --bg-card: rgba(18, 24, 38, 0.65);
      --bg-card-light: rgba(18, 24, 38, 0.8);
      --border-light: var(--border);
      --text-secondary: var(--text-muted);
      --accent-green: var(--accent);
      --accent-gold: var(--accent);
      --bg: transparent;
      --surface: var(--card-bg);
      --surface2: rgba(18, 24, 38, 0.8);
      --text: var(--text-primary);
      --muted: var(--text-muted);
      --accent-soft: var(--accent-dim);
      --ok: var(--success);
      --ok-bg: rgba(100, 200, 100, 0.15);
      --bad: var(--danger);
      --bad-bg: rgba(200, 100, 100, 0.15);
      --skip: var(--text-muted);
      --skip-bg: rgba(244, 241, 234, 0.08);
      --radius: 0.8rem;
      --radius-sm: 0.5rem;
      font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg-gradient);
      color: var(--text-primary);
      line-height: 1.55;
      padding: clamp(1rem, 2vw, 2rem);
      font-family: inherit;
      transition: background 0.2s, color 0.2s;
    }
    h1, h2 {
      color: var(--accent);
      text-transform: uppercase;
      border-bottom: 1px solid var(--accent-dim);
    }
    h3 { color: var(--text-primary); }
    .card, .panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      backdrop-filter: blur(10px);
      transition: all 0.2s ease;
    }
    .card:hover, .panel:hover {
      border-color: var(--accent);
      background: rgba(18, 24, 38, 0.8);
    }
    table { border-collapse: collapse; width: 100%; }
    th {
      background: rgba(232, 192, 125, 0.08);
      color: var(--accent);
      text-transform: uppercase;
      font-size: 0.72rem;
    }
    td, th { border: 1px solid var(--border); padding: 0.65rem 0.85rem; }
    tr { transition: all 0.2s ease; }
    tr:hover td { background: rgba(232, 192, 125, 0.1); }
    .check { color: var(--success); }
    .cross { color: var(--danger); }
    .warn { color: var(--warning); }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.6rem;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      transition: all 0.2s ease;
    }
    .badge-success, .badge-ok { background: rgba(100,200,100,0.15); color: var(--success); border: 1px solid var(--success); }
    .badge-warning, .badge-on { background: rgba(232,192,125,0.15); color: var(--accent); border: 1px solid var(--accent); }
    .badge-danger, .badge-bad { background: rgba(200,100,100,0.15); color: var(--danger); border: 1px solid var(--danger); }
    .badge-skip, .badge-off { background: rgba(244,241,234,0.08); color: var(--text-muted); border: 1px solid var(--border); }
    input, textarea, select {
      background: rgba(18, 24, 38, 0.8);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 0.75rem 1rem;
      color: var(--text-primary);
      font-family: inherit;
    }
    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: var(--accent);
    }
    button {
      background: var(--accent-dim);
      border: 1px solid var(--accent);
      border-radius: var(--radius-sm);
      padding: 0.5rem 1.2rem;
      color: var(--accent);
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    button:hover {
      background: var(--accent);
      color: #121826;
    }
    .comparison-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 0.75rem;
    }
    @media (max-width: 768px) {
      .comparison-grid { grid-template-columns: 1fr; }
      table { font-size: 0.75rem; }
      th, td { padding: 0.5rem; }
    }
    .dashboard { max-width: 1600px; margin: 0 auto; }
    .subpage-content { max-width: 1120px; }
    .dashboard-footer {
      margin-top: 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      font-size: 11px;
      color: var(--text-muted);
      flex-wrap: wrap;
      gap: 12px;
    }
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
    out = (
        html_fragment.replace("{{SUBPAGE_SKIN}}", SUBPAGE_SKIN_STYLES)
        .replace("{{UI_BASE_PATH}}", normalize_ui_base_path())
        .replace("{{UI_PAGES_BASE}}", ui_pages_base())
    )
    return inject_top_nav(out, current)
