"""Политика s3-mcp из общего mcp.conf (modules.s3_mcp)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from s3_mcp.config import _env_bool


@dataclass(frozen=True)
class S3McpPolicy:
    allow_put: bool = False
    allow_delete: bool = False
    max_put_bytes: int = 1_048_576

    def public_status(self) -> dict[str, object]:
        return {
            "allow_put": self.allow_put,
            "allow_delete": self.allow_delete,
            "max_put_bytes": self.max_put_bytes,
            "hint": "Включить запись/удаление: UI SDocsMCP → Консоль → S3 MCP или modules.s3_mcp в mcp.conf",
        }


def load_s3_mcp_policy() -> S3McpPolicy:
    """YAML modules.s3_mcp; env S3_MCP_ALLOW_PUT / S3_MCP_ALLOW_DELETE — явный override."""
    allow_put = False
    allow_delete = False
    max_put = 1_048_576
    try:
        from sdocs_mcp.config import load_config

        p = load_config().modules.s3_mcp
        allow_put = p.allow_put
        allow_delete = p.allow_delete
        max_put = p.max_put_bytes
    except Exception:
        pass
    if "S3_MCP_ALLOW_PUT" in os.environ:
        allow_put = _env_bool("S3_MCP_ALLOW_PUT")
    if "S3_MCP_ALLOW_DELETE" in os.environ:
        allow_delete = _env_bool("S3_MCP_ALLOW_DELETE")
    return S3McpPolicy(allow_put=allow_put, allow_delete=allow_delete, max_put_bytes=max_put)
