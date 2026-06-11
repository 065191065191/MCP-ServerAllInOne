"""Точечное обновление YAML-конфига (без потери остальных ключей)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sdocs_mcp.config import _load_yaml, resolve_config_path


def patch_modules_s3_mcp(
    *,
    allow_put: bool | None = None,
    allow_delete: bool | None = None,
) -> dict[str, Any]:
    """
    Обновить modules.s3_mcp.allow_put / allow_delete в файле SDOCS_MCP_CONFIG.
    Возвращает новые значения флагов.
    """
    path, source = resolve_config_path()
    if path is None or not path.is_file():
        raise FileNotFoundError(f"config file not found ({source})")

    data = _load_yaml(path)
    modules = data.setdefault("modules", {})
    if not isinstance(modules, dict):
        modules = {}
        data["modules"] = modules
    s3 = modules.setdefault("s3_mcp", {})
    if not isinstance(s3, dict):
        s3 = {}
        modules["s3_mcp"] = s3

    if allow_put is not None:
        s3["allow_put"] = bool(allow_put)
    if allow_delete is not None:
        s3["allow_delete"] = bool(allow_delete)

    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return {
        "path": str(path),
        "allow_put": bool(s3.get("allow_put", False)),
        "allow_delete": bool(s3.get("allow_delete", False)),
    }
