#!/usr/bin/env python3
"""Сборка ZIP-архива s3-mcp для передачи в закрытый контур."""
from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Файлы пакета s3-mcp
S3_MCP_FILES = [
    "src/s3_mcp/__init__.py",
    "src/s3_mcp/__main__.py",
    "src/s3_mcp/config.py",
    "src/s3_mcp/s3_client.py",
    "src/s3_mcp/server.py",
    "s3-mcp/README.md",
    "docs/S3_MCP.md",
    "tests/test_s3_client.py",
    "tests/test_s3_mcp_server.py",
    "pyproject.toml",
]


def main() -> None:
    from s3_mcp import __version__

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = ROOT / "release"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_zip = out_dir / f"s3-mcp-{__version__}-bundle-{stamp}.zip"
    out_manifest = out_dir / f"s3-mcp-{__version__}-bundle-MANIFEST.txt"

    if out_zip.exists():
        out_zip.unlink()

    included: list[str] = []
    missing: list[str] = []
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in S3_MCP_FILES:
            path = ROOT / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
                included.append(rel)
            else:
                missing.append(rel)

    manifest = [
        f"# s3-mcp bundle v{__version__}",
        f"# Собрано: {stamp} (UTC)",
        "",
        f"## Файлы ({len(included)})",
        "",
        *included,
    ]
    if missing:
        manifest.extend(["", "## Отсутствуют", "", *missing])
    out_manifest.write_text("\n".join(manifest) + "\n", encoding="utf-8")

    size_kb = out_zip.stat().st_size // 1024
    print(f"ZIP: {out_zip} ({len(included)} files, {size_kb} KiB)")
    print(f"MANIFEST: {out_manifest}")


if __name__ == "__main__":
    main()
