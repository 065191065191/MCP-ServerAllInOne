from __future__ import annotations

import json
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException

from stack_mcp.backend_tls import opensearch_client_kwargs
from stack_mcp.config import OpenSearchModuleConfig
from stack_mcp.credentials import env_required


def _client(cfg: OpenSearchModuleConfig) -> OpenSearch:
    pw = cfg.password
    if (cfg.password_env or "").strip():
        pw = env_required(cfg.password_env, what="opensearch password")
    auth = (cfg.username, pw) if cfg.username else None
    kw: dict[str, Any] = {
        "hosts": cfg.hosts,
        "use_ssl": cfg.use_ssl,
        "verify_certs": cfg.verify_certs,
        "http_auth": auth,
        "timeout": cfg.request_timeout_seconds,
    }
    kw.update(opensearch_client_kwargs(cfg))
    return OpenSearch(**kw)


def connect_opensearch(cfg: OpenSearchModuleConfig) -> OpenSearch:
    """Клиент OpenSearch с учётом mtls_* из конфига (для UI и тестов)."""
    return _client(cfg)


def opensearch_cluster_health(cfg: OpenSearchModuleConfig) -> str:
    client = _client(cfg)
    try:
        return json.dumps(client.cluster.health(), indent=2)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_cluster_health_debug(cfg: OpenSearchModuleConfig) -> str:
    """Extended health payload with pending tasks and shard view."""
    client = _client(cfg)
    try:
        health = client.cluster.health(level="shards")
        pending = client.cluster.pending_tasks()
        shards = client.cat.shards(
            format="json",
            h="index,shard,prirep,state,docs,store,node,unassigned.reason",
        )
        return json.dumps(
            {
                "health": health,
                "pending_tasks": pending,
                "shards": shards,
            },
            indent=2,
            default=str,
        )
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_cluster_stats(cfg: OpenSearchModuleConfig) -> str:
    client = _client(cfg)
    try:
        return json.dumps(client.cluster.stats(), indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_nodes_stats(cfg: OpenSearchModuleConfig) -> str:
    client = _client(cfg)
    try:
        stats = client.nodes.stats(metric="os,jvm,process,fs,indices,thread_pool,transport,http")
        return json.dumps(stats, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_pending_tasks(cfg: OpenSearchModuleConfig) -> str:
    client = _client(cfg)
    try:
        return json.dumps(client.cluster.pending_tasks(), indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_cluster_settings(cfg: OpenSearchModuleConfig) -> str:
    client = _client(cfg)
    try:
        settings = client.cluster.get_settings(include_defaults=True)
        return json.dumps(settings, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_cat_shards(cfg: OpenSearchModuleConfig, index: str = "*") -> str:
    if not index or len(index) > 200:
        raise ValueError("index must be 1..200 characters")
    client = _client(cfg)
    try:
        shards = client.cat.shards(
            index=index,
            format="json",
            h="index,shard,prirep,state,docs,store,node,unassigned.reason",
        )
        return json.dumps(shards, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_allocation_explain(
    cfg: OpenSearchModuleConfig,
    index: str | None = None,
    shard: int | None = None,
    primary: bool | None = None,
) -> str:
    client = _client(cfg)
    body: dict[str, Any] = {}
    if index is not None:
        if not index or len(index) > 200:
            raise ValueError("index must be 1..200 characters")
        body["index"] = index
    if shard is not None:
        if shard < 0:
            raise ValueError("shard must be >= 0")
        body["shard"] = shard
    if primary is not None:
        body["primary"] = primary
    try:
        if body:
            resp = client.cluster.allocation_explain(body=body)
        else:
            resp = client.cluster.allocation_explain()
        return json.dumps(resp, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_list_indices(cfg: OpenSearchModuleConfig, pattern: str = "*") -> str:
    if not pattern or len(pattern) > 200:
        raise ValueError("pattern must be 1..200 characters")
    client = _client(cfg)
    try:
        indices = client.cat.indices(index=pattern, format="json", h="index,health,status,docs.count,store.size")
        return json.dumps(indices, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_get_mapping(cfg: OpenSearchModuleConfig, index: str) -> str:
    if not index or len(index) > 200:
        raise ValueError("index must be 1..200 characters")
    client = _client(cfg)
    try:
        return json.dumps(client.indices.get_mapping(index=index), indent=2)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_search(cfg: OpenSearchModuleConfig, index: str, query_json: str) -> str:
    if not index or len(index) > 200:
        raise ValueError("index must be 1..200 characters")
    try:
        body = json.loads(query_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid query_json: {e}") from e
    if not isinstance(body, dict):
        raise ValueError("query_json must be a JSON object")
    size = int(body.get("size", 10))
    cap = max(1, min(cfg.search_max_size, 100))
    body["size"] = min(size, cap)
    client = _client(cfg)
    try:
        resp = client.search(index=index, body=body)
        return json.dumps(resp, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_count(cfg: OpenSearchModuleConfig, index: str, query_json: str | None = None) -> str:
    if not index or len(index) > 200:
        raise ValueError("index must be 1..200 characters")
    body: dict[str, Any] | None = None
    if query_json:
        try:
            parsed = json.loads(query_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid query_json: {e}") from e
        if not isinstance(parsed, dict):
            raise ValueError("query_json must be a JSON object")
        body = parsed
    client = _client(cfg)
    try:
        if body is None:
            resp = client.count(index=index)
        else:
            resp = client.count(index=index, body=body)
        return json.dumps(resp, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_delete_index(cfg: OpenSearchModuleConfig, index: str) -> str:
    if not cfg.allow_write:
        raise PermissionError("destructive OpenSearch operations are disabled (allow_write: false)")
    if not index or len(index) > 200:
        raise ValueError("index must be 1..200 characters")
    client = _client(cfg)
    try:
        resp = client.indices.delete(index=index, ignore_unavailable=True)
        return json.dumps(resp, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)
