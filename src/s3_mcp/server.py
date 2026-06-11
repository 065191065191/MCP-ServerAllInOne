"""S3 MCP — Streamable HTTP, диагностика Ceph/S3 и метаданные объектов."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import sys
from typing import Any

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP

from s3_mcp import __version__
from s3_mcp.config import load_s3_config
from s3_mcp.mcp_tool_docs import S3_SERVER_MISSION_RU, tool_doc
from s3_mcp.policy import S3McpPolicy, load_s3_mcp_policy
from s3_mcp.s3_client import S3Client, human_size

_log = logging.getLogger("s3_mcp")


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes")


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _policy_fingerprint() -> tuple[bool, bool, int]:
    p = load_s3_mcp_policy()
    return (p.allow_put, p.allow_delete, p.max_put_bytes)


def _client_or_error() -> tuple[S3Client | None, str | None]:
    cfg = load_s3_config()
    if not cfg.ready:
        return None, "Задайте S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY"
    try:
        return S3Client(cfg), None
    except ValueError as e:
        return None, str(e)


def build_mcp(
    policy: S3McpPolicy | None = None,
    *,
    host: str = "0.0.0.0",
    port: int = 8766,
) -> FastMCP:
    pol = policy or load_s3_mcp_policy()
    fm_kw: dict[str, Any] = {
        "name": "s3-mcp",
        "instructions": S3_SERVER_MISSION_RU,
        "host": host,
        "port": port,
    }
    if _env_truthy("S3_MCP_STATELESS_HTTP"):
        fm_kw["stateless_http"] = True

    mcp = FastMCP(**fm_kw)

    @mcp.tool(description=tool_doc("s3_mcp_status"))
    def s3_mcp_status() -> str:
        cfg = load_s3_config()
        pol_now = load_s3_mcp_policy()
        return json.dumps(
            {
                "server": "s3-mcp",
                "version": __version__,
                "s3": cfg.public_status(),
                "policy": pol_now.public_status(),
                "write_tools_active": {
                    "s3_put_object": pol_now.allow_put,
                    "s3_delete_object": pol_now.allow_delete,
                },
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool(description=tool_doc("s3_list_buckets"))
    def s3_list_buckets() -> str:
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        buckets = client.list_all_buckets()
        return json.dumps({"ok": True, "count": len(buckets), "buckets": buckets}, indent=2, ensure_ascii=False)

    @mcp.tool(description=tool_doc("s3_bucket_stats"))
    def s3_bucket_stats(bucket: str) -> str:
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        stats = client.get_bucket_stats_quick(bucket)
        if stats is not None:
            obj_cnt, bytes_used = stats
            return json.dumps(
                {
                    "ok": True,
                    "bucket": bucket,
                    "object_count": obj_cnt,
                    "bytes_used": bytes_used,
                    "size_human": human_size(bytes_used),
                    "source": "head_rgw",
                },
                indent=2,
                ensure_ascii=False,
            )
        objs = client.list_objects_in_bucket(bucket, max_keys=1000)
        total = sum(int(o.get("size", 0)) for o in objs)
        return json.dumps(
            {
                "ok": True,
                "bucket": bucket,
                "object_count": len(objs),
                "bytes_used": total,
                "size_human": human_size(total),
                "source": "list_objects_sample",
                "note": "до 1000 объектов, если HEAD RGW недоступен",
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool(description=tool_doc("s3_bucket_latest_files"))
    def s3_bucket_latest_files(bucket: str, count: int = 3) -> str:
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        count = max(1, min(int(count), 20))
        latest = client.get_latest_files(bucket, count=count)
        for obj in latest:
            obj["size_human"] = human_size(int(obj.get("size", 0)))
        return json.dumps({"ok": True, "bucket": bucket, "files": latest}, indent=2, ensure_ascii=False)

    @mcp.tool(description=tool_doc("s3_write_test"))
    def s3_write_test(bucket: str) -> str:
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        ok, msg = client.write_test_on_bucket(bucket)
        return json.dumps({"ok": ok, "bucket": bucket, "message": msg}, ensure_ascii=False)

    @mcp.tool(description=tool_doc("s3_object_metadata"))
    def s3_object_metadata(bucket: str, key: str) -> str:
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        meta = client.get_object_metadata(bucket, key)
        meta["ok"] = bool(meta.get("exists"))
        return json.dumps(meta, indent=2, ensure_ascii=False)

    if pol.allow_put:

        @mcp.tool(description=tool_doc("s3_put_object"))
        def s3_put_object(bucket: str, key: str, content_base64: str) -> str:
            pol_now = load_s3_mcp_policy()
            if not pol_now.allow_put:
                return json.dumps(
                    {"ok": False, "error": "allow_put=false — включите в UI SDocsMCP → S3 MCP"},
                    ensure_ascii=False,
                )
            client, err = _client_or_error()
            if client is None:
                return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
            try:
                body = base64.b64decode(content_base64, validate=True)
            except (binascii.Error, ValueError) as e:
                return json.dumps({"ok": False, "error": f"invalid base64: {e}"}, ensure_ascii=False)
            if len(body) > pol_now.max_put_bytes:
                return json.dumps(
                    {
                        "ok": False,
                        "error": f"payload {len(body)} bytes > max_put_bytes {pol_now.max_put_bytes}",
                    },
                    ensure_ascii=False,
                )
            try:
                meta = client.put_object(bucket, key, body)
                meta["ok"] = True
                return json.dumps(meta, indent=2, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    if pol.allow_delete:

        @mcp.tool(description=tool_doc("s3_delete_object"))
        def s3_delete_object(bucket: str, key: str) -> str:
            pol_now = load_s3_mcp_policy()
            if not pol_now.allow_delete:
                return json.dumps(
                    {"ok": False, "error": "allow_delete=false — включите в UI SDocsMCP → S3 MCP"},
                    ensure_ascii=False,
                )
            client, err = _client_or_error()
            if client is None:
                return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
            try:
                result = client.delete_object(bucket, key)
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    return mcp


async def _run_http(mcp: FastMCP, transport: str) -> None:
    app = mcp.streamable_http_app() if transport == "streamable-http" else mcp.sse_app(None)
    await uvicorn.Server(
        uvicorn.Config(
            app,
            host=mcp.settings.host,
            port=mcp.settings.port,
            log_level=mcp.settings.log_level.lower(),
        )
    ).serve()


async def _policy_watch_restart(initial: tuple[bool, bool, int]) -> None:
    """При смене modules.s3_mcp в mcp.conf — exit(0) для рестарта пода K8s."""
    interval = max(5.0, _env_float("S3_MCP_CONFIG_RELOAD_INTERVAL", 15.0))
    while True:
        await anyio.sleep(interval)
        if _policy_fingerprint() != initial:
            _log.info("modules.s3_mcp изменился — завершение процесса для перезапуска пода")
            os._exit(0)


async def _run_with_policy_watch(mcp: FastMCP, transport: str) -> None:
    fp = _policy_fingerprint()
    async with anyio.create_task_group() as tg:
        tg.start_soon(_policy_watch_restart, fp)
        await _run_http(mcp, transport)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    transport = (os.environ.get("S3_MCP_TRANSPORT") or "streamable-http").strip().lower()
    host = (os.environ.get("S3_MCP_HOST") or "0.0.0.0").strip()
    port = int(os.environ.get("S3_MCP_PORT", "8766"))

    if transport == "stdio":
        mcp = build_mcp()
        mcp.run(transport="stdio")
        return

    if transport not in ("streamable-http", "sse"):
        _log.error("Unknown S3_MCP_TRANSPORT=%r", transport)
        sys.exit(2)

    mcp = build_mcp(host=host, port=port)
    path = mcp.settings.streamable_http_path if transport == "streamable-http" else mcp.settings.sse_path
    _log.info("S3 MCP %s on http://%s:%s%s", transport, host, port, path)
    anyio.run(_run_with_policy_watch, mcp, transport)


if __name__ == "__main__":
    main()
