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

export STACK_MCP_CONFIG="${STACK_MCP_CONFIG:-$ROOT/config.docker.yaml}"
export STACK_MCP_UI_HOST="${STACK_MCP_UI_HOST:-127.0.0.1}"
export STACK_MCP_UI_PORT="${STACK_MCP_UI_PORT:-8888}"
# По умолчанию без токенов. Раскомментируйте для закрытого /api/* и /metrics:
# export STACK_MCP_UI_TOKEN="demo-ui-token-change-me"
# export STACK_MCP_METRICS_TOKEN="demo-metrics-token-change-me"

echo ""
echo "Конфиг MCP: $STACK_MCP_CONFIG"
echo "Откройте http://${STACK_MCP_UI_HOST}:${STACK_MCP_UI_PORT} — UI (stack-mcp-ui)."
echo "MCP по HTTP: STACK_MCP_DEV_LOCAL=true STACK_MCP_HOST=127.0.0.1 stack-mcp (порт 8765, путь /mcp) — только для отладки."
echo ""

exec .venv/bin/stack-mcp-ui
