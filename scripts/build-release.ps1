# Three bundles: full repo; runtime+ wheels; runtime-online without wheels. Windows / PowerShell.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$Version = & $Python -c "import tomllib, pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); print(d['project']['version'])"
$Stamp = Get-Date -Format "yyyyMMddHHmm"
$Out = Join-Path $Root "release"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$FullName = "stack-mcp-server-full-${Version}-${Stamp}.tar.gz"
$RunName = "stack-mcp-server-runtime-${Version}-${Stamp}.tar.gz"
$OnlineName = "stack-mcp-server-runtime-online-${Version}-${Stamp}.tar.gz"
$FullPath = Join-Path $Out $FullName
$RunPath = Join-Path $Out $RunName
$OnlinePath = Join-Path $Out $OnlineName

$excludes = @(
 ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "*.egg-info", "dist", "build", "release", ".bundles", "stack-mcp-server-*.tar.gz"
)

Write-Host "==> full bundle -> $FullPath"
$tarArgs = @("-czf", $FullPath)
foreach ($e in $excludes) { $tarArgs += "--exclude=$e" }
$tarArgs += "-C", $Root, "."
& tar @tarArgs

function Copy-RuntimeTree {
    param([string]$Dest, [bool]$IncludeWheels)
    New-Item -ItemType Directory -Force -Path (Join-Path $Dest "docs") | Out-Null
    Copy-Item -Recurse -Force (Join-Path $Root "src") (Join-Path $Dest "src")
    Copy-Item -Force (Join-Path $Root "pyproject.toml") $Dest
    Copy-Item -Force (Join-Path $Root "README.md") $Dest
    Copy-Item -Force (Join-Path $Root "config.example.yaml") $Dest
    Copy-Item -Force (Join-Path $Root "docs\CAPABILITIES.md") (Join-Path $Dest "docs")
    Copy-Item -Force (Join-Path $Root "scripts\install.sh") (Join-Path $Dest "install.sh")
    if ($IncludeWheels) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Dest "wheels") | Out-Null
    }
}

$Stage = Join-Path $env:TEMP ("mcp-runtime-" + [Guid]::NewGuid().ToString("n"))
$StageOnline = Join-Path $env:TEMP ("mcp-online-" + [Guid]::NewGuid().ToString("n"))
$RunRootName = "stack-mcp-server-runtime-$Version"
$OnlineRootName = "stack-mcp-server-runtime-online-$Version"
$RunRoot = Join-Path $Stage $RunRootName
$OnlineRoot = Join-Path $StageOnline $OnlineRootName

Copy-RuntimeTree -Dest $RunRoot -IncludeWheels $true
Copy-RuntimeTree -Dest $OnlineRoot -IncludeWheels $false

$BUNDLE = @"
stack-mcp-server runtime bundle (with vendored wheels)
version: $Version
built: $Stamp

Install online: ./install.sh
Install offline: ./install.sh --offline ./wheels
"@
Set-Content -Path (Join-Path $RunRoot "BUNDLE.txt") -Value $BUNDLE -Encoding UTF8

$BUNDLEOnline = @"
stack-mcp-server runtime-online (no wheels)
version: $Version
built: $Stamp

No pre-downloaded wheels. Run ./install.sh with PyPI access.
"@
Set-Content -Path (Join-Path $OnlineRoot "BUNDLE.txt") -Value $BUNDLEOnline -Encoding UTF8

Write-Host "==> pip download -> wheels (offline runtime only)"
Push-Location $RunRoot
try {
    & $Python -m pip download -q -d wheels "pip>=24" setuptools wheel
    & $Python -m pip download -q -d wheels .
}
finally {
    Pop-Location
}

Write-Host "==> runtime (with wheels) -> $RunPath"
& tar -czf $RunPath -C $Stage $RunRootName

Write-Host "==> runtime-online (no wheels) -> $OnlinePath"
& tar -czf $OnlinePath -C $StageOnline $OnlineRootName

Remove-Item -Recurse -Force $Stage
Remove-Item -Recurse -Force $StageOnline

Write-Host ""
Write-Host "Done:"
Write-Host "  $FullPath"
Write-Host "  $RunPath"
Write-Host "  $OnlinePath"
Get-Item $FullPath, $RunPath, $OnlinePath | Format-Table Name, Length -AutoSize
