#!/usr/bin/env python3
"""Собрать offline-wheels и единый ZIP для установки без интернета."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL_DIR = ROOT / "offline-wheels"
DIST = ROOT / "dist"
DEFAULT_ZIP = DIST / "stack-mcp-server-offline.zip"

# Не класть в архив
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "offline-wheels",  # кладём отдельной стадией из WHEEL_DIR
    }
)


def _under_skip(path: Path, base: Path) -> bool:
    try:
        rel = path.relative_to(base)
    except ValueError:
        return True
    for part in rel.parts:
        if part in SKIP_DIR_NAMES:
            return True
        if part.endswith(".egg-info"):
            return True
    return False


def run_pip_wheel(with_dev: bool) -> None:
    if WHEEL_DIR.exists():
        shutil.rmtree(WHEEL_DIR)
    WHEEL_DIR.mkdir(parents=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pip",
        "wheel",
        "setuptools",
    ]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    spec = ".[dev]" if with_dev else "."
    # У pip wheel нет --upgrade; свежие версии даёт --no-cache-dir + актуальный pip/setuptools.
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        spec,
        "-w",
        str(WHEEL_DIR),
        "--no-cache-dir",
    ]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "setuptools>=69",
        "wheel",
        "-w",
        str(WHEEL_DIR),
        "--no-cache-dir",
    ]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def write_bundle_info(wheel_dir: Path, dist_info: Path) -> None:
    import platform
    import struct

    lines = [
        f"python: {sys.version.split()[0]} ({sys.executable})",
        f"platform: {platform.platform()}",
        f"machine: {platform.machine()} bits={struct.calcsize('P') * 8}",
        "",
        "Колёса в offline-wheels собраны под эту связку Python+ОС.",
        "На другой ОС / другой минорной версии Python ставьте с машины с интернетом",
        "на той же целевой платформе или пересоберите архив там.",
    ]
    dist_info.parent.mkdir(parents=True, exist_ok=True)
    (dist_info.parent / "BUNDLE_INFO.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_zip(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    count = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if path.is_dir():
                continue
            if _under_skip(path, ROOT):
                continue
            if path.resolve() == out.resolve():
                continue
            arc = path.relative_to(ROOT).as_posix()
            zf.write(path, arcname=arc)
            count += 1
        wheel_root = ROOT / "offline-wheels"
        for whl in sorted(wheel_root.glob("*.whl")):
            zf.write(whl, arcname=f"offline-wheels/{whl.name}")
            count += 1
        for other in wheel_root.glob("*"):
            if other.suffix == ".whl":
                continue
            if other.is_file():
                zf.write(other, arcname=f"offline-wheels/{other.name}")
                count += 1
    print(f"ZIP: {out} ({count} files)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-dev", action="store_true", help="не тянуть dev-зависимости (pytest/ruff)")
    p.add_argument(
        "--zip-only",
        action="store_true",
        help="не вызывать pip wheel (нужна уже заполненная папка offline-wheels)",
    )
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_ZIP)
    args = p.parse_args()
    if not args.zip_only:
        run_pip_wheel(with_dev=not args.no_dev)
    elif not any(WHEEL_DIR.glob("*.whl")):
        print("offline-wheels пуста: сначала запустите без --zip-only", file=sys.stderr)
        sys.exit(1)
    write_bundle_info(WHEEL_DIR, args.output)
    make_zip(args.output.resolve())
    print("Done. See OFFLINE_INSTALL.md and dist/BUNDLE_INFO.txt")


if __name__ == "__main__":
    main()
