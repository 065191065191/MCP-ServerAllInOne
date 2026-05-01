# Браузерный MCP (ma-pony/mcp-playwright) — **в том же пакете**

Зависимость **`mcp-playwright`** входит в основной `pyproject.toml`: после **`pip install -e .`** отдельно ставить пакет не нужно.

## Один раз после клона / переноса каталога

```bash
pip install -e .
playwright install chromium
```

(Если используется **patchright** из зависимостей пакета и `playwright install` не хватает — выполните **`patchright install chromium`**.)

## Браузеры «рядом» (офлайн / без `playwright install` на целевой машине)

Один раз на машине с интернетом (желательно та же ОС и архитектура, что у прод):

- **`./scripts/vendor-playwright-browsers.sh`** или **`.\scripts\vendor-playwright-browsers.ps1`** — кладёт Chromium в **`playwright-browsers/`** в корне репозитория.
- Либо вручную: `export PLAYWRIGHT_BROWSERS_PATH="$PWD/playwright-browsers"` и `playwright install chromium` (см. [Playwright: managed directories](https://playwright.dev/docs/browsers)).

Перенесите репозиторий **вместе с каталогом** `playwright-browsers/`. При запуске **`stack-mcp-playwright`** путь подставится сам, если каталог не пустой и переменная `PLAYWRIGHT_BROWSERS_PATH` не задана (проверяются текущая директория и корень editable-установки). Иначе задайте **`PLAYWRIGHT_BROWSERS_PATH`** до старта процесса.

Подробнее: **`playwright-browsers/README.md`**.

## Запуск (тот же venv, что и `stack-mcp`)

```bash
stack-mcp-playwright
```

По умолчанию: **Streamable HTTP** `http://0.0.0.0:8770/mcp`. Переменные **`MCP_PLAYWRIGHT_HOST`**, **`MCP_PLAYWRIGHT_PORT`**.

Параллельно в другом терминале: `stack-mcp` на `:8765/mcp`.

## Docker (без ручного pip на хосте)

Корень репозитория как контекст сборки — в образ попадает тот же код и зависимости:

```bash
docker compose -f docker-compose.playwright.yml up -d --build
```

URL: **`http://127.0.0.1:8770/mcp`**.

## Исходный проект

https://github.com/ma-pony/mcp-playwright — обновления версии: диапазон в `pyproject.toml` (`mcp-playwright>=…,<…`).
