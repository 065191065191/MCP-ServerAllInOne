from __future__ import annotations

import json
import uuid
from typing import Any

from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic

from stack_mcp.backend_tls import kafka_apply_mtls
from stack_mcp.config import KafkaModuleConfig


def _base_kafka_connection(cfg: KafkaModuleConfig) -> dict[str, Any]:
    conf: dict[str, Any] = {
        "bootstrap_servers": cfg.bootstrap_servers,
        "security_protocol": cfg.security_protocol,
    }
    if cfg.sasl_mechanism:
        conf["sasl_mechanism"] = cfg.sasl_mechanism
    if cfg.sasl_username:
        conf["sasl_plain_username"] = cfg.sasl_username
    if cfg.sasl_password:
        conf["sasl_plain_password"] = cfg.sasl_password
    kafka_apply_mtls(conf, cfg)
    return conf


def kafka_broker_client_config(cfg: KafkaModuleConfig) -> dict[str, Any]:
    """Bootstrap + SASL + опциональный mTLS (для UI-проб и внешних вызовов)."""
    return _base_kafka_connection(cfg)


def _consumer_config(cfg: KafkaModuleConfig) -> dict[str, Any]:
    conf = _base_kafka_connection(cfg)
    conf.update(
        {
            "enable_auto_commit": False,
            "consumer_timeout_ms": max(1000, cfg.consume_timeout_seconds * 1000),
            "group_id": f"stack-mcp-{uuid.uuid4()}",
        }
    )
    return conf


def _producer_config(cfg: KafkaModuleConfig) -> dict[str, Any]:
    return _base_kafka_connection(cfg)


def _admin_config(cfg: KafkaModuleConfig) -> dict[str, Any]:
    return _base_kafka_connection(cfg)


def _ensure_topic(cfg: KafkaModuleConfig, topic: str) -> None:
    if topic not in cfg.topic_allowlist:
        raise PermissionError(f"topic {topic!r} not in allowlist {cfg.topic_allowlist!r}")


def kafka_list_topics(cfg: KafkaModuleConfig) -> str:
    consumer = KafkaConsumer(**_consumer_config(cfg))
    try:
        topics = sorted(consumer.topics())
    finally:
        consumer.close()
    cap = min(cfg.list_topics_max, 5000)
    return json.dumps({"topics": topics[:cap], "truncated": len(topics) > cap, "total": len(topics)}, indent=2)


def kafka_describe_topic(cfg: KafkaModuleConfig, topic: str) -> str:
    _ensure_topic(cfg, topic)
    consumer = KafkaConsumer(**_consumer_config(cfg))
    try:
        parts = consumer.partitions_for_topic(topic) or set()
        out: dict[str, Any] = {"topic": topic, "partitions": sorted(parts)}
    finally:
        consumer.close()
    return json.dumps(out, indent=2)


def kafka_consume_recent(
    cfg: KafkaModuleConfig,
    topic: str,
    partition: int,
    max_messages: int | None = None,
) -> str:
    _ensure_topic(cfg, topic)
    cap_m = max_messages if max_messages is not None else cfg.consume_max_messages
    cap_m = max(1, min(cap_m, cfg.consume_max_messages))
    max_bytes = max(1024, min(cfg.consume_max_bytes, 16_777_216))

    consumer = KafkaConsumer(**_consumer_config(cfg))
    try:
        tp = TopicPartition(topic, partition)
        consumer.assign([tp])
        end = consumer.end_offsets([tp])[tp]
        start = max(0, end - cap_m)
        consumer.seek(tp, start)
        collected: list[dict[str, Any]] = []
        total_bytes = 0
        stop_outer = False
        while len(collected) < cap_m:
            batch = consumer.poll(timeout_ms=500)
            if not batch:
                break
            stop_outer = False
            for _, records in batch.items():
                for rec in records:
                    raw = rec.value or b""
                    if total_bytes + len(raw) > max_bytes:
                        return json.dumps(
                            {
                                "messages": collected,
                                "truncated_bytes": True,
                                "note": "stopped due to consume_max_bytes",
                            },
                            indent=2,
                            default=str,
                        )
                    total_bytes += len(raw)
                    collected.append(
                        {
                            "partition": rec.partition,
                            "offset": rec.offset,
                            "key": (rec.key.decode("utf-8", errors="replace") if rec.key else None),
                            "value": raw.decode("utf-8", errors="replace"),
                            "timestamp": rec.timestamp,
                        }
                    )
                    if len(collected) >= cap_m:
                        stop_outer = True
                        break
                if stop_outer:
                    break
            if stop_outer:
                break
    finally:
        consumer.close()

    return json.dumps({"messages": collected, "truncated_bytes": False}, indent=2, default=str)


def kafka_produce(
    cfg: KafkaModuleConfig,
    topic: str,
    messages: list[dict[str, str]],
) -> str:
    if not cfg.allow_produce:
        raise PermissionError("kafka produce is disabled (allow_produce: false)")
    _ensure_topic(cfg, topic)
    if not messages:
        raise ValueError("messages must be non-empty")
    if len(messages) > cfg.produce_max_messages:
        raise ValueError(f"at most {cfg.produce_max_messages} messages per call")
    producer = KafkaProducer(**_producer_config(cfg))
    try:
        for m in messages:
            val = (m.get("value") or "").encode("utf-8")
            if len(val) > cfg.produce_max_message_bytes:
                raise ValueError(f"message exceeds produce_max_message_bytes ({cfg.produce_max_message_bytes})")
            key = m.get("key")
            kb = key.encode("utf-8") if key else None
            producer.send(topic, value=val, key=kb)
        producer.flush(timeout=30)
    finally:
        producer.close()
    return json.dumps({"ok": True, "sent": len(messages)}, indent=2)


def kafka_create_topic(cfg: KafkaModuleConfig, topic: str, num_partitions: int = 1, replication_factor: int = 1) -> str:
    if not cfg.allow_admin:
        raise PermissionError("kafka admin is disabled (allow_admin: false)")
    _ensure_topic(cfg, topic)
    admin = KafkaAdminClient(**_admin_config(cfg))
    try:
        admin.create_topics(
            [NewTopic(name=topic, num_partitions=num_partitions, replication_factor=replication_factor)],
            validate_only=False,
        )
    finally:
        admin.close()
    return json.dumps({"ok": True, "created": topic}, indent=2)
