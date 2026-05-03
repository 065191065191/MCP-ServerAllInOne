#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> docker compose up"
docker compose up -d

if [[ ! -x .venv/bin/python ]]; then
  echo "==> python3 -m venv .venv"
  python3 -m venv .venv
fi

echo "==> pip install -e ."
.venv/bin/pip install -e .

export SDOCS_MCP_CONFIG="${SDOCS_MCP_CONFIG:-$ROOT/config.docker.yaml}"
export SDOCS_MCP_UI_HOST="${SDOCS_MCP_UI_HOST:-127.0.0.1}"
export SDOCS_MCP_UI_PORT="${SDOCS_MCP_UI_PORT:-8888}"
# По умолчанию без токенов. Раскомментируйте для закрытого /api/* и /metrics:
# export SDOCS_MCP_UI_TOKEN="demo-ui-token-change-me"
# export SDOCS_MCP_METRICS_TOKEN="demo-metrics-token-change-me"

echo ""
echo "Конфиг MCP: $SDOCS_MCP_CONFIG"
echo "Откройте http://${SDOCS_MCP_UI_HOST}:${SDOCS_MCP_UI_PORT} — UI (sdocs-mcp-ui)."
echo "MCP по HTTP: SDOCS_MCP_DEV_LOCAL=true SDOCS_MCP_HOST=127.0.0.1 sdocs-mcp (порт 8765, путь /mcp) — только для отладки."
echo ""

exec .venv/bin/sdocs-mcp-ui
