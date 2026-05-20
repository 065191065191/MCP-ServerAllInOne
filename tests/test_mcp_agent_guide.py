import asyncio
import json

from sdocs_mcp.config import (
    AppConfig,
    ModulesConfig,
    OpenSearchModuleConfig,
    PostgresModuleConfig,
)
from sdocs_mcp.mcp_agent_guide import (
    build_capabilities_payload,
    build_mcp_instructions,
    tools_by_module,
)
from sdocs_mcp.server import build_mcp


def test_capabilities_lists_core_always() -> None:
    app = AppConfig(modules=ModulesConfig())
    cap = build_capabilities_payload(app)
    assert "sdocs_mcp_capabilities" in [t["name"] for t in cap["tools_by_module"]["core"]]
    assert cap["tools_total"] >= 2


def test_postgres_module_adds_many_tools() -> None:
    app = AppConfig(modules=ModulesConfig(postgres=PostgresModuleConfig(enabled=True)))
    names = [t["name"] for t in tools_by_module(app).get("postgres", [])]
    assert "postgres_connections_overview" in names
    assert len(names) >= 10


def test_instructions_mention_capabilities() -> None:
    app = AppConfig(modules=ModulesConfig(postgres=PostgresModuleConfig(enabled=True)))
    text = build_mcp_instructions(app)
    assert "sdocs_mcp_capabilities" in text
    assert "postgres" in text.lower()


def test_opensearch_enabled_does_not_crash_capabilities() -> None:
    app = AppConfig(
        modules=ModulesConfig(
            opensearch=OpenSearchModuleConfig(enabled=True, allow_write=True),
        ),
    )
    cap = build_capabilities_payload(app)
    names = [t["name"] for t in cap["tools_by_module"]["opensearch"]]
    assert "opensearch_count" in names
    assert "opensearch_delete_index" in names


def test_sdocs_mcp_status_tools_total_matches_list_tools() -> None:
    app = AppConfig(
        modules=ModulesConfig(
            postgres=PostgresModuleConfig(enabled=True),
            opensearch=OpenSearchModuleConfig(enabled=True, allow_write=True),
        ),
    )
    mcp = build_mcp(app)
    listed = {t.name for t in asyncio.run(mcp.list_tools())}
    status_fn = mcp._tool_manager._tools["sdocs_mcp_status"].fn
    status = json.loads(status_fn())
    cap = build_capabilities_payload(app)
    manifest = {t["name"] for mod in cap["tools_by_module"].values() for t in mod}

    assert status["tools_total"] == len(listed) == cap["tools_total"]
    assert manifest == listed
    assert status["postgres"] is True
    assert status["opensearch"] is True
    assert status["opensearch_rag"] is False
    assert "hint" in status
    assert "config" in status and "path" in status["config"]
