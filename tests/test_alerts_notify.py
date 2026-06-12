"""Тесты доставки алертов и полей OpenSearch-правил."""

from __future__ import annotations

from unittest.mock import patch

from sdocs_mcp.alerts_evaluator import resolve_opensearch_rule_fields, rule_enabled
from sdocs_mcp.alerts_notify import (
    deliver_alert,
    format_alert_message,
    notify_log_snapshot,
    resolve_email_recipients,
    resolve_rule_notify,
)
from sdocs_mcp.config import AlertingNotifyConfig, AppConfig, MailModuleConfig


def test_resolve_opensearch_rule_fields_explicit() -> None:
    rule = {
        "index": "app-logs",
        "query": "level:WARN",
        "condition": "no_logs",
        "window_hours": 2,
        "threshold": 5,
    }
    f = resolve_opensearch_rule_fields(rule)
    assert f["index"] == "app-logs"
    assert f["query"] == "level:WARN"
    assert f["condition"] == "no_logs"
    assert f["window_hours"] == 2.0


def test_resolve_opensearch_rule_fields_legacy_params() -> None:
    rule = {"params": "index ms-logs; query level:ERROR AND message:*timeout*"}
    f = resolve_opensearch_rule_fields(rule)
    assert f["index"] == "ms-logs"
    assert "timeout" in f["query"]


def test_rule_enabled_default_true() -> None:
    assert rule_enabled({"name": "x"}) is True
    assert rule_enabled({"name": "x", "enabled": False}) is False


def test_resolve_email_from_group() -> None:
    cfg = AppConfig()
    rule = {"group_id": "ops"}
    groups = [{"id": "ops", "emails": "a@x.com, b@x.com"}]
    assert resolve_email_recipients(cfg, rule, groups) == "a@x.com, b@x.com"
    rule2 = {"notify_target": "direct@x.com", "group_id": "ops"}
    assert resolve_email_recipients(cfg, rule2, groups) == "direct@x.com"


def test_resolve_rule_notify_webhook_default() -> None:
    n = AlertingNotifyConfig(default_channel="webhook", webhook_url="https://hook.example/alerts")
    ch, tgt = resolve_rule_notify({"notify_channel": "webhook"}, n)
    assert ch == "webhook"
    assert tgt == "https://hook.example/alerts"


def test_deliver_alert_none_channel() -> None:
    cfg = AppConfig()
    cfg.modules.alerting.notify.default_channel = "none"
    ev = {"rule_name": "test", "detail": "x", "fired_at": "t"}
    entry = deliver_alert(cfg, {"name": "test", "notify_channel": "none"}, ev)
    assert entry["ok"] is True
    assert "none" in entry["detail"]
    assert notify_log_snapshot(5)


def test_deliver_alert_email_mock() -> None:
    cfg = AppConfig()
    cfg.modules.mail = MailModuleConfig(
        enabled=True,
        imap_password="imap-secret",
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_username="u",
        smtp_password="p",
    )
    rule = {"name": "r1", "notify_channel": "email", "notify_target": "ops@test.com"}
    ev = {"rule_name": "r1", "detail": "5 hits", "fired_at": "2026-01-01T00:00:00Z", "mcp_source": "opensearch"}
    with patch("sdocs_mcp.alerts_notify.mail_smtp_send", return_value='{"ok": true}') as m:
        entry = deliver_alert(cfg, rule, ev)
    assert entry["ok"] is True
    m.assert_called_once()
    subj, body = format_alert_message(ev, rule)
    assert "r1" in subj
    assert "5 hits" in body


def test_deliver_alert_email_failure_logged() -> None:
    cfg = AppConfig()
    cfg.modules.mail.enabled = False
    entry = deliver_alert(
        cfg,
        {"name": "r", "notify_channel": "email", "notify_target": "a@b.c"},
        {"rule_name": "r"},
    )
    assert entry["ok"] is False
    assert "mail" in entry["detail"].lower() or "enabled" in entry["detail"].lower()
