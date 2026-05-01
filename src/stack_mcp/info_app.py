from __future__ import annotations

import hmac
import json
import logging
import os
import socket
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import httpx
import psycopg
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from kafka import KafkaConsumer, TopicPartition
from starlette.middleware.trustedhost import TrustedHostMiddleware

from stack_mcp.backend_tls import (
    make_postgres_conninfo,
    prometheus_httpx_verify_and_cert,
)
from stack_mcp.config import AppConfig, load_config
from stack_mcp.kafka_tools import kafka_broker_client_config
from stack_mcp.mail_tools import mail_imap_verify
from stack_mcp.opensearch_tools import connect_opensearch
from stack_mcp.redis_tools import redis_ping, redis_setex
from stack_mcp.server import build_mcp

# Безопасный список: только чтение / диагностика + статус (без произвольного SQL и т.д.).
_INVOKE_ALLOWLIST: dict[str, dict[str, Any] | None] = {
    "stack_mcp_status": {},
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
    "ssh_command_policy": {},
}

app = FastAPI(title="stack-mcp UI", version="0.2.2")

_trusted_hosts_raw = (os.environ.get("STACK_MCP_UI_TRUSTED_HOSTS") or "").strip()
if _trusted_hosts_raw:
    _trusted_hosts = [h.strip() for h in _trusted_hosts_raw.split(",") if h.strip()]
    if _trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

_API_TOKEN = (os.environ.get("STACK_MCP_UI_TOKEN") or "").strip()
_ENABLE_INVOKE = os.environ.get("STACK_MCP_UI_ENABLE_INVOKE", "false").strip().lower() == "true"
_ENABLE_SEED = os.environ.get("STACK_MCP_UI_ENABLE_SEED", "false").strip().lower() == "true"
_RATE_LIMIT_RPM = max(1, int(os.environ.get("STACK_MCP_UI_RATE_LIMIT_RPM", "60")))
_AUDIT_LOG_PATH = Path(os.environ.get("STACK_MCP_UI_AUDIT_LOG_PATH", "logs/ui-audit.log"))

# /metrics (и опционально тот же секрет в UI status-page): без IP-whitelist, только shared secret.
_METRICS_TOKEN = (os.environ.get("STACK_MCP_METRICS_TOKEN") or "").strip()
_METRICS_REQUIRE_TOKEN = os.environ.get("STACK_MCP_METRICS_REQUIRE_TOKEN", "false").strip().lower() == "true"
_METRICS_ACCEPT_UI_BEARER = os.environ.get("STACK_MCP_METRICS_ACCEPT_UI_BEARER", "false").strip().lower() == "true"
_METRICS_RATE_LIMIT_RPM = max(1, int(os.environ.get("STACK_MCP_METRICS_RATE_LIMIT_RPM", "120")))


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
    x = req.headers.get("x-stack-mcp-metrics-token", "").strip()
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
    path = os.environ.get("STACK_MCP_CONFIG", "")
    if not path or not os.path.isfile(path):
        raise HTTPException(
            status_code=500,
            detail="Set STACK_MCP_CONFIG to an existing yaml (e.g. config.docker.yaml).",
        )
    return load_config()


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
        h = client.cluster.health()
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
            group_id=f"stack-mcp-ui-probe-{int(time.time() * 1000)}",
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


