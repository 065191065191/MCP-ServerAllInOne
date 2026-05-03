# stack-mcp-server

Модульный **MCP-сервер** на Python: OpenSearch (включая RAG), Kafka, PostgreSQL, Redis, Prometheus, почта, SSH. В каждом бэкенде — **лимиты и безопасные сценарии** без произвольных опасных операций из коробки.

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
| **[`docs/PRODUCT_OVERVIEW.html`](docs/PRODUCT_OVERVIEW.html)** | **Только для ТОП:** витрина «посмотрели — купили»; без интернета. |
| **[`docs/PRODUCT_OVERVIEW_SPEAKER_NOTES.html`](docs/PRODUCT_OVERVIEW_SPEAKER_NOTES.html)** | **Только для вас:** конспект, тайминг, Q&amp;A; не слать совету. |
| **Canvas в Cursor** | Интерактивный одностраничный обзор: файл **`stack-mcp-product-overview.canvas.tsx`** в каталоге canvases проекта IDE (типичный путь Windows: `C:\Users\<user>\.cursor\projects\e-git-mcp-server\canvases\`). Откройте файл в Cursor — панель Canvas рядом с чатом. **В git этот путь обычно не лежит**; дублирует смысл `PRODUCT_OVERVIEW.md`. |

Браузерный MCP в пакет **не входит**; при необходимости — отдельно [mcp-playwright](https://github.com/ma-pony/mcp-playwright).

---

## Два процесса и конфигурация

| Команда | Назначение | Порт по умолчанию |
|---------|------------|-------------------|
| `stack-mcp` | Только MCP по HTTP | `8765`, путь `/mcp` |
| `stack-mcp-ui` | Дашборд, `/metrics`, опционально встроенный MCP | `8888` |

- **Конфиг:** переменная **`STACK_MCP_CONFIG`** — абсолютный путь к YAML. Шаблоны: **`config.example.yaml`**, демо под Docker: **`config.docker.yaml`**, пример RAG + Kafka + Postgres + Redis: **`config.integrated.example.yaml`**.
- **Прод:** образы, Compose, OpenShift, systemd — **[`deploy/README.md`](deploy/README.md)**.
- **Журнал изменений:** [`CHANGELOG.md`](CHANGELOG.md).

---

## Документация

| Документ | Зачем |
|----------|--------|
| [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) | Полная матрица tools и лимитов |
| [`docs/PRODUCT_OVERVIEW.md`](docs/PRODUCT_OVERVIEW.md) | Архитектура «одним слайдом» (Markdown + Mermaid) |
| [`docs/PRODUCT_OVERVIEW.html`](docs/PRODUCT_OVERVIEW.html) | HTML для ТОП (витрина) |
| [`docs/PRODUCT_OVERVIEW_SPEAKER_NOTES.html`](docs/PRODUCT_OVERVIEW_SPEAKER_NOTES.html) | Личный конспект докладчика |
| [`docs/OFFLINE_AND_PROXY_INSTALL.md`](docs/OFFLINE_AND_PROXY_INSTALL.md) | Закрытый контур, прокси, wheelhouse, секреты BuildKit |
| [`docs/TOOL_CALL_AUDIT.md`](docs/TOOL_CALL_AUDIT.md) | Аудит вызовов MCP tools в OpenSearch |
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

Скопируйте `config.example.yaml` в `config.yaml` (или укажите путь в `STACK_MCP_CONFIG`) и включите нужные `modules.*.enabled`.

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
  -t stack-mcp-ui:0.3.2 .
```

### Прокси с логином и паролем (секрет не в слоях образа)

Не передавайте пароль через `--build-arg`. Используйте **BuildKit** и файл с одной строкой URL (файл **`build-proxy.url`** добавлен в `.gitignore`):

```bash
printf '%s' 'http://USER:PASSWORD@proxy.example.corp:8080' > build-proxy.url

DOCKER_BUILDKIT=1 docker build \
  --secret id=build_proxy,src=build-proxy.url \
  -f deploy/Dockerfile.buildkit-proxy \
  -t stack-mcp-ui:0.3.2 .
```

Dockerfile: **`deploy/Dockerfile.buildkit-proxy`**. Пример для Compose и **`NO_PROXY` для бэкендов** (OpenSearch, Kafka и т.д.) — в офлайн-доке.

### Перенос в изолированную сеть

На машине со сборкой: `docker save stack-mcp-ui:0.3.2 -o stack-mcp-ui-0.3.2.tar` → перенос → на целевой площадке: `docker load -i ...`.

---

## MCP: транспорт, stateless, аудит

- По умолчанию **`STACK_MCP_TRANSPORT=streamable-http`**, URL вида `http(s)://хост:порт/mcp`.
- **`STACK_MCP_HOST`** по умолчанию `0.0.0.0`. Привязка к `localhost` без **`STACK_MCP_DEV_LOCAL=true`** запрещена (режим прод за reverse proxy / firewall).
- **`STACK_MCP_STATELESS_HTTP=true`** — stateless Streamable HTTP (несколько воркеров UI / реплики без sticky). Иначе **`STACK_MCP_UI_WORKERS=1`**. В **`stack_mcp_status`** есть поле **`stateless_http`**.
- Альтернатива: **`STACK_MCP_TRANSPORT=sse`**. **`stdio`** — только с **`STACK_MCP_DEV_LOCAL=true`**.

**Аудит вызовов tools в OpenSearch:** `modules.opensearch.tool_call_audit.enabled: true` (нужен `opensearch.enabled`): 10 признаков классификации, `caller_id` / опционально IP, аргументы и ответ с лимитами. Подробнее: [`docs/TOOL_CALL_AUDIT.md`](docs/TOOL_CALL_AUDIT.md).

---

## Запуск MCP (HTTP)

```bash
export STACK_MCP_CONFIG="$PWD/config.yaml"
stack-mcp
```

| Переменная | По умолчанию | Смысл |
|------------|--------------|--------|
| `STACK_MCP_TRANSPORT` | `streamable-http` | `streamable-http`, `sse` или `stdio` (только с `STACK_MCP_DEV_LOCAL=true`) |
| `STACK_MCP_HOST` | `0.0.0.0` | `127.0.0.1` / `localhost` / `::1` без dev-флага — ошибка |
| `STACK_MCP_PORT` | `8765` | Порт HTTP MCP |
| `STACK_MCP_STATELESS_HTTP` | выкл. | Включить stateless Streamable HTTP |
| `STACK_MCP_DEV_LOCAL` | — | `true` — localhost и stdio для отладки |

Инструмент **`stack_mcp_status`** всегда доступен: какие модули включены (без секретов).

---

## Веб-UI и один порт с MCP

При **`STACK_MCP_EMBED_MCP=true`** процесс **`stack-mcp-ui`** отдаёт MCP на **`http://<хост>:<порт>/mcp`** на том же порту, что UI и `/metrics`. Либо **`STACK_MCP_UI_WORKERS=1`**, либо **`STACK_MCP_STATELESS_HTTP=true`** при большем числе воркеров или реплик.

**stdio по умолчанию отключён** без `STACK_MCP_DEV_LOCAL=true`.

---

## Конфигурация модулей (кратко)

- **PostgreSQL** — фиксированные диагностические сценарии; произвольный SQL только из YAML (`allowlisted_queries`), клиент передаёт `query_id`.
- **Redis** — встроенный RESP2-клиент; чтение с лимитами, `SETEX` и опциональный `SCAN` по allowlist.
- **Kafka** — только топики из `topic_allowlist`; produce/admin отдельными флагами.
- **Почта** — IMAP/SMTP; пароли через env.
- **OpenSearch** — cluster/cat/search и опционально **RAG** в allowlist-индексах.

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
export STACK_MCP_CONFIG="$PWD/config.docker.yaml"
stack-mcp-ui
```

- Дашборд: [http://127.0.0.1:8888](http://127.0.0.1:8888)
- Операции: [http://127.0.0.1:8888/ops](http://127.0.0.1:8888/ops)
- Статус: `/status-page`, метрики: `/metrics`

Скрипт: **`scripts/run-demo.sh`**.

Отладочный **`stack-mcp`** на `8765` в том же стенде: `export STACK_MCP_DEV_LOCAL=true STACK_MCP_HOST=127.0.0.1` и в другом терминале `stack-mcp` → `http://127.0.0.1:8765/mcp`.

**Scrape `/metrics` в Prometheus** (предпочтительно Bearer, не светить секрет в URL):

```yaml
authorization:
  type: Bearer
  credentials: "<STACK_MCP_METRICS_TOKEN>"
```

Подробнее про токены и лимиты: переменные **`STACK_MCP_METRICS_*`**, **[`deploy/README.md`](deploy/README.md)**.

---

## Безопасный запуск UI

По умолчанию **`STACK_MCP_UI_TOKEN` не задан** — `/api/*` без Bearer (есть rate limit и audit). Для Bearer-защиты задайте непустой **`STACK_MCP_UI_TOKEN`**.

Пример переменных:

```bash
# export STACK_MCP_UI_TOKEN="change-me-strong-token"
export STACK_MCP_UI_ENABLE_INVOKE="false"
export STACK_MCP_UI_ENABLE_SEED="false"
export STACK_MCP_UI_RATE_LIMIT_RPM="60"
export STACK_MCP_UI_AUDIT_LOG_PATH="$PWD/data/logs/ui-audit.log"
export STACK_MCP_UI_HOST="127.0.0.1"

export STACK_MCP_METRICS_TOKEN="change-me-metrics-secret"
export STACK_MCP_METRICS_REQUIRE_TOKEN="false"
export STACK_MCP_METRICS_ACCEPT_UI_BEARER="false"
export STACK_MCP_METRICS_RATE_LIMIT_RPM="120"
```

Журнал UI (JSONL): события `access`, `auth_failed`, `rate_limit`, `mcp_invoke_*`, `seed`, `metrics_*`.

---

## Автор и версия

**Автор:** Gos Stepan Ulievich.

Версия: **`pyproject.toml`** → **`src/stack_mcp/__init__.py`** → метаданные UI; теги образов в **`deploy/*`**. Текущая: **0.3.2**. При изменениях — SemVer, обновление **`CHANGELOG.md`**, коммит. Пользовательская документация — **на русском** (`README.md`, `CHANGELOG.md`).
