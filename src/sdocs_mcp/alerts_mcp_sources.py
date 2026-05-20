"""Доступные источники проверок Alert = модули MCP."""

from __future__ import annotations

from typing import Any

from sdocs_mcp.config import AppConfig

# id → label, модуль конфига, пример
MCP_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("opensearch", "OpenSearch", "opensearch"),
    ("prometheus", "Prometheus", "prometheus"),
    ("postgres", "PostgreSQL", "postgres"),
    ("redis", "Redis", "redis"),
    ("kafka", "Kafka", "kafka"),
    ("mail", "Mail", "mail"),
    ("ssh", "SSH", "ssh"),
)


def list_sources(cfg: AppConfig) -> list[dict[str, Any]]:
    m = cfg.modules
    enabled_map = {
        "opensearch": m.opensearch.enabled,
        "prometheus": m.prometheus.enabled,
        "postgres": m.postgres.enabled,
        "redis": m.redis.enabled,
        "kafka": m.kafka.enabled,
        "mail": m.mail.enabled,
        "ssh": m.ssh.enabled,
    }
    out: list[dict[str, Any]] = []
    for sid, label, _mod in MCP_SOURCES:
        out.append(
            {
                "id": sid,
                "label": label,
                "enabled_in_config": enabled_map.get(sid, False),
                "example_source": f"{sid}: см. поле параметров",
            }
        )
    return out


def module_enabled(cfg: AppConfig, source_id: str) -> bool:
    m = cfg.modules
    return {
        "opensearch": m.opensearch.enabled,
        "prometheus": m.prometheus.enabled,
        "postgres": m.postgres.enabled,
        "redis": m.redis.enabled,
        "kafka": m.kafka.enabled,
        "mail": m.mail.enabled,
        "ssh": m.ssh.enabled,
    }.get(source_id, False)
