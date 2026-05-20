"""Выбор Kafka для Alert: отдельный кластер или fallback на modules.kafka."""

from __future__ import annotations

from sdocs_mcp.config import AppConfig, KafkaModuleConfig
from sdocs_mcp.kafka_topics import SDOCS_ALERTS_EVENTS, SDOCS_ALERTS_LOCK, SDOCS_ALERTS_RULES

_ALERT_TOPICS = (SDOCS_ALERTS_RULES, SDOCS_ALERTS_EVENTS, SDOCS_ALERTS_LOCK)


def resolve_alerts_kafka(cfg: AppConfig) -> tuple[KafkaModuleConfig | None, str]:
    """
    Приоритет: modules.alerting.kafka (отдельный брокер для Alert),
    иначе modules.kafka (если enabled + allow_produce).
    """
    al = cfg.modules.alerting
    if al.enabled and al.kafka.enabled:
        return al.kafka, "modules.alerting.kafka"
    k = cfg.modules.kafka
    if k.enabled and k.allow_produce:
        return k, "modules.kafka"
    return None, "none"


def alerts_kafka_ready(cfg: AppConfig) -> tuple[bool, str]:
    """Готовность sync: брокер выбран и все sdocs.alerts.* в topic_allowlist."""
    k, source = resolve_alerts_kafka(cfg)
    if k is None:
        return False, "no kafka for alerting (enable modules.alerting.kafka or modules.kafka)"
    missing = [t for t in _ALERT_TOPICS if t not in k.topic_allowlist]
    if missing:
        return False, f"{source}: add to topic_allowlist: {missing}"
    return True, source
