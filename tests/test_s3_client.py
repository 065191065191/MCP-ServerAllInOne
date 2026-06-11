from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from s3_mcp.config import S3Config
from s3_mcp.s3_client import (
    S3Client,
    _parse_buckets_list,
    _parse_objects_list,
    build_headers_v4,
    human_size,
    parse_endpoint,
)


def test_parse_endpoint_https_port() -> None:
    use_https, host, port, base = parse_endpoint("https://s3.example.com:8443/ceph")
    assert use_https is True
    assert host == "s3.example.com"
    assert port == 8443
    assert base == "/ceph"


def test_human_size() -> None:
    assert human_size(500) == "500 B"
    assert "KB" in human_size(2048)


def test_parse_buckets_xml() -> None:
    xml = b"""<?xml version="1.0"?>
    <ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <Buckets><Bucket><Name>docs</Name></Bucket></Buckets>
    </ListAllMyBucketsResult>"""
    assert _parse_buckets_list(xml) == ["docs"]


def test_parse_objects_xml() -> None:
    xml = b"""<?xml version="1.0"?>
    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      <Contents>
        <Key>a.txt</Key><LastModified>2026-01-02T03:04:05.000Z</LastModified><Size>42</Size>
      </Contents>
      <IsTruncated>false</IsTruncated>
    </ListBucketResult>"""
    objs, truncated, marker = _parse_objects_list(xml)
    assert truncated is False
    assert marker is None
    assert objs[0]["key"] == "a.txt"
    assert objs[0]["size"] == 42


def test_build_headers_v4_has_authorization() -> None:
    h = build_headers_v4("GET", "host:443", "/bucket/", "", b"", "AK", "SK")
    assert "Authorization" in h
    assert h["Authorization"].startswith("AWS4-HMAC-SHA256")


def test_get_object_metadata_exists() -> None:
    cfg = S3Config(endpoint="http://localhost:9000", access_key="a", secret_key="b")
    client = S3Client(cfg)
    mock_resp = MagicMock()
    mock_resp.headers = {
        "Content-Length": "1024",
        "Last-Modified": "Mon, 01 Jan 2026 12:00:00 GMT",
        "ETag": '"abc123"',
        "Content-Type": "application/pdf",
    }
    with patch.object(client, "_head_response", return_value=(mock_resp, None, None)):
        meta = client.get_object_metadata("docs", "report.pdf")
    assert meta["exists"] is True
    assert meta["size_bytes"] == 1024
    assert meta["content_returned"] is False
    assert "application/pdf" in meta["content_type"]


def test_get_object_metadata_not_found() -> None:
    cfg = S3Config(endpoint="http://localhost:9000", access_key="a", secret_key="b")
    client = S3Client(cfg)
    with patch.object(client, "_head_response", return_value=(None, 404, "Not Found")):
        meta = client.get_object_metadata("docs", "missing.pdf")
    assert meta["exists"] is False
    assert meta["content_returned"] is False


def test_client_requires_config() -> None:
    with pytest.raises(ValueError):
        S3Client(S3Config(endpoint="", access_key="", secret_key=""))
