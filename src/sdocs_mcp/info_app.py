from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import socket
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

import httpx
import psycopg
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from kafka import KafkaConsumer, TopicPartition
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sdocs_mcp.backend_tls import (
    make_postgres_conninfo,
    prometheus_httpx_verify_and_cert,
)
from sdocs_mcp.config import AppConfig, config_path_for_display, load_config
from sdocs_mcp.config_yaml_patch import patch_modules_s3_mcp
from sdocs_mcp.executive_dashboard_html import DASHBOARD_HTML
from sdocs_mcp.ui_alerts_page import ALERTS_PAGE_HTML
from sdocs_mcp.ui_cron_page import CRON_PAGE_HTML
from sdocs_mcp.kafka_tools import kafka_broker_client_config
from sdocs_mcp.http_access_log import install_access_logging
from sdocs_mcp.mcp_telemetry import mcp_http_requests_total, wrap_mcp_http_app
from sdocs_mcp.mail_tools import _imap_user, mail_imap_verify, mail_smtp_send
from sdocs_mcp.mtls import resolve_mcp_mtls_uvicorn_kwargs
from sdocs_mcp.opensearch_tools import close_opensearch_client, connect_opensearch
from sdocs_mcp.postgres_tools import postgres_allowlisted_query_catalog
from sdocs_mcp.redis_tools import redis_ping, redis_setex
from sdocs_mcp.alerts_evaluator import rule_ui_statuses
from sdocs_mcp.alerts_notify import notify_log_snapshot
from sdocs_mcp.alerts_kafka_resolve import alerts_kafka_ready, resolve_alerts_kafka
from sdocs_mcp.alerts_kafka_sync import is_alert_leader, publish_rules_snapshot, start_alerts_kafka_sync, stop_alerts_kafka_sync
from sdocs_mcp.alerts_mcp_sources import list_sources
from sdocs_mcp.alerts_store import save_from_ui, snapshot as alerts_snapshot
from sdocs_mcp.config_runtime import public_config_status, refresh_config_state_from_disk
from sdocs_mcp.embedded_mcp import (
    EmbeddedMcpHolder,
    config_reload_interval_seconds,
    config_wait_seconds,
)
from sdocs_mcp.kafka_topics import SDOCS_KAFKA_TOPICS_CREATE, TOPIC_NOTES
from sdocs_mcp.server import build_mcp
from sdocs_mcp.tool_audit_http_context import ToolAuditCallerMiddleware
from sdocs_mcp.ui_nav import inject_subpage
from sdocs_mcp.ui_paths import (
    normalize_ui_base_path,
    normalize_ui_pages_prefix,
    ui_pages_base,
)

# Безопасный список: только чтение / диагностика + статус (без произвольного SQL и т.д.).
_INVOKE_ALLOWLIST: dict[str, dict[str, Any] | None] = {
    "sdocs_mcp_status": {},
    "redis_ping": {},
    "redis_info": {},
    "redis_dbsize": {},
    "postgres_connections_overview": {},
    "postgres_database_sizes": {},
    "postgres_table_sizes": {},
    "opensearch_cluster_health": {},
    "opensearch_rag_policy": {},
    "opensearch_list_indices": {"pattern": "*"},
    "kafka_list_topics": {},
    "kafka_describe_topic": {"topic": "demo.events"},
    "kafka_consume_recent": {"topic": "demo.events", "partition": 0, "max_messages": 5},
}

UI_BASE = normalize_ui_base_path()
UI_PAGES = normalize_ui_pages_prefix()

# Встроенный MCP: session_manager в lifespan; конфиг — wait + reload (embedded_mcp.py).
_embedded_mcp_holder: EmbeddedMcpHolder | None = None


@asynccontextmanager
async def _app_lifespan(_application: FastAPI):
    from sdocs_mcp.prometheus_cron import (
        start_prometheus_metrics_cron,
        stop_prometheus_metrics_cron,
    )

    start_prometheus_metrics_cron()
    start_alerts_kafka_sync()
    stop = asyncio.Event()
    sm_task: asyncio.Task[None] | None = None
    try:
        if _embedded_mcp_holder is not None:
            sm_task = asyncio.create_task(_embedded_mcp_holder.run_session_manager_loop(stop))
        yield
    finally:
        stop.set()
        if sm_task is not None:
            sm_task.cancel()
            try:
                await sm_task
            except asyncio.CancelledError:
                pass
        stop_alerts_kafka_sync()
        stop_prometheus_metrics_cron()


app = FastAPI(title="SDocsMCP UI", version="0.7.2", lifespan=_app_lifespan)
web_router = APIRouter()
pages_router = APIRouter()

install_access_logging(app, load_config().logging)

_trusted_hosts_raw = (os.environ.get("SDOCS_MCP_UI_TRUSTED_HOSTS") or "").strip()
if _trusted_hosts_raw:
    _trusted_hosts = [h.strip() for h in _trusted_hosts_raw.split(",") if h.strip()]
    if _trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)


_API_TOKEN = (os.environ.get("SDOCS_MCP_UI_TOKEN") or "").strip()
_ENABLE_INVOKE = os.environ.get("SDOCS_MCP_UI_ENABLE_INVOKE", "false").strip().lower() == "true"
_ENABLE_SEED = os.environ.get("SDOCS_MCP_UI_ENABLE_SEED", "false").strip().lower() == "true"
_RATE_LIMIT_RPM = max(1, int(os.environ.get("SDOCS_MCP_UI_RATE_LIMIT_RPM", "60")))
_AUDIT_LOG_PATH = Path(os.environ.get("SDOCS_MCP_UI_AUDIT_LOG_PATH", "logs/ui-audit.log"))

# /metrics (и опционально тот же секрет в UI status-page): без IP-whitelist, только shared secret.
_METRICS_TOKEN = (os.environ.get("SDOCS_MCP_METRICS_TOKEN") or "").strip()
_METRICS_REQUIRE_TOKEN = os.environ.get("SDOCS_MCP_METRICS_REQUIRE_TOKEN", "false").strip().lower() == "true"
_METRICS_ACCEPT_UI_BEARER = os.environ.get("SDOCS_MCP_METRICS_ACCEPT_UI_BEARER", "false").strip().lower() == "true"
_METRICS_RATE_LIMIT_RPM = max(1, int(os.environ.get("SDOCS_MCP_METRICS_RATE_LIMIT_RPM", "120")))


class _RateLimiter:
    def __init__(self, rpm: int) -> None:
        self._rpm = rpm
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - 60.0
        with self._lock:
            q = self._events[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self._rpm:
                retry_after = max(1, int(60 - (now - q[0])))
                return False, retry_after
            q.append(now)
            return True, 0


_RATE_LIMITER = _RateLimiter(_RATE_LIMIT_RPM)
_METRICS_LIMITER = _RateLimiter(_METRICS_RATE_LIMIT_RPM)
_AUDIT_LOCK = threading.Lock()
_METRICS_LOCK = threading.Lock()
_UI_METRICS: dict[str, float] = {
    "requests_total": 0.0,
    "auth_failed_total": 0.0,
    "rate_limited_total": 0.0,
    "request_errors_total": 0.0,
    "request_latency_sum_seconds": 0.0,
    "request_latency_count": 0.0,
    "metrics_auth_failed_total": 0.0,
}


def _metrics_inc(name: str, value: float = 1.0) -> None:
    with _METRICS_LOCK:
        _UI_METRICS[name] = _UI_METRICS.get(name, 0.0) + value


def _audit_log(event: dict[str, Any]) -> None:
    _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    with _AUDIT_LOCK:
        with _AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "").strip()
    if fwd:
        return fwd.split(",")[0].strip()
    if req.client and req.client.host:
        return req.client.host
    return "unknown"


def _auth_token_ok(req: Request) -> bool:
    if not _API_TOKEN:
        return True
    header = req.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    token = header[7:]
    return hmac.compare_digest(token, _API_TOKEN)


def _metrics_auth_required() -> bool:
    return bool(_METRICS_TOKEN) or _METRICS_ACCEPT_UI_BEARER or _METRICS_REQUIRE_TOKEN


def _metrics_secret_from_request(req: Request) -> str | None:
    header = req.headers.get("authorization", "")
    if header.startswith("Bearer "):
        s = header[7:].strip()
        return s or None
    x = req.headers.get("x-sdocs-mcp-metrics-token", "").strip()
    if x:
        return x
    q = req.query_params.get("metrics_token")
    if q is not None:
        s = str(q).strip()
        return s or None
    return None


def _metrics_secret_ok(secret: str) -> bool:
    if _METRICS_TOKEN and hmac.compare_digest(secret, _METRICS_TOKEN):
        return True
    if _METRICS_ACCEPT_UI_BEARER and _API_TOKEN and hmac.compare_digest(secret, _API_TOKEN):
        return True
    return False


def _secure_metrics(req: Request) -> None:
    """Защита /metrics: rate limit + shared secret (без IP whitelist)."""
    ip = _client_ip(req)
    allowed, retry = _METRICS_LIMITER.check(ip)
    if not allowed:
        _audit_log(
            {
                "ts": int(time.time()),
                "event": "metrics_rate_limit",
                "ip": ip,
                "path": str(req.url.path),
                "retry_after_sec": retry,
            }
        )
        raise HTTPException(status_code=429, detail=f"metrics rate limit exceeded, retry in {retry}s")

    if not _metrics_auth_required():
        return

    secret = _metrics_secret_from_request(req)
    if secret is None or not _metrics_secret_ok(secret):
        _metrics_inc("metrics_auth_failed_total", 1.0)
        _audit_log(
            {
                "ts": int(time.time()),
                "event": "metrics_auth_failed",
                "ip": ip,
                "path": str(req.url.path),
            }
        )
        raise HTTPException(status_code=401, detail="metrics unauthorized")


