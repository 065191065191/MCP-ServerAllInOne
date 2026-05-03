"""Учёт вызовов MCP tools в OpenSearch: 10 признаков классификации, аргументы, ответ, длительность."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from opensearchpy.exceptions import OpenSearchException

from sdocs_mcp.config import OpenSearchModuleConfig, OpenSearchToolCallAuditConfig
from sdocs_mcp.opensearch_tools import connect_opensearch
from sdocs_mcp.tool_audit_http_context import current_http_caller_hints

log = logging.getLogger("sdocs_mcp.tool_audit")

# Увеличивайте при изменении mapping / обязательных полей (старый индекс с strict — см. README).
_TOOL_AUDIT_SCHEMA_VERSION = 3

_ADMIN_TOOLS = frozenset({"opensearch_delete_index", "kafka_create_topic"})
_WRITE_TOOLS = frozenset(
    {
        "kafka_produce",
        "redis_setex",
        "mail_smtp_send",
        "ssh_run_command",
        "opensearch_rag_store",
        "opensearch_rag_delete_document",
        "prometheus_export_instant_to_kafka",
    }
)

# Инструменты с наиболее чувствительным или широким эффектом на внешние системы.
_HIGH_RISK_TOOLS = frozenset(
    {
        "ssh_run_command",
        "opensearch_delete_index",
        "kafka_create_topic",
        "kafka_produce",
        "mail_smtp_send",
    }
)

_MODULE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("postgres_", "postgres"),
    ("redis_", "redis"),
    ("kafka_", "kafka"),
    ("mail_", "mail"),
    ("prometheus_", "prometheus"),
    ("opensearch_", "opensearch"),
    ("ssh_", "ssh"),
)


def classify_tool_invocation(tool_name: str) -> dict[str, str]:
    """Базовые три поля (совместимость с тестами и старыми отчётами)."""
    facets = tool_audit_classification_facets(tool_name, {}, 0.0)
    return {
        "module": str(facets["module"]),
        "category": str(facets["category"]),
        "operation_kind": str(facets["operation_kind"]),
    }


def _duration_bucket(duration_ms: float) -> str:
    if duration_ms < 50:
        return "lt_50ms"
    if duration_ms < 200:
        return "50ms_200ms"
    if duration_ms < 1000:
        return "200ms_1s"
    if duration_ms < 10_000:
        return "1s_10s"
    return "gte_10s"


def _tool_family(name: str) -> str:
    if name == "sdocs_mcp_status":
        return "meta"
    if "_" in name:
        return name.split("_", 1)[0]
    return "other"


def _risk_tier(name: str, operation_kind: str) -> str:
    if name in _HIGH_RISK_TOOLS:
        return "high"
    if operation_kind == "admin":
        return "high"
    if operation_kind == "write":
        return "medium"
    return "low"


def tool_audit_classification_facets(
    tool_name: str,
    arguments: dict[str, Any],
    duration_ms: float,
) -> dict[str, Any]:
    """Десять аналитических признаков вызова (плюс производные для фильтров в OpenSearch).

    1. module — семья бэкенда (postgres, redis, …).
    2. category — meta | data_plane | rag.
    3. operation_kind — read | write | admin.
    4. tool_family — грубая группа по префиксу имени (первый сегмент до «_»).
    5. risk_tier — low | medium | high (эвристика по инструменту и виду операции).
    6. api_surface — источник вызова (сейчас всегда mcp_tool; зарезервировано).
    7. rag_lane — затронут ли RAG-слой OpenSearch (имя содержит opensearch_rag).
    8. mutating — потенциальная запись/админ-действие (write или admin).
    9. argument_key_count — число ключей в JSON аргументах.
    10. duration_bucket — корзина длительности для гистограмм без числовых aggs по float.
    """
    name = tool_name.strip()
    module = "other"
    for prefix, mod in _MODULE_PREFIXES:
        if name.startswith(prefix):
            module = mod
            break
    if name == "sdocs_mcp_status":
        module = "core"

    if "opensearch_rag" in name:
        category = "rag"
    elif module == "core":
        category = "meta"
    else:
        category = "data_plane"

    if name in _ADMIN_TOOLS:
        operation_kind = "admin"
    elif name in _WRITE_TOOLS:
        operation_kind = "write"
    else:
        operation_kind = "read"

    rag_lane = "opensearch_rag" in name
    mutating = operation_kind in ("write", "admin")

    return {
        "module": module,
        "category": category,
        "operation_kind": operation_kind,
        "tool_family": _tool_family(name),
        "risk_tier": _risk_tier(name, operation_kind),
        "api_surface": "mcp_tool",
        "rag_lane": rag_lane,
        "mutating": mutating,
        "argument_key_count": len(arguments or {}),
        "duration_bucket": _duration_bucket(duration_ms),
    }


def audit_should_skip(tool_name: str, aud: OpenSearchToolCallAuditConfig) -> bool:
    return tool_name.strip() in aud.exclude_tools


def default_tool_audit_index_body() -> dict[str, Any]:
    """Mapping нового индекса аудита (strict). См. README про миграцию при смене schema_version."""
    return {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "schema_version": {"type": "integer"},
                "ingested_at": {"type": "date"},
                "instance_id": {"type": "keyword"},
                "caller_id": {"type": "keyword"},
                "caller_client_ip": {"type": "keyword"},
                "tool_name": {"type": "keyword"},
                "module": {"type": "keyword"},
                "category": {"type": "keyword"},
                "operation_kind": {"type": "keyword"},
                "tool_family": {"type": "keyword"},
                "risk_tier": {"type": "keyword"},
                "api_surface": {"type": "keyword"},
                "rag_lane": {"type": "boolean"},
                "mutating": {"type": "boolean"},
                "argument_key_count": {"type": "integer"},
                "duration_bucket": {"type": "keyword"},
                "ok": {"type": "boolean"},
                "duration_ms": {"type": "float"},
                "error": {"type": "text", "index": False},
                "arguments_json": {"type": "text", "index": False},
                "arguments_truncated": {"type": "boolean"},
                "result_text": {"type": "text", "index": False},
                "result_truncated": {"type": "boolean"},
                "result_chars": {"type": "integer"},
            },
        },
    }


def _ensure_tool_audit_index(client: Any, index: str, auto_create: bool) -> None:
    if client.indices.exists(index=index):
        return
    if not auto_create:
        raise ValueError(
            f"OpenSearch tool_call_audit: индекс {index!r} отсутствует. Создайте его или включите tool_call_audit.auto_create_index"
        )
    client.indices.create(index=index, body=default_tool_audit_index_body())


def _tool_result_to_audit_text(result: Any, max_chars: int) -> tuple[str, bool]:
    truncated = False
    if result is None:
        s = ""
    elif isinstance(result, dict):
        s = json.dumps(result, ensure_ascii=False)
    elif isinstance(result, str):
        s = result
    elif isinstance(result, (list, tuple)):
        parts: list[str] = []
        for block in result:
            txt = getattr(block, "text", None)
            if txt is not None:
                parts.append(str(txt))
            else:
                parts.append(f"<{type(block).__name__}>")
        s = "\n".join(parts)
    else:
        s = str(result)
    if len(s) > max_chars:
        s = s[:max_chars]
        truncated = True
    return s, truncated


def resolve_tool_audit_caller(aud: OpenSearchToolCallAuditConfig) -> tuple[str, str]:
    """Идентификатор вызывающей стороны и (опционально) IP для HTTP; для stdio — env/конфиг."""
    hints = current_http_caller_hints()
    principal = (hints.header_caller or "").strip()
    if not principal:
        principal = (os.environ.get("SDOCS_MCP_AUDIT_CALLER_ID") or aud.default_caller_id or "").strip()
    if not principal:
        principal = "unknown"
    ip = ""
    if aud.log_http_client_ip:
        ip = (hints.client_host or "").strip()
    return principal, ip


def _arguments_json(arguments: dict[str, Any], max_chars: int) -> tuple[str, bool]:
    try:
        raw = json.dumps(arguments or {}, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        raw = json.dumps({"_serialization_error": True}, ensure_ascii=False)
    truncated = len(raw) > max_chars
    if truncated:
        raw = raw[:max_chars]
    return raw, truncated


def audit_log_tool_invocation_sync(
    os_cfg: OpenSearchModuleConfig,
    aud: OpenSearchToolCallAuditConfig,
    tool_name: str,
    arguments: dict[str, Any],
    result: Any,
    error: str | None,
    duration_ms: float,
) -> None:
    if not os_cfg.enabled or not aud.enabled:
        return
    idx = aud.index.strip()
    facets = tool_audit_classification_facets(tool_name, arguments, duration_ms)
    args_s, args_trunc = _arguments_json(arguments or {}, aud.max_arguments_json_chars)
    res_s, res_trunc = _tool_result_to_audit_text(result, aud.max_result_chars)
    instance = (os.environ.get("SDOCS_MCP_AUDIT_INSTANCE_ID") or aud.instance_id or "").strip()
    caller_id, caller_ip = resolve_tool_audit_caller(aud)

    body: dict[str, Any] = {
        "schema_version": _TOOL_AUDIT_SCHEMA_VERSION,
        "ingested_at": datetime.now(UTC).isoformat(),
        "instance_id": instance or "default",
        "caller_id": caller_id,
        "caller_client_ip": caller_ip,
        "tool_name": tool_name,
        "module": facets["module"],
        "category": facets["category"],
        "operation_kind": facets["operation_kind"],
        "tool_family": facets["tool_family"],
        "risk_tier": facets["risk_tier"],
        "api_surface": facets["api_surface"],
        "rag_lane": facets["rag_lane"],
        "mutating": facets["mutating"],
        "argument_key_count": facets["argument_key_count"],
        "duration_bucket": facets["duration_bucket"],
        "ok": error is None,
        "duration_ms": round(duration_ms, 3),
        "error": error or "",
        "arguments_json": args_s,
        "arguments_truncated": args_trunc,
        "result_text": res_s,
        "result_truncated": res_trunc,
        "result_chars": len(res_s),
    }

    client = connect_opensearch(os_cfg)
    _ensure_tool_audit_index(client, idx, aud.auto_create_index)
    try:
        client.index(
            index=idx,
            id=str(uuid.uuid4()),
            body=body,
            refresh=False,
        )
    except OpenSearchException as e:
        log.warning("OpenSearch tool audit index failed: %s", e)
