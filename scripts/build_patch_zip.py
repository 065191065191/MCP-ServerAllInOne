#!/usr/bin/env python3
"""ZIP с файлами между двумя тегами + MANIFEST (для закрытого контура)."""
from __future__ import annotations

import argparse
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since", default="v0.6.5", help="начальный тег/коммит")
    p.add_argument("--until", default="HEAD", help="конечный тег/коммит")
    p.add_argument("--version", default=None, help="имя версии в имени архива")
    args = p.parse_args()
    version = args.version or git("describe", "--tags", "--abbrev=0")
    version = version.lstrip("v")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_zip = ROOT / "release" / f"sdocs-mcp-{version}-patch-{stamp}.zip"
    out_manifest = ROOT / "release" / f"sdocs-mcp-{version}-patch-MANIFEST.txt"
    out_files = ROOT / "release" / f"sdocs-mcp-{version}-patch-files.txt"

    commits = git("log", f"{args.since}..{args.until}", "--oneline")
    files = [f for f in git("diff", "--name-only", f"{args.since}..{args.until}").splitlines() if f.strip()]

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()

    missing: list[str] = []
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            path = ROOT / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
            else:
                missing.append(rel)

    manifest = [
        f"# Патч sdocs-mcp {version}",
        f"# Собрано: {stamp} (UTC)",
        f"# Диапазон: {args.since}..{args.until}",
        "",
        "## Коммиты",
        commits or "(нет)",
        "",
        f"## Файлы ({len(files)})",
        "",
        *files,
    ]
    if missing:
        manifest.extend(["", "## Отсутствуют на диске", "", *missing])

    out_manifest.write_text("\n".join(manifest) + "\n", encoding="utf-8")
    out_files.write_text(
        "\n".join(
            [
                f"# Изменённые файлы ({args.since}..{args.until})",
                "",
                *files,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    size_kb = out_zip.stat().st_size // 1024
    print(f"ZIP: {out_zip} ({len(files)} paths, {size_kb} KiB)")
    print(f"MANIFEST: {out_manifest}")
    print(f"FILES: {out_files}")


if __name__ == "__main__":
    main()
