#!/usr/bin/env bash
# Установка sdocs-mcp в venv (онлайн или из каталога wheels рядом с проектом).
set -euo pipefail

OFFLINE_WHEELS=""
VENV_DIR=".venv"
PYTHON="${PYTHON:-python3}"

usage() {
  sed -n '1,200p' <<'EOF'
Использование:
  ./scripts/install.sh              # из корня клона: venv + pip install -e .
  ./install.sh                      # из корня минимальной сборки (рядом pyproject.toml)
  ./scripts/install.sh --venv /path/to/venv
  ./scripts/install.sh --offline ./wheels   # только из локальных wheel/sdist

Переменные:
  PYTHON   интерпретатор (по умолчанию python3)
  VENV_DIR каталог venv относительно корня проекта (по умолчанию .venv)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --offline)
      OFFLINE_WHEELS="${2:-}"
      if [[ -z "$OFFLINE_WHEELS" ]]; then echo >&2 "--offline требует путь к каталогу с wheel"; exit 2; fi
      shift 2
      ;;
    --venv)
      VENV_DIR="${2:-}"
      if [[ -z "$VENV_DIR" ]]; then echo >&2 "--venv требует путь"; exit 2; fi
      shift 2
      ;;
    *)
      echo >&2 "Неизвестный аргумент: $1"
      usage
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
  ROOT="$SCRIPT_DIR"
elif [[ -f "$(cd "$SCRIPT_DIR/.." && pwd)/pyproject.toml" ]]; then
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  echo >&2 "Не найден pyproject.toml (ожидается рядом со скриптом или в родительском каталоге)."
  exit 1
fi
cd "$ROOT"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo >&2 "Нет интерпретатора: $PYTHON"
  exit 1
fi

VENV_PATH="$ROOT/$VENV_DIR"
if [[ ! -d "$VENV_PATH" ]]; then
  echo "==> $PYTHON -m venv $VENV_DIR"
  "$PYTHON" -m venv "$VENV_PATH"
fi

PIP=( "$VENV_PATH/bin/pip" )
if [[ ! -x "${PIP[0]}" ]]; then
  echo >&2 "Не найден ${PIP[0]} (нужен Unix venv; в Windows используйте WSL или создайте venv вручную)."
  exit 1
fi

echo "==> pip install --upgrade pip"
"${PIP[@]}" install --upgrade pip

if [[ -n "$OFFLINE_WHEELS" ]]; then
  OFFLINE_WHEELS="$(cd "$OFFLINE_WHEELS" && pwd)"
  echo "==> офлайн-установка из $OFFLINE_WHEELS"
  "${PIP[@]}" install --no-index --find-links="$OFFLINE_WHEELS" -e "$ROOT"
else
  echo "==> pip install -e ."
  "${PIP[@]}" install -e "$ROOT"
fi

echo ""
echo "Готово. Активируйте venv: source $VENV_DIR/bin/activate"
echo "Конфиг: скопируйте config.example.yaml в config.yaml или задайте SDOCS_MCP_CONFIG."
echo "Запуск: sdocs-mcp  |  sdocs-mcp-ui"
