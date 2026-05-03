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
$env:SDOCS_MCP_CONFIG = $cfg
$env:SDOCS_MCP_UI_HOST = "127.0.0.1"
$env:SDOCS_MCP_UI_PORT = "8888"

Write-Host ""
Write-Host "Конфиг MCP: $cfg"
Write-Host "Откройте http://127.0.0.1:8888 — UI (sdocs-mcp-ui)."
Write-Host "В другом терминале для Cursor MCP: sdocs-mcp (stdio) с тем же SDOCS_MCP_CONFIG."
Write-Host ""

& .\.venv\Scripts\sdocs-mcp-ui
