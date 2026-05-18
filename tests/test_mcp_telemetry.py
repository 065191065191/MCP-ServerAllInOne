from __future__ import annotations

from sdocs_mcp.mcp_telemetry import inc_mcp_http_request, mcp_http_requests_total


def test_mcp_http_request_counter() -> None:
    before = mcp_http_requests_total()
    inc_mcp_http_request()
    assert mcp_http_requests_total() == before + 1
