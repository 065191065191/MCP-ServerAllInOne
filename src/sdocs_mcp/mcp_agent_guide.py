"""Справочник для LLM: модули, tools и порядок работы (instructions + sdocs_mcp_capabilities)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sdocs_mcp import __version__
from sdocs_mcp.config import AppConfig
from sdocs_mcp.mcp_tool_docs import SERVER_MISSION_RU, _WORKFLOWS_RU, tool_hint

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LLM_PROMPT_PATH = _REPO_ROOT / "docs" / "LLM_SYSTEM_PROMPT.md"


def load_llm_system_prompt() -> str:
    """Текст для system prompt агента (из docs/LLM_SYSTEM_PROMPT.md)."""
    if not _LLM_PROMPT_PATH.is_file():
        return SERVER_MISSION_RU
    raw = _LLM_PROMPT_PATH.read_text(encoding="utf-8")
    if "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            block = parts[1].strip()
            if block.startswith("\n"):
                block = block[1:]
            if block and not block.startswith("Ты"):
                # fenced block after language tag line
                lines = block.splitlines()
                if lines and lines[0].isascii() and len(lines[0]) < 20:
                    block = "\n".join(lines[1:]).strip()
            return block.strip() or SERVER_MISSION_RU
    return raw.strip() or SERVER_MISSION_RU

# Имена tools (регистрация в server.py должна совпадать).
_POSTGRES_TOOLS = [
    "postgres_connections_overview",
    "postgres_long_running_queries",
    "postgres_blocking_chains",
    "postgres_database_sizes",
    "postgres_table_sizes",
    "postgres_index_usage",
    "postgres_cache_hit_ratio",
    "postgres_replication_lag",
    "postgres_autovacuum_health",
    "postgres_statements_top",
    "postgres_allowlisted_query_catalog",
    "postgres_allowlisted_query",
]

_TOOL_HINTS: dict[str, list[tuple[str, str]]] = {
    "core": [
        ("sdocs_mcp_status", tool_hint("sdocs_mcp_status")),
        ("sdocs_mcp_capabilities", tool_hint("sdocs_mcp_capabilities")),
        ("sdocs_alerting_status", tool_hint("sdocs_alerting_status")),
    ],
    "postgres": [(n, tool_hint(n)) for n in _POSTGRES_TOOLS],
    "redis": [
        ("redis_ping", "Redis PING — жив ли инстанс."),
        ("redis_info", "Redis INFO: server, memory, stats (снимок состояния кэша)."),
        ("redis_memory_stats", "Redis MEMORY STATS — детализация памяти."),
        ("redis_dbsize", "Redis DBSIZE — число ключей в текущей БД."),
        ("redis_slowlog_get", "Redis SLOWLOG — медленные команды."),
        ("redis_get", "Redis GET одного ключа (значение обрезается лимитом)."),
        ("redis_mget", "Redis MGET нескольких ключей."),
        ("redis_hgetall", "Redis HGETALL хэша."),
        ("redis_setex", "Redis SETEX — запись с TTL (лимиты размера)."),
        ("redis_scan_prefix", "Redis SCAN по prefix (только scan_enabled)."),
    ],
    "kafka": [
        (n, tool_hint(n))
        for n in (
            "kafka_list_topics",
            "kafka_describe_topic",
            "kafka_consume_recent",
            "kafka_produce",
            "kafka_create_topic",
        )
    ],
    "prometheus": [(n, tool_hint(n)) for n in (
        "prometheus_mcp_guide",
        "prometheus_query_instant",
        "prometheus_query_range",
        "prometheus_targets",
        "prometheus_metadata",
        "prometheus_series",
        "prometheus_labels",
        "prometheus_rules",
        "prometheus_alerts",
        "prometheus_export_instant_to_kafka",
    )],
    "mail": [
        ("mail_imap_list_mailboxes", "IMAP: список папок."),
        ("mail_imap_search", "IMAP: поиск UID писем."),
        ("mail_imap_fetch_rfc822", "IMAP: тело письма по UID (лимит байт)."),
        ("mail_smtp_send", "SMTP: to_addr, subject, body_text (не to/body)."),
    ],
    "opensearch": [(n, tool_hint(n)) for n in (
        "opensearch_cluster_health",
        "opensearch_cluster_health_debug",
        "opensearch_cluster_stats",
        "opensearch_nodes_stats",
        "opensearch_pending_tasks",
        "opensearch_cluster_settings",
        "opensearch_cat_shards",
        "opensearch_allocation_explain",
        "opensearch_list_indices",
        "opensearch_get_mapping",
        "opensearch_search",
        "opensearch_count",
        "opensearch_delete_index",
    )],
    "opensearch_rag": [
        ("opensearch_rag_policy", "RAG: политика — перед записью в память агента."),
        ("opensearch_rag_stats", "RAG: число документов в allowlist индексах."),
        ("opensearch_rag_store", "RAG: сохранить текст."),
        ("opensearch_rag_search", "RAG: поиск."),
        ("opensearch_rag_delete_document", "RAG: удалить doc (allow_delete_by_id)."),
    ],
    "ssh": [
        ("ssh_command_policy", "SSH: правила команд — прочитать перед ssh_run_command."),
        ("ssh_hosts_overview", "SSH: список host_id из конфига."),
        ("ssh_run_command", "SSH: команда на host_id (фильтры безопасности)."),
    ],
}

_WORKFLOWS = dict(_WORKFLOWS_RU)


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
        "mission": SERVER_MISSION_RU,
        "llm_system_prompt": load_llm_system_prompt(),
        "modules_enabled": enabled,
        "tools_total": len(flat),
        "tools_by_module": by_mod,
        "workflows": workflows,
        "s3_mcp_note": (
            "Отдельный MCP s3-mcp :8766. Запись s3_put_object (до 1 МБ) и удаление s3_delete_object "
            "выключены по умолчанию — UI Консоль → MCP → S3 MCP → allow_put / allow_delete."
        ),
    }


def build_mcp_instructions(app: AppConfig) -> str:
    cap = build_capabilities_payload(app)
    enabled_names = [k for k, v in cap["modules_enabled"].items() if v and k != "opensearch_rag"]
    if cap["modules_enabled"].get("opensearch_rag"):
        enabled_names.append("opensearch_rag")
    mods = ", ".join(enabled_names) if enabled_names else "только core"
    return (
        f"{SERVER_MISSION_RU} "
        f"SDocsMCP v{__version__}. Модули: {mods}. Tools: {cap['tools_total']}. "
        "sdocs_mcp_capabilities — полный справочник. "
        "Prometheus = метрики подов. OpenSearch = логи (*ds*, ms-*, istio, ingress, sowa, iam). "
        "Kafka consume_recent = свежесть данных в топике. Postgres = 10 диагностик без psql."
    )


def capabilities_json(app: AppConfig) -> str:
    return json.dumps(build_capabilities_payload(app), indent=2, ensure_ascii=False)
