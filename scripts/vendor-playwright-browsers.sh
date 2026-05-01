#!/usr/bin/env bash
# Скачать Chromium в playwright-browsers/ (задайте PLAYWRIGHT_BROWSERS_PATH или скрипт возьмёт корень репо).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/playwright-browsers}"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
cd "$ROOT"
python -m playwright install chromium
# mcp-playwright тянет patchright — на всякий случай тот же путь
if python -c "import patchright" 2>/dev/null; then
  python -m patchright install chromium || true
fi
echo "Browsers in: $PLAYWRIGHT_BROWSERS_PATH"
