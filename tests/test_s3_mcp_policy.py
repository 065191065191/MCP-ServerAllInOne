from __future__ import annotations

import asyncio

from s3_mcp.policy import S3McpPolicy
from s3_mcp.server import build_mcp


def test_build_mcp_without_write_tools_by_default() -> None:
    mcp = build_mcp(S3McpPolicy(allow_put=False, allow_delete=False))
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "s3_object_metadata" in names
    assert "s3_put_object" not in names
    assert "s3_delete_object" not in names


def test_build_mcp_with_write_tools_when_enabled() -> None:
    mcp = build_mcp(S3McpPolicy(allow_put=True, allow_delete=True))
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "s3_put_object" in names
    assert "s3_delete_object" in names
