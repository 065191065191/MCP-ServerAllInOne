"""Классификация и конфиг аудита вызовов MCP tools."""

from __future__ import annotations

import pytest

from stack_mcp.config import AppConfig, OpenSearchToolCallAuditConfig
from stack_mcp.tool_audit_http_context import http_caller_hints_override
from stack_mcp.tool_audit_opensearch import (
    audit_should_skip,
    classify_tool_invocation,
    default_tool_audit_index_body,
    resolve_tool_audit_caller,
    tool_audit_classification_facets,
)


def test_classify_core() -> None:
    c = classify_tool_invocation("stack_mcp_status")
    assert c["module"] == "core"
    assert c["category"] == "meta"
    assert c["operation_kind"] == "read"


def test_classify_postgres_read() -> None:
    c = classify_tool_invocation("postgres_connections_overview")
    assert c["module"] == "postgres"
    assert c["category"] == "data_plane"
    assert c["operation_kind"] == "read"


def test_classify_rag() -> None:
    c = classify_tool_invocation("opensearch_rag_store")
    assert c["module"] == "opensearch"
    assert c["category"] == "rag"
    assert c["operation_kind"] == "write"


def test_classify_admin() -> None:
    c = classify_tool_invocation("opensearch_delete_index")
    assert c["operation_kind"] == "admin"


def test_classification_ten_facets() -> None:
    f = tool_audit_classification_facets(
        "opensearch_rag_search",
        {"index": "mem", "query_text": "x"},
        150.0,
    )
    expected_keys = {
        "module",
        "category",
        "operation_kind",
        "tool_family",
        "risk_tier",
        "api_surface",
        "rag_lane",
        "mutating",
        "argument_key_count",
        "duration_bucket",
    }
    assert set(f.keys()) == expected_keys
    assert f["rag_lane"] is True
    assert f["argument_key_count"] == 2
    assert f["duration_bucket"] == "50ms_200ms"
    assert f["api_surface"] == "mcp_tool"


def test_duration_bucket_edges() -> None:
    assert tool_audit_classification_facets("redis_ping", {}, 10.0)["duration_bucket"] == "lt_50ms"
    assert tool_audit_classification_facets("redis_ping", {}, 15_000.0)["duration_bucket"] == "gte_10s"


def test_mapping_has_classification_fields() -> None:
    props = default_tool_audit_index_body()["mappings"]["properties"]
    for k in (
        "caller_id",
        "caller_client_ip",
        "tool_family",
        "risk_tier",
        "api_surface",
        "rag_lane",
        "mutating",
        "argument_key_count",
        "duration_bucket",
    ):
        assert k in props


def test_resolve_audit_caller_unknown() -> None:
    aud = OpenSearchToolCallAuditConfig(enabled=True)
    assert resolve_tool_audit_caller(aud) == ("unknown", "")


def test_resolve_audit_caller_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STACK_MCP_AUDIT_CALLER_ID", "from-env")
    aud = OpenSearchToolCallAuditConfig(enabled=True)
    assert resolve_tool_audit_caller(aud)[0] == "from-env"


def test_resolve_audit_caller_header_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STACK_MCP_AUDIT_CALLER_ID", "from-env")
    aud = OpenSearchToolCallAuditConfig(enabled=True)
    with http_caller_hints_override(header_caller="from-header", client_host="10.0.0.2"):
        assert resolve_tool_audit_caller(aud) == ("from-header", "")


def test_resolve_audit_caller_ip_when_enabled() -> None:
    aud = OpenSearchToolCallAuditConfig(enabled=True, log_http_client_ip=True)
    with http_caller_hints_override(header_caller="", client_host="10.0.0.3"):
        assert resolve_tool_audit_caller(aud) == ("unknown", "10.0.0.3")


def test_exclude_tools() -> None:
    aud = OpenSearchToolCallAuditConfig(enabled=True, exclude_tools=["stack_mcp_status"])
    assert audit_should_skip("stack_mcp_status", aud) is True
    assert audit_should_skip("redis_ping", aud) is False


def test_tool_call_audit_requires_opensearch_enabled() -> None:
    with pytest.raises(ValueError, match="tool_call_audit"):
        AppConfig.model_validate(
            {
                "modules": {
                    "opensearch": {
                        "enabled": False,
                        "tool_call_audit": {"enabled": True},
                    }
                }
            }
        )
