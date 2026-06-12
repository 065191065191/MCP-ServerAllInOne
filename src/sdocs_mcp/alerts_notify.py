"""Доставка сработавших алертов (email / webhook / telegram) и журнал попыток."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any

from sdocs_mcp.config import AlertingNotifyConfig, AppConfig, MailModuleConfig
from sdocs_mcp.credentials import env_optional
from sdocs_mcp.mail_tools import mail_smtp_send

_log = logging.getLogger("sdocs_mcp.alerts_notify")

_MAX_LOG = 200
_log_lock = threading.Lock()
_notify_log: deque[dict[str, Any]] = deque(maxlen=_MAX_LOG)


def notify_log_snapshot(limit: int = 50) -> list[dict[str, Any]]:
    cap = max(1, min(limit, _MAX_LOG))
    with _log_lock:
        return list(_notify_log)[-cap:]


def _append_log(entry: dict[str, Any]) -> None:
    with _log_lock:
        _notify_log.append(entry)


def resolve_rule_notify(rule: dict[str, Any], notify_cfg: AlertingNotifyConfig) -> tuple[str, str]:
    """(channel, target) — из правила или defaults из конфига."""
    ch = str(rule.get("notify_channel") or notify_cfg.default_channel or "email").strip().lower()
    if ch not in ("email", "webhook", "telegram", "none"):
        ch = notify_cfg.default_channel
    target = str(rule.get("notify_target") or "").strip()
    if ch == "webhook" and not target:
        target = (notify_cfg.webhook_url or "").strip()
    if ch == "telegram" and not target:
        target = (notify_cfg.telegram_chat_id or "").strip()
    return ch, target


def _telegram_token(notify_cfg: AlertingNotifyConfig) -> str:
    if (notify_cfg.telegram_bot_token or "").strip():
        return notify_cfg.telegram_bot_token.strip()
    if (notify_cfg.telegram_bot_token_env or "").strip():
        return (env_optional(notify_cfg.telegram_bot_token_env) or "").strip()
    return ""


def resolve_email_recipients(cfg: AppConfig, rule: dict[str, Any], groups: list[dict[str, Any]] | None = None) -> str:
    """Получатели email: rule.notify_target → группа → пусто."""
    target = str(rule.get("notify_target") or "").strip()
    if target:
        return target
    gid = str(rule.get("group_id") or "").strip()
    if not gid:
        return ""
    for g in groups or []:
        if str(g.get("id") or "") == gid:
            return str(g.get("emails") or "").strip()
    return ""


def format_alert_message(event: dict[str, Any], rule: dict[str, Any] | None = None) -> tuple[str, str]:
    """(subject, body_text) для уведомления."""
    name = str(event.get("rule_name") or (rule or {}).get("name") or "Alert")
    detail = str(event.get("detail") or "")
    fired = str(event.get("fired_at") or "")
    src = str(event.get("mcp_source") or "")
    idx = str(event.get("index") or (rule or {}).get("index") or "")
    q = str(event.get("query") or (rule or {}).get("query") or "")
    subject = f"[SDocsMCP Alert] {name}"
    lines = [
        f"Правило: {name}",
        f"Источник: {src}",
        f"Время: {fired}",
        f"Детали: {detail}",
    ]
    if idx:
        lines.append(f"Индекс: {idx}")
    if q:
        lines.append(f"Запрос: {q}")
    if rule and rule.get("description"):
        lines.append(f"Описание: {rule['description']}")
    return subject, "\n".join(lines)


def _http_post_json(url: str, payload: dict[str, Any], timeout: float) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def _send_webhook(url: str, subject: str, body: str, event: dict[str, Any], timeout: float) -> None:
    if not url:
        raise ValueError("webhook URL не задан (правило notify_target или modules.alerting.notify.webhook_url)")
    payload = {
        "subject": subject,
        "text": body,
        "alert": event,
    }
    _http_post_json(url, payload, timeout)


def _send_telegram(token: str, chat_id: str, text: str, api_base: str) -> None:
    if not token:
        raise ValueError("telegram bot token не задан (modules.alerting.notify.telegram_bot_token или _env)")
    if not chat_id:
        raise ValueError("telegram chat_id не задан (правило notify_target или modules.alerting.notify.telegram_chat_id)")
    base = (api_base or "https://api.telegram.org").rstrip("/")
    url = f"{base}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": True,
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def deliver_alert(
    cfg: AppConfig,
    rule: dict[str, Any],
    event: dict[str, Any],
    *,
    groups: list[dict[str, Any]] | None = None,
    instance_id: str = "",
) -> dict[str, Any]:
    """
    Отправить уведомление по правилу. Возвращает запись для журнала.
  Не бросает исключение наружу — ошибки в ok=False.
    """
    notify_cfg = cfg.modules.alerting.notify
    channel, target = resolve_rule_notify(rule, notify_cfg)
    subject, body = format_alert_message(event, rule)
    t0 = time.time()
    entry: dict[str, Any] = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rule_id": event.get("rule_id"),
        "rule_name": event.get("rule_name"),
        "channel": channel,
        "target": target[:200] if target else "",
        "instance_id": instance_id,
        "ok": False,
        "detail": "",
        "duration_ms": 0,
    }

    if channel == "none":
        entry["ok"] = True
        entry["detail"] = "канал none — уведомление пропущено"
        entry["duration_ms"] = int((time.time() - t0) * 1000)
        _append_log(entry)
        _log.info(
            "alert notify skipped rule=%r channel=none",
            event.get("rule_name"),
        )
        return entry

    try:
        if channel == "email":
            mail_cfg: MailModuleConfig = cfg.modules.mail
            if not mail_cfg.enabled:
                raise ValueError("modules.mail.enabled=false — включите SMTP для email-алертов")
            recipients = resolve_email_recipients(cfg, rule, groups)
            if not recipients:
                raise ValueError(
                    "нет получателей email: укажите notify_target в правиле или emails в группе"
                )
            for addr in [a.strip() for a in recipients.replace(";", ",").split(",") if a.strip()]:
                mail_smtp_send(mail_cfg, addr, subject, body)
            entry["target"] = recipients[:200]
            entry["ok"] = True
            entry["detail"] = f"отправлено на {recipients}"
            _log.info(
                "alert notify ok rule=%r channel=email to=%r",
                event.get("rule_name"),
                recipients,
            )
        elif channel == "webhook":
            url = target or notify_cfg.webhook_url
            _send_webhook(url, subject, body, event, float(notify_cfg.webhook_timeout_seconds))
            entry["target"] = (url or "")[:200]
            entry["ok"] = True
            entry["detail"] = "webhook POST ok"
            _log.info("alert notify ok rule=%r channel=webhook url=%r", event.get("rule_name"), url[:80])
        elif channel == "telegram":
            token = _telegram_token(notify_cfg)
            chat = target or notify_cfg.telegram_chat_id
            _send_telegram(token, chat, f"{subject}\n\n{body}", notify_cfg.telegram_api_base)
            entry["target"] = f"chat:{chat}"[:200]
            entry["ok"] = True
            entry["detail"] = "telegram sendMessage ok"
            _log.info("alert notify ok rule=%r channel=telegram chat=%r", event.get("rule_name"), chat)
        else:
            raise ValueError(f"неизвестный канал: {channel}")
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
        entry["ok"] = False
        entry["detail"] = str(e)[:500]
        _log.warning(
            "alert notify failed rule=%r channel=%s target=%r: %s",
            event.get("rule_name"),
            channel,
            target[:80] if target else "",
            e,
        )
    except Exception as e:
        entry["ok"] = False
        entry["detail"] = str(e)[:500]
        _log.exception(
            "alert notify error rule=%r channel=%s",
            event.get("rule_name"),
            channel,
        )

    entry["duration_ms"] = int((time.time() - t0) * 1000)
    _append_log(entry)
    return entry
