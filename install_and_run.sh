#!/usr/bin/env bash
# Минимальный локальный запуск: venv → pip install → sdocs-mcp (Streamable HTTP).
# Требуется: Python 3.11+, интернет (для pip).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY=""
if command -v python3 >/dev/null 2>&1; then PY="python3"; elif command -v python >/dev/null 2>&1; then PY="python"; else
  echo "Не найден python3/python в PATH" >&2
  exit 1
fi

"$PY" - <<'PY' || { echo "Нужен Python >= 3.11" >&2; exit 1; }
import sys
if sys.version_info < (3, 11):
    sys.exit(1)
PY

if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
fi

if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
elif [[ -f .venv/Scripts/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/Scripts/activate
else
  echo "Не найден activate в .venv" >&2
  exit 1
fi

python -m pip install -q --upgrade pip
python -m pip install -q -e .

if [[ ! -f config.yaml ]]; then
  cp -f config.example.yaml config.yaml
  echo "[install] Создан config.yaml из config.example.yaml — при необходимости отредактируйте."
fi

export SDOCS_MCP_CONFIG="${SDOCS_MCP_CONFIG:-$ROOT/config.yaml}"
export SDOCS_MCP_TRANSPORT="${SDOCS_MCP_TRANSPORT:-streamable-http}"
export SDOCS_MCP_HOST="${SDOCS_MCP_HOST:-127.0.0.1}"
export SDOCS_MCP_PORT="${SDOCS_MCP_PORT:-8765}"
export SDOCS_MCP_DEV_LOCAL="${SDOCS_MCP_DEV_LOCAL:-true}"

MODE="${1:-mcp}"
case "$MODE" in
  mcp)
    echo "[install] SDOCS_MCP_CONFIG=$SDOCS_MCP_CONFIG"
    echo "[install] MCP: http://${SDOCS_MCP_HOST}:${SDOCS_MCP_PORT}/mcp (transport=$SDOCS_MCP_TRANSPORT)"
    exec sdocs-mcp
    ;;
  ui)
    export SDOCS_MCP_UI_HOST="${SDOCS_MCP_UI_HOST:-127.0.0.1}"
    export SDOCS_MCP_UI_PORT="${SDOCS_MCP_UI_PORT:-8888}"
    echo "[install] UI: http://${SDOCS_MCP_UI_HOST}:${SDOCS_MCP_UI_PORT}/"
    exec sdocs-mcp-ui
    ;;
  install-only)
    echo "[install] Зависимости установлены, venv активен в этой сессии. Запуск: sdocs-mcp  или  sdocs-mcp-ui"
    ;;
  *)
    echo "Использование: $0 [mcp|ui|install-only]" >&2
    echo "  mcp          — установить и запустить MCP (по умолчанию)" >&2
    echo "  ui           — установить и запустить демо-UI" >&2
    echo "  install-only — только pip install -e ." >&2
    exit 1
    ;;
esac