def _secure_api(req: Request, action: str) -> None:
    _metrics_inc("requests_total", 1.0)
    ip = _client_ip(req)
    allowed, retry = _RATE_LIMITER.check(ip)
    if not allowed:
        _metrics_inc("rate_limited_total", 1.0)
        _audit_log(
            {
                "ts": int(time.time()),
                "event": "rate_limit",
                "ip": ip,
                "path": str(req.url.path),
                "action": action,
                "retry_after_sec": retry,
            }
        )
        raise HTTPException(status_code=429, detail=f"rate limit exceeded, retry in {retry}s")

    if not _auth_token_ok(req):
        _metrics_inc("auth_failed_total", 1.0)
        _audit_log(
            {
                "ts": int(time.time()),
                "event": "auth_failed",
                "ip": ip,
                "path": str(req.url.path),
                "action": action,
            }
        )
        raise HTTPException(status_code=401, detail="unauthorized")

    _audit_log(
        {
            "ts": int(time.time()),
            "event": "access",
            "ip": ip,
            "path": str(req.url.path),
            "action": action,
            "method": req.method,
        }
    )


def _record_request_timing(start_perf: float, ok: bool) -> None:
    elapsed = max(0.0, time.perf_counter() - start_perf)
    _metrics_inc("request_latency_sum_seconds", elapsed)
    _metrics_inc("request_latency_count", 1.0)
    if not ok:
        _metrics_inc("request_errors_total", 1.0)


def _rate_limiter_window_stats() -> dict[str, int]:
    now = time.time()
    cutoff = now - 60.0
    with _RATE_LIMITER._lock:
        active_ips = 0
        events = 0
        for q in _RATE_LIMITER._events.values():
            cnt = 0
            for ts in q:
                if ts >= cutoff:
                    cnt += 1
            if cnt > 0:
                active_ips += 1
                events += cnt
    return {"active_ips": active_ips, "events_last_minute": events}


def _cfg() -> AppConfig:
    return load_config()


_DASHBOARD_MODULE_META: tuple[tuple[str, str, str], ...] = (
    ("postgres", "PostgreSQL", "БД"),
    ("redis", "Redis", "Кэш"),
    ("kafka", "Kafka", "Потоки"),
    ("prometheus", "Prometheus", "Метрики"),
    ("opensearch", "OpenSearch", "Поиск / логи"),
    ("mail", "Mail", "Почта"),
    ("ssh", "SSH", "Доступ"),
)


def _build_dashboard_stats(cfg: AppConfig) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {
        "postgres": _check_postgres(cfg),
        "redis": _check_redis(cfg),
        "kafka": _check_kafka(cfg),
        "prometheus": _check_prometheus(cfg),
        "opensearch": _check_opensearch(cfg),
        "mail": _check_mail(cfg),
        "ssh": _check_ssh(cfg),
    }
    me = cfg.modules
    modules_enabled = {
        "postgres": me.postgres.enabled,
        "redis": me.redis.enabled,
        "kafka": me.kafka.enabled,
        "prometheus": me.prometheus.enabled,
        "opensearch": me.opensearch.enabled,
        "mail": me.mail.enabled,
        "ssh": me.ssh.enabled,
    }
    modules_out: list[dict[str, Any]] = []
    for key, label, typ in _DASHBOARD_MODULE_META:
        st = checks[key]
        en = modules_enabled[key]
        lat = st.get("latency_ms")
        latency = int(lat) if isinstance(lat, int) else None
        modules_out.append(
            {
                "id": key,
                "name": label,
                "type": typ,
                "enabled": en,
                "ok": bool(st.get("ok")),
                "skipped": bool(st.get("skipped")),
                "latency_ms": latency,
                "detail": str(st.get("detail", ""))[:300],
            }
        )
    enabled_cnt = sum(1 for v in modules_enabled.values() if v)
    healthy_cnt = sum(1 for k, en in modules_enabled.items() if en and checks[k].get("ok"))
    latencies = [
        int(checks[k]["latency_ms"])
        for k in modules_enabled
        if modules_enabled[k] and isinstance(checks[k].get("latency_ms"), int)
    ]
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    uptime_pct = round(100.0 * healthy_cnt / enabled_cnt, 1) if enabled_cnt else 100.0
    with _METRICS_LOCK:
        snap = dict(_UI_METRICS)
    limiter = _rate_limiter_window_stats()
    return {
        "collected_at": int(time.time()),
        "data_sources_note": (
            "Факт: health и latency — прямые проверки UI к модулям из конфига; "
            "обращения — HTTP к MCP (Streamable HTTP / SSE), не /api/* UI. "
            "Углы «сэкономлено» — расчётная модель (не биллинг и не учёт тикетов)."
        ),
        "roi_model": {
            "is_illustrative": True,
            "formula_short": "(ручное_время − MCP) × инциденты/мес × 1.15 × доля_аптайма модулей",
            "scales_with_period_buttons": True,
        },
        "summary": {
            "mcp_enabled_count": enabled_cnt,
            "mcp_healthy_count": healthy_cnt,
            "mcp_requests_total": mcp_http_requests_total(),
            "ui_requests_total": int(snap.get("requests_total", 0.0)),
            "ui_events_last_minute": limiter["events_last_minute"],
            "ui_active_ips": limiter["active_ips"],
            "avg_check_latency_ms": avg_lat,
            "uptime_score_pct": min(100.0, uptime_pct),
        },
        "modules": modules_out,
        "business_defaults": {
            "rub_per_hour": 1875,
            "incidents_month": 1200,
            "mcp_response_sec": 12,
            "manual_min_min": 3,
            "manual_max_min": 15,
            "complexity_multipliers": {"one_mcp": 1.0, "multi_mcp": 1.4},
        },
    }


