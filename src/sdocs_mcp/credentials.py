from __future__ import annotations

import os


def env_optional(name: str | None) -> str | None:
    if not name or not str(name).strip():
        return None
    v = os.environ.get(str(name).strip())
    if v is None or v == "":
        return None
    return v


def env_required(name: str | None, *, what: str) -> str:
    label = (name or "").strip()
    if not label:
        raise ValueError(f"{what}: environment variable name is empty")
    v = os.environ.get(label)
    if v is None or v == "":
        raise ValueError(f"{what}: set environment variable {label!r}")
    return v


def config_or_env(plain: str | None, env_name: str | None, *, what: str) -> str:
    """Значение из YAML (plain) или из переменной окружения (env_name)."""
    if (plain or "").strip():
        return str(plain).strip()
    return env_required(env_name, what=what)
