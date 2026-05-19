"""Общая обёртка подстраниц UI (тема + навигация)."""

from __future__ import annotations

from sdocs_mcp.ui_nav import NavPage, inject_subpage
from sdocs_mcp.ui_paths import normalize_ui_base_path

SUBPAGE_LAYOUT_CSS = """
    .shell { max-width: 1120px; margin: 0 auto; }
    .page-head { padding: 0 0 0.85rem; margin-bottom: 0.75rem; border-bottom: 1px solid var(--border); }
    .page-head h1 { margin: 0 0 0.35rem; font-size: 1.1rem; font-weight: 600; letter-spacing: 0.04em; border: none; text-transform: uppercase; }
    .lede { margin: 0; color: var(--text-muted); font-size: 0.82rem; max-width: 52rem; }
    .section-title { margin: 1rem 0 0.35rem; font-size: 0.95rem; font-weight: 600; color: var(--accent); border: none; text-transform: uppercase; }
    .section-note { margin: 0 0 0.65rem; font-size: 0.82rem; color: var(--text-muted); line-height: 1.45; }
    .muted { color: var(--text-muted); font-size: 0.82rem; }
    .field-group { margin: 0.5rem 0 0; }
    .field-label {
      display: block; font-size: 0.68rem; font-weight: 650; text-transform: uppercase;
      letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.25rem;
    }
    .btn-row { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; margin-top: 0.5rem; }
    button.primary { background: var(--accent-dim); border-color: var(--accent); font-weight: 650; }
    .alert { margin: 0.5rem 0; padding: 0.6rem 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--danger); background: var(--bad-bg); font-size: 0.86rem; }
    .alert.warn { border-color: var(--accent); background: rgba(232, 192, 125, 0.12); color: var(--text-primary); }
    pre { background: rgba(18, 24, 38, 0.9); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.65rem; overflow: auto; font-size: 0.78rem; }
    code { font-family: ui-monospace, Consolas, monospace; font-size: 0.85em; padding: 0.1em 0.32em; border-radius: 3px; background: var(--accent-dim); }
    .alerts-grid {
      display: grid;
      gap: 1rem;
      grid-template-columns: 1fr 1fr;
      align-items: start;
    }
    .alerts-grid .panel { padding: 1rem 1.15rem; border: none; }
    .alerts-grid-full { grid-column: 1 / -1; }
    @media (max-width: 900px) { .alerts-grid { grid-template-columns: 1fr; } }
    .groups-editor textarea {
      min-height: 11rem;
      font-family: ui-monospace, Consolas, monospace;
      font-size: 0.8rem;
      line-height: 1.45;
      resize: vertical;
    }
    .cron-settings-row {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: 0.75rem 1.25rem;
      margin: 0.75rem 0;
    }
    .cron-settings-row label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .cron-settings-row label.cron-promql { flex: 1 1 16rem; min-width: 12rem; }
    .cron-settings-row label.cron-promql input { width: 100%; min-width: 0; font-family: ui-monospace, Consolas, monospace; font-size: 0.88rem; padding: 0.45rem 0.55rem; }
    .cron-settings-row label.cron-check { flex-direction: row; align-items: center; text-transform: none; font-size: 0.88rem; color: var(--text-primary); gap: 0.4rem; padding-bottom: 0.35rem; }
    .cron-settings-row select { min-width: 8.5rem; }
    .cron-hint { margin: 0 0 0.75rem; font-size: 0.8rem; color: var(--text-muted); line-height: 1.45; max-width: 52rem; }
    .form-grid { display: grid; gap: 0.65rem; }
    .form-grid label { display: grid; gap: 0.25rem; font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .form-grid input, .form-grid select, .form-grid textarea { width: 100%; }
    .example-box { margin-top: 0.75rem; padding: 0.75rem; border-left: 2px solid var(--accent); background: rgba(232, 192, 125, 0.05); border-radius: 0 0.5rem 0.5rem 0; font-size: 0.8rem; line-height: 1.45; }
    .cron-form { max-width: 56rem; }
    .cron-row { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
    .interval-select-wide { min-width: 9rem; }
"""


def build_subpage_html(
    *,
    title: str,
    page: NavPage,
    body_html: str,
    extra_script: str = "",
) -> str:
    script_block = f"\n  <script>\n{extra_script}\n  </script>\n" if extra_script else ""
    raw = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <script>const __UI_BASE="{{{{UI_BASE_PATH}}}}";</script>
  <style>
{{{{TOPNAV_STYLES}}}}
{{{{SUBPAGE_SKIN}}}}
{SUBPAGE_LAYOUT_CSS}
  </style>
</head>
<body>
  <a class="skip-link" href="#main">К основному содержимому</a>
  <div class="dashboard">
  {{{{TOPNAV}}}}
  <div class="subpage-content">
  <div class="shell" id="main" tabindex="-1">
{body_html}
  </div>
  </div>
  <div class="dashboard-footer">
    <div>SDocsMCP</div>
  </div>
  </div>
{script_block}
</body>
</html>"""
    raw = raw.replace("<div", "<div").replace("</div>", "</div>")
    return inject_subpage(
        raw.replace("{{UI_BASE_PATH}}", normalize_ui_base_path()),
        page,
    )
