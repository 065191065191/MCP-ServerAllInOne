from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import paramiko

from stack_mcp.config import SshHostEntry, SshModuleConfig

# Встроенный слой (~«+20%» к denylist): не песочница, но отсекает частые опасные однострочники.
_BUILTIN_SAFETY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(sudo|doas)\b"), "sudo/doas"),
    (re.compile(r"(?i)\b(reboot|shutdown|poweroff|halt|telinit)\b"), "power/halt"),
    (re.compile(r"(?i)\binit\s+[06]\b"), "init 0/6"),
    (re.compile(r"(?i)\bmkfs\b"), "mkfs"),
    (re.compile(r"(?i)\bdd\b"), "dd"),
    (re.compile(r"(?i)\bwipefs\b"), "wipefs"),
    (re.compile(r"(?i)\bshred\b"), "shred"),
    (re.compile(r"(?i)\b(curl|wget)\b"), "curl/wget"),
    (re.compile(r"(?i)\b(?:python3?|perl|ruby)\s+-(?:c|e)\b"), "inline script (-c/-e)"),
    (re.compile(r"(?i)\b(?:bash|sh)\s+-c\b"), "shell -c inline"),
    (re.compile(r"(?i)\bbase64\s+(?:-d|--decode)\b"), "base64 decode pipe trick"),
    (re.compile(r"(?i)\beval\s+"), "eval"),
    (re.compile(r"(?i)[>|]\s*/dev/(?:sd|nvme|vd|hd|mmcblk)"), "redirect to block device"),
    (re.compile(r"(?i)\bchmod\b.*\b777\b"), "chmod to 777"),
    (re.compile(r"(?i)>\s*/etc/\S"), "redirect into /etc"),
    (re.compile(r"(?i)\bchown\s+"), "chown"),
    (re.compile(r"(?i)\bchgrp\s+"), "chgrp"),
    (re.compile(r"(?i)\brm\s+-\w*"), "rm with destructive flags"),
    (re.compile(r"(?i)\b(userdel|groupdel)\b"), "account/group deletion"),
    (re.compile(r"(?i)\b(?:nc|netcat)\b.+?\s-[lL]\b"), "netcat listen"),
]

# Подмешивается при merge_recommended_substring_blocklist=true (средний риск; жёсткий слой — _BUILTIN_SAFETY).
_RECOMMENDED_SUBSTRING_BLOCKLIST: tuple[str, ...] = (
    "rm -rf",
    "/etc/shadow",
    "/etc/sudoers",
    "> /etc/",
    "chmod 000",
    "chmod 4777",
    "mkfs.",
    "fdisk",
    "wipefs",
    "iptables",
    "nft flush",
    "systemctl daemon-reexec",
)


def ssh_command_policy(cfg: SshModuleConfig) -> str:
    """JSON: что именно блокируется в ssh_run_command до отправки на хост."""
    body: dict[str, Any] = {
        "from_config": {
            "forbidden_substrings": list(cfg.forbidden_substrings),
            "merge_recommended_substring_blocklist": cfg.merge_recommended_substring_blocklist,
            "forbidden_regex": list(cfg.forbidden_regex),
            "allow_shell_operators": cfg.allow_shell_operators,
            "builtin_safety_filter": cfg.builtin_safety_filter,
        },
        "recommended_substrings_when_merge_enabled": list(_RECOMMENDED_SUBSTRING_BLOCKLIST),
        "enforced_in_code": {
            "max_command_length_chars": 16_384,
            "empty_command_rejected": True,
            "builtin_safety_rules": [
                {"pattern": p.pattern, "description": label} for p, label in _BUILTIN_SAFETY
            ]
            if cfg.builtin_safety_filter
            else "disabled (builtin_safety_filter=false)",
        },
    }
    if cfg.allow_shell_operators:
        body["enforced_in_code"]["shell_operator_policy"] = (
            "allow_shell_operators=true: символы ; | ` перевод строк && || $( ${ не отсекает код "
            "(остаются forbidden_substrings / forbidden_regex и лимит длины)."
        )
    else:
        body["enforced_in_code"]["shell_operator_policy"] = [
            "Любая команда, содержащая ; | ` или перевод строки — отклонена.",
            "Подстроки && или || — отклонены.",
            "Подстроки $( или ${ — отклонены (подстановка команд).",
        ]
    body["how_matching_works"] = {
        "forbidden_substrings": "Проверка без учёта регистра: если подстрока входит в команду — отказ.",
        "forbidden_regex": "Python re.search по каждому шаблону — любое совпадение отказ.",
    }
    return json.dumps(body, indent=2, ensure_ascii=False)


def ssh_hosts_overview(cfg: SshModuleConfig) -> str:
    """Список хостов для агента: id, hostname, port, description (без секретов)."""
    rows = [
        {
            "id": h.id,
            "hostname": h.hostname,
            "port": h.port,
            "username": h.username,
            "description": h.description or None,
        }
        for h in cfg.hosts
    ]
    return json.dumps({"hosts": rows}, indent=2, ensure_ascii=False)


