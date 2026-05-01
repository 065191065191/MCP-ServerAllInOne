# Скачать Chromium в playwright-browsers\ от корня репозитория
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $env:PLAYWRIGHT_BROWSERS_PATH) {
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Root "playwright-browsers"
}
New-Item -ItemType Directory -Force -Path $env:PLAYWRIGHT_BROWSERS_PATH | Out-Null
Set-Location $Root
python -m playwright install chromium
try { python -m patchright install chromium } catch { }
Write-Host "Browsers in: $($env:PLAYWRIGHT_BROWSERS_PATH)"
