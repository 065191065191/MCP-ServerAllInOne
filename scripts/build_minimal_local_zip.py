#!/usr/bin/env python3
"""Архив без .whl: только код + конфиги + install_and_run.sh для локального запуска с pip по сети."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "stack-mcp-server-local.zip"

# Не включаем в минимальный пакет
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "offline-wheels",
        ".offline-test-venv",
    }
)
SKIP_FILES = frozenset(
    {
        "docker.zip",  # большой бинарник, для pip-запуска не нужен
    }
)
# Для локального MCP+pip не обязательны (сильно уменьшают архив):
SKIP_TOP_LEVEL_DIRS = frozenset(
    {
        "docs",
        "tests",
        ".github",
        "deploy",
        "scripts",
        "logs",
        "build",  # артефакт setuptools, не исходники
    }
)


def skip_path(rel: Path) -> bool:
    if rel.parts and rel.parts[0] == "dist":
        return True
    if rel.parts and rel.parts[0] in SKIP_TOP_LEVEL_DIRS:
        return True
    if rel.name in SKIP_FILES:
        return True
    for part in rel.parts:
        if part in SKIP_DIR_NAMES:
            return True
        if part.endswith(".egg-info"):
            return True
    return False


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    n = 0
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(ROOT)
            if skip_path(rel):
                continue
            if path.resolve() == OUT.resolve():
                continue
            zf.write(path, rel.as_posix())
            n += 1
    print(f"Wrote {OUT} ({n} files), size {OUT.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