def _check_postgres(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.postgres.enabled:
        return {"ok": False, "skipped": True, "detail": "postgres module disabled"}
    t0 = time.perf_counter()
    try:
        with psycopg.connect(make_postgres_conninfo(cfg.modules.postgres), connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                one = cur.fetchone()
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": True, "detail": "SELECT 1", "result": one, "latency_ms": dt_ms}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_redis(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.redis.enabled:
        return {"ok": False, "skipped": True, "detail": "redis module disabled"}
    t0 = time.perf_counter()
    try:
        payload = json.loads(redis_ping(cfg.modules.redis))
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": bool(payload.get("ok")), "detail": "PING", "latency_ms": dt_ms}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_mail(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.mail.enabled:
        return {"ok": False, "skipped": True, "detail": "mail module disabled"}
    t0 = time.perf_counter()
    try:
        payload = json.loads(mail_imap_verify(cfg.modules.mail))
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": bool(payload.get("ok")), "detail": "IMAP login+NOOP", "latency_ms": dt_ms}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_opensearch(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.opensearch.enabled:
        return {"ok": False, "skipped": True, "detail": "opensearch module disabled"}
    t0 = time.perf_counter()
    try:
        m = cfg.modules.opensearch
        client = connect_opensearch(m)
        try:
            h = client.cluster.health()
        finally:
            close_opensearch_client(client)
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": True, "detail": "cluster.health()", "cluster": h.get("cluster_name"), "status": h.get("status"), "latency_ms": dt_ms}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_kafka(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.kafka.enabled:
        return {"ok": False, "skipped": True, "detail": "kafka module disabled"}
    t0 = time.perf_counter()
    try:
        k = cfg.modules.kafka
        consumer = KafkaConsumer(
            **kafka_broker_client_config(k),
            consumer_timeout_ms=8000,
            group_id=f"sdocs-mcp-ui-probe-{int(time.time() * 1000)}",
        )
        try:
            topics = sorted(consumer.topics())
        finally:
            consumer.close()
        dt_ms = int((time.perf_counter() - t0) * 1000)
        has_demo = "demo.events" in topics
        return {
            "ok": True,
            "detail": "metadata topics()",
            "topic_count": len(topics),
            "has_demo_events": has_demo,
            "latency_ms": dt_ms,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_prometheus(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.prometheus.enabled:
        return {"ok": False, "skipped": True, "detail": "prometheus module disabled"}
    t0 = time.perf_counter()
    try:
        p = cfg.modules.prometheus
        headers: dict[str, str] = {}
        if p.bearer_token:
            headers["Authorization"] = f"Bearer {p.bearer_token}"
        elif p.bearer_token_path:
            token_path = Path(p.bearer_token_path)
            if token_path.is_file():
                token = token_path.read_text(encoding="utf-8").strip()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
        auth: httpx.BasicAuth | None = None
        if p.basic_auth_username and p.basic_auth_password is not None:
            auth = httpx.BasicAuth(p.basic_auth_username, p.basic_auth_password)
        verify, cert = prometheus_httpx_verify_and_cert(p)
        with httpx.Client(
            base_url=p.base_url.rstrip("/"),
            headers=headers,
            auth=auth,
            timeout=min(10, p.timeout_seconds),
            verify=verify,
            cert=cert,
        ) as client:
            r = client.get("/api/v1/query", params={"query": "up"})
            r.raise_for_status()
            body = r.json()
        result = body.get("data", {}).get("result")
        sample_count = len(result) if isinstance(result, list) else 0
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": True,
            "detail": "query up",
            "latency_ms": dt_ms,
            "up_samples": sample_count,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _check_ssh(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.ssh.enabled:
        return {"ok": False, "skipped": True, "detail": "ssh module disabled"}
    hosts = cfg.modules.ssh.hosts
    if not hosts:
        return {"ok": False, "detail": "ssh enabled but hosts list is empty"}
    t0 = time.perf_counter()
    max_hosts = 12
    rows: list[dict[str, Any]] = []
    any_tcp_ok = False
    for h in hosts[:max_hosts]:
        try:
            with socket.create_connection((h.hostname, h.port), timeout=min(5, cfg.modules.ssh.connect_timeout_seconds)):
                any_tcp_ok = True
                rows.append({"id": h.id, "hostname": h.hostname, "port": h.port, "ok": True, "detail": "tcp open"})
        except OSError as e:
            rows.append({"id": h.id, "hostname": h.hostname, "port": h.port, "ok": False, "detail": str(e)})
    dt_ms = int((time.perf_counter() - t0) * 1000)
    extra = len(hosts) - max_hosts
    out: dict[str, Any] = {
        "ok": any_tcp_ok,
        "detail": "tcp connect host:port (не проверка SSH-auth)",
        "hosts": rows,
        "latency_ms": dt_ms,
    }
    if extra > 0:
        out["hosts_omitted"] = extra
    return out


def _kafka_queue_load(cfg: AppConfig) -> dict[str, Any]:
    if not cfg.modules.kafka.enabled:
        return {"ok": False, "skipped": True, "detail": "kafka module disabled"}
    topics = cfg.modules.kafka.topic_allowlist[:20]
    if not topics:
        return {"ok": False, "skipped": True, "detail": "empty topic_allowlist"}
    t0 = time.perf_counter()
    try:
        k = cfg.modules.kafka
        consumer = KafkaConsumer(
            **kafka_broker_client_config(k),
            consumer_timeout_ms=8000,
            group_id=None,
        )
        try:
            # Подтянуть metadata (как в _check_kafka), иначе partitions_for_topic часто пустой.
            _ = consumer.topics()
            summary: dict[str, Any] = {}
            total_messages = 0
            for topic in topics:
                partitions = consumer.partitions_for_topic(topic) or set()
                if not partitions:
                    summary[topic] = {"ok": False, "detail": "topic not found or no partitions"}
                    continue
                tps = [TopicPartition(topic, p) for p in partitions]
                begins = consumer.beginning_offsets(tps, timeout=8)
                ends = consumer.end_offsets(tps, timeout=8)
                lag = 0
                partitions_view: list[dict[str, int]] = []
                for tp in tps:
                    begin = int(begins.get(tp, 0))
                    end = int(ends.get(tp, 0))
                    retained = max(0, end - begin)
                    lag += retained
                    partitions_view.append(
                        {"partition": tp.partition, "begin": begin, "end": end, "retained_messages": retained}
                    )
                total_messages += lag
                summary[topic] = {"ok": True, "retained_messages": lag, "partitions": partitions_view}
        finally:
            consumer.close()
        dt_ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": True, "latency_ms": dt_ms, "total_retained_messages": total_messages, "topics": summary}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@web_router.get("/health")
async def health() -> PlainTextResponse:
    """Liveness: без конфига и без авторизации (Docker/Kubernetes)."""
    return PlainTextResponse("ok", status_code=200)


@web_router.get("/ready")
async def ready() -> JSONResponse:
    """Readiness: конфиг парсится (файл опционален — используются значения по умолчанию)."""
    try:
        load_config()
    except Exception as e:
        return JSONResponse({"status": "not_ready", "detail": str(e)}, status_code=503)
    return JSONResponse({"status": "ready"})


def _mcp_http_path() -> str:
    p = f"{UI_BASE}/mcp" if UI_BASE else "/mcp"
    return p.rstrip("/") + "/"


def _root_landing_html() -> str:
    mcp = _mcp_http_path()
    console = ui_pages_base()
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SDocsMCP</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 42rem; margin: 2.5rem auto; padding: 0 1rem; line-height: 1.5; color: #e8e6e3; background: #0f1419; }}
    h1 {{ font-size: 1.15rem; font-weight: 600; }}
    a {{ color: #e8c07d; }}
    code {{ font-size: 0.9em; }}
    p.muted {{ color: #9aa5b5; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>SDocsMCP — MCP data-plane</h1>
  <p>Для агентов (Cursor и др.): подключение Streamable HTTP MCP — <a href="{mcp}"><code>{mcp}</code></a>.</p>
  <p>Сначала вызовите tools <code>sdocs_mcp_status</code> и <code>sdocs_mcp_capabilities</code> — не открывайте HTML-страницы вместо MCP.</p>
  <p class="muted">Веб-консоль для людей: <a href="{console}/">{console}/</a></p>
</body>
</html>"""


@pages_router.get("/", response_class=HTMLResponse)
async def index() -> str:
    return DASHBOARD_HTML


@pages_router.get("/dashboard", response_class=HTMLResponse)
async def executive_dashboard() -> str:
    return DASHBOARD_HTML


@pages_router.get("/ops", response_class=HTMLResponse)
async def ops_console() -> str:
    return _OPS_HTML


@pages_router.get("/cron-page", response_class=HTMLResponse)
async def cron_page() -> str:
    return CRON_PAGE_HTML


@pages_router.get("/alerts-page", response_class=HTMLResponse)
async def alerts_page() -> str:
    return ALERTS_PAGE_HTML


if UI_PAGES:

    @web_router.get("/", response_class=HTMLResponse)
    async def root_landing() -> str:
        return _root_landing_html()

    def _redirect_to_pages(subpath: str) -> RedirectResponse:
        base = ui_pages_base()
        url = f"{base}{subpath}" if subpath.startswith("/") else f"{base}/{subpath}"
        return RedirectResponse(url=url, status_code=302)

    @web_router.get("/dashboard")
    async def legacy_dashboard() -> RedirectResponse:
        return _redirect_to_pages("/dashboard")

    @web_router.get("/ops")
    async def legacy_ops() -> RedirectResponse:
        return _redirect_to_pages("/ops")

    @web_router.get("/cron-page")
    async def legacy_cron_page() -> RedirectResponse:
        return _redirect_to_pages("/cron-page")

    @web_router.get("/alerts-page")
    async def legacy_alerts_page() -> RedirectResponse:
        return _redirect_to_pages("/alerts-page")

    @web_router.get("/status-page")
    async def legacy_status_page() -> RedirectResponse:
        return _redirect_to_pages("/status-page")


@web_router.post("/api/mail/test-send")
async def api_mail_test_send(req: Request) -> JSONResponse:
    """Тест SMTP: письмо на адрес IMAP-пользователя."""
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "mail_test_send")
        cfg = _cfg()
        mail_cfg = cfg.modules.mail
        if not mail_cfg.enabled:
            raise HTTPException(status_code=404, detail="mail module disabled")
        to_addr = _imap_user(mail_cfg)
        body = mail_smtp_send(
            mail_cfg,
            to_addr,
            "SDocsMCP test",
            "Тестовое письмо с панели SDocsMCP (отправка самому себе).",
        )
        ok = True
        return JSONResponse(json.loads(body))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:300]) from e
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/dashboard-stats")
async def api_dashboard_stats(req: Request) -> JSONResponse:
    """Агрегат для главного дашборда: реальные проверки модулей и телеметрия UI."""
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "dashboard_stats")
        cfg = _cfg()
        body = _build_dashboard_stats(cfg)
        ok = True
        return JSONResponse(body)
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/auth-config")
async def api_auth_config() -> JSONResponse:
    """Публично: нужен ли Bearer для /api/* и /metrics (для подсказок в UI)."""
    return JSONResponse(
        {
            "ui_bearer_enabled": bool(_API_TOKEN),
            "metrics_auth_required": _metrics_auth_required(),
            "ui_invoke_enabled": _ENABLE_INVOKE,
            "ui_seed_enabled": _ENABLE_SEED,
        }
    )


@web_router.get("/api/config-load")
async def api_config_load(req: Request) -> JSONResponse:
    """Статус конфига для UI/LLM: ok / missing / invalid + время загрузки (без пути к файлу)."""
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "config_load")
        try:
            refresh_config_state_from_disk()
        except Exception:
            pass
        body = public_config_status()
        ok = True
        return JSONResponse(body)
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/kafka/topics-required")
async def api_kafka_topics_required(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "kafka_topics")
        cfg = _cfg()
        topics = [{"name": t, "note": TOPIC_NOTES.get(t, "")} for t in SDOCS_KAFKA_TOPICS_CREATE]
        ready, kafka_src = alerts_kafka_ready(cfg)
        ok = True
        return JSONResponse(
            {
                "topics": topics,
                "alerting_kafka_source": kafka_src,
                "alerting_kafka_ready": ready,
                "allowlist_hint": (
                    "Alert: modules.alerting.kafka.topic_allowlist (отдельный кластер). "
                    "Мониторинг: modules.kafka.topic_allowlist (ms-eda, prometheus.metrics)."
                ),
            }
        )
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/alerts/mcp-sources")
async def api_alerts_mcp_sources(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "alerts_mcp_sources")
        cfg = _cfg()
        ok = True
        return JSONResponse({"sources": list_sources(cfg)})
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/alerts/status")
async def api_alerts_status(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "alerts_status")
        cfg = _cfg()
        ready, kafka_src = alerts_kafka_ready(cfg)
        ok = True
        notify = cfg.modules.alerting.notify
        return JSONResponse(
            {
                "leader": is_alert_leader(),
                "instance": (os.environ.get("HOSTNAME") or "").strip() or "local",
                "alerting_kafka_source": kafka_src,
                "alerting_kafka_ready": ready,
                "rules": rule_ui_statuses(cfg),
                "store_revision": alerts_snapshot().get("revision"),
                "notify_defaults": {
                    "default_channel": notify.default_channel,
                    "webhook_configured": bool((notify.webhook_url or "").strip()),
                    "telegram_configured": bool(
                        (notify.telegram_chat_id or "").strip()
                        and (
                            (notify.telegram_bot_token or "").strip()
                            or (notify.telegram_bot_token_env or "").strip()
                        )
                    ),
                    "mail_enabled": cfg.modules.mail.enabled,
                },
            }
        )
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/alerts/notify-log")
async def api_alerts_notify_log(req: Request, limit: int = 50) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "alerts_notify_log")
        ok = True
        return JSONResponse({"entries": notify_log_snapshot(limit)})
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/alerts/rules")
async def api_alerts_rules_get(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "alerts_rules_get")
        ok = True
        return JSONResponse(alerts_snapshot())
    finally:
        _record_request_timing(started, ok)


@web_router.post("/api/alerts/rules")
async def api_alerts_rules_post(req: Request, body: dict[str, Any]) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "alerts_rules_post")
        groups = body.get("groups")
        rules = body.get("rules")
        if not isinstance(groups, list) or not isinstance(rules, list):
            raise HTTPException(status_code=400, detail="groups and rules must be arrays")
        snap = save_from_ui(groups, rules)
        published = publish_rules_snapshot()
        ok = True
        return JSONResponse({"ok": True, "kafka_published": published, **snap})
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/s3-mcp/policy")
async def api_s3_mcp_policy_get(req: Request) -> JSONResponse:
    """Политика опасных tools s3-mcp (modules.s3_mcp в mcp.conf)."""
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "s3_mcp_policy_get")
        cfg = _cfg()
        p = cfg.modules.s3_mcp
        ok = True
        return JSONResponse(
            {
                "allow_put": p.allow_put,
                "allow_delete": p.allow_delete,
                "max_put_bytes": p.max_put_bytes,
                "max_put_human": "1 МБ" if p.max_put_bytes == 1_048_576 else f"{p.max_put_bytes} bytes",
                "tools_when_enabled": {
                    "s3_put_object": p.allow_put,
                    "s3_delete_object": p.allow_delete,
                },
                "note": (
                    "После сохранения s3-mcp перезапустится (S3_MCP_CONFIG_RELOAD_INTERVAL) "
                    "или перезапустите под вручную."
                ),
            }
        )
    finally:
        _record_request_timing(started, ok)


@web_router.post("/api/s3-mcp/policy")
async def api_s3_mcp_policy_post(req: Request, body: dict[str, Any]) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "s3_mcp_policy_post")
        allow_put = body.get("allow_put")
        allow_delete = body.get("allow_delete")
        if allow_put is None and allow_delete is None:
            raise HTTPException(status_code=400, detail="allow_put or allow_delete required")
        try:
            result = patch_modules_s3_mcp(
                allow_put=bool(allow_put) if allow_put is not None else None,
                allow_delete=bool(allow_delete) if allow_delete is not None else None,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        try:
            refresh_config_state_from_disk()
        except Exception:
            pass
        ok = True
        return JSONResponse({"ok": True, **result})
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/config-path")
async def api_config_path(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "config_path")
        p = os.environ.get("SDOCS_MCP_CONFIG", "")
        meta = config_path_for_display()
        ok = True
        return JSONResponse(
            {
                "path": meta["path"],
                "exists": meta["file_found"],
                "source": meta["source"],
                "env_sdocs_mcp_config": p,
            }
        )
    finally:
        _record_request_timing(started, ok)


@web_router.get("/api/status")
async def api_status(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "status")
        cfg = _cfg()
        limiter = _rate_limiter_window_stats()
        body = {
            "postgres": _check_postgres(cfg),
            "redis": _check_redis(cfg),
            "kafka": _check_kafka(cfg),
            "prometheus": _check_prometheus(cfg),
            "opensearch": _check_opensearch(cfg),
            "mail": _check_mail(cfg),
            "ssh": _check_ssh(cfg),
            "kafka_queue": _kafka_queue_load(cfg),
            "ui_rate_limiter": {
                "ok": True,
                "info": True,
                "detail": "внутренняя телеметрия UI (/api/*), не проверка бэкенда",
                "rpm_limit": _RATE_LIMIT_RPM,
                "active_ips": limiter["active_ips"],
                "events_last_minute": limiter["events_last_minute"],
            },
            "modules_enabled": {
                "postgres": cfg.modules.postgres.enabled,
                "redis": cfg.modules.redis.enabled,
                "kafka": cfg.modules.kafka.enabled,
                "prometheus": cfg.modules.prometheus.enabled,
                "mail": cfg.modules.mail.enabled,
                "opensearch": cfg.modules.opensearch.enabled,
                "ssh": cfg.modules.ssh.enabled,
            },
        }
        ok = True
        return JSONResponse(body)
    finally:
        _record_request_timing(started, ok)


@web_router.get("/metrics")
async def prometheus_metrics(req: Request) -> PlainTextResponse:
    """Prometheus scrape endpoint with MCP/UI status and queue gauges."""
    _secure_metrics(req)
    cfg = _cfg()
    checks = {
        "postgres": _check_postgres(cfg),
        "redis": _check_redis(cfg),
        "kafka": _check_kafka(cfg),
        "prometheus": _check_prometheus(cfg),
        "opensearch": _check_opensearch(cfg),
        "mail": _check_mail(cfg),
        "ssh": _check_ssh(cfg),
    }
    queue = _kafka_queue_load(cfg)
    limiter = _rate_limiter_window_stats()
    with _METRICS_LOCK:
        snap = dict(_UI_METRICS)

    lines = [
        "# HELP sdocs_mcp_ui_up UI process is healthy.",
        "# TYPE sdocs_mcp_ui_up gauge",
        "sdocs_mcp_ui_up 1",
        "# HELP sdocs_mcp_module_up Backend module health check (1=ok).",
        "# TYPE sdocs_mcp_module_up gauge",
    ]
    for name, st in checks.items():
        value = 1 if st.get("ok") else 0
        lines.append(f'sdocs_mcp_module_up{{module="{name}"}} {value}')
        latency = st.get("latency_ms")
        if isinstance(latency, int):
            lines.append(f'sdocs_mcp_module_latency_ms{{module="{name}"}} {latency}')

    lines.extend(
        [
            "# HELP sdocs_mcp_ui_requests_total Total secured API requests.",
            "# TYPE sdocs_mcp_ui_requests_total counter",
            f"sdocs_mcp_ui_requests_total {int(snap.get('requests_total', 0.0))}",
            "# HELP sdocs_mcp_ui_auth_failed_total Unauthorized API requests.",
            "# TYPE sdocs_mcp_ui_auth_failed_total counter",
            f"sdocs_mcp_ui_auth_failed_total {int(snap.get('auth_failed_total', 0.0))}",
            "# HELP sdocs_mcp_ui_rate_limited_total Rate-limited API requests.",
            "# TYPE sdocs_mcp_ui_rate_limited_total counter",
            f"sdocs_mcp_ui_rate_limited_total {int(snap.get('rate_limited_total', 0.0))}",
            "# HELP sdocs_mcp_ui_request_errors_total API handler errors.",
            "# TYPE sdocs_mcp_ui_request_errors_total counter",
            f"sdocs_mcp_ui_request_errors_total {int(snap.get('request_errors_total', 0.0))}",
            "# HELP sdocs_mcp_ui_request_latency_seconds_sum Total API handler latency.",
            "# TYPE sdocs_mcp_ui_request_latency_seconds_sum counter",
            f"sdocs_mcp_ui_request_latency_seconds_sum {snap.get('request_latency_sum_seconds', 0.0):.6f}",
            "# HELP sdocs_mcp_ui_request_latency_seconds_count API handler count for latency.",
            "# TYPE sdocs_mcp_ui_request_latency_seconds_count counter",
            f"sdocs_mcp_ui_request_latency_seconds_count {int(snap.get('request_latency_count', 0.0))}",
            "# HELP sdocs_mcp_mcp_http_requests_total HTTP requests to MCP endpoint (not UI /api/*).",
            "# TYPE sdocs_mcp_mcp_http_requests_total counter",
            f"sdocs_mcp_mcp_http_requests_total {mcp_http_requests_total()}",
            "# HELP sdocs_mcp_ui_rate_limiter_events_last_minute Requests observed in in-memory limiter window.",
            "# TYPE sdocs_mcp_ui_rate_limiter_events_last_minute gauge",
            f"sdocs_mcp_ui_rate_limiter_events_last_minute {limiter['events_last_minute']}",
            "# HELP sdocs_mcp_metrics_auth_failed_total Failed /metrics auth attempts.",
            "# TYPE sdocs_mcp_metrics_auth_failed_total counter",
            f"sdocs_mcp_metrics_auth_failed_total {int(snap.get('metrics_auth_failed_total', 0.0))}",
        ]
    )

    if queue.get("ok"):
        lines.extend(
            [
                "# HELP sdocs_mcp_kafka_retained_messages Approx retained messages by topic (end-begin).",
                "# TYPE sdocs_mcp_kafka_retained_messages gauge",
            ]
        )
        topics = queue.get("topics", {})
        if isinstance(topics, dict):
            for topic, tdata in topics.items():
                if isinstance(tdata, dict):
                    retained = tdata.get("retained_messages")
                    if isinstance(retained, int):
                        lines.append(f'sdocs_mcp_kafka_retained_messages{{topic="{topic}"}} {retained}')
        total_retained = queue.get("total_retained_messages")
        if isinstance(total_retained, int):
            lines.append(
                "# HELP sdocs_mcp_kafka_retained_messages_total Sum retained messages over allowlisted topics."
            )
            lines.append("# TYPE sdocs_mcp_kafka_retained_messages_total gauge")
            lines.append(f"sdocs_mcp_kafka_retained_messages_total {total_retained}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@web_router.get("/api/mcp/tools")
async def api_mcp_tools(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "mcp_tools")
        cfg = _cfg()
        mcp = build_mcp(cfg)
        tools = await mcp.list_tools()
        out = [
            {
                "name": t.name,
                "title": t.title,
                "description": t.description,
                "input_schema": t.inputSchema,
            }
            for t in tools
        ]
        ok = True
        return JSONResponse({"tools": out, "count": len(out)})
    finally:
        _record_request_timing(started, ok)


def _tool_result_pack(call_out: Any) -> dict[str, Any]:
    contents, structured = call_out
    text_parts: list[str] = []
    for c in contents or []:
        if getattr(c, "text", None):
            text_parts.append(c.text)
    return {
        "text": "\n".join(text_parts) if text_parts else None,
        "structured": structured,
    }


@web_router.post("/api/mcp/invoke")
async def api_mcp_invoke(req: Request, body: dict[str, Any]) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "mcp_invoke")
        if not _ENABLE_INVOKE:
            raise HTTPException(status_code=403, detail="invoke endpoint disabled by policy")
        name = body.get("tool")
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail="tool name required")
        if name not in _INVOKE_ALLOWLIST:
            raise HTTPException(status_code=403, detail=f"tool not allowed from UI: {name}")
        args = _INVOKE_ALLOWLIST[name]
        cfg = _cfg()
        mcp = build_mcp(cfg)
        try:
            out = await mcp.call_tool(name, dict(args) if args is not None else {})
            _audit_log(
                {
                    "ts": int(time.time()),
                    "event": "mcp_invoke_ok",
                    "ip": _client_ip(req),
                    "tool": name,
                    "arguments": args,
                }
            )
            ok = True
            return JSONResponse({"tool": name, "arguments": args, "result": _tool_result_pack(out)})
        except Exception as e:
            _audit_log(
                {
                    "ts": int(time.time()),
                    "event": "mcp_invoke_error",
                    "ip": _client_ip(req),
                    "tool": name,
                    "error": str(e),
                }
            )
            raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        _record_request_timing(started, ok)


@web_router.post("/api/seed")
async def api_seed(req: Request) -> JSONResponse:
    """Реальные записи в сервисы (не мок): Postgres INSERT, Redis SET, OpenSearch index, Kafka produce."""
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "seed")
        if not _ENABLE_SEED:
            raise HTTPException(status_code=403, detail="seed endpoint disabled by policy")
        cfg = _cfg()
        report: dict[str, Any] = {}
        if cfg.modules.postgres.enabled:
            try:
                with psycopg.connect(make_postgres_conninfo(cfg.modules.postgres), connect_timeout=10) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO demo_ping (msg) VALUES (%s) RETURNING id, created_at;",
                            ("seed from sdocs-mcp-ui",),
                        )
                        row = cur.fetchone()
                    conn.commit()
                if not row:
                    report["postgres"] = {"ok": False, "error": "insert returned no row"}
                else:
                    report["postgres"] = {"ok": True, "row": {"id": row[0], "created_at": str(row[1])}}
            except Exception as e:
                report["postgres"] = {"ok": False, "error": str(e)}
        else:
            report["postgres"] = {"ok": False, "skipped": True}

        if cfg.modules.redis.enabled:
            try:
                json.loads(redis_setex(cfg.modules.redis, "demo:mcp:ping", 3600, f"ts={time.time()}"))
                report["redis"] = {"ok": True, "key": "demo:mcp:ping"}
            except Exception as e:
                report["redis"] = {"ok": False, "error": str(e)}
        else:
            report["redis"] = {"ok": False, "skipped": True}

        if cfg.modules.opensearch.enabled:
            try:
                m = cfg.modules.opensearch
                client = connect_opensearch(m)
                doc = {"event": "seed", "ts": time.time(), "source": "sdocs-mcp-ui"}
                try:
                    resp = client.index(
                        index="demo-mcp",
                        id=f"seed-{int(time.time())}",
                        body=doc,
                        refresh="true",
                    )
                finally:
                    close_opensearch_client(client)
                report["opensearch"] = {
                    "ok": True,
                    "index": resp.get("_index"),
                    "id": resp.get("_id"),
                    "result": resp.get("result"),
                }
            except Exception as e:
                report["opensearch"] = {"ok": False, "error": str(e)}
        else:
            report["opensearch"] = {"ok": False, "skipped": True}

        if cfg.modules.kafka.enabled and cfg.modules.kafka.allow_produce:
            try:
                from sdocs_mcp.kafka_tools import kafka_produce

                payload = json.dumps({"event": "seed", "ts": time.time()}, ensure_ascii=False)
                report["kafka"] = json.loads(
                    kafka_produce(
                        cfg.modules.kafka,
                        "demo.events",
                        [{"key": "demo", "value": payload}],
                    )
                )
            except Exception as e:
                report["kafka"] = {"ok": False, "error": str(e)}
        else:
            report["kafka"] = {"ok": False, "skipped": True, "detail": "kafka disabled or allow_produce false"}

        _audit_log(
            {
                "ts": int(time.time()),
                "event": "seed",
                "ip": _client_ip(req),
                "result": report,
            }
        )
        ok = True
        return JSONResponse(report)
    finally:
        _record_request_timing(started, ok)


@pages_router.get("/status-page", response_class=HTMLResponse)
async def status_page() -> str:
    return _STATUS_HTML


@web_router.get("/api/prometheus-metrics-cron")
async def api_prometheus_metrics_cron_get(req: Request) -> dict[str, Any]:
    """Статус фонового Prometheus→Kafka (вкладка Cron)."""
    from sdocs_mcp.prometheus_cron import get_cron_status

    _secure_api(req, "prometheus_metrics_cron")
    return get_cron_status()


@web_router.post("/api/prometheus-metrics-cron")
async def api_prometheus_metrics_cron_post(req: Request) -> dict[str, Any]:
    """Обновить интервал/запрос/включение cron (в памяти процесса)."""
    from sdocs_mcp.prometheus_cron import apply_cron_runtime

    _secure_api(req, "prometheus_metrics_cron")
    body = await req.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected JSON object")
    try:
        return apply_cron_runtime(
            enabled=body.get("enabled") if "enabled" in body else None,
            interval_seconds=body.get("interval_seconds")
            if "interval_seconds" in body
            else None,
            query=body.get("query") if "query" in body else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@web_router.get("/api/postgres-allowlist")
async def api_postgres_allowlist(req: Request) -> JSONResponse:
    """Список query_id из modules.postgres.allowlisted_queries (без текста SQL) — для обзора и внешних вызовов по id."""
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "postgres_allowlist")
        cfg = _cfg()
        pg = cfg.modules.postgres
        if not pg.enabled:
            ok = True
            return JSONResponse(
                {
                    "postgres_enabled": False,
                    "allowlist_configured": False,
                    "queries": [],
                    "detail": "модуль postgres выключен в конфиге",
                }
            )
        if not pg.allowlisted_queries:
            ok = True
            return JSONResponse(
                {
                    "postgres_enabled": True,
                    "allowlist_configured": False,
                    "queries": [],
                    "detail": "allowlisted_queries пуст — добавьте именованные SELECT в YAML; клиенты передают только query_id",
                }
            )
        catalog = json.loads(postgres_allowlisted_query_catalog(pg))
        ok = True
        return JSONResponse(
            {
                "postgres_enabled": True,
                "allowlist_configured": True,
                "queries": catalog.get("queries", []),
                "detail": None,
            }
        )
    finally:
        _record_request_timing(started, ok)


app.include_router(web_router, prefix=UI_BASE)
app.include_router(pages_router, prefix=ui_pages_base() if UI_PAGES else UI_BASE)


def _embed_sdocs_mcp_if_enabled() -> None:
    """Один порт с UI: Streamable HTTP MCP на пути {base}/mcp (SDOCS_MCP_EMBED_MCP=true)."""
    global _embedded_mcp_holder
    if (os.environ.get("SDOCS_MCP_EMBED_MCP") or "").strip().lower() not in ("1", "true", "yes"):
        return
    cfg = load_config()
    os_mod = cfg.modules.opensearch
    mcp_path = f"{UI_BASE}/mcp" if UI_BASE else "/mcp"
    if os_mod.enabled and os_mod.tool_call_audit.enabled:
        app.add_middleware(
            ToolAuditCallerMiddleware,
            audit_cfg=os_mod.tool_call_audit,
            path_prefix=mcp_path,
        )
    holder = EmbeddedMcpHolder(streamable_http_path="/")
    _embedded_mcp_holder = holder
    mount_path = mcp_path if mcp_path.endswith("/") else f"{mcp_path}/"
    app.mount(mount_path, holder.asgi_app)
    logging.getLogger("sdocs_mcp.ui").info(
        "Embedded sdocs-mcp: Streamable HTTP on same port as UI at path %s "
        "(SDOCS_MCP_CONFIG_WAIT_SECONDS=%s, SDOCS_MCP_CONFIG_RELOAD_INTERVAL=%s).",
        mount_path,
        int(config_wait_seconds()),
        int(config_reload_interval_seconds()),
    )


_embed_sdocs_mcp_if_enabled()


_OPS_HTML_RAW = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>sdocs-mcp — консоль</title>
  <script>const __UI_BASE="{{UI_BASE_PATH}}";</script>
  <style>
{{TOPNAV_STYLES}}
{{SUBPAGE_SKIN}}
    .shell { max-width: 1120px; margin: 0 auto; padding: 1.75rem 1.35rem 2.75rem; }
    .page-head {
      padding: 0 0 1.1rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }
    .page-head h1 { margin: 0 0 0.35rem; font-size: 1.1rem; font-weight: 600; letter-spacing: 0.04em; border: none; }
    .lede { margin: 0; color: var(--muted); font-size: 0.82rem; max-width: 52rem; }
    .ops-meta-grid { margin-bottom: 0.75rem; }
    .compact-panel { padding: 0.75rem 0.9rem; margin: 0; }
    .compact-panel h3 {
      margin: 0 0 0.45rem;
      font-size: 0.7rem;
      font-weight: 650;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--accent);
      border: none;
    }
    .compact-panel .field-group { margin: 0.35rem 0 0; }
    .compact-panel .field-label { margin-bottom: 0.2rem; font-size: 0.68rem; }
    .compact-panel .muted { font-size: 0.78rem; line-height: 1.35; }
    .cron-form { display: grid; gap: 0.65rem; max-width: 36rem; }
    .cron-form label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .cron-row { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
    #cron-status-box { font-size: 0.82rem; line-height: 1.45; }
    .top-links { font-size: 0.9rem; display: flex; flex-wrap: wrap; gap: 0.35rem 1rem; align-items: baseline; }
    .top-links a { color: var(--accent); text-decoration: none; font-weight: 500; border-bottom: 1px solid transparent; }
    .top-links a:hover { border-bottom-color: var(--accent); }
    .flow-list { margin: 0; padding: 0; list-style: none; counter-reset: step; }
    .flow-list > li { counter-increment: step; margin-bottom: 1rem; padding-left: 2rem; position: relative; }
    .flow-list > li::before {
      content: counter(step);
      position: absolute;
      left: 0;
      top: 0.1rem;
      width: 1.35rem;
      height: 1.35rem;
      font-size: 0.75rem;
      font-weight: 600;
      line-height: 1.35rem;
      text-align: center;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
    }
    .step-title { margin: 0 0 0.35rem; font-size: 0.82rem; font-weight: 650; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem 1.15rem;
      margin-bottom: 0.85rem;
    }
    .field-group { margin: 0.65rem 0 0; }
    .field-label {
      display: block;
      font-size: 0.72rem;
      font-weight: 650;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin-bottom: 0.35rem;
    }
    input[type="password"] {
      width: min(480px, 100%);
      padding: 0.5rem 0.7rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-size: 0.9rem;
    }
    input[type="password"]:focus {
      outline: 2px solid var(--accent);
      outline-offset: 1px;
    }
    .btn-row { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
    button {
      padding: 0.45rem 0.8rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      cursor: pointer;
      font-size: 0.86rem;
      font-weight: 500;
    }
    button:hover { border-color: var(--accent); background: var(--accent-soft); }
    button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    button.primary { border-color: var(--accent); background: var(--accent-soft); font-weight: 600; }
    button.primary:hover { filter: brightness(0.97); }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .tablist {
      display: flex;
      flex-wrap: wrap;
      gap: 0;
      border-bottom: 1px solid var(--border);
      margin: 1rem 0 0;
    }
    .tablist button[role="tab"] {
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      padding: 0.6rem 1rem;
      margin-bottom: -1px;
      color: var(--muted);
      font-weight: 500;
      font-size: 0.88rem;
      cursor: pointer;
      border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    }
    .tablist button[role="tab"]:hover { color: var(--text); background: var(--accent-soft); }
    .tablist button[role="tab"][aria-selected="true"] {
      color: var(--text);
      border-bottom-color: var(--accent);
      font-weight: 600;
    }
    .tablist button[role="tab"]:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    [role="tabpanel"] { padding: 1rem 0 0; }
    [role="tabpanel"]:focus { outline: none; }
    .section-title { margin: 0 0 0.35rem; font-size: 1rem; font-weight: 600; letter-spacing: -0.015em; }
    .section-note { margin: 0 0 0.75rem; color: var(--muted); font-size: 0.88rem; max-width: 50rem; }
    .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(236px, 1fr)); gap: 0.75rem; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 0;
      overflow: hidden;
    }
    .card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.55rem 0.75rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface2);
    }
    .card-head strong { font-size: 0.88rem; font-weight: 600; }
    .badge {
      font-size: 0.65rem;
      font-weight: 650;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 0.18rem 0.45rem;
      border-radius: 4px;
      flex-shrink: 0;
    }
    .badge-ok { background: var(--ok-bg); color: var(--ok); }
    .badge-bad { background: var(--bad-bg); color: var(--bad); }
    .badge-skip { background: var(--skip-bg); color: var(--skip); }
    .badge-on { background: var(--ok-bg); color: var(--ok); }
    .badge-off { background: var(--border); color: var(--muted); }
    .card pre {
      margin: 0;
      border: none;
      border-radius: 0;
      max-height: 280px;
      background: var(--surface);
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: var(--surface2);
      padding: 0.75rem 0.9rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      font-size: 0.76rem;
      line-height: 1.45;
      max-height: 320px;
      overflow: auto;
    }
    #metrics-preview { max-height: 220px; }
    #invoke-buttons { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; }
    .muted { color: var(--muted); font-size: 0.88rem; margin: 0.3rem 0; }
    code {
      font-family: ui-monospace, "Cascadia Code", "SF Mono", Consolas, monospace;
      font-size: 0.85em;
      padding: 0.1em 0.32em;
      border-radius: 3px;
      background: var(--accent-soft);
    }
    .alert { margin: 0.5rem 0; padding: 0.6rem 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--bad); background: var(--bad-bg); color: var(--text); font-size: 0.86rem; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">К основному содержимому</a>
  <div class="dashboard">
  {{TOPNAV}}
  <div class="subpage-content">
  <div class="shell">
  <header class="page-head">
    <h1>Консоль — диагностика и MCP</h1>
    <p class="lede">Токены, статус, Cron Prometheus→Kafka, отладка tools. Сводка ROI — на главной.</p>
  </header>

  <div class="comparison-grid ops-meta-grid">
    <div class="panel compact-panel">
      <h3>Доступ</h3>
      <p class="muted">Bearer для <code>/api/*</code> и отдельный токен для <code>/metrics</code> при необходимости.</p>
        <p class="muted" id="auth-hint" aria-live="polite"></p>
        <div class="field-group">
          <label class="field-label" for="token">UI / API</label>
          <input id="token" type="password" placeholder="SDOCS_MCP_UI_TOKEN" autocomplete="off" />
        </div>
        <div class="field-group">
          <label class="field-label" for="metrics-token">Метрики</label>
          <input id="metrics-token" type="password" placeholder="SDOCS_MCP_METRICS_TOKEN" autocomplete="off" />
        </div>
        <p class="muted" id="cfgpath" aria-live="polite"></p>
    </div>
    <div class="panel compact-panel">
      <h3>Актуальные данные</h3>
      <p class="muted">Карточки модулей и проверок. Tools, seed, /metrics — во вкладках ниже.</p>
      <div class="btn-row" style="margin-top:0.5rem;">
        <button type="button" class="primary" id="btn-refresh">Обновить статус</button>
      </div>
    </div>
  </div>

  <p id="status-error" class="alert" role="alert" hidden></p>

  <div id="main" tabindex="-1">
    <span id="tabs-label" class="sr-only">Разделы подробностей</span>
    <div class="tablist" role="tablist" aria-labelledby="tabs-label">
      <button type="button" role="tab" id="tab-services" aria-selected="true" aria-controls="panel-services">Сервисы</button>
      <button type="button" role="tab" id="tab-observe" aria-selected="false" aria-controls="panel-observe" tabindex="-1">Наблюдение</button>
      <button type="button" role="tab" id="tab-mcp" aria-selected="false" aria-controls="panel-mcp" tabindex="-1">MCP и отладка</button>
    </div>

    <div id="panel-services" role="tabpanel" aria-labelledby="tab-services">
      <h2 class="section-title">Модули в конфиге</h2>
      <p class="section-note">Что включено в <code>sdocs_mcp_status</code>: postgres, redis, kafka, prometheus, mail, opensearch, ssh.</p>
      <div class="row" id="modules-config"></div>
      <h2 class="section-title" style="margin-top:1.25rem;">Доступность интеграций</h2>
      <p class="section-note">Прямые проверки к зависимостям. Сбой здесь обычно важнее, чем вспомогательные счётчики во вкладке «Наблюдение».</p>
      <div class="row" id="status-core"></div>
    </div>

    <div id="panel-observe" role="tabpanel" aria-labelledby="tab-observe" hidden>
      <h2 class="section-title">Очередь и лимиты</h2>
      <p class="section-note"><strong>kafka_queue</strong> — оценка объёма сообщений по allowlist (не замена мониторинга кластера). <strong>ui_rate_limiter</strong> — нагрузка на <code>/api/*</code>, не статус брокеров или БД.</p>
      <div class="row" id="status-aux"></div>
      <h2 class="section-title" style="margin-top:1.25rem;">Статус и /metrics</h2>
      <p class="section-note">Ниже — <strong>метрики самого SDocsMCP</strong> (<code>/metrics</code>). Запросы к Prometheus — tools <code>prometheus_*</code> и страница <a href="{{UI_PAGES_BASE}}/cron-page" style="color:var(--accent);">Cron</a>.</p>
      <div class="btn-row" style="margin-bottom:0.5rem;">
        <button type="button" id="btn-metrics">Обновить превью экспозиции /metrics</button>
      </div>
      <pre id="metrics-preview">—</pre>
    </div>

    <div id="panel-mcp" role="tabpanel" aria-labelledby="tab-mcp" hidden>
      <h2 class="section-title">Инструменты MCP</h2>
      <p class="section-note">Справочный список; не влияет на работу сервисов.</p>
      <div class="btn-row">
        <button type="button" id="btn-tools">Загрузить список tools</button>
      </div>
      <pre id="tools">—</pre>
      <h2 class="section-title" style="margin-top:1.25rem;">S3 MCP — запись и удаление (выкл. по умолчанию)</h2>
      <p class="section-note">
        Отдельный процесс <code>s3-mcp</code> (порт <strong>8766</strong>), не путать с <code>sdocs-mcp</code>.
        <strong>Сейчас по умолчанию</strong> в MCP доступны только чтение: список bucket, метаданные файла (<code>s3_object_metadata</code>), статистика.
        <strong>Запись файла до 1&nbsp;МБ</strong> (<code>s3_put_object</code>) и <strong>удаление</strong> (<code>s3_delete_object</code>) — <em>отключены</em>, пока не включите чекбоксы ниже и не нажмёте «Сохранить».
        После сохранения в <code>mcp.conf</code> под <code>s3-mcp</code> перезапустится (≈15&nbsp;с) и в <code>tools/list</code> появятся новые tools.
      </p>
      <div class="row" style="gap:1rem;align-items:center;margin-bottom:0.75rem;flex-wrap:wrap;">
        <label><input type="checkbox" id="s3-allow-put"> <strong>allow_put</strong> — разрешить <code>s3_put_object</code> (файл в base64, макс. 1&nbsp;МБ)</label>
        <label><input type="checkbox" id="s3-allow-delete"> <strong>allow_delete</strong> — разрешить <code>s3_delete_object</code></label>
        <button type="button" id="btn-s3-policy-save">Сохранить в mcp.conf</button>
        <button type="button" id="btn-s3-policy-load">Обновить</button>
      </div>
      <pre id="s3-policy-out">—</pre>
      <h2 class="section-title" style="margin-top:1.25rem;">Вызовы из UI (allowlist)</h2>
      <p class="section-note">Кнопки дергают <code>FastMCP.call_tool</code> на сервере (нужен <code>SDOCS_MCP_UI_ENABLE_INVOKE=true</code>). <strong>Seed</strong> — <code>SDOCS_MCP_UI_ENABLE_SEED=true</code>.</p>
      <div class="btn-row">
        <button type="button" id="btn-seed">Seed (Postgres / Redis / OpenSearch / Kafka)</button>
        <button type="button" id="btn-mail-test">✉ Тест почты (себе)</button>
      </div>
      <div id="invoke-buttons"></div>
      <p class="muted" id="invoke-label"><strong>Ответ</strong></p>
      <pre id="invoke-out" aria-labelledby="invoke-label">—</pre>
    </div>

  </div>
  </div>
  </div>
  <div class="dashboard-footer">
    <div>SDocsMCP · консоль</div>
  </div>
</div>

  <script>
    const $ = (id) => document.getElementById(id);
    function authHeader() {
      const t = ($('token').value || '').trim();
      return t ? { 'Authorization': 'Bearer ' + t } : {};
    }
    function metricsAuthHeader() {
      const m = ($('metrics-token').value || '').trim();
      return m ? { 'Authorization': 'Bearer ' + m } : {};
    }
    async function jget(path) { const r = await fetch(__UI_BASE + path, { headers: authHeader() }); if (!r.ok) throw new Error(await r.text()); return r.json(); }
    async function jpost(path, body) {
      const r = await fetch(__UI_BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify(body || {}) });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    }
    function card(title, obj) {
      const el = document.createElement('div');
      el.className = 'card';
      if (obj && obj.info === true) {
        el.innerHTML = '<div class="card-head"><strong>' + title + '</strong><span class="badge badge-skip">info</span></div>' +
          '<pre>' + JSON.stringify(obj, null, 2) + '</pre>';
        return el;
      }
      const badgeClass = obj && obj.skipped ? 'badge-skip' : (obj && obj.ok ? 'badge-ok' : 'badge-bad');
      const badgeText = obj && obj.skipped ? 'skipped' : (obj && obj.ok ? 'ok' : 'fail');
      el.innerHTML = '<div class="card-head"><strong>' + title + '</strong><span class="badge ' + badgeClass + '">' + badgeText + '</span></div>' +
        '<pre>' + JSON.stringify(obj, null, 2) + '</pre>';
      return el;
    }
    function moduleChip(name, on) {
      const el = document.createElement('div');
      el.className = 'card';
      const b = on ? 'badge-on' : 'badge-off';
      const t = on ? 'on' : 'off';
      el.innerHTML = '<div class="card-head"><strong>' + name + '</strong><span class="badge ' + b + '">' + t + '</span></div>';
      return el;
    }
    function renderModulesEnabled(m) {
      const host = $('modules-config');
      host.innerHTML = '';
      const order = ['postgres', 'redis', 'kafka', 'prometheus', 'mail', 'opensearch', 'ssh'];
      order.forEach((k) => {
        if (m && Object.prototype.hasOwnProperty.call(m, k)) {
          host.appendChild(moduleChip(k, !!m[k]));
        }
      });
    }
    function initTabs() {
      const tablist = document.querySelector('[role="tablist"]');
      const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
      const panels = tabs.map((t) => $(t.getAttribute('aria-controls')));
      function select(i) {
        tabs.forEach((tab, j) => {
          const on = j === i;
          tab.setAttribute('aria-selected', on);
          tab.tabIndex = on ? 0 : -1;
          panels[j].hidden = !on;
        });
      }
      tabs.forEach((tab, i) => {
        tab.addEventListener('click', () => { select(i); tab.focus(); });
        tab.addEventListener('keydown', (e) => {
          let n = i;
          if (e.key === 'ArrowRight') { e.preventDefault(); n = (i + 1) % tabs.length; }
          else if (e.key === 'ArrowLeft') { e.preventDefault(); n = (i - 1 + tabs.length) % tabs.length; }
          else if (e.key === 'Home') { e.preventDefault(); n = 0; }
          else if (e.key === 'End') { e.preventDefault(); n = tabs.length - 1; }
          else { return; }
          select(n);
          tabs[n].focus();
        });
      });
      select(0);
    }
    async function refreshStatus() {
      const err = $('status-error');
      err.hidden = true;
      err.textContent = '';
      const s = await jget('/api/status');
      renderModulesEnabled(s.modules_enabled);
      const core = $('status-core');
      core.innerHTML = '';
      core.appendChild(card('postgres', s.postgres));
      core.appendChild(card('redis', s.redis));
      core.appendChild(card('kafka', s.kafka));
      core.appendChild(card('prometheus', s.prometheus));
      core.appendChild(card('opensearch', s.opensearch));
      core.appendChild(card('mail', s.mail));
      core.appendChild(card('ssh', s.ssh));
      const aux = $('status-aux');
      aux.innerHTML = '';
      aux.appendChild(card('kafka_queue', s.kafka_queue));
      aux.appendChild(card('ui_rate_limiter', s.ui_rate_limiter));
    }
    async function refreshMetricsPreview() {
      const r = await fetch(__UI_BASE + '/metrics', { headers: metricsAuthHeader() });
      const t = await r.text();
      if (!r.ok) throw new Error(t);
      $('metrics-preview').textContent = t;
    }
    async function loadTools() {
      const t = await jget('/api/mcp/tools');
      $('tools').textContent = JSON.stringify(t, null, 2);
    }
    async function invoke(name) {
      const out = $('invoke-out');
      out.textContent = '…';
      try {
        const r = await jpost('/api/mcp/invoke', { tool: name });
        out.textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        out.textContent = 'Ошибка: ' + e;
      }
    }
    async function seed() {
      const out = $('invoke-out');
      out.textContent = 'Seeding…';
      try {
        const r = await jpost('/api/seed', {});
        out.textContent = JSON.stringify(r, null, 2);
        await refreshStatus();
        await refreshMetricsPreview().catch(() => {});
      } catch (e) {
        out.textContent = 'Ошибка: ' + e;
      }
    }
    async function mailTest() {
      const out = $('invoke-out');
      out.textContent = 'Отправка…';
      try {
        const r = await jpost('/api/mail/test-send', {});
        out.textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        out.textContent = 'Ошибка: ' + e;
      }
    }
    const allowed = [
      'sdocs_mcp_status','sdocs_mcp_capabilities','redis_ping','redis_info','redis_dbsize','postgres_connections_overview','postgres_database_sizes',
      'postgres_table_sizes','opensearch_cluster_health','opensearch_rag_policy','opensearch_list_indices','kafka_list_topics',
      'kafka_describe_topic','kafka_consume_recent'
    ];
    function buildInvokeButtons() {
      const host = $('invoke-buttons');
      host.innerHTML = '';
      allowed.forEach(n => {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = n;
        b.onclick = () => invoke(n);
        host.appendChild(b);
      });
    }
    async function boot() {
      const saved = localStorage.getItem('sdocs_mcp_ui_token') || '';
      $('token').value = saved;
      $('token').onchange = () => localStorage.setItem('sdocs_mcp_ui_token', $('token').value || '');
      const savedM = localStorage.getItem('sdocs_mcp_metrics_token') || '';
      $('metrics-token').value = savedM;
      $('metrics-token').onchange = () => localStorage.setItem('sdocs_mcp_metrics_token', $('metrics-token').value || '');
      try {
        const ac = await fetch(__UI_BASE + '/api/auth-config').then((r) => r.json());
        let hint = ac.ui_bearer_enabled
          ? 'Сейчас: для /api/* нужен Bearer (SDOCS_MCP_UI_TOKEN).'
          : 'Сейчас: /api/* без Bearer (токен UI на сервере не задан).';
        if (!ac.ui_invoke_enabled) {
          hint += ' Вызов tools из UI выключен (SDOCS_MCP_UI_ENABLE_INVOKE=false).';
        }
        $('auth-hint').textContent = hint;
      } catch (e) {
        $('auth-hint').textContent = '';
      }
      try {
        const c = await jget('/api/config-load');
        const el = $('cfgpath');
        if (c.state === 'ok') {
          el.innerHTML = '<span style="color:#6ee7a0;font-weight:600">✓ Конфиг загружен</span>' + (c.loaded_at ? ' · ' + c.loaded_at : '') + ' — ' + (c.message || '');
        } else if (c.state === 'invalid') {
          el.innerHTML = '<span style="color:#fca5a5;font-weight:600">✗ Ошибка конфига</span> — ' + (c.error || c.message || '');
        } else {
          el.innerHTML = '<span style="color:#fcd34d;font-weight:600">○ Конфиг не загружен</span> — ' + (c.message || '');
        }
      } catch (e) {
        $('cfgpath').textContent = 'Статус конфига: ошибка — ' + e;
      }
      buildInvokeButtons();
      initTabs();
      $('btn-refresh').onclick = () => refreshStatus().catch(e => {
        const err = $('status-error');
        err.hidden = false;
        err.textContent = String(e);
      });
      $('btn-tools').onclick = () => loadTools().catch(e => alert(e));
      async function loadS3Policy() {
        const p = await jget('/api/s3-mcp/policy');
        $('s3-allow-put').checked = !!p.allow_put;
        $('s3-allow-delete').checked = !!p.allow_delete;
        $('s3-policy-out').textContent = JSON.stringify(p, null, 2);
      }
      async function saveS3Policy() {
        const body = {
          allow_put: $('s3-allow-put').checked,
          allow_delete: $('s3-allow-delete').checked,
        };
        const r = await jpost('/api/s3-mcp/policy', body);
        $('s3-policy-out').textContent = JSON.stringify(r, null, 2);
      }
      $('btn-s3-policy-load').onclick = () => loadS3Policy().catch(e => { $('s3-policy-out').textContent = String(e); });
      $('btn-s3-policy-save').onclick = () => saveS3Policy().catch(e => { $('s3-policy-out').textContent = String(e); });
      loadS3Policy().catch(() => {});
      $('btn-seed').onclick = () => seed().catch(e => { $('invoke-out').textContent = 'Ошибка: ' + e; });
      $('btn-mail-test').onclick = () => mailTest().catch(e => { $('invoke-out').textContent = 'Ошибка: ' + e; });
      $('btn-metrics').onclick = () => refreshMetricsPreview().catch(e => { $('metrics-preview').textContent = String(e); });
      await refreshStatus().catch(e => {
        const err = $('status-error');
        err.hidden = false;
        err.textContent = String(e);
      });
      await refreshMetricsPreview().catch(e => { $('metrics-preview').textContent = String(e); });
    }
    boot();
  </script>
</body>
</html>"""

_STATUS_HTML_RAW = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Статус и /metrics — sdocs-mcp</title>
  <script>const __UI_BASE="{{UI_BASE_PATH}}";</script>
  <style>
{{TOPNAV_STYLES}}
{{SUBPAGE_SKIN}}
    .page-hero {
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 1rem;
      margin-bottom: 1.25rem;
    }
    .page-hero h1 { margin: 0; font-size: 1.35rem; font-weight: 600; letter-spacing: -0.02em; }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem 1.15rem;
      margin-bottom: 1rem;
    }
    .muted { color: var(--muted); font-size: 0.9rem; margin: 0.4rem 0; }
    code {
      font-family: ui-monospace, "Cascadia Code", "SF Mono", Consolas, monospace;
      font-size: 0.86em;
      padding: 0.12em 0.35em;
      border-radius: 4px;
      background: var(--accent-soft);
    }
    input {
      width: min(520px, 100%);
      padding: 0.55rem 0.75rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-size: 0.9rem;
    }
    input:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: var(--surface2);
      padding: 0.85rem 1rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      font-size: 0.78rem;
      line-height: 1.45;
      margin: 0;
      max-height: min(70vh, 560px);
      overflow: auto;
    }
  </style>
</head>
<body>
  <div class="dashboard">
  {{TOPNAV}}
  <div class="subpage-content">
  <header class="page-hero">
    <h1>Статус и /metrics</h1>
  </header>
  <div class="panel">
    <p class="muted">Данные с <code>/metrics</code>. При <code>SDOCS_MCP_METRICS_TOKEN</code> (или UI Bearer) введите секрет — только заголовок <code>Authorization</code>, не URL.</p>
    <p class="muted">JSON <code>/api/status</code> — Bearer, если на сервере задан <code>SDOCS_MCP_UI_TOKEN</code>.</p>
    <input id="mtok" type="password" placeholder="SDOCS_MCP_METRICS_TOKEN (если требуется)" autocomplete="off" />
  </div>
  <pre id="out">Loading /metrics...</pre>
  </div>
  <div class="dashboard-footer">
    <div>SDocsMCP · метрики</div>
    <div class="theme-switch" id="themeToggle" role="button" tabindex="0" aria-label="Переключить светлую тему">
      <span>☀</span>
      <div class="toggle-track"><div class="toggle-thumb"></div></div>
      <span>☾</span>
    </div>
  </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    function metricsHeaders() {
      const t = ($('mtok').value || '').trim();
      return t ? { 'Authorization': 'Bearer ' + t } : {};
    }
    async function load() {
      const r = await fetch(__UI_BASE + '/metrics', { headers: metricsHeaders() });
      const t = await r.text();
      $('out').textContent = t;
    }
    $('mtok').value = localStorage.getItem('sdocs_mcp_metrics_token') || '';
    $('mtok').onchange = () => localStorage.setItem('sdocs_mcp_metrics_token', $('mtok').value || '');
    load().catch(e => { $('out').textContent = String(e); });
    setInterval(() => load().catch(() => {}), 15000);
    (function () {
      const tt = document.getElementById('themeToggle');
      if (!tt) return;
      tt.addEventListener('click', function () { document.body.classList.toggle('light'); });
      tt.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); document.body.classList.toggle('light'); }
      });
    })();
  </script>
</body>
</html>
"""

_OPS_HTML = inject_subpage(_OPS_HTML_RAW, "ops")
_STATUS_HTML = inject_subpage(_STATUS_HTML_RAW, "status")


def main() -> None:
    if _METRICS_REQUIRE_TOKEN and not _METRICS_TOKEN:
        raise RuntimeError(
            "SDOCS_MCP_METRICS_REQUIRE_TOKEN=true requires non-empty SDOCS_MCP_METRICS_TOKEN "
            "(use Prometheus scrape authorization or params metrics_token)."
        )
    log = logging.getLogger("uvicorn.error")
    log.info(
        "UI security: invoke=%s seed=%s rate_limit_rpm=%s audit_log=%s",
        _ENABLE_INVOKE,
        _ENABLE_SEED,
        _RATE_LIMIT_RPM,
        str(_AUDIT_LOG_PATH),
    )
    log.info(
        "Metrics security: auth_required=%s metrics_rate_limit_rpm=%s accept_ui_bearer=%s",
        _metrics_auth_required(),
        _METRICS_RATE_LIMIT_RPM,
        _METRICS_ACCEPT_UI_BEARER,
    )
    if not _API_TOKEN:
        log.warning("SDOCS_MCP_UI_TOKEN not set: /api/* accepts requests without Bearer (set token to enforce).")
    host = os.environ.get("SDOCS_MCP_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("SDOCS_MCP_UI_PORT", "8888"))
    if host.strip() in ("0.0.0.0", "[::]", "::"):
        if not _API_TOKEN:
            log.warning(
                "Listening on all interfaces: /api/* is not Bearer-protected (empty SDOCS_MCP_UI_TOKEN)."
            )
        if not _metrics_auth_required():
            log.warning(
                "Listening on all interfaces without /metrics authentication; set SDOCS_MCP_METRICS_TOKEN "
                "or SDOCS_MCP_METRICS_ACCEPT_UI_BEARER=true (or SDOCS_MCP_METRICS_REQUIRE_TOKEN=true)."
            )
    workers = max(1, int(os.environ.get("SDOCS_MCP_UI_WORKERS", "1")))
    log_level = (os.environ.get("SDOCS_MCP_LOG_LEVEL") or "info").strip().lower()
    if workers > 1:
        log.info("Uvicorn workers=%s (SDOCS_MCP_UI_WORKERS)", workers)
        log.warning(
            "SDOCS_MCP_UI_WORKERS>1: фоновый Prometheus→Kafka Cron запускается в каждом воркере — "
            "дубли сообщений. Рекомендуется workers=1 или SDOCS_MCP_PROMETHEUS_CRON=false."
        )
    if (
        workers > 1
        and (os.environ.get("SDOCS_MCP_EMBED_MCP") or "").strip().lower() in ("1", "true", "yes")
        and (os.environ.get("SDOCS_MCP_STATELESS_HTTP") or "").strip().lower() not in ("1", "true", "yes", "on")
    ):
        log.warning(
            "SDOCS_MCP_EMBED_MCP with SDOCS_MCP_UI_WORKERS>1 can break stateful MCP Streamable HTTP sessions; "
            "use SDOCS_MCP_UI_WORKERS=1 or set SDOCS_MCP_STATELESS_HTTP=true."
        )
    run_kw: dict[str, Any] = {
        "host": host,
        "port": port,
        "workers": workers,
        "reload": False,
        "log_level": log_level,
    }
    ssl_kw = resolve_mcp_mtls_uvicorn_kwargs(log)
    if ssl_kw:
        run_kw.update(ssl_kw)
        log.info("HTTPS + mTLS for UI and embedded /mcp (SDOCS_MCP_MTLS_*).")
    uvicorn.run(
        "sdocs_mcp.info_app:app",
        **run_kw,
    )


if __name__ == "__main__":
    main()
