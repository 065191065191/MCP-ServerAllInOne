"""Состояние загрузки конфига для MCP, UI и LLM (без пути к файлу в публичном статусе)."""

from __future__ import annotations

import threading
import time
from typing import Any, Literal

from sdocs_mcp.config import AppConfig, load_config

ConfigLoadState = Literal["missing", "ok", "invalid"]

_lock = threading.Lock()
_state: dict[str, Any] = {
    "state": "missing",
    "loaded_at": None,
    "loaded_at_unix": None,
    "message": "Конфиг не загружен",
    "modules_enabled": {},
    "tools_total_on_disk": 0,
    "error": None,
}


def _flags(cfg: AppConfig) -> dict[str, bool]:
    m = cfg.modules
    return {
        "postgres": m.postgres.enabled,
        "redis": m.redis.enabled,
        "kafka": m.kafka.enabled,
        "prometheus": m.prometheus.enabled,
        "mail": m.mail.enabled,
        "opensearch": m.opensearch.enabled,
        "ssh": m.ssh.enabled,
    }


def _tools_total(cfg: AppConfig) -> int:
    from sdocs_mcp.mcp_agent_guide import build_capabilities_payload

    return int(build_capabilities_payload(cfg).get("tools_total", 0))


def record_config_loaded(cfg: AppConfig | None, *, error: str | None = None) -> None:
    """Вызывается после успешной пересборки MCP или явной ошибки разбора."""
    now = time.time()
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    with _lock:
        if error:
            _state.update(
                {
                    "state": "invalid",
                    "loaded_at": iso,
                    "loaded_at_unix": now,
                    "message": "Ошибка конфигурации",
                    "modules_enabled": {},
                    "tools_total_on_disk": 0,
                    "error": error[:500],
                }
            )
            return
        if cfg is None:
            _state.update(
                {
                    "state": "missing",
                    "loaded_at": None,
                    "loaded_at_unix": None,
                    "message": "Конфиг отсутствует — модули не активны",
                    "modules_enabled": {},
                    "tools_total_on_disk": 0,
                    "error": None,
                }
            )
            return
        flags = _flags(cfg)
        any_on = any(flags.values())
        _state.update(
            {
                "state": "ok" if any_on else "missing",
                "loaded_at": iso,
                "loaded_at_unix": now,
                "message": "Конфиг загружен" if any_on else "Конфиг пустой — включите modules.*.enabled",
                "modules_enabled": flags,
                "tools_total_on_disk": _tools_total(cfg),
                "error": None,
            }
        )


def refresh_config_state_from_disk() -> AppConfig:
    """Перечитать YAML и обновить публичное состояние (для API/UI)."""
    try:
        cfg = load_config()
        record_config_loaded(cfg)
        return cfg
    except Exception as e:
        record_config_loaded(None, error=str(e))
        raise


def public_config_status() -> dict[str, Any]:
    """Для UI и sdocs_mcp_status: без пути к файлу."""
    with _lock:
        return {
            "state": _state["state"],
            "message": _state["message"],
            "loaded_at": _state["loaded_at"],
            "modules_enabled": dict(_state["modules_enabled"]),
            "tools_total": _state["tools_total_on_disk"],
            "error": _state["error"],
        }
