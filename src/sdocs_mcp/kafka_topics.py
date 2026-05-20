"""Имена топиков Kafka SDocsMCP (единый префикс sdocs.*)."""

from __future__ import annotations

# Prometheus Cron → Kafka (уже использовался)
SDOCS_PROMETHEUS_METRICS = "sdocs.prometheus.metrics"

# Alerting: правила, события, блокировка лидера (1 partition)
SDOCS_ALERTS_RULES = "sdocs.alerts.rules"
SDOCS_ALERTS_EVENTS = "sdocs.alerts.events"
SDOCS_ALERTS_LOCK = "sdocs.alerts.lock"

# Для документации / allowlist в config.example
SDOCS_KAFKA_TOPICS_CREATE: tuple[str, ...] = (
    SDOCS_PROMETHEUS_METRICS,
    SDOCS_ALERTS_RULES,
    SDOCS_ALERTS_EVENTS,
    SDOCS_ALERTS_LOCK,
)

TOPIC_NOTES: dict[str, str] = {
    SDOCS_PROMETHEUS_METRICS: "Cron/UI: снимки PromQL (instant), ключ metrics_cron",
    SDOCS_ALERTS_RULES: "Все поды: синхронизация правил и групп Alert (JSON)",
    SDOCS_ALERTS_EVENTS: "Сработавшие алерты с dedup_key (не спамить почтой)",
    SDOCS_ALERTS_LOCK: "1 partition — только лидер выполняет проверки правил",
}
