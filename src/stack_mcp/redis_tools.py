from __future__ import annotations

import json
from typing import Any

from stack_mcp.config import RedisModuleConfig
from stack_mcp.redis_resp import RedisRawClient, connect_redis

_INFO_SECTIONS = ("server", "memory", "stats", "replication", "cpu", "commandstats")


def _client(cfg: RedisModuleConfig) -> RedisRawClient:
    return connect_redis(cfg)


def redis_ping(cfg: RedisModuleConfig) -> str:
    c = _client(cfg)
    try:
        r = c.execute("PING")
        return json.dumps({"ok": r == "PONG", "pong": r}, indent=2)
    finally:
        c.close()


def redis_setex(cfg: RedisModuleConfig, key: str, seconds: int, value: str) -> str:
    if not key or len(key) > 512:
        raise ValueError("key must be 1..512 characters")
    if seconds < 1 or seconds > 86400 * 30:
        raise ValueError("seconds must be between 1 and 30 days")
    if len(value) > 1_048_576:
        raise ValueError("value too large")
    c = _client(cfg)
    try:
        c.execute("SETEX", key, seconds, value)
        return json.dumps({"ok": True, "key": key, "ttl_seconds": seconds}, indent=2, ensure_ascii=False)
    finally:
        c.close()


def redis_info(cfg: RedisModuleConfig) -> str:
    """Fixed INFO sections only: server, memory, stats, replication, cpu, commandstats."""
    c = _client(cfg)
    try:
        parts: dict[str, str] = {}
        for section in _INFO_SECTIONS:
            raw = c.execute("INFO", section)
            parts[section] = raw if isinstance(raw, str) else str(raw)
        return json.dumps(parts, indent=2, default=str)
    finally:
        c.close()


def redis_memory_stats(cfg: RedisModuleConfig) -> str:
    c = _client(cfg)
    try:
        data = c.execute("MEMORY", "STATS")
    except Exception as e:
        return json.dumps({"error": str(e), "hint": "Requires Redis with MEMORY STATS support"}, indent=2)
    finally:
        c.close()
    return json.dumps(data, indent=2, default=str)


def redis_dbsize(cfg: RedisModuleConfig) -> str:
    c = _client(cfg)
    try:
        n = c.execute("DBSIZE")
        return json.dumps({"db_size": int(n)}, indent=2)
    finally:
        c.close()


def redis_slowlog_get(cfg: RedisModuleConfig) -> str:
    limit = max(1, min(cfg.slowlog_max_entries, 128))
    c = _client(cfg)
    try:
        entries = c.execute("SLOWLOG", "GET", limit)
    finally:
        c.close()
    if not isinstance(entries, list):
        return json.dumps({"error": "unexpected SLOWLOG reply", "raw": str(entries)}, indent=2)
    out = []
    for e in entries:
        if not isinstance(e, list) or len(e) < 4:
            continue
        cmd_raw = e[3]
        cmd_list = cmd_raw if isinstance(cmd_raw, list) else [cmd_raw]
        out.append(
            {
                "id": e[0],
                "start_time": e[1],
                "duration_us": e[2],
                "command": [str(x) for x in cmd_list][:20],
            }
        )
    return json.dumps(out, indent=2, default=str)


