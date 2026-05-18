"""Фоновый опрос Prometheus → Kafka (вкладка Cron в UI, конфиг modules.prometheus.metrics_cron)."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from sdocs_mcp.config import AppConfig, load_config
from sdocs_mcp.prometheus_tools import prometheus_export_instant_to_kafka, resolve_kafka_metrics_topic

_log = logging.getLogger("sdocs_mcp.prometheus_cron")

_MIN_INTERVAL = 15
_MAX_INTERVAL = 86_400
# Верхняя граница одного тика (Prometheus timeout + Kafka flush); не блокируем API/UI — только daemon-поток.
_TICK_BUDGET_HINT_SEC = 65


@dataclass
class PrometheusCronRuntime:
    """Переопределения из UI (в памяти процесса)."""

    enabled: bool | None = None
    interval_seconds: int | None = None
    query: str | None = None


@dataclass
class PrometheusCronState:
    configured: bool = False
    ready_reason: str = ""
    running: bool = False
    last_run_at: float | None = None
    last_success_at: float | None = None
    last_error: str | None = None
    last_skip_reason: str | None = None
    runs_total: int = 0
    successes_total: int = 0
    skips_total: int = 0


_lock = threading.Lock()
_runtime = PrometheusCronRuntime()
_state = PrometheusCronState()
_stop = threading.Event()
_thread: threading.Thread | None = None
_workers_warned = False


def _ui_workers() -> int:
    try:
        return max(1, int(os.environ.get("SDOCS_MCP_UI_WORKERS", "1")))
    except ValueError:
        return 1


def cron_readiness(cfg: AppConfig) -> tuple[bool, str]:
    prom = cfg.modules.prometheus
    kafka = cfg.modules.kafka
    if not prom.enabled:
        return False, "MCP Prometheus не настроен: modules.prometheus.enabled: false."
    if not (prom.base_url or "").strip():
        return False, "MCP Prometheus не настроен: не задан modules.prometheus.base_url."
    if not kafka.enabled:
        return False, "Для выгрузки в Kafka нужен modules.kafka.enabled: true."
    if not kafka.allow_produce:
        return False, "Для выгрузки нужен modules.kafka.allow_produce: true."
    try:
        topic = resolve_kafka_metrics_topic(prom, None)
    except ValueError as e:
        return False, str(e)
    if topic not in kafka.topic_allowlist:
        return (
            False,
            f"Топик {topic!r} должен быть в kafka.topic_allowlist.",
        )
    return True, "ok"


def _effective_settings(cfg: AppConfig) -> dict[str, Any]:
    prom = cfg.modules.prometheus
    cron = prom.metrics_cron
    with _lock:
        enabled = cron.enabled if _runtime.enabled is None else _runtime.enabled
        interval = (
            _runtime.interval_seconds
            if _runtime.interval_seconds is not None
            else cron.interval_seconds
        )
        query = (_runtime.query if _runtime.query is not None else cron.query).strip() or "up"
    interval = max(_MIN_INTERVAL, min(_MAX_INTERVAL, int(interval)))
    topic = resolve_kafka_metrics_topic(prom, None)
    return {
        "enabled": bool(enabled),
        "interval_seconds": interval,
        "query": query,
        "topic": topic,
        "base_url": (prom.base_url or "").strip(),
    }


def get_cron_status() -> dict[str, Any]:
    cfg = load_config()
    ready, reason = cron_readiness(cfg)
    eff = _effective_settings(cfg)
    intent_enabled = eff["enabled"]
    active = intent_enabled and ready
    with _lock:
        st = _state
    return {
        "configured": ready,
        "ready_reason": reason if not ready else "Prometheus и Kafka настроены для экспорта.",
        "enabled": intent_enabled,
        "active": active,
        "running": st.running,
        "interval_seconds": eff["interval_seconds"],
        "query": eff["query"],
        "kafka_topic": eff["topic"],
        "prometheus_base_url": eff["base_url"],
        "last_run_at": st.last_run_at,
        "last_success_at": st.last_success_at,
        "last_error": st.last_error,
        "last_skip_reason": st.last_skip_reason,
        "runs_total": st.runs_total,
        "successes_total": st.successes_total,
        "skips_total": st.skips_total,
        "tick_budget_hint_seconds": _TICK_BUDGET_HINT_SEC,
        "ui_workers": _ui_workers(),
        "mcp_tools_hint": (
            "Сначала prometheus_mcp_guide. Запросы: prometheus_query_instant, prometheus_query_range, "
            "prometheus_targets, prometheus_alerts. В Kafka: prometheus_export_instant_to_kafka "
            f"(топик по умолчанию {eff['topic']!r}). Не путать с HTTP /metrics — метрики самого SDocsMCP."
        ),
    }


def apply_cron_runtime(
    *,
    enabled: bool | None = None,
    interval_seconds: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    with _lock:
        if enabled is not None:
            _runtime.enabled = enabled
        if interval_seconds is not None:
            _runtime.interval_seconds = max(_MIN_INTERVAL, min(_MAX_INTERVAL, int(interval_seconds)))
        if query is not None:
            q = str(query).strip()
            if not q:
                raise ValueError("query must be non-empty")
            _runtime.query = q
    return get_cron_status()


def _run_once() -> None:
    cfg = load_config()
    eff = _effective_settings(cfg)
    ready, reason = cron_readiness(cfg)
    now = time.time()
    with _lock:
        _state.runs_total += 1
        _state.last_run_at = now
        if not eff["enabled"]:
            _state.skips_total += 1
            _state.last_skip_reason = "Cron выключен (metrics_cron.enabled или UI)."
            return
        if not ready:
            _state.skips_total += 1
            _state.last_skip_reason = reason
            return
        _state.running = True
        _state.last_skip_reason = None
    try:
        prometheus_export_instant_to_kafka(
            cfg.modules.prometheus,
            cfg.modules.kafka,
            eff["query"],
            topic=None,
            message_key="metrics_cron",
        )
    except Exception as e:
        with _lock:
            _state.last_error = str(e)[:500]
            _state.running = False
        _log.warning("prometheus metrics cron failed: %s", e)
        return
    with _lock:
        _state.successes_total += 1
        _state.last_success_at = now
        _state.last_error = None
        _state.running = False
    _log.info(
        "prometheus metrics cron ok query=%r topic=%r",
        eff["query"],
        eff["topic"],
    )


def _loop() -> None:
    # Первый тик сразу после старта, дальше — пауза после завершения (не до).
    while not _stop.is_set():
        try:
            _run_once()
        except Exception:
            _log.exception("prometheus metrics cron tick")
        if _stop.is_set():
            break
        try:
            cfg = load_config()
            interval = _effective_settings(cfg)["interval_seconds"]
        except Exception as e:
            _log.exception("prometheus cron settings: %s", e)
            interval = 60
        if _stop.wait(timeout=interval):
            break


def start_prometheus_metrics_cron() -> None:
    global _thread, _workers_warned
    if os.environ.get("SDOCS_MCP_PROMETHEUS_CRON", "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        _log.info("prometheus metrics cron disabled (SDOCS_MCP_PROMETHEUS_CRON)")
        return
    workers = _ui_workers()
    if workers > 1 and not _workers_warned:
        _workers_warned = True
        _log.warning(
            "SDOCS_MCP_UI_WORKERS=%s: в каждом воркере свой поток Cron → дубли в Kafka. "
            "Для одной выгрузки используйте workers=1 или SDOCS_MCP_PROMETHEUS_CRON=false "
            "на всех воркерах кроме одного.",
            workers,
        )
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="prometheus-metrics-cron", daemon=True)
    _thread.start()
    _log.info("prometheus metrics cron thread started")


def stop_prometheus_metrics_cron() -> None:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=_TICK_BUDGET_HINT_SEC + 5)
        if _thread.is_alive():
            _log.warning(
                "prometheus metrics cron thread did not stop within timeout "
                "(возможен зависший HTTP/Kafka в тике)"
            )
        _thread = None
    with _lock:
        _state.running = False
    _log.info("prometheus metrics cron thread stopped")
