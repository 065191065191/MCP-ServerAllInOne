"""S3 MCP — Streamable HTTP, tools для Ceph/S3 (без скачивания содержимого объектов)."""

from __future__ import annotations

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
from s3_mcp.s3_client import S3Client, human_size

_log = logging.getLogger("s3_mcp")


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes")


def _client_or_error() -> tuple[S3Client | None, str | None]:
    cfg = load_s3_config()
    if not cfg.ready:
        return None, "Задайте S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY"
    try:
        return S3Client(cfg), None
    except ValueError as e:
        return None, str(e)


def build_mcp(*, host: str = "0.0.0.0", port: int = 8766) -> FastMCP:
    fm_kw: dict[str, Any] = {
        "name": "s3-mcp",
        "instructions": (
            f"S3 MCP v{__version__}: Ceph/S3 диагностика (AWS Sig V4, stdlib). "
            "Сначала s3_mcp_status. Для проверки документа — s3_object_metadata(bucket, key): "
            "только метаданные (размер, дата), содержимое не возвращается."
        ),
        "host": host,
        "port": port,
    }
    if _env_truthy("S3_MCP_STATELESS_HTTP"):
        fm_kw["stateless_http"] = True

    mcp = FastMCP(**fm_kw)

    @mcp.tool()
    def s3_mcp_status() -> str:
        """Статус конфигурации S3 (без секретов)."""
        cfg = load_s3_config()
        return json.dumps(
            {
                "server": "s3-mcp",
                "version": __version__,
                "s3": cfg.public_status(),
                "hint": "tools: s3_list_buckets, s3_bucket_stats, s3_bucket_latest_files, "
                "s3_write_test, s3_object_metadata",
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    def s3_list_buckets() -> str:
        """Список всех bucket (с пагинацией)."""
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        buckets = client.list_all_buckets()
        return json.dumps({"ok": True, "count": len(buckets), "buckets": buckets}, indent=2, ensure_ascii=False)

    @mcp.tool()
    def s3_bucket_stats(bucket: str) -> str:
        """Статистика bucket: число объектов и занятое место (HEAD RGW или list fallback)."""
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

    @mcp.tool()
    def s3_bucket_latest_files(bucket: str, count: int = 3) -> str:
        """Последние N файлов в bucket по LastModified (метаданные, без содержимого)."""
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        count = max(1, min(int(count), 20))
        latest = client.get_latest_files(bucket, count=count)
        for obj in latest:
            obj["size_human"] = human_size(int(obj.get("size", 0)))
        return json.dumps({"ok": True, "bucket": bucket, "files": latest}, indent=2, ensure_ascii=False)

    @mcp.tool()
    def s3_write_test(bucket: str) -> str:
        """Тест записи: PUT 1MB -> HEAD -> DELETE во временный ключ."""
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        ok, msg = client.write_test_on_bucket(bucket)
        return json.dumps({"ok": ok, "bucket": bucket, "message": msg}, ensure_ascii=False)

    @mcp.tool()
    def s3_object_metadata(bucket: str, key: str) -> str:
        """
        Проверить конкретный объект (документ): наличие, размер, дата изменения.

        Только HEAD — содержимое файла не возвращается.
        """
        client, err = _client_or_error()
        if client is None:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        meta = client.get_object_metadata(bucket, key)
        meta["ok"] = bool(meta.get("exists"))
        return json.dumps(meta, indent=2, ensure_ascii=False)

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
    anyio.run(_run_http, mcp, transport)


if __name__ == "__main__":
    main()
