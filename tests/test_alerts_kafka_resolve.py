from __future__ import annotations

from sdocs_mcp.alerts_kafka_resolve import alerts_kafka_ready, resolve_alerts_kafka
from sdocs_mcp.config import AlertingModuleConfig, AppConfig, KafkaModuleConfig, ModulesConfig
from sdocs_mcp.kafka_topics import SDOCS_ALERTS_EVENTS, SDOCS_ALERTS_LOCK, SDOCS_ALERTS_RULES


def _alert_topics() -> list[str]:
    return [SDOCS_ALERTS_RULES, SDOCS_ALERTS_EVENTS, SDOCS_ALERTS_LOCK]


def test_resolve_prefers_alerting_kafka() -> None:
    cfg = AppConfig(
        modules=ModulesConfig(
            kafka=KafkaModuleConfig(
                enabled=True,
                bootstrap_servers=["mon:9092"],
                topic_allowlist=["ms-eda"],
                allow_produce=True,
            ),
            alerting=AlertingModuleConfig(
                enabled=True,
                kafka=KafkaModuleConfig(
                    enabled=True,
                    bootstrap_servers=["alerts:9092"],
                    topic_allowlist=_alert_topics(),
                    allow_produce=True,
                ),
            ),
        )
    )
    k, src = resolve_alerts_kafka(cfg)
    assert k is not None
    assert k.bootstrap_servers == ["alerts:9092"]
    assert src == "modules.alerting.kafka"
    assert alerts_kafka_ready(cfg)[0] is True


def test_resolve_fallback_modules_kafka() -> None:
    cfg = AppConfig(
        modules=ModulesConfig(
            kafka=KafkaModuleConfig(
                enabled=True,
                bootstrap_servers=["mon:9092"],
                topic_allowlist=["ms-eda", *_alert_topics()],
                allow_produce=True,
            ),
        )
    )
    k, src = resolve_alerts_kafka(cfg)
    assert src == "modules.kafka"
    assert alerts_kafka_ready(cfg)[0] is True