def _find_host(cfg: SshModuleConfig, host_id: str) -> SshHostEntry:
    for h in cfg.hosts:
        if h.id == host_id:
            return h
    raise ValueError(f"Unknown host id: {host_id!r}. Use ssh_hosts_overview.")


def _validate_command(cfg: SshModuleConfig, command: str) -> None:
    cmd = command.strip()
    if not cmd:
        raise ValueError("command must be non-empty")
    if len(cmd) > 16_384:
        raise ValueError("command too long (max 16384 characters)")

    lower = cmd.lower()
    effective_substrings = [s for s in cfg.forbidden_substrings if s]
    if cfg.merge_recommended_substring_blocklist:
        have = {s.lower() for s in effective_substrings}
        for s in _RECOMMENDED_SUBSTRING_BLOCKLIST:
            if s.lower() not in have:
                effective_substrings.append(s)
                have.add(s.lower())
    for sub in effective_substrings:
        if sub.lower() in lower:
            raise ValueError(f"Command blocked: forbidden substring matches {sub!r}")

    for pattern in cfg.forbidden_regex:
        if re.search(pattern, cmd):
            raise ValueError(f"Command blocked: forbidden regex matches {pattern!r}")

    if cfg.builtin_safety_filter:
        for rx, label in _BUILTIN_SAFETY:
            if rx.search(cmd):
                raise ValueError(f"Command blocked: builtin safety filter ({label})")

    if not cfg.allow_shell_operators:
        if any(ch in cmd for ch in ";\n\r`|"):
            raise ValueError("Command blocked: shell operators not allowed (; | ` newline)")
        if "&&" in cmd or "||" in cmd:
            raise ValueError("Command blocked: shell operators not allowed (&& ||)")
        if "$(" in cmd or "${" in cmd:
            raise ValueError("Command blocked: command substitution not allowed")


def _load_private_key(path: str, passphrase: str | None) -> paramiko.PKey:
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError(f"Private key file not found: {p}")
    # Paramiko выбирает тип ключа по содержимому.
    return paramiko.PKey.from_private_key_file(str(p), password=passphrase)


def _connect(client: paramiko.SSHClient, host: SshHostEntry, cfg: SshModuleConfig) -> None:
    if cfg.strict_host_key_checking:
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    password: str | None = None
    pkey: paramiko.PKey | None = None
    if host.private_key_path:
        phrase: str | None = None
        if host.private_key_passphrase_env:
            phrase = os.environ.get(host.private_key_passphrase_env)
        pkey = _load_private_key(host.private_key_path, phrase)
    elif host.password_env:
        password = os.environ.get(host.password_env)
        if password is None:
            raise ValueError(f"Environment variable {host.password_env!r} is not set")

    client.connect(
        hostname=host.hostname,
        port=host.port,
        username=host.username,
        pkey=pkey,
        password=password,
        timeout=cfg.connect_timeout_seconds,
        banner_timeout=cfg.connect_timeout_seconds,
        auth_timeout=cfg.connect_timeout_seconds,
        allow_agent=False,
        look_for_keys=False,
    )


def _read_stream_limited(stream: paramiko.ChannelFile, max_bytes: int) -> tuple[str, bool]:
    data = b""
    truncated = False
    while len(data) < max_bytes:
        chunk = stream.read(min(65536, max_bytes - len(data)))
        if not chunk:
            break
        data += chunk
    if len(data) >= max_bytes:
        rest = stream.read(1)
        truncated = bool(rest)
    return data.decode("utf-8", errors="replace"), truncated


def ssh_run_command(cfg: SshModuleConfig, host_id: str, command: str) -> str:
    """Выполнить одну команду на удалённом хосте после проверки запретов из конфига."""
    host = _find_host(cfg, host_id)
    _validate_command(cfg, command)
    cmd = command.strip()
    max_stream = max(1024, cfg.max_output_bytes)

    client = paramiko.SSHClient()
    try:
        _connect(client, host, cfg)
        stdin, stdout, stderr = client.exec_command(
            cmd,
            timeout=cfg.command_timeout_seconds,
            get_pty=False,
        )
        stdin.close()
        out_text, out_trunc = _read_stream_limited(stdout, max_stream)
        err_text, err_trunc = _read_stream_limited(stderr, max_stream)
        exit_code = stdout.channel.recv_exit_status()
        return json.dumps(
            {
                "host_id": host.id,
                "hostname": host.hostname,
                "command": cmd,
                "exit_code": exit_code,
                "stdout": out_text,
                "stderr": err_text,
                "stdout_truncated": out_trunc,
                "stderr_truncated": err_trunc,
            },
            indent=2,
            ensure_ascii=False,
        )
    except paramiko.SSHException as e:
        return json.dumps(
            {"error": "ssh_error", "message": str(e), "host_id": host.id},
            indent=2,
            ensure_ascii=False,
        )
    except OSError as e:
        return json.dumps(
            {"error": "os_error", "message": str(e), "host_id": host.id},
            indent=2,
            ensure_ascii=False,
        )
    finally:
        client.close()
