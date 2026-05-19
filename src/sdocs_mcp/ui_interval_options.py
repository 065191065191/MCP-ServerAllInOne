"""Пресеты интервалов опроса (Cron, Alert)."""

from __future__ import annotations

# (секунды, подпись)
INTERVAL_PRESETS: tuple[tuple[int, str], ...] = (
    (30, "30 сек"),
    (60, "1 мин"),
    (120, "2 мин"),
    (180, "3 мин"),
    (300, "5 мин"),
    (600, "10 мин"),
    (900, "15 мин"),
    (1800, "30 мин"),
    (3600, "1 час"),
    (7200, "2 часа"),
    (10800, "3 часа"),
    (21600, "6 часов"),
    (86400, "24 часа"),
)

INTERVAL_PRESET_SECONDS = frozenset(s for s, _ in INTERVAL_PRESETS)


def render_interval_options(
    *,
    default_seconds: int = 3600,
    selected: int | None = None,
    include_custom: bool = True,
) -> str:
    sel = selected if selected is not None else default_seconds
    parts: list[str] = []
    for sec, label in INTERVAL_PRESETS:
        attr = ' selected' if sec == sel else ""
        parts.append(f'<option value="{sec}"{attr}>{label}</option>')
    if sel not in INTERVAL_PRESET_SECONDS:
        parts.append(f'<option value="{sel}" selected>Сохранённое ({sel} с)</option>')
    if include_custom:
        parts.append('<option value="custom">Свой (мин)…</option>')
    return "\n".join(parts)
