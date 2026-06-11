from __future__ import annotations

import asyncio
import json

from s3_mcp.server import build_mcp


def test_build_mcp_registers_tools() -> None:
    mcp = build_mcp()
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    expected = {
        "s3_mcp_status",
        "s3_list_buckets",
        "s3_bucket_stats",
        "s3_bucket_latest_files",
        "s3_write_test",
        "s3_object_metadata",
    }
    assert expected <= names


def test_s3_mcp_status_without_env() -> None:
    mcp = build_mcp()
    fn = mcp._tool_manager._tools["s3_mcp_status"].fn
    data = json.loads(fn())
    assert data["server"] == "s3-mcp"
    assert data["s3"]["ready"] is False