def _truncate(val: str | None, max_bytes: int) -> tuple[str, bool]:
    if val is None:
        return "", False
    raw = val.encode("utf-8")
    if len(raw) <= max_bytes:
        return val, False
    truncated = raw[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def redis_get(cfg: RedisModuleConfig, key: str) -> str:
    if not key or len(key) > 512:
        raise ValueError("key must be 1..512 characters")
    c = _client(cfg)
    try:
        val = c.execute("GET", key)
        text = val if isinstance(val, str) else ("" if val is None else str(val))
        text, trunc = _truncate(text or None, cfg.get_max_value_bytes)
        return json.dumps({"key": key, "value": text, "truncated": trunc}, indent=2, ensure_ascii=False)
    finally:
        c.close()


def redis_mget(cfg: RedisModuleConfig, keys: list[str]) -> str:
    if not keys:
        raise ValueError("keys must be non-empty")
    if len(keys) > cfg.mget_max_keys:
        raise ValueError(f"at most {cfg.mget_max_keys} keys allowed")
    for k in keys:
        if not k or len(k) > 512:
            raise ValueError("each key must be 1..512 characters")
    c = _client(cfg)
    try:
        values = c.execute("MGET", *keys)
    finally:
        c.close()
    if not isinstance(values, list) or len(values) != len(keys):
        raise RuntimeError("unexpected MGET response")
    out = []
    for k, v in zip(keys, values, strict=True):
        text = v if isinstance(v, str) else ("" if v is None else str(v))
        t2, trunc = _truncate(text or None, cfg.get_max_value_bytes)
        out.append({"key": k, "value": t2, "truncated": trunc})
    return json.dumps(out, indent=2, ensure_ascii=False)


def _hgetall_pairs(raw: Any) -> dict[str, str]:
    if not isinstance(raw, list):
        return {}
    fields: dict[str, str] = {}
    i = 0
    while i + 1 < len(raw):
        fk = raw[i]
        fv = raw[i + 1]
        fields[str(fk)] = str(fv)
        i += 2
    return fields


def redis_hgetall(cfg: RedisModuleConfig, key: str) -> str:
    if not key or len(key) > 512:
        raise ValueError("key must be 1..512 characters")
    c = _client(cfg)
    try:
        data = c.execute("HGETALL", key)
    finally:
        c.close()
    flat = _hgetall_pairs(data)
    if not flat:
        return json.dumps({"key": key, "fields": {}, "truncated": False}, indent=2, ensure_ascii=False)
    if len(flat) > cfg.hgetall_max_fields:
        raise ValueError(f"hash has {len(flat)} fields; limit is {cfg.hgetall_max_fields}")
    total = 0
    fields: dict[str, str] = {}
    truncated = False
    for fk, fv in flat.items():
        b = str(fv).encode("utf-8")
        if total + len(b) > cfg.hgetall_max_total_bytes:
            truncated = True
            remaining = cfg.hgetall_max_total_bytes - total
            if remaining > 0:
                fields[fk] = b[:remaining].decode("utf-8", errors="ignore")
            break
        fields[fk] = str(fv)
        total += len(b)
    return json.dumps({"key": key, "fields": fields, "truncated": truncated}, indent=2, ensure_ascii=False)


def redis_scan_prefix(cfg: RedisModuleConfig, prefix: str) -> str:
    if not cfg.scan_enabled:
        raise PermissionError("redis scan is disabled in config (scan_enabled: false)")
    if not prefix:
        raise ValueError("prefix must be non-empty")
    allowed = cfg.scan_prefix_allowlist
    if not any(prefix.startswith(p) for p in allowed):
        raise PermissionError(f"prefix must match one of scan_prefix_allowlist: {allowed!r}")
    c = _client(cfg)
    try:
        keys_out: list[str] = []
        iterations = 0
        cursor = "0"
        match = f"{prefix}*"
        while iterations < cfg.scan_max_iterations:
            resp = c.execute("SCAN", cursor, "MATCH", match, "COUNT", cfg.scan_count)
            if not isinstance(resp, list) or len(resp) != 2:
                break
            cursor = str(resp[0])
            chunk = resp[1]
            if isinstance(chunk, list):
                keys_out.extend(str(x) for x in chunk)
            iterations += 1
            if cursor == "0":
                break
    finally:
        c.close()
    return json.dumps(
        {
            "prefix": prefix,
            "iterations": iterations,
            "keys": keys_out[: cfg.scan_count * cfg.scan_max_iterations],
        },
        indent=2,
        ensure_ascii=False,
    )
