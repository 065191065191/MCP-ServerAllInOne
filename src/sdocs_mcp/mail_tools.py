from __future__ import annotations

import imaplib
import json
import smtplib
from email.message import EmailMessage

from sdocs_mcp.config import MailModuleConfig
from sdocs_mcp.credentials import config_or_env, env_optional


def _imap_user(cfg: MailModuleConfig) -> str:
    u = (cfg.imap_username or "").strip()
    if u:
        return u
    env_u = env_optional(cfg.imap_username_env)
    if env_u:
        return env_u
    raise ValueError("mail: задайте imap_username или imap_username_env")


def _imap_pass(cfg: MailModuleConfig) -> str:
    return config_or_env(cfg.imap_password, cfg.imap_password_env, what="mail IMAP password")


def _smtp_user(cfg: MailModuleConfig) -> str:
    u = (cfg.smtp_username or "").strip()
    if u:
        return u
    env_u = env_optional(cfg.smtp_username_env)
    if env_u:
        return env_u
    return _imap_user(cfg)


def _smtp_pass(cfg: MailModuleConfig) -> str:
    if (cfg.smtp_password or "").strip() or (cfg.smtp_password_env or "").strip():
        return config_or_env(cfg.smtp_password, cfg.smtp_password_env, what="mail SMTP password")
    return _imap_pass(cfg)


def _default_from(cfg: MailModuleConfig) -> str | None:
    env_f = (cfg.default_from_env or "").strip()
    if not env_f:
        return None
    return env_optional(env_f)


def mail_imap_verify(cfg: MailModuleConfig) -> str:
    """IMAP login + NOOP для health-check (без LIST)."""
    user, pwd = _imap_user(cfg), _imap_pass(cfg)
    if cfg.imap_ssl:
        M = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port, timeout=15)
    else:
        M = imaplib.IMAP4(cfg.imap_host, cfg.imap_port, timeout=15)
    try:
        M.login(user, pwd)
        typ, _ = M.noop()
        return json.dumps({"ok": typ == "OK"}, indent=2)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def mail_imap_list_mailboxes(cfg: MailModuleConfig) -> str:
    user, pwd = _imap_user(cfg), _imap_pass(cfg)
    if cfg.imap_ssl:
        M = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port, timeout=30)
    else:
        M = imaplib.IMAP4(cfg.imap_host, cfg.imap_port, timeout=30)
    try:
        M.login(user, pwd)
        typ, data = M.list()
        if typ != "OK" or not data:
            return json.dumps({"mailboxes": [], "detail": typ}, indent=2)
        rows: list[str] = []
        for raw in data[: cfg.list_mailboxes_max]:
            if isinstance(raw, bytes):
                rows.append(raw.decode("utf-8", errors="replace"))
            else:
                rows.append(str(raw))
        return json.dumps({"mailboxes": rows, "truncated": len(data) > len(rows)}, indent=2, ensure_ascii=False)
    finally:
        try:
            M.logout()
        except Exception:
            pass


def mail_imap_search(
    cfg: MailModuleConfig,
    folder: str | None = None,
    unseen_only: bool = True,
    max_messages: int | None = None,
) -> str:
    mb = (folder or cfg.default_mailbox or "INBOX").strip() or "INBOX"
    cap = max_messages if max_messages is not None else cfg.search_max_messages
    cap = max(1, min(cap, 200))
    user, pwd = _imap_user(cfg), _imap_pass(cfg)
    if cfg.imap_ssl:
        M = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port, timeout=30)
    else:
        M = imaplib.IMAP4(cfg.imap_host, cfg.imap_port, timeout=30)
    try:
        M.login(user, pwd)
        M.select(mb, readonly=True)
        criterion = "UNSEEN" if unseen_only else "ALL"
        typ, data = M.search(None, criterion)
        if typ != "OK" or not data or not data[0]:
            return json.dumps({"folder": mb, "uids": [], "count": 0}, indent=2)
        uids = data[0].split()
        uids = uids[-cap:]
        out_uids = [x.decode("ascii", errors="ignore") for x in uids]
        return json.dumps(
            {
                "folder": mb,
                "uids": out_uids,
                "count": len(out_uids),
                "criterion": criterion,
            },
            indent=2,
        )
    finally:
        try:
            M.logout()
        except Exception:
            pass


def mail_imap_fetch_rfc822(cfg: MailModuleConfig, folder: str, uid: str) -> str:
    if not uid or len(uid) > 32:
        raise ValueError("uid must be non-empty, reasonable length")
    mb = (folder or cfg.default_mailbox or "INBOX").strip() or "INBOX"
    user, pwd = _imap_user(cfg), _imap_pass(cfg)
    if cfg.imap_ssl:
        M = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port, timeout=30)
    else:
        M = imaplib.IMAP4(cfg.imap_host, cfg.imap_port, timeout=30)
    try:
        M.login(user, pwd)
        M.select(mb, readonly=True)
        typ, data = M.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data:
            return json.dumps({"error": "fetch failed", "typ": typ}, indent=2)
        raw: bytes | None = None
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                raw = part[1] if isinstance(part[1], (bytes, bytearray)) else None
                if raw:
                    break
        if not raw:
            return json.dumps({"error": "empty body", "uid": uid}, indent=2)
        max_b = max(1024, min(cfg.fetch_max_bytes, 2_097_152))
        truncated = len(raw) > max_b
        text = raw[:max_b].decode("utf-8", errors="replace")
        return json.dumps(
            {
                "folder": mb,
                "uid": uid,
                "rfc822_preview": text,
                "truncated": truncated,
                "bytes_total": len(raw),
            },
            indent=2,
            ensure_ascii=False,
        )
    finally:
        try:
            M.logout()
        except Exception:
            pass


def mail_smtp_send(
    cfg: MailModuleConfig,
    to_addr: str,
    subject: str,
    body_text: str,
    from_addr: str | None = None,
) -> str:
    if not to_addr or not subject:
        raise ValueError("to_addr and subject required")
    if len(body_text) > 2_000_000:
        raise ValueError("body_text too large")
    sender = (from_addr or "").strip() or _default_from(cfg)
    if not sender:
        sender = _smtp_user(cfg)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.set_content(body_text)
    user, pwd = _smtp_user(cfg), _smtp_pass(cfg)
    if cfg.smtp_ssl:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds) as s:
            if cfg.smtp_starttls:
                s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
    return json.dumps({"ok": True, "to": to_addr, "from": sender}, indent=2, ensure_ascii=False)
