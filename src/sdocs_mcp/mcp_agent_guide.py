"""Справочник для LLM: модули, tools и порядок работы (instructions + sdocs_mcp_capabilities)."""

from __future__ import annotations

import json
from typing import Any

from sdocs_mcp import __version__
from sdocs_mcp.config import AppConfig

# Имена tools и краткие подсказки (регистрация в server.py должна совпадать).
_TOOL_HINTS: dict[str, list[tuple[str, str]]] = {
    "core": [
        ("sdocs_mcp_status", "Какие модули enabled в конфиге (вызовите первым)."),
        ("sdocs_mcp_capabilities", "Этот путеводитель: все tools по модулям и сценарии."),
    ],
    "postgres": [
        ("postgres_connections_overview", "Сессии по state."),
        ("postgres_long_running_queries", "Долгие активные запросы."),
        ("postgres_blocking_chains", "Блокировки."),
        ("postgres_database_sizes", "Размеры БД."),
        ("postgres_table_sizes", "Топ таблиц в schema_allowlist."),
        ("postgres_index_usage", "Малоиспользуемые индексы."),
        ("postgres_cache_hit_ratio", "Hit ratio буфера."),
        ("postgres_replication_lag", "Репликация."),
        ("postgres_autovacuum_health", "Autovacuum / dead tuples."),
        ("postgres_statements_top", "pg_stat_statements."),
        ("postgres_allowlisted_query_catalog", "Список id allowlisted SQL (если есть в конфиге)."),
        ("postgres_allowlisted_query", "Выполнить allowlisted SELECT по query_id (не сырой SQL)."),
    ],
    "redis": [
        ("redis_ping", "PING."),
        ("redis_info", "INFO server/memory/…"),
        ("redis_memory_stats", "MEMORY STATS."),
        ("redis_dbsize", "DBSIZE."),
        ("redis_slowlog_get", "SLOWLOG."),
        ("redis_get", "GET ключа."),
        ("redis_mget", "MGET."),
        ("redis_hgetall", "HGETALL."),
        ("redis_setex", "SETEX (лимиты)."),
        ("redis_scan_prefix", "SCAN по prefix (если scan_enabled)."),
    ],
    "kafka": [
        ("kafka_list_topics", "Список топиков."),
        ("kafka_describe_topic", "Партиции топика."),
        ("kafka_consume_recent", "Хвост партиции."),
        ("kafka_produce", "Запись в allowlisted topic (allow_produce)."),
        ("kafka_create_topic", "Создать топик (allow_admin)."),
    ],
    "prometheus": [
        ("prometheus_mcp_guide", "Отличие MCP Prometheus от /metrics SDocsMCP."),
        ("prometheus_query_instant", "PromQL instant к base_url."),
        ("prometheus_query_range", "PromQL range."),
        ("prometheus_targets", "Scrape targets."),
        ("prometheus_metadata", "Метаданные метрик."),
        ("prometheus_series", "Series match[]."),
        ("prometheus_labels", "Имена labels."),
        ("prometheus_rules", "Recording/alerting rules."),
        ("prometheus_alerts", "Активные алерты."),
        ("prometheus_export_instant_to_kafka", "Instant → Kafka (allow_produce + allowlist)."),
    ],
    "mail": [
        ("mail_imap_list_mailboxes", "Список ящиков IMAP."),
        ("mail_imap_search", "Поиск писем."),
        ("mail_imap_fetch_rfc822", "Получить письмо по UID."),
        ("mail_smtp_send", "SMTP: to_addr, subject, body_text (не to/body)."),
    ],
    "opensearch": [
        ("opensearch_cluster_health", "Health кластера."),
        ("opensearch_cluster_health_debug", "Health + отладка."),
        ("opensearch_cluster_stats", "Статистика кластера."),
        ("opensearch_nodes_stats", "Статистика нод."),
        ("opensearch_pending_tasks", "Очередь задач."),
        ("opensearch_cluster_settings", "Настройки кластера."),
        ("opensearch_cat_shards", "Шарды."),
        ("opensearch_allocation_explain", "Explain allocation."),
        ("opensearch_list_indices", "Список индексов."),
        ("opensearch_get_mapping", "Mapping индекса."),
        ("opensearch_search", "Поиск: query_json — строка JSON DSL."),
        ("opensearch_count", "Count документов."),
        ("opensearch_delete_index", "Удалить индекс (если allow_write)."),
    ],
    "opensearch_rag": [
        ("opensearch_rag_policy", "Политика RAG — вызвать перед записью."),
        ("opensearch_rag_stats", "Число документов в allowlist индексах."),
        ("opensearch_rag_store", "Сохранить текст в RAG."),
        ("opensearch_rag_search", "Поиск в RAG."),
        ("opensearch_rag_delete_document", "Удалить doc (если allow_delete_by_id)."),
    ],
    "ssh": [
        ("ssh_command_policy", "Правила команд SSH — прочитать перед ssh_run_command."),
        ("ssh_hosts_overview", "Список host_id из конфига."),
        ("ssh_run_command", "Команда на host_id (фильтры безопасности)."),
    ],
}

