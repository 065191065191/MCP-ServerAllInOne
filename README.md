# SDocsMCP (`sdocs-mcp`)

Модульный **MCP-сервер** на Python (**SDocsMCP**): OpenSearch (включая RAG), Kafka, PostgreSQL, Redis, Prometheus, почта, SSH. В каждом бэкенде — **лимиты и безопасные сценарии** без произвольных опасных операций из коробки.

**Репозиторий:** [github.com/065191065191/MCP-ServerAllInOne](https://github.com/065191065191/MCP-ServerAllInOne)

---

## Содержание

1. [Обзор проекта и «слайд» с модулями](#обзор-проекта-и-слайд-с-модулями)
2. [Два процесса и конфигурация](#два-процесса-и-конфигурация)
3. [Документация](#документация)
4. [Установка](#установка)
5. [Закрытый контур, прокси и секреты при `docker build`](#закрытый-контур-прокси-и-секреты-при-docker-build)
6. [MCP: транспорт, stateless, аудит](#mcp-транспорт-stateless-аудит)
7. [Запуск MCP (HTTP)](#запуск-mcp-http)
8. [Веб-UI и один порт с MCP](#веб-ui-и-один-порт-с-mcp)
9. [Конфигурация модулей (кратко)](#конфигурация-модулей-кратко)
10. [Docker: демо-стенд](#docker-демо-стенд)
11. [Безопасный запуск UI](#безопасный-запуск-ui)
12. [Автор и версия](#автор-и-версия)

---

## Обзор проекта и «слайд» с модулями

Нужна **одна страница**: кто куда ходит, что пишет, как связаны части.

| Где смотреть | Описание |
|--------------|----------|
| **[`docs/PRODUCT_OVERVIEW.md`](docs/PRODUCT_OVERVIEW.md)** | Обзор в Markdown + Mermaid (удобно на GitHub). |
| **[`docs/EXECUTIVE_ONEPAGER.html`](docs/EXECUTIVE_ONEPAGER.html)** | **Только для ТОП:** визуальный one-pager (SVG, без внешних картинок); открыть в браузере или в PDF. |
| **[`docs/EXECUTIVE_ONEPAGER.md`](docs/EXECUTIVE_ONEPAGER.md)** | **Только для вас:** сценарий показа, тайминг, структура слайда; не рассылать совету. |
| **Canvas в Cursor** | Интерактивный одностраничный обзор: файл **`sdocs-mcp-product-overview.canvas.tsx`** в каталоге canvases проекта IDE (типичный путь Windows: `C:\Users\<user>\.cursor\projects\e-git-mcp-server\canvases\`). Откройте файл в Cursor — панель Canvas рядом с чатом. **В git этот путь обычно не лежит**; дублирует смысл `PRODUCT_OVERVIEW.md`. |

Браузерный MCP в пакет **не входит**; при необходимости — отдельно [mcp-playwright](https://github.com/ma-pony/mcp-playwright).

---

## Два процесса и конфигурация

| Команда | Назначение | Порт по умолчанию |
|---------|------------|-------------------|
| `sdocs-mcp` | Только MCP по HTTP | `8765`, путь `/mcp` |
| `sdocs-mcp-ui` | Дашборд, `/metrics`, опционально встроенный MCP | `8888` |

- **Конфиг:** опционально **`SDOCS_MCP_CONFIG`** — абсолютный путь к YAML. Если переменная не задана или файла нет, подставляется пустой YAML: работают **дефолты** `AppConfig` (в YAML указывайте только отличия). Шаблоны: **`config.example.yaml`**, демо под Docker: **`config.docker.yaml`**, пример RAG + Kafka + Postgres + Redis: **`config.integrated.example.yaml`**.
- **Прод:** образы, Compose, OpenShift, systemd — **[`deploy/README.md`](deploy/README.md)**.
- **Журнал изменений:** [`CHANGELOG.md`](CHANGELOG.md).

---

## Документация

| Документ | Зачем |
|----------|--------|
| [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) | Полная матрица tools и лимитов |
| [`docs/PRODUCT_OVERVIEW.md`](docs/PRODUCT_OVERVIEW.md) | Архитектура «одним слайдом» (Markdown + Mermaid) |
| [`docs/EXECUTIVE_ONEPAGER.html`](docs/EXECUTIVE_ONEPAGER.html) | Визуальная витрина для руководства (HTML + SVG) |
| [`docs/EXECUTIVE_ONEPAGER.md`](docs/EXECUTIVE_ONEPAGER.md) | Сценарий и заметки к показу one-pager |
| [`docs/OFFLINE_AND_PROXY_INSTALL.md`](docs/OFFLINE_AND_PROXY_INSTALL.md) | Закрытый контур, прокси, wheelhouse, секреты BuildKit |
| [`docs/TOOL_CALL_AUDIT.md`](docs/TOOL_CALL_AUDIT.md) | Аудит вызовов MCP tools в OpenSearch |
| [`docs/SSH_SCALE.md`](docs/SSH_SCALE.md) | Много SSH-хостов: лимиты, `SDOCS_MCP_SSH_HOSTS_FILE`, CSV |
| [`docs/INSTALL_AND_RELEASE.md`](docs/INSTALL_AND_RELEASE.md) | Релизные архивы и установка |
| [`deploy/README.md`](deploy/README.md) | Промышленный деплой |

---

## Установка

**Вариант A — скрипт** (Linux / macOS / WSL):

```bash
chmod +x scripts/install.sh
./scripts/install.sh
source .venv/bin/activate
```

**Вариант B — вручную:**

```bash
cd <каталог-клона>
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Скопируйте `config.example.yaml` в `config.yaml` (или укажите путь в `SDOCS_MCP_CONFIG`) и включите нужные `modules.*.enabled`.

### Релизные архивы

Из корня репозитория:

```powershell
# Windows
.\scripts\build-release.ps1
```

```bash
# Linux / macOS
chmod +x scripts/build-release.sh
./scripts/build-release.sh
```

В **`release/`** появятся архивы **full**, **runtime** (с `wheels/`) и **runtime-online**. Подробнее: [`release/README.md`](release/README.md), [`docs/INSTALL_AND_RELEASE.md`](docs/INSTALL_AND_RELEASE.md).

---

## Закрытый контур, прокси и секреты при `docker build`

Полная пошаговая инструкция: **[`docs/OFFLINE_AND_PROXY_INSTALL.md`](docs/OFFLINE_AND_PROXY_INSTALL.md)**. Ниже — самое нужное для README.

### Прокси без пароля (build-arg)

```bash
export HTTP_PROXY=http://proxy.example.corp:8080
export HTTPS_PROXY=http://proxy.example.corp:8080
export NO_PROXY=localhost,127.0.0.1,.example.corp

docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -f deploy/Dockerfile \
  -t sdocs-mcp-ui:0.6.1 .
```

### Прокси с логином и паролем (секрет не в слоях образа)

Не передавайте пароль через `--build-arg`. Используйте **BuildKit** и файл с одной строкой URL (файл **`build-proxy.url`** добавлен в `.gitignore`):

```bash
printf '%s' 'http://USER:PASSWORD@proxy.example.corp:8080' > build-proxy.url

DOCKER_BUILDKIT=1 docker build \
  --secret id=build_proxy,src=build-proxy.url \
  -f deploy/Dockerfile.buildkit-proxy \
  -t sdocs-mcp-ui:0.6.1 .
```

Dockerfile: **`deploy/Dockerfile.buildkit-proxy`**. Пример для Compose и **`NO_PROXY` для бэкендов** (OpenSearch, Kafka и т.д.) — в офлайн-доке.

### Перенос в изолированную сеть

На машине со сборкой: `docker save sdocs-mcp-ui:0.6.1 -o sdocs-mcp-ui-0.6.1.tar` → перенос → на целевой площадке: `docker load -i ...`.

---

## MCP: транспорт, stateless, аудит

- По умолчанию **`SDOCS_MCP_TRANSPORT=streamable-http`**, URL вида `http(s)://хост:порт/mcp`.
- **`SDOCS_MCP_HOST`** по умолчанию `0.0.0.0`. Привязка к `localhost` без **`SDOCS_MCP_DEV_LOCAL=true`** запрещена (режим прод за reverse proxy / firewall).
- **`SDOCS_MCP_STATELESS_HTTP=true`** — stateless Streamable HTTP (несколько воркеров UI / реплики без sticky). Иначе **`SDOCS_MCP_UI_WORKERS=1`**. В **`sdocs_mcp_status`** есть поле **`stateless_http`**.
- Альтернатива: **`SDOCS_MCP_TRANSPORT=sse`**. **`stdio`** — только с **`SDOCS_MCP_DEV_LOCAL=true`**.

**Аудит вызовов tools в OpenSearch:** `modules.opensearch.tool_call_audit.enabled: true` (нужен `opensearch.enabled`): журнал **вызовов MCP tools** (аргументы, ответ, длительность) — для разборов инцидентов; это не то же самое, что **RAG-память** (`opensearch_rag_*`). Подробнее: [`docs/TOOL_CALL_AUDIT.md`](docs/TOOL_CALL_AUDIT.md).

---

## Запуск MCP (HTTP)

```bash
export SDOCS_MCP_CONFIG="$PWD/config.yaml"
sdocs-mcp
```

| Переменная | По умолчанию | Смысл |
|------------|--------------|--------|
| `SDOCS_MCP_TRANSPORT` | `streamable-http` | `streamable-http`, `sse` или `stdio` (только с `SDOCS_MCP_DEV_LOCAL=true`) |
| `SDOCS_MCP_HOST` | `0.0.0.0` | `127.0.0.1` / `localhost` / `::1` без dev-флага — ошибка |
| `SDOCS_MCP_PORT` | `8765` | Порт HTTP MCP |
| `SDOCS_MCP_STATELESS_HTTP` | выкл. | Включить stateless Streamable HTTP |
| `SDOCS_MCP_DEV_LOCAL` | — | `true` — localhost и stdio для отладки |

Инструмент **`sdocs_mcp_status`** всегда доступен: какие модули включены (без секретов).

---

## Веб-UI и один порт с MCP

При **`SDOCS_MCP_EMBED_MCP=true`** процесс **`sdocs-mcp-ui`** отдаёт MCP на **`http://<хост>:<порт>/sdocs/mcp`** (по умолчанию; путь = **`<SDOCS_MCP_UI_BASE_PATH>/mcp`**) на том же порту, что UI и `/sdocs/metrics`. Либо **`SDOCS_MCP_UI_WORKERS=1`**, либо **`SDOCS_MCP_STATELESS_HTTP=true`** при большем числе воркеров или реплик.

**Префикс приложения:** по умолчанию **`SDOCS_MCP_UI_BASE_PATH=/sdocs`** — `/sdocs/health`, `/sdocs/api/*`, `/sdocs/metrics`, MCP на **`/sdocs/mcp`**, landing на **`/sdocs/`**. Корень хоста **`/`** не занят (на том же origin могут жить другие сервисы). Пусто или `/` — всё на корне (отдельный порт / локальная отладка).

**HTML-консоль:** по умолчанию **`SDOCS_MCP_UI_PAGES_PREFIX=/console`** → **`/sdocs/console/`** (дашборд, ops, cron). Пусто — страницы прямо под `/sdocs/`.

**stdio по умолчанию отключён** без `SDOCS_MCP_DEV_LOCAL=true`.

---

## Конфигурация модулей (кратко)

- **PostgreSQL** — фиксированные диагностические сценарии; произвольный SQL только из YAML (`allowlisted_queries`), клиент передаёт `query_id`.
- **Redis** — встроенный RESP2-клиент; чтение с лимитами, `SETEX` и опциональный `SCAN` по allowlist.
- **Kafka** — только топики из `topic_allowlist`; produce/admin отдельными флагами.
- **Почта** — IMAP/SMTP; пароли через env.
- **Prometheus** — HTTP API; по умолчанию **`truncate_responses: false`** (крупные ответы не режутся на стороне MCP).
- **OpenSearch** — cluster/cat/search/count; по умолчанию без деструктивных API (`allow_write: false`). Опционально **RAG** в allowlist-индексах.

Детали: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

---

## Docker: демо-стенд

1. Поднять инфраструктуру:

```bash
docker compose up -d
```

Postgres `localhost:5432`, Redis `6379`, OpenSearch `http://localhost:9200`, Kafka bootstrap **`localhost:9094`**. Топик `demo.events` создаётся job `kafka-init`.

2. Конфиг: **`config.docker.yaml`**.

3. UI:

```bash
source .venv/bin/activate
export SDOCS_MCP_CONFIG="$PWD/config.docker.yaml"
sdocs-mcp-ui
```

- MCP (агенты): [http://127.0.0.1:8888/sdocs/mcp](http://127.0.0.1:8888/sdocs/mcp)
- Landing: [http://127.0.0.1:8888/sdocs/](http://127.0.0.1:8888/sdocs/)
- Дашборд: [http://127.0.0.1:8888/sdocs/console/](http://127.0.0.1:8888/sdocs/console/)
- Консоль: [http://127.0.0.1:8888/sdocs/console/ops](http://127.0.0.1:8888/sdocs/console/ops)
- Метрики: `/sdocs/metrics`. Корень `http://127.0.0.1:8888/` — не SDocsMCP.

Скрипт: **`scripts/run-demo.sh`**.

Отладочный **`sdocs-mcp`** на `8765` в том же стенде: `export SDOCS_MCP_DEV_LOCAL=true SDOCS_MCP_HOST=127.0.0.1` и в другом терминале `sdocs-mcp` → `http://127.0.0.1:8765/mcp`.

**Scrape `/metrics` в Prometheus** (предпочтительно Bearer, не светить секрет в URL):

```yaml
authorization:
  type: Bearer
  credentials: "<SDOCS_MCP_METRICS_TOKEN>"
```

Подробнее про токены и лимиты: переменные **`SDOCS_MCP_METRICS_*`**, **[`deploy/README.md`](deploy/README.md)**.

---

## Безопасный запуск UI

По умолчанию **`SDOCS_MCP_UI_TOKEN` не задан** — `/api/*` без Bearer (есть rate limit и audit). Для Bearer-защиты задайте непустой **`SDOCS_MCP_UI_TOKEN`**.

Пример переменных:

```bash
# export SDOCS_MCP_UI_TOKEN="change-me-strong-token"
export SDOCS_MCP_UI_ENABLE_INVOKE="false"
export SDOCS_MCP_UI_ENABLE_SEED="false"
export SDOCS_MCP_UI_RATE_LIMIT_RPM="60"
export SDOCS_MCP_UI_AUDIT_LOG_PATH="$PWD/data/logs/ui-audit.log"
export SDOCS_MCP_UI_HOST="127.0.0.1"

export SDOCS_MCP_METRICS_TOKEN="change-me-metrics-secret"
export SDOCS_MCP_METRICS_REQUIRE_TOKEN="false"
export SDOCS_MCP_METRICS_ACCEPT_UI_BEARER="false"
export SDOCS_MCP_METRICS_RATE_LIMIT_RPM="120"
```

Журнал UI (JSONL): события `access`, `auth_failed`, `rate_limit`, `mcp_invoke_*`, `seed`, `metrics_*`.

---

## Автор и версия

**Автор:** Gos Stepan Ulievich.

Версия: **`pyproject.toml`** → **`src/sdocs_mcp/__init__.py`** → метаданные UI; теги образов в **`deploy/*`**. Текущая: **0.6.1**. При изменениях — SemVer, обновление **`CHANGELOG.md`**, коммит. Пользовательская документация — **на русском** (`README.md`, `CHANGELOG.md`).
