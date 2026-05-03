from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from sdocs_mcp.backend_tls import prometheus_httpx_verify_and_cert
from sdocs_mcp.config import KafkaModuleConfig, PrometheusModuleConfig


def _read_optional_token(cfg: PrometheusModuleConfig) -> str | None:
    if cfg.bearer_token:
        return cfg.bearer_token
    if cfg.bearer_token_path:
        p = Path(cfg.bearer_token_path)
        if not p.is_file():
            raise FileNotFoundError(f"bearer_token_path not found: {p}")
        return p.read_text(encoding="utf-8").strip()
    return None


def _client(cfg: PrometheusModuleConfig) -> httpx.Client:
    token = _read_optional_token(cfg)
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    auth: httpx.Auth | None = None
    if cfg.basic_auth_username and cfg.basic_auth_password is not None:
        auth = httpx.BasicAuth(cfg.basic_auth_username, cfg.basic_auth_password)
    verify, cert = prometheus_httpx_verify_and_cert(cfg)
    return httpx.Client(
        base_url=cfg.base_url.rstrip("/"),
        headers=headers,
        auth=auth,
        timeout=cfg.timeout_seconds,
        verify=verify,
        cert=cert,
    )


def _get_json(cfg: PrometheusModuleConfig, path: str, params: dict[str, Any]) -> dict[str, Any]:
    with _client(cfg) as client:
        r = client.get(path, params=params)
        r.raise_for_status()
        return r.json()


def _truncate_instant_data(data: dict[str, Any], max_samples: int) -> dict[str, Any]:
    result = data.get("data", {}).get("result")
    if not isinstance(result, list) or len(result) <= max_samples:
        return data
    out = json.loads(json.dumps(data))
    out["data"]["result"] = result[:max_samples]
    out["_truncated"] = True
    out["_truncated_note"] = f"vector truncated to {max_samples} samples"
    return out


def _truncate_matrix_data(data: dict[str, Any], max_series: int, max_points_per_series: int) -> dict[str, Any]:
    result = data.get("data", {}).get("result")
    if not isinstance(result, list):
        return data
    out = json.loads(json.dumps(data))
    series = result[:max_series]
    for s in series:
        vals = s.get("values")
        if isinstance(vals, list) and len(vals) > max_points_per_series:
            s["values"] = vals[:max_points_per_series]
            s["_truncated_values"] = True
    out["data"]["result"] = series
    if len(result) > max_series:
        out["_truncated"] = True
        out["_truncated_note"] = f"matrix truncated to {max_series} series"
    return out


def _parse_ts(s: str) -> float:
    try:
        return float(s)
    except ValueError as e:
        raise ValueError(f"invalid timestamp: {s!r}") from e


def prometheus_query_instant(cfg: PrometheusModuleConfig, query: str, at_time: str | None = None) -> str:
    if not query or len(query) > 16_384:
        raise ValueError("query must be 1..16384 characters")
    params: dict[str, Any] = {"query": query}
    if at_time is not None:
        params["time"] = at_time
    data = _get_json(cfg, "/api/v1/query", params)
    data = _truncate_instant_data(data, cfg.max_vector_samples)
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_query_range(
    cfg: PrometheusModuleConfig,
    query: str,
    start: str,
    end: str,
    step: str,
) -> str:
    if not query or len(query) > 16_384:
        raise ValueError("query must be 1..16384 characters")
    t0 = _parse_ts(start)
    t1 = _parse_ts(end)
    if t1 < t0:
        raise ValueError("end must be >= start")
    if (t1 - t0) > cfg.max_query_range_seconds:
        raise ValueError(
            f"range {(t1 - t0):.0f}s exceeds max_query_range_seconds ({cfg.max_query_range_seconds})"
        )
    step_f = _parse_ts(step)
    if step_f <= 0:
        raise ValueError("step must be positive")
    points = (t1 - t0) / step_f
    if points > cfg.max_step_points:
        step_f = (t1 - t0) / cfg.max_step_points
        if step_f < cfg.min_step_seconds:
            step_f = cfg.min_step_seconds
        step = str(step_f)
    params = {"query": query, "start": start, "end": end, "step": step}
    data = _get_json(cfg, "/api/v1/query_range", params)
    data = _truncate_matrix_data(data, cfg.max_matrix_series, cfg.max_points_per_series)
    if points > cfg.max_step_points:
        data["_adjusted_step"] = step
        data["_adjusted_note"] = "step widened to respect max_step_points"
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_targets(cfg: PrometheusModuleConfig, state: str | None = None) -> str:
    params: dict[str, Any] = {}
    if state:
        if state not in ("active", "dropped", "any"):
            raise ValueError("state must be active|dropped|any")
        params["state"] = state
    data = _get_json(cfg, "/api/v1/targets", params)
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_metadata(cfg: PrometheusModuleConfig, metric: str | None = None) -> str:
    params: dict[str, Any] = {}
    if metric:
        params["metric"] = metric
    data = _get_json(cfg, "/api/v1/metadata", params)
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_series(
    cfg: PrometheusModuleConfig,
    match_queries: list[str],
    start: str | None = None,
    end: str | None = None,
) -> str:
    if not match_queries:
        raise ValueError("match_queries must be non-empty")
    if len(match_queries) > 20:
        raise ValueError("at most 20 match[] selectors")
    q: list[tuple[str, str]] = [("match[]", m) for m in match_queries]
    if start is not None:
        q.append(("start", start))
    if end is not None:
        q.append(("end", end))
    with _client(cfg) as client:
        r = client.get("/api/v1/series", params=q)
        r.raise_for_status()
        data = r.json()
    if isinstance(data.get("data"), list) and len(data["data"]) > cfg.max_series_matches:
        data["_truncated"] = True
        data["data"] = data["data"][: cfg.max_series_matches]
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_labels(cfg: PrometheusModuleConfig) -> str:
    data = _get_json(cfg, "/api/v1/labels", {})
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_rules(cfg: PrometheusModuleConfig) -> str:
    data = _get_json(cfg, "/api/v1/rules", {})
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_alerts(cfg: PrometheusModuleConfig) -> str:
    data = _get_json(cfg, "/api/v1/alerts", {})
    return json.dumps(data, indent=2, ensure_ascii=False)


def prometheus_export_instant_to_kafka(
    prom: PrometheusModuleConfig,
    kafka: KafkaModuleConfig,
    query: str,
    topic: str | None = None,
    message_key: str | None = None,
) -> str:
    if not kafka.allow_produce:
        raise PermissionError("kafka allow_produce must be true to export metrics")
    target_topic = topic or prom.kafka_metrics_topic
    if not target_topic:
        raise ValueError("topic required (or set prometheus.kafka_metrics_topic)")
    if target_topic not in kafka.topic_allowlist:
        raise PermissionError(f"topic {target_topic!r} not in kafka.topic_allowlist")

    payload = json.loads(prometheus_query_instant(prom, query))
    envelope = {
        "source": "sdocs-mcp-prometheus",
        "exported_at": time.time(),
        "query": query,
        "prometheus": prom.base_url,
        "result": payload,
    }
    body = json.dumps(envelope, ensure_ascii=False)
    if len(body.encode("utf-8")) > kafka.produce_max_message_bytes:
        raise ValueError(
            f"serialized payload exceeds kafka.produce_max_message_bytes ({kafka.produce_max_message_bytes})"
        )
    from sdocs_mcp.kafka_tools import kafka_produce

    return kafka_produce(
        kafka,
        target_topic,
        [{"key": message_key or "prometheus", "value": body}],
    )
