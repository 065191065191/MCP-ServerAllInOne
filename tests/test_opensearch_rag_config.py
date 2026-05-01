from __future__ import annotations

import pytest

from stack_mcp.config import OpenSearchModuleConfig, OpenSearchRagConfig


def test_rag_allowlist_required_when_enabled() -> None:
    with pytest.raises(ValueError, match="index_allowlist"):
        OpenSearchModuleConfig(
            enabled=True,
            rag=OpenSearchRagConfig(enabled=True, index_allowlist=[]),
        )


def test_rag_requires_opensearch_enabled() -> None:
    with pytest.raises(ValueError, match="rag.enabled requires opensearch"):
        OpenSearchModuleConfig(
            enabled=False,
            rag=OpenSearchRagConfig(enabled=True, index_allowlist=["mem"]),
        )


def test_rag_ok_when_both_enabled() -> None:
    c = OpenSearchModuleConfig(
        enabled=True,
        rag=OpenSearchRagConfig(enabled=True, index_allowlist=["agent-memory"]),
    )
    assert c.rag.index_allowlist == ["agent-memory"]
