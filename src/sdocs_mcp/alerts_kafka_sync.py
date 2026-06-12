"""Синхронизация Alert между подами: Kafka topics sdocs.alerts.*."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from typing import Any

from kafka import KafkaConsumer, KafkaProducer

from sdocs_mcp.alerts_evaluator import run_leader_evaluation_tick
from sdocs_mcp.alerts_notify import deliver_alert
from sdocs_mcp.alerts_store import apply_payload, list_rules, snapshot
from sdocs_mcp.alerts_kafka_resolve import alerts_kafka_ready, resolve_alerts_kafka
from sdocs_mcp.config import AppConfig, load_config
from sdocs_mcp.config_runtime import refresh_config_state_from_disk
from sdocs_mcp.kafka_topics import SDOCS_ALERTS_EVENTS, SDOCS_ALERTS_LOCK, SDOCS_ALERTS_RULES
from sdocs_mcp.kafka_tools import kafka_broker_client_config

_log = logging.getLogger("sdocs_mcp.alerts_kafka")

_instance_id = (
    (os.environ.get("SDOCS_MCP_AUDIT_INSTANCE_ID") or "").strip()
    or (os.environ.get("HOSTNAME") or "").strip()
    or socket.gethostname()
)
_stop = threading.Event()
_threads: list[threading.Thread] = []
_is_leader = False
_leader_lock = threading.Lock()


def publish_rules_snapshot() -> bool:
    cfg = load_config()
    ready, _src = alerts_kafka_ready(cfg)
    if not ready:
        return False
    k, _ = resolve_alerts_kafka(cfg)
    assert k is not None
    payload = snapshot()
    payload["source"] = _instance_id
    payload["type"] = "rules_sync"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    prod = KafkaProducer(**kafka_broker_client_config(k))
    try:
        prod.send(SDOCS_ALERTS_RULES, value=body, key=b"rules")
        prod.flush(10)
        return True
    finally:
        prod.close()


def _rules_consumer_loop() -> None:
    while not _stop.is_set():
        try:
            cfg = load_config()
            k, src = resolve_alerts_kafka(cfg)
            if k is None:
                time.sleep(5)
                continue
            consumer = KafkaConsumer(
                SDOCS_ALERTS_RULES,
                **kafka_broker_client_config(k),
                group_id="sdocs-mcp-alerts-rules",
                auto_offset_reset="latest",
                enable_auto_commit=True,
                consumer_timeout_ms=2000,
            )
            while not _stop.is_set():
                for msg in consumer:
                    try:
                        data = json.loads(msg.value.decode("utf-8"))
                        if isinstance(data, dict):
                            apply_payload(data)
                    except Exception as e:
                        _log.warning("rules message parse error: %s", e)
            consumer.close()
        except Exception as e:
            # Невалидный mcp.conf (напр. allowlisted_queries без sql) — не спамить traceback.
            if "ValidationError" in type(e).__name__ or "validation error" in str(e).lower():
                _log.error("rules consumer: invalid config — %s", e)
            else:
                _log.warning("rules consumer restart: %s", e)
            time.sleep(30)


def _leader_loop() -> None:
    global _is_leader
    while not _stop.is_set():
        try:
            cfg = load_config()
            ready, src = alerts_kafka_ready(cfg)
            if not ready:
                time.sleep(10)
                continue
            k, _ = resolve_alerts_kafka(cfg)
            assert k is not None
            consumer = KafkaConsumer(
                **kafka_broker_client_config(k),
                group_id="sdocs-mcp-alerts-leader",
                enable_auto_commit=True,
                consumer_timeout_ms=3000,
            )
            consumer.subscribe([SDOCS_ALERTS_LOCK])
            while not _stop.is_set():
                consumer.poll(timeout_ms=5000)
                assigned = consumer.assignment()
                lead = any(tp.topic == SDOCS_ALERTS_LOCK and tp.partition == 0 for tp in assigned)
                with _leader_lock:
                    _is_leader = lead
                if lead:
                    _evaluator_tick(cfg)
                time.sleep(max(15, int(os.environ.get("SDOCS_MCP_ALERTS_TICK_SEC", "60"))))
            consumer.close()
        except Exception as e:
            _log.warning("leader loop: %s", e)
            time.sleep(10)


def _rule_by_id(rule_id: str | None) -> dict[str, Any] | None:
    if not rule_id:
        return None
    for r in list_rules():
        if str(r.get("id") or "") == str(rule_id):
            return r
    return None


def _evaluator_tick(cfg: AppConfig) -> None:
    try:
        cfg = refresh_config_state_from_disk()
    except Exception:
        cfg = load_config()
    events = run_leader_evaluation_tick(cfg)
    if not events:
        return
    snap = snapshot()
    groups = snap.get("groups") if isinstance(snap.get("groups"), list) else []
    for ev in events:
        rule = _rule_by_id(ev.get("rule_id"))
        if rule is None:
            rule = {"name": ev.get("rule_name"), "id": ev.get("rule_id")}
        deliver_alert(
            cfg,
            rule,
            ev,
            groups=groups,
            instance_id=_instance_id,
        )
    k, _ = resolve_alerts_kafka(cfg)
    if k is None:
        return
    prod = KafkaProducer(**kafka_broker_client_config(k))
    try:
        for ev in events:
            prod.send(
                SDOCS_ALERTS_EVENTS,
                value=json.dumps(ev, ensure_ascii=False).encode("utf-8"),
                key=str(ev.get("dedup_key", "")).encode("utf-8"),
            )
        prod.flush(10)
    finally:
        prod.close()


def is_alert_leader() -> bool:
    with _leader_lock:
        return _is_leader


def start_alerts_kafka_sync() -> None:
    if (os.environ.get("SDOCS_MCP_ALERTS_SYNC") or "true").strip().lower() in ("0", "false", "no"):
        return
    if _threads:
        return
    t1 = threading.Thread(target=_rules_consumer_loop, name="alerts-rules", daemon=True)
    t2 = threading.Thread(target=_leader_loop, name="alerts-leader", daemon=True)
    _threads.extend([t1, t2])
    t1.start()
    t2.start()
    cfg = load_config()
    _, src = resolve_alerts_kafka(cfg)
    _log.info(
        "Alerts Kafka sync started via %s (topics %s, %s, %s); instance=%s",
        src,
        SDOCS_ALERTS_RULES,
        SDOCS_ALERTS_EVENTS,
        SDOCS_ALERTS_LOCK,
        _instance_id,
    )


def stop_alerts_kafka_sync() -> None:
    _stop.set()
