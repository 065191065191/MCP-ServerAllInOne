#!/usr/bin/env python3
"""Генерация YAML для STACK_MCP_SSH_HOSTS_FILE из CSV (десятки/сотни хостов).

Формат CSV (первая строка — заголовок, UTF-8):
  id,hostname,username[,port][,auth][,private_key_path][,password_env][,description]

  auth: key (по умолчанию) или password.
  Для auth=key пустой private_key_path означает использование modules.ssh.default_private_key_path в основном конфиге.

Пример:
  id,hostname,username,port,auth,password_env
  web-01,10.0.0.1,deploy,22,key,
  legacy-02,10.0.0.2,admin,22,password,SSH_LEGACY_02_PASSWORD

Вывод: YAML со списком хостов (подходит как содержимое файла для STACK_MCP_SSH_HOSTS_FILE).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml


def row_to_host(r: dict[str, str]) -> dict:
    hid = (r.get("id") or "").strip()
    hostname = (r.get("hostname") or "").strip()
    username = (r.get("username") or "").strip()
    if not hid or not hostname or not username:
        raise ValueError(f"строка без id/hostname/username: {r!r}")

    port_s = (r.get("port") or "22").strip()
    try:
        port = int(port_s)
    except ValueError as e:
        raise ValueError(f"id={hid!r}: неверный port {port_s!r}") from e

    auth = (r.get("auth") or "key").strip().lower()
    desc = (r.get("description") or "").strip() or None
    key_path = (r.get("private_key_path") or "").strip() or None
    pw_env = (r.get("password_env") or "").strip() or None

    entry: dict = {
        "id": hid,
        "hostname": hostname,
        "port": port,
        "username": username,
    }
    if desc:
        entry["description"] = desc

    if auth == "password":
        if not pw_env:
            raise ValueError(f"id={hid!r}: auth=password требует password_env")
        if key_path:
            raise ValueError(f"id={hid!r}: при password не указывайте private_key_path")
        entry["password_env"] = pw_env
    elif auth == "key":
        if pw_env:
            raise ValueError(
                f"id={hid!r}: для ключа не заполняйте password_env (или используйте auth=password)"
            )
        if key_path:
            entry["private_key_path"] = key_path
    else:
        raise ValueError(f"id={hid!r}: auth должен быть key или password, не {auth!r}")

    return entry


def main() -> None:
    p = argparse.ArgumentParser(description="CSV → YAML для STACK_MCP_SSH_HOSTS_FILE")
    p.add_argument("csv_path", type=Path, help="Путь к .csv")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Файл вывода (по умолчанию stdout)",
    )
    args = p.parse_args()

    if not args.csv_path.is_file():
        print(f"Файл не найден: {args.csv_path}", file=sys.stderr)
        sys.exit(2)

    with args.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("CSV без заголовка", file=sys.stderr)
            sys.exit(2)
        hosts = []
        for i, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            try:
                hosts.append(row_to_host({k: (v or "") for k, v in row.items()}))
            except ValueError as e:
                print(f"Строка {i}: {e}", file=sys.stderr)
                sys.exit(1)

    out = yaml.safe_dump(
        hosts,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