_WORKFLOWS: dict[str, str] = {
    "postgres": "Диагностика: connections_overview → long_running / blocking → table_sizes. Allowlist: catalog → allowlisted_query(query_id).",
    "redis": "ping → info / memory_stats → get/mget при известных ключах.",
    "kafka": "list_topics → describe_topic → consume_recent; produce только в topic_allowlist.",
    "prometheus": "Сначала prometheus_mcp_guide. PromQL: query_instant / query_range. Не путать с HTTP /metrics SDocsMCP.",
    "mail": "imap_list_mailboxes → search → fetch; отправка: smtp_send.",
    "opensearch": "cluster_health → list_indices → search/count по индексу.",
    "opensearch_rag": "rag_policy → rag_store / rag_search.",
    "ssh": "ssh_command_policy → ssh_hosts_overview → ssh_run_command.",
}


def _postgres_tools(app: AppConfig) -> list[tuple[str, str]]:
    out = list(_TOOL_HINTS["postgres"][:10])
    if app.modules.postgres.allowlisted_queries:
        out.extend(_TOOL_HINTS["postgres"][10:12])
    return out


def _redis_tools(app: AppConfig) -> list[tuple[str, str]]:
    out = list(_TOOL_HINTS["redis"][:8])
    if app.modules.redis.scan_enabled:
        out.append(_TOOL_HINTS["redis"][8])
    return out


def _kafka_tools(app: AppConfig) -> list[tuple[str, str]]:
    k = app.modules.kafka
    out = list(_TOOL_HINTS["kafka"][:3])
    if k.allow_produce:
        out.append(_TOOL_HINTS["kafka"][3])
    if k.allow_admin:
        out.append(_TOOL_HINTS["kafka"][4])
    return out


def _prometheus_tools(app: AppConfig) -> list[tuple[str, str]]:
    p = app.modules.prometheus
    k = app.modules.kafka
    out = list(_TOOL_HINTS["prometheus"][:9])
    if k.enabled and k.allow_produce:
        out.append(_TOOL_HINTS["prometheus"][9])
    return out


def _opensearch_tools(app: AppConfig) -> list[tuple[str, str]]:
    o = app.modules.opensearch
    # Индексы 0..11 — всегда регистрируются в server._register_opensearch; [12] — delete_index.
    out = list(_TOOL_HINTS["opensearch"][:12])
    if o.allow_write:
        out.append(_TOOL_HINTS["opensearch"][12])
    return out


def _opensearch_rag_tools(app: AppConfig) -> list[tuple[str, str]]:
    o = app.modules.opensearch
    if not o.enabled or not o.rag.enabled:
        return []
    out = list(_TOOL_HINTS["opensearch_rag"][:4])
    if o.rag.allow_delete_by_id:
        out.append(_TOOL_HINTS["opensearch_rag"][4])
    return out


