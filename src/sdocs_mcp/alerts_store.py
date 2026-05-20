"""Хранилище правил Alert (память + синхронизация через Kafka)."""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any

_lock = threading.Lock()
_groups: list[dict[str, Any]] = []
_rules: list[dict[str, Any]] = []
_revision: int = 0


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "revision": _revision,
            "groups": json.loads(json.dumps(_groups)),
            "rules": json.loads(json.dumps(_rules)),
        }


def apply_payload(data: dict[str, Any]) -> None:
    global _revision
    with _lock:
        if "groups" in data and isinstance(data["groups"], list):
            _groups.clear()
            _groups.extend(data["groups"])
        if "rules" in data and isinstance(data["rules"], list):
            _rules.clear()
            _rules.extend(data["rules"])
        if "revision" in data:
            _revision = int(data["revision"])
        else:
            _revision += 1


def save_from_ui(groups: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    global _revision
    with _lock:
        _groups.clear()
        _groups.extend(groups)
        _rules.clear()
        for r in rules:
            row = dict(r)
            if not row.get("id"):
                row["id"] = str(uuid.uuid4())
            _rules.append(row)
        _revision += 1
        return snapshot()


def list_rules() -> list[dict[str, Any]]:
    with _lock:
        return json.loads(json.dumps(_rules))
