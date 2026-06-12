"""Проверка правил Alert и статусы MCP-источников (серый / зелёный / красный)."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from sdocs_mcp.alerts_mcp_sources import module_enabled
from sdocs_mcp.alerts_store import list_rules
from sdocs_mcp.config import AppConfig
from sdocs_mcp.opensearch_tools import close_opensearch_client, connect_opensearch, opensearch_cluster_health

# rule_id → last_fire_unix
_fire_cooldown: dict[str, float] = {}

RuleUiState = str  # inactive | ok | error | firing


def _parse_opensearch_params(params: str) -> dict[str, str]:
    """index ms-logs; query level:ERROR AND message:*404* (legacy строка params)."""
    out: dict[str, str] = {}
    s = (params or "").strip()
    if not s:
        return out
    m = re.search(r"index\s+([\w.*-]+)", s, re.I)
    if m:
        out["index"] = m.group(1).rstrip(";,")
    m = re.search(r"query\s+(.+)$", s, re.I)
    if m:
        out["query"] = m.group(1).strip()
    return out


def resolve_opensearch_rule_fields(rule: dict[str, Any]) -> dict[str, Any]:
    """
    Нормализованные поля OpenSearch-правила для UI и evaluator.
    Явные rule.index / rule.query имеют приоритет над legacy params.
    """
    legacy = _parse_opensearch_params(str(rule.get("params") or rule.get("source") or ""))
    index = str(rule.get("index") or legacy.get("index") or "*").strip() or "*"
    query = str(rule.get("query") or legacy.get("query") or "level:ERROR").strip() or "level:ERROR"
    condition = str(rule.get("condition") or "count_threshold").strip().lower()
    if condition not in ("count_threshold", "no_logs"):
        condition = "count_threshold"
    time_field = str(rule.get("time_field") or "@timestamp").strip() or "@timestamp"
    return {
        "index": index,
        "query": query,
        "condition": condition,
        "time_field": time_field,
        "window_hours": float(rule.get("window_hours") or 1),
        "threshold": int(rule.get("threshold") or 2),
    }


def rule_enabled(rule: dict[str, Any]) -> bool:
    if "enabled" not in rule:
        return True
    return bool(rule.get("enabled"))


def mcp_source_health(cfg: AppConfig, source_id: str) -> dict[str, Any]:
    if not module_enabled(cfg, source_id):
        return {
            "state": "inactive",
            "label": "не в конфиге",
            "detail": f"modules.{source_id}.enabled=false",
        }
    if source_id == "opensearch":
        try:
            raw = json.loads(opensearch_cluster_health(cfg.modules.opensearch))
            if "error" in raw:
                return {"state": "error", "label": "ошибка", "detail": str(raw["error"])[:300]}
            status = str(raw.get("status", "")).lower()
            if status in ("green", "yellow"):
                return {"state": "ok", "label": "доступен", "detail": f"cluster {status}"}
            return {"state": "error", "label": "кластер", "detail": f"status={status}"}
        except Exception as e:
            return {"state": "error", "label": "ошибка", "detail": str(e)[:300]}
    if source_id == "prometheus":
        from sdocs_mcp.info_app import _check_prometheus

        st = _check_prometheus(cfg)
        if st.get("skipped"):
            return {"state": "inactive", "label": "выкл.", "detail": st.get("detail", "")}
        if st.get("ok"):
            return {"state": "ok", "label": "доступен", "detail": st.get("detail", "")}
        return {"state": "error", "label": "ошибка", "detail": st.get("detail", "")[:300]}
    if source_id == "kafka":
        from sdocs_mcp.info_app import _check_kafka

        st = _check_kafka(cfg)
        if st.get("skipped"):
            return {"state": "inactive", "label": "выкл.", "detail": st.get("detail", "")}
        if st.get("ok"):
            return {"state": "ok", "label": "доступен", "detail": f"topics={st.get('topic_count', '?')}"}
        return {"state": "error", "label": "ошибка", "detail": st.get("detail", "")[:300]}
    if source_id == "redis":
        from sdocs_mcp.info_app import _check_redis

        st = _check_redis(cfg)
        if st.get("ok"):
            return {"state": "ok", "label": "доступен", "detail": st.get("detail", "")}
        if st.get("skipped"):
            return {"state": "inactive", "label": "выкл.", "detail": st.get("detail", "")}
        return {"state": "error", "label": "ошибка", "detail": st.get("detail", "")[:300]}
    if source_id == "postgres":
        from sdocs_mcp.info_app import _check_postgres

        st = _check_postgres(cfg)
        if st.get("ok"):
            return {"state": "ok", "label": "доступен", "detail": st.get("detail", "")}
        if st.get("skipped"):
            return {"state": "inactive", "label": "выкл.", "detail": st.get("detail", "")}
        return {"state": "error", "label": "ошибка", "detail": st.get("detail", "")[:300]}
    return {"state": "inactive", "label": "нет проверки", "detail": "источник без health probe"}


def _opensearch_log_count(cfg: AppConfig, fields: dict[str, Any]) -> int:
    index = fields["index"]
    q = fields["query"]
    window_h = fields["window_hours"]
    time_field = fields["time_field"]
    client = connect_opensearch(cfg.modules.opensearch)
    body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [{"query_string": {"query": q}}],
                "filter": [{"range": {time_field: {"gte": f"now-{max(1, int(window_h))}h"}}}],
            }
        },
    }
    try:
        resp = client.search(index=index if index != "*" else "*", body=body)
    finally:
        close_opensearch_client(client)
    total = resp.get("hits", {}).get("total", {})
    return int(total.get("value", total) if isinstance(total, dict) else int(total or 0))


def _eval_opensearch_rule(cfg: AppConfig, rule: dict[str, Any]) -> dict[str, Any]:
    fields = resolve_opensearch_rule_fields(rule)
    count = _opensearch_log_count(cfg, fields)
    condition = fields["condition"]
    threshold = fields["threshold"]
    window_h = fields["window_hours"]

    if condition == "no_logs":
        fired = count == 0
        detail = (
            f"нет логов по запросу за {window_h}ч (найдено {count})"
            if fired
            else f"{count} hits за {window_h}ч — условие «нет логов» не выполнено"
        )
    else:
        fired = count >= threshold
        detail = f"{count} hits за {window_h}ч (порог ≥{threshold})"

    return {
        "ok": True,
        "count": count,
        "threshold": threshold,
        "condition": condition,
        "index": fields["index"],
        "query": fields["query"],
        "fired": fired,
        "detail": detail,
    }


def evaluate_rule(cfg: AppConfig, rule: dict[str, Any]) -> dict[str, Any]:
    if not rule_enabled(rule):
        return {
            "ui_state": "inactive",
            "health": {"state": "inactive", "label": "выкл.", "detail": "правило отключено"},
            "evaluation": None,
        }
    src = str(rule.get("mcp_source") or "").strip().lower()
    health = mcp_source_health(cfg, src)
    if health["state"] == "inactive":
        return {"ui_state": "inactive", "health": health, "evaluation": None}
    if health["state"] == "error":
        return {"ui_state": "error", "health": health, "evaluation": None}
    if src == "opensearch":
        try:
            ev = _eval_opensearch_rule(cfg, rule)
            ui = "firing" if ev.get("fired") else "ok"
            return {"ui_state": ui, "health": health, "evaluation": ev}
        except Exception as e:
            return {
                "ui_state": "error",
                "health": health,
                "evaluation": {"ok": False, "detail": str(e)[:400]},
            }
    return {
        "ui_state": "ok",
        "health": health,
        "evaluation": {"ok": True, "detail": "источник доступен; условие не автоматизировано"},
    }


def rule_ui_statuses(cfg: AppConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rule in list_rules():
        st = evaluate_rule(cfg, rule)
        fields = resolve_opensearch_rule_fields(rule) if str(rule.get("mcp_source") or "").lower() == "opensearch" else {}
        rows.append(
            {
                "id": rule.get("id"),
                "name": rule.get("name"),
                "mcp_source": rule.get("mcp_source"),
                "enabled": rule_enabled(rule),
                "index": fields.get("index"),
                "query": fields.get("query"),
                "condition": fields.get("condition"),
                "notify_channel": rule.get("notify_channel"),
                "notify_target": rule.get("notify_target"),
                "ui_state": st["ui_state"],
                "health": st["health"],
                "evaluation": st.get("evaluation"),
            }
        )
    return rows


def should_emit_alert(rule: dict[str, Any]) -> bool:
    rid = str(rule.get("id") or rule.get("name") or "")
    cooldown = max(60, int(rule.get("cooldown_sec") or rule.get("interval_sec") or 3600))
    now = time.time()
    last = _fire_cooldown.get(rid, 0)
    if now - last < cooldown:
        return False
    _fire_cooldown[rid] = now
    return True


def run_leader_evaluation_tick(cfg: AppConfig) -> list[dict[str, Any]]:
    """Один проход для лидера; возвращает события для Kafka."""
    events: list[dict[str, Any]] = []
    for rule in list_rules():
        st = evaluate_rule(cfg, rule)
        if st["ui_state"] != "firing":
            continue
        if not should_emit_alert(rule):
            continue
        ev_body = st.get("evaluation") or {}
        events.append(
            {
                "type": "alert_fired",
                "rule_id": rule.get("id"),
                "rule_name": rule.get("name"),
                "mcp_source": rule.get("mcp_source"),
                "group_id": rule.get("group_id"),
                "index": ev_body.get("index") or rule.get("index"),
                "query": ev_body.get("query") or rule.get("query"),
                "notify_channel": rule.get("notify_channel"),
                "notify_target": rule.get("notify_target"),
                "detail": ev_body.get("detail"),
                "fired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "dedup_key": f"{rule.get('id')}:{int(time.time()) // max(60, int(rule.get('cooldown_sec') or 3600))}",
            }
        )
    return events