@app.get("/health")
async def health() -> PlainTextResponse:
    """Liveness: без конфига и без авторизации (Docker/Kubernetes)."""
    return PlainTextResponse("ok", status_code=200)


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness: конфиг существует и парсится."""
    path = os.environ.get("STACK_MCP_CONFIG", "")
    if not path or not os.path.isfile(path):
        return JSONResponse(
            {"status": "not_ready", "detail": "STACK_MCP_CONFIG missing or not a file"},
            status_code=503,
        )
    try:
        load_config()
    except Exception as e:
        return JSONResponse({"status": "not_ready", "detail": str(e)}, status_code=503)
    return JSONResponse({"status": "ready"})


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _INDEX_HTML


@app.get("/api/auth-config")
async def api_auth_config() -> JSONResponse:
    """Публично: нужен ли Bearer для /api/* и /metrics (для подсказок в UI)."""
    return JSONResponse(
        {
            "ui_bearer_enabled": bool(_API_TOKEN),
            "metrics_auth_required": _metrics_auth_required(),
        }
    )


@app.get("/api/config-path")
async def api_config_path(req: Request) -> JSONResponse:
    started = time.perf_counter()
    ok = False
    try:
        _secure_api(req, "config_path")
        p = os.environ.get("STACK_MCP_CONFIG", "")
        ok = True
        return JSONResponse({"path": p, "exists": bool(p and os.path.isfile(p))})
    finally:
        _record_request_timing(started, ok)


@app.get("/api/status")
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


@app.get("/metrics")
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
        "# HELP stack_mcp_ui_up UI process is healthy.",
        "# TYPE stack_mcp_ui_up gauge",
        "stack_mcp_ui_up 1",
        "# HELP stack_mcp_module_up Backend module health check (1=ok).",
        "# TYPE stack_mcp_module_up gauge",
    ]
    for name, st in checks.items():
        value = 1 if st.get("ok") else 0
        lines.append(f'stack_mcp_module_up{{module="{name}"}} {value}')
        latency = st.get("latency_ms")
        if isinstance(latency, int):
            lines.append(f'stack_mcp_module_latency_ms{{module="{name}"}} {latency}')

    lines.extend(
        [
            "# HELP stack_mcp_ui_requests_total Total secured API requests.",
            "# TYPE stack_mcp_ui_requests_total counter",
            f"stack_mcp_ui_requests_total {int(snap.get('requests_total', 0.0))}",
            "# HELP stack_mcp_ui_auth_failed_total Unauthorized API requests.",
            "# TYPE stack_mcp_ui_auth_failed_total counter",
            f"stack_mcp_ui_auth_failed_total {int(snap.get('auth_failed_total', 0.0))}",
            "# HELP stack_mcp_ui_rate_limited_total Rate-limited API requests.",
            "# TYPE stack_mcp_ui_rate_limited_total counter",
            f"stack_mcp_ui_rate_limited_total {int(snap.get('rate_limited_total', 0.0))}",
            "# HELP stack_mcp_ui_request_errors_total API handler errors.",
            "# TYPE stack_mcp_ui_request_errors_total counter",
            f"stack_mcp_ui_request_errors_total {int(snap.get('request_errors_total', 0.0))}",
            "# HELP stack_mcp_ui_request_latency_seconds_sum Total API handler latency.",
            "# TYPE stack_mcp_ui_request_latency_seconds_sum counter",
            f"stack_mcp_ui_request_latency_seconds_sum {snap.get('request_latency_sum_seconds', 0.0):.6f}",
            "# HELP stack_mcp_ui_request_latency_seconds_count API handler count for latency.",
            "# TYPE stack_mcp_ui_request_latency_seconds_count counter",
            f"stack_mcp_ui_request_latency_seconds_count {int(snap.get('request_latency_count', 0.0))}",
            "# HELP stack_mcp_ui_rate_limiter_events_last_minute Requests observed in in-memory limiter window.",
            "# TYPE stack_mcp_ui_rate_limiter_events_last_minute gauge",
            f"stack_mcp_ui_rate_limiter_events_last_minute {limiter['events_last_minute']}",
            "# HELP stack_mcp_metrics_auth_failed_total Failed /metrics auth attempts.",
            "# TYPE stack_mcp_metrics_auth_failed_total counter",
            f"stack_mcp_metrics_auth_failed_total {int(snap.get('metrics_auth_failed_total', 0.0))}",
        ]
    )

    if queue.get("ok"):
        lines.extend(
            [
                "# HELP stack_mcp_kafka_retained_messages Approx retained messages by topic (end-begin).",
                "# TYPE stack_mcp_kafka_retained_messages gauge",
            ]
        )
        topics = queue.get("topics", {})
        if isinstance(topics, dict):
            for topic, tdata in topics.items():
                if isinstance(tdata, dict):
                    retained = tdata.get("retained_messages")
                    if isinstance(retained, int):
                        lines.append(f'stack_mcp_kafka_retained_messages{{topic="{topic}"}} {retained}')
        total_retained = queue.get("total_retained_messages")
        if isinstance(total_retained, int):
            lines.append(
                "# HELP stack_mcp_kafka_retained_messages_total Sum retained messages over allowlisted topics."
            )
            lines.append("# TYPE stack_mcp_kafka_retained_messages_total gauge")
            lines.append(f"stack_mcp_kafka_retained_messages_total {total_retained}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/api/mcp/tools")
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


@app.post("/api/mcp/invoke")
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


@app.post("/api/seed")
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
                            ("seed from stack-mcp-ui",),
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
                doc = {"event": "seed", "ts": time.time(), "source": "stack-mcp-ui"}
                resp = client.index(
                    index="demo-mcp",
                    id=f"seed-{int(time.time())}",
                    body=doc,
                    refresh="true",
                )
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
                from stack_mcp.kafka_tools import kafka_produce

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


@app.get("/status-page", response_class=HTMLResponse)
async def status_page() -> str:
    return _STATUS_HTML


_INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>stack-mcp demo</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0 auto; max-width: 1100px; padding: 1.25rem; line-height: 1.45; }
    h1 { font-size: 1.35rem; }
    .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.75rem; }
    .card { border: 1px solid #8884; border-radius: 10px; padding: 0.75rem 0.9rem; }
    .ok { color: #0a7; }
    .bad { color: #c33; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0001; padding: 0.6rem; border-radius: 8px; max-height: 320px; overflow: auto; }
    button { margin: 0.15rem 0.35rem 0.15rem 0; padding: 0.35rem 0.55rem; border-radius: 8px; border: 1px solid #8886; background: #fff3; cursor: pointer; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .muted { opacity: 0.75; font-size: 0.92rem; }
    a { color: inherit; }
    .nav { margin: 0.5rem 0 0.75rem; font-size: 0.95rem; }
    .nav a { margin-right: 1rem; }
  </style>
</head>
<body>
  <h1>stack-mcp — демо UI</h1>
  <p class="nav">
    <a href="/status-page">Страница статуса /metrics</a>
    <span class="muted">(тот же токен метрик, что ниже)</span>
  </p>
  <p class="muted">Для <code>/api/*</code>: если задан <code>STACK_MCP_UI_TOKEN</code> — нужен Bearer; по умолчанию токен не требуется.</p>
  <p class="muted" id="auth-hint"></p>
  <input id="token" type="password" placeholder="STACK_MCP_UI_TOKEN (опционально)" style="width: min(520px, 100%); padding: 0.45rem; border-radius: 8px; border: 1px solid #8886;" />
  <p class="muted">Для <code>/metrics</code> (Prometheus) — отдельный секрет, если задан <code>STACK_MCP_METRICS_TOKEN</code>, или тот же UI token при <code>STACK_MCP_METRICS_ACCEPT_UI_BEARER=true</code>:</p>
  <input id="metrics-token" type="password" placeholder="STACK_MCP_METRICS_TOKEN (опционально)" style="width: min(520px, 100%); padding: 0.45rem; border-radius: 8px; border: 1px solid #8886;" />
  <p class="muted">Проверки идут напрямую в Docker-сервисы. Вызовы MCP — через <code>FastMCP.call_tool</code> (реальный сервер, не мок).</p>
  <p class="muted" id="cfgpath"></p>

  <div class="row" style="margin: 0.75rem 0;">
    <button id="btn-refresh">Обновить статус</button>
    <button id="btn-tools">Загрузить список MCP tools</button>
    <button id="btn-seed">Seed данных (Postgres/Redis/OpenSearch/Kafka)</button>
    <button id="btn-metrics">Обновить превью /metrics</button>
  </div>

  <h2>Модули MCP (включено в конфиге)</h2>
  <p class="muted">Те же флаги, что в <code>stack_mcp_status</code>: postgres, redis, kafka, prometheus, mail, opensearch, ssh.</p>
  <div class="row" id="modules-config"></div>

  <h2>Проверки доступности</h2>
  <p class="muted"><strong>kafka_queue</strong> — оценка «сколько сообщений в топиках» по allowlist (end−begin оффсетов), для сценариев с Kafka/Prometheus; нужен доступ к брокеру как у карточки kafka. <strong>ui_rate_limiter</strong> — счётчики лимита запросов к <code>/api/*</code>, не ошибка сервиса. <strong>ssh skipped</strong> — в конфиге <code>modules.ssh.enabled: false</code> (в <code>config.docker.yaml</code> модуль по умолчанию не включён).</p>
  <div class="row" id="status"></div>

  <h2>Prometheus: превью /metrics</h2>
  <pre id="metrics-preview" style="max-height: 240px;">—</pre>

  <h2>MCP tools</h2>
  <pre id="tools">—</pre>

  <h2>Вызов MCP (allowlist)</h2>
  <div id="invoke-buttons"></div>
  <pre id="invoke-out">—</pre>

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
    async function jget(url) { const r = await fetch(url, { headers: authHeader() }); if (!r.ok) throw new Error(await r.text()); return r.json(); }
    async function jpost(url, body) {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify(body || {}) });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    }
    function card(title, obj) {
      const el = document.createElement('div');
      el.className = 'card';
      if (obj && obj.info === true) {
        el.innerHTML = '<strong>' + title + '</strong> <span class="muted">info</span>' +
          '<pre>' + JSON.stringify(obj, null, 2) + '</pre>';
        return el;
      }
      const ok = obj && (obj.ok === true || obj.skipped === true);
      const flag = obj && obj.skipped ? 'skipped' : (obj && obj.ok ? 'ok' : 'bad');
      el.innerHTML = '<strong>' + title + '</strong> <span class="' + flag + '">' + (obj && obj.skipped ? 'skipped' : (obj && obj.ok ? 'ok' : 'fail')) + '</span>' +
        '<pre>' + JSON.stringify(obj, null, 2) + '</pre>';
      return el;
    }
    function moduleChip(name, on) {
      const el = document.createElement('div');
      el.className = 'card';
      el.innerHTML = '<strong>' + name + '</strong> <span class="' + (on ? 'ok' : 'muted') + '">' + (on ? 'on' : 'off') + '</span>';
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
    async function refreshStatus() {
      const s = await jget('/api/status');
      renderModulesEnabled(s.modules_enabled);
      const host = $('status');
      host.innerHTML = '';
      host.appendChild(card('postgres', s.postgres));
      host.appendChild(card('redis', s.redis));
      host.appendChild(card('kafka', s.kafka));
      host.appendChild(card('prometheus', s.prometheus));
      host.appendChild(card('opensearch', s.opensearch));
      host.appendChild(card('mail', s.mail));
      host.appendChild(card('ssh', s.ssh));
      host.appendChild(card('kafka_queue', s.kafka_queue));
      host.appendChild(card('ui_rate_limiter', s.ui_rate_limiter));
    }
    async function refreshMetricsPreview() {
      const r = await fetch('/metrics', { headers: metricsAuthHeader() });
      const t = await r.text();
      if (!r.ok) throw new Error(t);
      $('metrics-preview').textContent = t;
    }
    async function loadTools() {
      const t = await jget('/api/mcp/tools');
      $('tools').textContent = JSON.stringify(t, null, 2);
    }
    async function invoke(name) {
      $('invoke-out').textContent = '…';
      const r = await jpost('/api/mcp/invoke', { tool: name });
      $('invoke-out').textContent = JSON.stringify(r, null, 2);
    }
    async function seed() {
      $('invoke-out').textContent = 'Seeding…';
      const r = await jpost('/api/seed', {});
      $('invoke-out').textContent = JSON.stringify(r, null, 2);
      await refreshStatus();
      await refreshMetricsPreview().catch(() => {});
    }
    const allowed = [
      'stack_mcp_status','redis_ping','redis_info','redis_dbsize','postgres_connections_overview','postgres_database_sizes',
      'postgres_table_sizes','opensearch_cluster_health','opensearch_rag_policy','opensearch_list_indices','kafka_list_topics',
      'kafka_describe_topic','kafka_consume_recent','ssh_command_policy'
    ];
    function buildInvokeButtons() {
      const host = $('invoke-buttons');
      host.innerHTML = '';
      allowed.forEach(n => {
        const b = document.createElement('button');
        b.textContent = n;
        b.onclick = () => invoke(n);
        host.appendChild(b);
      });
    }
    async function boot() {
      const saved = localStorage.getItem('stack_mcp_ui_token') || '';
      $('token').value = saved;
      $('token').onchange = () => localStorage.setItem('stack_mcp_ui_token', $('token').value || '');
      const savedM = localStorage.getItem('stack_mcp_metrics_token') || '';
      $('metrics-token').value = savedM;
      $('metrics-token').onchange = () => localStorage.setItem('stack_mcp_metrics_token', $('metrics-token').value || '');
      try {
        const ac = await fetch('/api/auth-config').then((r) => r.json());
        if (ac.ui_bearer_enabled) {
          $('auth-hint').textContent = 'Сервер ожидает Bearer (STACK_MCP_UI_TOKEN) для /api/*.';
        } else {
          $('auth-hint').textContent = 'Сервер: /api/* без Bearer (STACK_MCP_UI_TOKEN не задан).';
        }
      } catch (e) {
        $('auth-hint').textContent = '';
      }
      try {
        const c = await jget('/api/config-path');
        $('cfgpath').textContent = 'STACK_MCP_CONFIG: ' + (c.path || '(не задан)') + (c.exists ? ' (ok)' : ' (файл не найден)');
      } catch (e) {
        $('cfgpath').textContent = 'config path error: ' + e;
      }
      buildInvokeButtons();
      $('btn-refresh').onclick = () => refreshStatus().catch(e => alert(e));
      $('btn-tools').onclick = () => loadTools().catch(e => alert(e));
      $('btn-seed').onclick = () => seed().catch(e => alert(e));
      $('btn-metrics').onclick = () => refreshMetricsPreview().catch(e => { $('metrics-preview').textContent = String(e); });
      await refreshStatus().catch(e => { $('status').textContent = String(e); });
      await refreshMetricsPreview().catch(e => { $('metrics-preview').textContent = String(e); });
    }
    boot();
  </script>
</body>
</html>
"""

_STATUS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>stack-mcp status</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0 auto; max-width: 1100px; padding: 1.25rem; line-height: 1.45; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0001; padding: 0.6rem; border-radius: 8px; }
    .muted { opacity: 0.8; }
    input { width: min(520px, 100%); padding: 0.45rem; border-radius: 8px; border: 1px solid #8886; }
  </style>
</head>
<body>
  <h1>MCP status / queue</h1>
  <p class="muted"><a href="/">← Демо UI</a></p>
  <p class="muted">Данные с <code>/metrics</code>. Если на сервере задан <code>STACK_MCP_METRICS_TOKEN</code> (или включён приём UI Bearer), введите тот же секрет ниже — он уходит только в заголовке <code>Authorization</code>, не в URL.</p>
  <p class="muted">JSON <code>/api/status</code> — с Bearer только если на сервере задан <code>STACK_MCP_UI_TOKEN</code>.</p>
  <p><input id="mtok" type="password" placeholder="STACK_MCP_METRICS_TOKEN (если требуется)" autocomplete="off" /></p>
  <pre id="out">Loading /metrics...</pre>
  <script>
    const $ = (id) => document.getElementById(id);
    function metricsHeaders() {
      const t = ($('mtok').value || '').trim();
      return t ? { 'Authorization': 'Bearer ' + t } : {};
    }
    async function load() {
      const r = await fetch('/metrics', { headers: metricsHeaders() });
      const t = await r.text();
      $('out').textContent = t;
    }
    $('mtok').value = localStorage.getItem('stack_mcp_metrics_token') || '';
    $('mtok').onchange = () => localStorage.setItem('stack_mcp_metrics_token', $('mtok').value || '');
    load().catch(e => { $('out').textContent = String(e); });
    setInterval(() => load().catch(() => {}), 15000);
  </script>
</body>
</html>
"""


def main() -> None:
    if _METRICS_REQUIRE_TOKEN and not _METRICS_TOKEN:
        raise RuntimeError(
            "STACK_MCP_METRICS_REQUIRE_TOKEN=true requires non-empty STACK_MCP_METRICS_TOKEN "
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
        log.warning("STACK_MCP_UI_TOKEN not set: /api/* accepts requests without Bearer (set token to enforce).")
    host = os.environ.get("STACK_MCP_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("STACK_MCP_UI_PORT", "8888"))
    if host.strip() in ("0.0.0.0", "[::]", "::"):
        if not _API_TOKEN:
            log.warning(
                "Listening on all interfaces: /api/* is not Bearer-protected (empty STACK_MCP_UI_TOKEN)."
            )
        if not _metrics_auth_required():
            log.warning(
                "Listening on all interfaces without /metrics authentication; set STACK_MCP_METRICS_TOKEN "
                "or STACK_MCP_METRICS_ACCEPT_UI_BEARER=true (or STACK_MCP_METRICS_REQUIRE_TOKEN=true)."
            )
    workers = max(1, int(os.environ.get("STACK_MCP_UI_WORKERS", "1")))
    log_level = (os.environ.get("STACK_MCP_LOG_LEVEL") or "info").strip().lower()
    if workers > 1:
        log.info("Uvicorn workers=%s (STACK_MCP_UI_WORKERS)", workers)
    uvicorn.run(
        "stack_mcp.info_app:app",
        host=host,
        port=port,
        workers=workers,
        reload=False,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
