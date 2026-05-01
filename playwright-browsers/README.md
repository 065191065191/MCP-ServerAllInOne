# Локальные бинарники Chromium (рядом с репозиторием)

Чтобы **перенести проект без `playwright install` на целевой машине**, один раз соберите каталог здесь (на машине с интернетом и тем же ОС/архитектурой, что и прод, либо в CI):

**Linux / macOS**

```bash
cd /path/to/stack-mcp-server
export PLAYWRIGHT_BROWSERS_PATH="$PWD/playwright-browsers"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
./scripts/vendor-playwright-browsers.sh
```

**Windows (PowerShell)**

```powershell
cd E:\path\to\stack-mcp-server
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\playwright-browsers"
New-Item -ItemType Directory -Force -Path $env:PLAYWRIGHT_BROWSERS_PATH | Out-Null
.\scripts\vendor-playwright-browsers.ps1
```

Дальше **упакуйте репозиторий вместе с `playwright-browsers/`** (архив, rsync, образ). На целевой машине: `pip install -e .` и **`stack-mcp-playwright`** — если каталог на месте, путь подставится сам.

Явно: `PLAYWRIGHT_BROWSERS_PATH=/abs/path/to/playwright-browsers` до запуска процесса (см. [док Playwright](https://playwright.dev/docs/browsers)).

**Размер:** сотни МБ; каталог в `.gitignore` (кроме этого README), в git обычно не коммитят.
