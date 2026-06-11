"""Конфигурация S3 MCP из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    verify_ssl: bool = False

    @property
    def ready(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key)

    def public_status(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "access_key_set": bool(self.access_key),
            "secret_key_set": bool(self.secret_key),
            "verify_ssl": self.verify_ssl,
            "ready": self.ready,
        }


def load_s3_config() -> S3Config:
    return S3Config(
        endpoint=(os.environ.get("S3_ENDPOINT") or "").strip(),
        access_key=(os.environ.get("S3_ACCESS_KEY") or "").strip(),
        secret_key=(os.environ.get("S3_SECRET_KEY") or "").strip(),
        verify_ssl=_env_bool("S3_VERIFY_SSL", default=False),
    )
