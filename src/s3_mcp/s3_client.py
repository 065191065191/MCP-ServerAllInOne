"""
S3/Ceph клиент: AWS Signature V4, только stdlib.

Основан на проверенном s3_checker (Ceph/RGW).
"""

from __future__ import annotations

import hashlib
import hmac
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from s3_mcp.config import S3Config

S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"
REGION = "us-east-1"
SERVICE = "s3"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def build_headers_v4(
    method: str,
    host: str,
    path: str,
    query_str: str,
    body: bytes,
    access_key: str,
    secret_key: str,
) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    signed_headers_list = ["host", "x-amz-content-sha256", "x-amz-date"]
    signed_headers = ";".join(signed_headers_list)

    canonical_uri = "/" + path.lstrip("/") if path else "/"
    if query_str and query_str.startswith("?"):
        query_str = query_str[1:]

    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    canonical_request = (
        f"{method}\n"
        f"{canonical_uri}\n"
        f"{query_str}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )
    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    signing_key = _get_signature_key(secret_key, date_stamp, REGION, SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return {
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": authorization,
    }


def parse_endpoint(endpoint_str: str) -> tuple[bool, str, int, str]:
    """endpoint -> (use_https, host, port, base_path)."""
    use_https = endpoint_str.startswith("https://")
    if use_https:
        rest = endpoint_str[len("https://") :]
        default_port = 443
    else:
        rest = endpoint_str[len("http://") :]
        default_port = 80

    parts = rest.split("/", 1)
    host_port = parts[0]
    base_path = "/" + parts[1] if len(parts) > 1 else ""

    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = default_port

    return use_https, host, port, base_path.rstrip("/")


def human_size(n_bytes: int) -> str:
    if n_bytes >= 1024**4:
        return f"{n_bytes / 1024**4:.2f} TB"
    if n_bytes >= 1024**3:
        return f"{n_bytes / 1024**3:.2f} GB"
    if n_bytes >= 1024**2:
        return f"{n_bytes / 1024**2:.2f} MB"
    if n_bytes >= 1024:
        return f"{n_bytes / 1024:.2f} KB"
    return f"{n_bytes} B"


def _parse_buckets_list(xml_bytes: bytes) -> list[str]:
    if not xml_bytes:
        return []
    root = ET.fromstring(xml_bytes.decode("utf-8"))
    ns = "{" + S3_NS + "}"
    buckets: list[str] = []
    for b_el in root.findall(f".//{ns}Bucket"):
        name_el = b_el.find(f"{ns}Name")
        if name_el is not None and name_el.text:
            buckets.append(name_el.text)
    return buckets


def _parse_objects_list(xml_bytes: bytes) -> tuple[list[dict[str, Any]], bool, str | None]:
    if not xml_bytes:
        return [], False, None
    root = ET.fromstring(xml_bytes.decode("utf-8"))
    ns = "{" + S3_NS + "}"

    objects: list[dict[str, Any]] = []
    for cont in root.findall(f".//{ns}Contents"):
        key = cont.find(f"{ns}Key")
        lm = cont.find(f"{ns}LastModified")
        size = cont.find(f"{ns}Size")
        objects.append(
            {
                "key": key.text if key is not None else "",
                "last_modified": lm.text if lm is not None else "",
                "size": int(size.text) if size is not None else 0,
            }
        )

    is_truncated_el = root.find(f".//{ns}IsTruncated")
    is_truncated = is_truncated_el is not None and is_truncated_el.text == "true"

    nct = root.find(f".//{ns}NextContinuationToken")
    next_marker = nct.text if nct is not None else None
    if next_marker is None:
        nm = root.find(f".//{ns}NextMarker")
        next_marker = nm.text if nm is not None else None

    return objects, is_truncated, next_marker


@dataclass
class S3Client:
    cfg: S3Config

    def __post_init__(self) -> None:
        if not self.cfg.ready:
            raise ValueError("S3 config incomplete: set S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY")
        self.use_https, self.host, self.port, self.base_path = parse_endpoint(self.cfg.endpoint)
        if self.use_https and not self.cfg.verify_ssl:
            self._ssl_ctx = ssl.create_default_context()
            self._ssl_ctx.check_hostname = False
            self._ssl_ctx.verify_mode = ssl.CERT_NONE
        else:
            self._ssl_ctx = None

    def _build_url(self, key_path: str, query_params: dict[str, Any] | None = None) -> tuple[str, str, str]:
        path = self.base_path + "/" + key_path.lstrip("/")
        qs = ""
        if query_params:
            qs = "&".join(
                f"{k}={urllib.parse.quote(str(v), safe='')}"
                for k, v in sorted(query_params.items())
            )
        full_url = self.cfg.endpoint.rstrip("/") + path
        if qs:
            full_url += "?" + qs
        return full_url, path, qs

    @staticmethod
    def _safe_close(resp: Any) -> None:
        """Закрыть ответ/HTTPError, освободив сокет (иначе утечка fd/памяти)."""
        try:
            resp.close()
        except Exception:
            pass

    def _raw_req(
        self,
        method: str,
        key_path: str,
        body: bytes = b"",
        query_params: dict[str, Any] | None = None,
    ) -> urllib.response.addinfourl:
        full_url, canon_path, canon_qs = self._build_url(key_path, query_params)
        host_line = f"{self.host}:{self.port}"
        headers = build_headers_v4(
            method,
            host_line,
            canon_path,
            canon_qs,
            body,
            self.cfg.access_key,
            self.cfg.secret_key,
        )
        req = urllib.request.Request(full_url, data=body or None, method=method, headers=headers)
        if self.use_https:
            return urllib.request.urlopen(req, context=self._ssl_ctx, timeout=60)
        return urllib.request.urlopen(req, timeout=60)

    def _read_body(
        self,
        method: str,
        key_path: str,
        body: bytes = b"",
        query_params: dict[str, Any] | None = None,
    ) -> bytes | None:
        try:
            resp = self._raw_req(method, key_path, body, query_params)
        except urllib.error.HTTPError as e:
            try:
                e.close()
            except Exception:
                pass
            return None
        try:
            return resp.read()
        finally:
            resp.close()

    def _head_response(
        self,
        key_path: str,
    ) -> tuple[dict[str, str] | None, int | None, str | None]:
        """HEAD: (headers, http_code, error_detail). Соединение закрывается сразу."""
        try:
            resp = self._raw_req("HEAD", key_path)
        except urllib.error.HTTPError as e:
            detail = ""
            if e.fp:
                try:
                    detail = e.fp.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    pass
            try:
                e.close()
            except Exception:
                pass
            return None, e.code, detail or e.reason
        except Exception as e:
            return None, None, str(e)
        try:
            headers = {k: v for k, v in resp.headers.items()}
            return headers, None, None
        finally:
            resp.close()

    def list_all_buckets(self) -> list[str]:
        all_buckets: list[str] = []
        marker: str | None = None
        for _ in range(3):
            params: dict[str, Any] = {"max-keys": 200}
            if marker:
                params["marker"] = marker
            data = self._read_body("GET", "/", query_params=params)
            if data is None:
                break
            try:
                buckets = _parse_buckets_list(data)
            except ET.ParseError:
                buckets = []
            if not buckets:
                break
            for b in buckets:
                if b not in all_buckets:
                    all_buckets.append(b)
            if all_buckets:
                marker = all_buckets[-1]
        return all_buckets

    def list_objects_in_bucket(self, bucket: str, max_keys: int = 1000, prefix: str = "") -> list[dict[str, Any]]:
        all_objects: list[dict[str, Any]] = []
        marker: str | None = None
        for _ in range(200):
            params: dict[str, Any] = {"max-keys": max_keys}
            if prefix:
                params["prefix"] = prefix
            if marker:
                params["marker"] = marker
            data = self._read_body("GET", f"/{bucket}/", query_params=params)
            if data is None:
                break
            objs, truncated, next_marker = _parse_objects_list(data)
            all_objects.extend(objs)
            if not truncated or not next_marker:
                break
            marker = next_marker
        return all_objects

    def get_bucket_stats_quick(self, bucket: str) -> tuple[int, int] | None:
        """Ceph RGW: X-RGW-Object-Count, X-RGW-Bytes-Used."""
        headers, code, _ = self._head_response(f"/{bucket}/")
        if headers is not None:
            obj_count = headers.get("X-RGW-Object-Count")
            bytes_used = headers.get("X-RGW-Bytes-Used")
            if obj_count is not None:
                return int(obj_count), int(bytes_used) if bytes_used else 0
            return 0, 0
        if code == 404:
            return None
        return None

    def get_latest_files(self, bucket: str, count: int = 3, max_scan: int = 1000) -> list[dict[str, Any]]:
        all_objects: list[dict[str, Any]] = []
        marker: str | None = None
        max_pages = max_scan // 1000 + 1

        for _ in range(max_pages):
            params: dict[str, Any] = {"max-keys": 1000}
            if marker:
                params["marker"] = marker
            data = self._read_body("GET", f"/{bucket}/", query_params=params)
            if data is None:
                break
            objs, truncated, next_marker = _parse_objects_list(data)
            all_objects.extend(objs)
            if not truncated or not next_marker:
                break
            marker = next_marker

        def _parse_dt(s: str) -> datetime:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else datetime.min.replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)

        all_objects.sort(key=lambda x: _parse_dt(x.get("last_modified", "")), reverse=True)
        return all_objects[:count]

    def write_test_on_bucket(self, bucket: str) -> tuple[bool, str]:
        test_key = f"s3check_{uuid.uuid4().hex}.tmp"
        body = b"0" * (1024 * 1024)

        try:
            self._raw_req("PUT", f"{bucket}/{test_key}", body=body).close()
        except urllib.error.HTTPError as e:
            self._safe_close(e)
            return False, "PUT failed"
        except Exception as e:
            return False, f"PUT error: {e}"

        try:
            self._raw_req("HEAD", f"{bucket}/{test_key}").close()
        except urllib.error.HTTPError as e:
            self._safe_close(e)
            try:
                self._raw_req("DELETE", f"{bucket}/{test_key}").close()
            except Exception:
                pass
            return False, "HEAD failed"
        except Exception as e:
            return False, f"HEAD error: {e}"

        try:
            self._raw_req("DELETE", f"{bucket}/{test_key}").close()
        except urllib.error.HTTPError as e:
            self._safe_close(e)
            return False, "DELETE failed"
        except Exception as e:
            return False, f"DELETE error: {e}"

        return True, "OK"

    def get_object_metadata(self, bucket: str, key: str) -> dict[str, Any]:
        """
        Метаданные объекта через HEAD. Содержимое не скачивается.

        Возвращает exists, size_bytes, last_modified, etag, content_type.
        """
        object_key = key.lstrip("/")
        object_path = f"{bucket}/{object_key}"
        headers, code, detail = self._head_response(object_path)

        if headers is not None:
            size_raw = headers.get("Content-Length", "0")
            try:
                size_bytes = int(size_raw)
            except ValueError:
                size_bytes = 0
            last_modified = headers.get("Last-Modified") or ""
            etag = (headers.get("ETag") or "").strip('"')
            content_type = headers.get("Content-Type") or ""
            return {
                "exists": True,
                "bucket": bucket,
                "key": object_key,
                "size_bytes": size_bytes,
                "size_human": human_size(size_bytes),
                "last_modified": last_modified,
                "etag": etag,
                "content_type": content_type,
                "content_returned": False,
            }

        if code == 404:
            return {
                "exists": False,
                "bucket": bucket,
                "key": object_key,
                "content_returned": False,
            }

        return {
            "exists": False,
            "bucket": bucket,
            "key": object_key,
            "error": detail or f"HTTP {code}" if code else "request failed",
            "content_returned": False,
        }

    def put_object(self, bucket: str, key: str, body: bytes) -> dict[str, Any]:
        """PUT объекта. Возвращает метаданные, не эхо тела."""
        object_key = key.lstrip("/")
        self._raw_req("PUT", f"{bucket}/{object_key}", body=body).close()
        meta = self.get_object_metadata(bucket, object_key)
        meta["written"] = True
        meta["bytes_written"] = len(body)
        return meta

    def delete_object(self, bucket: str, key: str) -> dict[str, Any]:
        """DELETE объекта. Перед удалением — HEAD для метаданных в ответе."""
        object_key = key.lstrip("/")
        before = self.get_object_metadata(bucket, object_key)
        if not before.get("exists"):
            return {"ok": False, "deleted": False, "bucket": bucket, "key": object_key, "reason": "not_found"}
        self._raw_req("DELETE", f"{bucket}/{object_key}").close()
        return {
            "ok": True,
            "deleted": True,
            "bucket": bucket,
            "key": object_key,
            "previous_size_bytes": before.get("size_bytes"),
            "previous_last_modified": before.get("last_modified"),
        }
