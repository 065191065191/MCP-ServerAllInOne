from sdocs_mcp.config import (
    AppConfig,
    KafkaModuleConfig,
    ModulesConfig,
    PrometheusMetricsCronConfig,
    PrometheusModuleConfig,
)
from sdocs_mcp.prometheus_cron import cron_readiness, get_cron_status
from sdocs_mcp.prometheus_tools import (
    DEFAULT_KAFKA_METRICS_TOPIC,
    resolve_kafka_metrics_topic,
)


def test_resolve_kafka_metrics_topic_default() -> None:
    prom = PrometheusModuleConfig(enabled=True)
    assert resolve_kafka_metrics_topic(prom, None) == DEFAULT_KAFKA_METRICS_TOPIC
    assert resolve_kafka_metrics_topic(prom, "custom.topic") == "custom.topic"


def test_cron_readiness_requires_prometheus() -> None:
    cfg = AppConfig(
        modules=ModulesConfig(
            prometheus=PrometheusModuleConfig(enabled=False),
            kafka=KafkaModuleConfig(enabled=True, allow_produce=True, topic_allowlist=["x"]),
        )
    )
    ok, reason = cron_readiness(cfg)
    assert not ok
    assert "Prometheus" in reason


def test_cron_readiness_ok() -> None:
    topic = DEFAULT_KAFKA_METRICS_TOPIC
    cfg = AppConfig(
        modules=ModulesConfig(
            prometheus=PrometheusModuleConfig(
                enabled=True,
                base_url="http://127.0.0.1:9090",
                kafka_metrics_topic=topic,
                metrics_cron=PrometheusMetricsCronConfig(),
            ),
            kafka=KafkaModuleConfig(
                enabled=True,
                allow_produce=True,
                topic_allowlist=[topic],
            ),
        )
    )
    ok, _ = cron_readiness(cfg)
    assert ok


def test_get_cron_status_includes_hint(monkeypatch) -> None:
    topic = DEFAULT_KAFKA_METRICS_TOPIC
    cfg = AppConfig(
        modules=ModulesConfig(
            prometheus=PrometheusModuleConfig(
                enabled=True,
                base_url="http://127.0.0.1:9090",
                kafka_metrics_topic=topic,
            ),
            kafka=KafkaModuleConfig(
                enabled=True,
                allow_produce=True,
                topic_allowlist=[topic],
            ),
        )
    )

    import sdocs_mcp.prometheus_cron as pc

    monkeypatch.setattr(pc, "load_config", lambda: cfg)
    st = get_cron_status()
    assert st["configured"] is True
    assert st["active"] is True
    assert st["enabled"] is True
    assert st["running"] is False
    assert "prometheus_mcp_guide" in st["mcp_tools_hint"]


def test_cron_skip_does_not_set_last_error(monkeypatch) -> None:
    cfg = AppConfig(
        modules=ModulesConfig(
            prometheus=PrometheusModuleConfig(enabled=False),
        )
    )
    import sdocs_mcp.prometheus_cron as pc

    monkeypatch.setattr(pc, "load_config", lambda: cfg)
    pc._run_once()
    st = get_cron_status()
    assert st["last_skip_reason"]
    assert st["last_error"] is None
