"""RAG-память поверх OpenSearch: только allowlist индексов, лимиты размера и объёма (BM25 / multi_match)."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from opensearchpy.exceptions import OpenSearchException

from stack_mcp.config import OpenSearchModuleConfig, OpenSearchRagConfig
from stack_mcp.opensearch_tools import connect_opensearch

_DOC_ID_RE = re.compile(r"^[-_a-zA-Z0-9]{1,128}$")


def _rag(cfg: OpenSearchModuleConfig) -> OpenSearchRagConfig:
    r = cfg.rag
    if not cfg.enabled or not r.enabled:
        raise PermissionError("OpenSearch RAG отключён (нужны opensearch.enabled и opensearch.rag.enabled)")
    return r


def _assert_index_allowed(r: OpenSearchRagConfig, index: str) -> None:
    if index not in r.index_allowlist:
        raise PermissionError(f"индекс {index!r} не в opensearch.rag.index_allowlist")


def _utf8_len(s: str) -> int:
    return len(s.encode("utf-8"))


def _default_index_body(r: OpenSearchRagConfig) -> dict[str, Any]:
    return {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                r.title_field: {"type": "text"},
                r.text_field: {"type": "text"},
                r.ingested_at_field: {"type": "date"},
                r.source_field: {"type": "keyword"},
                r.session_id_field: {"type": "keyword"},
                r.metadata_json_field: {"type": "text", "index": False},
            },
        },
    }


def _ensure_index(client: Any, cfg: OpenSearchModuleConfig, index: str) -> None:
    r = cfg.rag
    if client.indices.exists(index=index):
        return
    if not r.auto_create_index:
        raise ValueError(
            f"индекс {index!r} не существует. Создайте его в OpenSearch или включите opensearch.rag.auto_create_index"
        )
    client.indices.create(index=index, body=_default_index_body(r))


def opensearch_rag_policy(cfg: OpenSearchModuleConfig) -> str:
    """Политика RAG для агента: куда можно писать, лимиты, имена полей (без секретов)."""
    r = cfg.rag
    if not cfg.enabled:
        return json.dumps({"rag_enabled": False, "detail": "opensearch module disabled"}, indent=2)
    body = {
        "rag_enabled": bool(r.enabled),
        "opensearch_enabled": True,
        "index_allowlist": list(r.index_allowlist),
        "max_text_bytes": r.max_text_bytes,
        "max_title_bytes": r.max_title_bytes,
        "max_metadata_json_bytes": r.max_metadata_json_bytes,
        "max_metadata_keys": r.max_metadata_keys,
        "max_docs_per_index": r.max_docs_per_index,
        "retrieval_size_cap": r.retrieval_size_cap,
        "allow_delete_by_id": r.allow_delete_by_id,
        "auto_create_index": r.auto_create_index,
        "source_tag": r.source_tag,
        "fields": {
            "text": r.text_field,
            "title": r.title_field,
            "ingested_at": r.ingested_at_field,
            "source": r.source_field,
            "session_id": r.session_id_field,
            "metadata_json": r.metadata_json_field,
        },
        "retrieval": "BM25 multi_match по полям text и title; для семантики позже можно добавить knn в индекс отдельно.",
        "guidance": (
            "Храните долговременные факты только в индексах из index_allowlist через opensearch_rag_store; "
            "не пишите в произвольные индексы. Перед записью вызывайте opensearch_rag_policy. "
            "Поиск контекста — opensearch_rag_search; объём выдачи ограничен retrieval_size_cap. "
            "Запись помечается полем source=source_tag; поиск и лимиты документов учитывают только такие записи."
        ),
    }
    return json.dumps(body, indent=2, ensure_ascii=False)


def opensearch_rag_stats(cfg: OpenSearchModuleConfig) -> str:
    """Число документов по каждому разрешённому RAG-индексу."""
    _rag(cfg)
    client = connect_opensearch(cfg)
    r = cfg.rag
    out: dict[str, Any] = {}
    for idx in r.index_allowlist:
        try:
            resp = client.count(
                index=idx,
                ignore_unavailable=True,
                body={"query": {"term": {r.source_field: r.source_tag}}},
            )
            out[idx] = {"count": int(resp.get("count", 0)), "filter_source": r.source_tag}
        except OpenSearchException as e:
            out[idx] = {"error": str(e)}
    return json.dumps(out, indent=2)


def _normalize_metadata(r: OpenSearchRagConfig, metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    if len(metadata) > r.max_metadata_keys:
        raise ValueError(f"metadata: не более {r.max_metadata_keys} ключей")
    flat: dict[str, str] = {}
    for k, v in metadata.items():
        ks = str(k).strip()
        if not ks or len(ks) > 128:
            raise ValueError("metadata keys must be 1..128 characters")
        flat[ks] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    raw = json.dumps(flat, ensure_ascii=False)
    if _utf8_len(raw) > r.max_metadata_json_bytes:
        raise ValueError(f"metadata JSON превышает max_metadata_json_bytes={r.max_metadata_json_bytes}")
    return raw


def opensearch_rag_store(
    cfg: OpenSearchModuleConfig,
    index: str,
    text: str,
    title: str | None = None,
    session_id: str | None = None,
    doc_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Индексирует один фрагмент памяти (текст + опции) только в allowlist-индекс."""
    r = _rag(cfg)
    _assert_index_allowed(r, index)
    if not text or not text.strip():
        raise ValueError("text must be non-empty")
    if _utf8_len(text) > r.max_text_bytes:
        raise ValueError(f"text exceeds max_text_bytes={r.max_text_bytes}")
    tit = (title or "").strip()
    if tit and _utf8_len(tit) > r.max_title_bytes:
        raise ValueError(f"title exceeds max_title_bytes={r.max_title_bytes}")
    sid = (session_id or "").strip()
    if sid and len(sid) > 128:
        raise ValueError("session_id must be at most 128 characters")
    if doc_id is not None:
        doc_id = doc_id.strip()
        if not doc_id or not _DOC_ID_RE.match(doc_id):
            raise ValueError("doc_id must match [-_a-zA-Z0-9]{1,128}")
    meta_s = _normalize_metadata(r, metadata)

    client = connect_opensearch(cfg)
    _ensure_index(client, cfg, index)
    if r.max_docs_per_index > 0:
        try:
            cnt = int(
                client.count(
                    index=index,
                    body={"query": {"term": {r.source_field: r.source_tag}}},
                ).get("count", 0)
            )
        except OpenSearchException as e:
            return json.dumps({"error": str(e), "phase": "count"}, indent=2)
        if cnt >= r.max_docs_per_index:
            raise PermissionError(
                f"лимит документов в индексе ({r.max_docs_per_index}) достигнут; удалите старые или поднимите max_docs_per_index"
            )

    body: dict[str, Any] = {
        r.text_field: text,
        r.source_field: r.source_tag,
        r.ingested_at_field: datetime.now(UTC).isoformat(),
    }
    if tit:
        body[r.title_field] = tit
    if sid:
        body[r.session_id_field] = sid
    if meta_s:
        body[r.metadata_json_field] = meta_s

    try:
        if doc_id:
            resp = client.index(index=index, id=doc_id, body=body, refresh="wait_for")
        else:
            resp = client.index(index=index, body=body, refresh="wait_for")
        return json.dumps(
            {
                "ok": True,
                "index": resp.get("_index"),
                "id": resp.get("_id"),
                "result": resp.get("result"),
            },
            indent=2,
        )
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_rag_search(
    cfg: OpenSearchModuleConfig,
    index: str,
    query_text: str,
    session_id: str | None = None,
    size: int | None = None,
) -> str:
    """Полнотекстовый поиск (BM25) по RAG-индексу; опциональный фильтр session_id."""
    r = _rag(cfg)
    _assert_index_allowed(r, index)
    q = (query_text or "").strip()
    if not q:
        raise ValueError("query_text must be non-empty")
    if len(q) > 2000:
        raise ValueError("query_text too long (max 2000 characters)")
    req = int(size) if size is not None else r.retrieval_size_cap
    cap = max(1, min(req, r.retrieval_size_cap))
    sid = (session_id or "").strip() or None

    must: list[dict[str, Any]] = [
        {
            "multi_match": {
                "query": q,
                "fields": [f"{r.text_field}^2", r.title_field],
                "type": "best_fields",
            }
        }
    ]
    filter_clauses: list[dict[str, Any]] = []
    filter_clauses.append({"term": {r.source_field: r.source_tag}})
    if sid:
        filter_clauses.append({"term": {r.session_id_field: sid}})

    bool_query: dict[str, Any] = {"must": must}
    if filter_clauses:
        bool_query["filter"] = filter_clauses

    body: dict[str, Any] = {
        "size": cap,
        "_source": [
            r.title_field,
            r.text_field,
            r.session_id_field,
            r.ingested_at_field,
            r.source_field,
            r.metadata_json_field,
        ],
        "query": {"bool": bool_query},
        "highlight": {
            "fields": {
                r.text_field: {"fragment_size": 220, "number_of_fragments": 3},
                r.title_field: {"number_of_fragments": 1},
            }
        },
    }
    client = connect_opensearch(cfg)
    try:
        resp = client.search(index=index, body=body)
        hits = resp.get("hits", {})
        total = hits.get("total", {})
        if isinstance(total, dict):
            total_v = total.get("value")
        else:
            total_v = total
        slim_hits = []
        for h in (hits.get("hits") or [])[:cap]:
            slim_hits.append(
                {
                    "_id": h.get("_id"),
                    "_score": h.get("_score"),
                    "_source": h.get("_source"),
                    "highlight": h.get("highlight"),
                }
            )
        return json.dumps(
            {
                "index": index,
                "took_ms": resp.get("took"),
                "total": total_v,
                "hits": slim_hits,
            },
            indent=2,
            default=str,
            ensure_ascii=False,
        )
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)


def opensearch_rag_delete_document(cfg: OpenSearchModuleConfig, index: str, doc_id: str) -> str:
    """Удаляет документ по id только в allowlist-индексе (если rag.allow_delete_by_id)."""
    r = _rag(cfg)
    if not r.allow_delete_by_id:
        raise PermissionError("opensearch.rag.allow_delete_by_id is false")
    _assert_index_allowed(r, index)
    did = (doc_id or "").strip()
    if not did or not _DOC_ID_RE.match(did):
        raise ValueError("doc_id must match [-_a-zA-Z0-9]{1,128}")
    client = connect_opensearch(cfg)
    try:
        resp = client.delete(index=index, id=did, refresh="wait_for")
        return json.dumps({"ok": resp.get("result") in ("deleted", "not_found"), "result": resp}, indent=2, default=str)
    except OpenSearchException as e:
        return json.dumps({"error": str(e)}, indent=2)
