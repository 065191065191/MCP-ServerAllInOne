$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

Write-Host "==> docker compose up"
docker compose up -d

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "==> python -m venv .venv"
  python -m venv .venv
}

Write-Host "==> pip install -e ."
& .\.venv\Scripts\pip install -e . | Out-Host

$cfg = Join-Path $root "config.docker.yaml"
$env:STACK_MCP_CONFIG = $cfg
$env:STACK_MCP_UI_HOST = "127.0.0.1"
$env:STACK_MCP_UI_PORT = "8888"

Write-Host ""
Write-Host "Конфиг MCP: $cfg"
Write-Host "Откройте http://127.0.0.1:8888 — UI (stack-mcp-ui)."
Write-Host "В другом терминале для Cursor MCP: stack-mcp (stdio) с тем же STACK_MCP_CONFIG."
Write-Host ""

& .\.venv\Scripts\stack-mcp-ui