def tools_by_module(app: AppConfig) -> dict[str, list[dict[str, str]]]:
    """Tools, доступные при текущем конфиге (как после build_mcp)."""
    m = app.modules
    result: dict[str, list[dict[str, str]]] = {
        "core": [{"name": n, "hint": h} for n, h in _TOOL_HINTS["core"]],
    }
    if m.postgres.enabled:
        result["postgres"] = [{"name": n, "hint": h} for n, h in _postgres_tools(app)]
    if m.redis.enabled:
        result["redis"] = [{"name": n, "hint": h} for n, h in _redis_tools(app)]
    if m.kafka.enabled:
        result["kafka"] = [{"name": n, "hint": h} for n, h in _kafka_tools(app)]
    if m.prometheus.enabled:
        result["prometheus"] = [{"name": n, "hint": h} for n, h in _prometheus_tools(app)]
    if m.mail.enabled:
        result["mail"] = [{"name": n, "hint": h} for n, h in _TOOL_HINTS["mail"]]
    if m.opensearch.enabled:
        result["opensearch"] = [{"name": n, "hint": h} for n, h in _opensearch_tools(app)]
        rag = _opensearch_rag_tools(app)
        if rag:
            result["opensearch_rag"] = [{"name": n, "hint": h} for n, h in rag]
    if m.ssh.enabled:
        result["ssh"] = [{"name": n, "hint": h} for n, h in _TOOL_HINTS["ssh"]]
    return result


def build_capabilities_payload(app: AppConfig) -> dict[str, Any]:
    by_mod = tools_by_module(app)
    flat = [t["name"] for tools in by_mod.values() for t in tools]
    enabled = {
        "postgres": app.modules.postgres.enabled,
        "redis": app.modules.redis.enabled,
        "kafka": app.modules.kafka.enabled,
        "prometheus": app.modules.prometheus.enabled,
        "mail": app.modules.mail.enabled,
        "opensearch": app.modules.opensearch.enabled,
        "opensearch_rag": app.modules.opensearch.enabled and app.modules.opensearch.rag.enabled,
        "ssh": app.modules.ssh.enabled,
    }
    workflows = {k: _WORKFLOWS[k] for k in by_mod if k in _WORKFLOWS}
    return {
        "server": "sdocs-mcp",
        "version": __version__,
        "modules_enabled": enabled,
        "tools_total": len(flat),
        "tools_by_module": by_mod,
        "workflows": workflows,
    }


def build_mcp_instructions(app: AppConfig) -> str:
    """Текст server instructions для MCP-клиента (Cursor и др.)."""
    cap = build_capabilities_payload(app)
    enabled_names = [k for k, v in cap["modules_enabled"].items() if v and k != "opensearch_rag"]
    if cap["modules_enabled"].get("opensearch_rag"):
        enabled_names.append("opensearch_rag")
    mods = ", ".join(enabled_names) if enabled_names else "только core (см. modules_enabled в sdocs_mcp_capabilities)"
    return (
        f"SDocsMCP v{__version__} — Streamable HTTP MCP. "
        f"sdocs_mcp_capabilities — полный список tools; sdocs_mcp_status — флаги модулей и путь к конфигу. "
        f"Модули в этом процессе: {mods}. "
        f"Всего tools: {cap['tools_total']}. "
        "PostgreSQL: диагностика + postgres_allowlisted_query(query_id). "
        "Prometheus: prometheus_* к удалённому Prometheus; не путать с /metrics SDocsMCP — prometheus_mcp_guide. "
        "Kafka: topic_allowlist; produce при allow_produce. "
        "OpenSearch RAG: opensearch_rag_policy перед записью. "
        "SSH: ssh_command_policy перед ssh_run_command."
    )


def capabilities_json(app: AppConfig) -> str:
    return json.dumps(build_capabilities_payload(app), indent=2, ensure_ascii=False)
