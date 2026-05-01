#!/usr/bin/env bash
# Три сборки: полный репозиторий; runtime с wheels (офлайн); runtime без wheels (только PyPI).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VERSION="$("$PYTHON" -c "import tomllib, pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); print(d['project']['version'])")"
STAMP="$(date +%Y%m%d%H%M)"
OUT="$ROOT/release"
mkdir -p "$OUT"

FULL_NAME="stack-mcp-server-full-${VERSION}-${STAMP}.tar.gz"
RUN_NAME="stack-mcp-server-runtime-${VERSION}-${STAMP}.tar.gz"
ONLINE_NAME="stack-mcp-server-runtime-online-${VERSION}-${STAMP}.tar.gz"

echo "==> полная сборка -> $OUT/$FULL_NAME"
tar -czf "$OUT/$FULL_NAME" \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='*.egg-info' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='release' \
  --exclude='.bundles' \
  --exclude='logs/*.log' \
  --exclude='stack-mcp-server-*.tar.gz' \
  -C "$ROOT" \
  .

_stage_runtime() {
  local dest="$1"
  local with_wheels="$2"
  mkdir -p "$dest/docs"
  cp -R "$ROOT/src" "$dest/"
  cp "$ROOT/pyproject.toml" "$ROOT/README.md" "$ROOT/config.example.yaml" "$dest/"
  cp "$ROOT/docs/CAPABILITIES.md" "$dest/docs/"
  cp "$ROOT/scripts/install.sh" "$dest/install.sh"
  chmod +x "$dest/install.sh"
  if [[ "$with_wheels" == "yes" ]]; then
    mkdir -p "$dest/wheels"
  fi
}

STAGE="$(mktemp -d)"
STAGE_ONLINE="$(mktemp -d)"
trap 'rm -rf "$STAGE" "$STAGE_ONLINE"' EXIT

RUN_ROOT="$STAGE/stack-mcp-server-runtime-${VERSION}"
ONLINE_ROOT="$STAGE_ONLINE/stack-mcp-server-runtime-online-${VERSION}"

_stage_runtime "$RUN_ROOT" yes
_stage_runtime "$ONLINE_ROOT" no

cat > "$RUN_ROOT/BUNDLE.txt" <<EOF
stack-mcp-server runtime bundle (with vendored wheels)
version: ${VERSION}
built: ${STAMP}

Contents: src/, pyproject.toml, README.md, config.example.yaml,
docs/CAPABILITIES.md, wheels/, install.sh

Online: ./install.sh
Offline: ./install.sh --offline ./wheels
EOF

cat > "$ONLINE_ROOT/BUNDLE.txt" <<EOF
stack-mcp-server runtime-online bundle (no wheels)
version: ${VERSION}
built: ${STAMP}

No pre-downloaded packages. ./install.sh needs PyPI/network.

Contents: src/, pyproject.toml, README.md, config.example.yaml,
docs/CAPABILITIES.md, install.sh
EOF

echo "==> pip download -> $RUN_ROOT/wheels"
(
  cd "$RUN_ROOT"
  "$PYTHON" -m pip download -q -d wheels "pip>=24" setuptools wheel
  "$PYTHON" -m pip download -q -d wheels .
)

echo "==> runtime (offline, with wheels) -> $OUT/$RUN_NAME"
tar -czf "$OUT/$RUN_NAME" -C "$STAGE" "$(basename "$RUN_ROOT")"

echo "==> runtime-online (no wheels) -> $OUT/$ONLINE_NAME"
tar -czf "$OUT/$ONLINE_NAME" -C "$STAGE_ONLINE" "$(basename "$ONLINE_ROOT")"

echo ""
echo "Готово:"
echo "  $OUT/$FULL_NAME"
echo "  $OUT/$RUN_NAME"
echo "  $OUT/$ONLINE_NAME"
ls -lh "$OUT/$FULL_NAME" "$OUT/$RUN_NAME" "$OUT/$ONLINE_NAME"
