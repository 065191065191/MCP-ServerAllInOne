# stack-mcp-server

**Исходный код и релизы:** [github.com/065191065191/MCP-ServerAllInOne](https://github.com/065191065191/MCP-ServerAllInOne) (`git clone` и `git push` — в этот репозиторий).

Единый MCP-сервер (Python) с **включаемыми модулями**: OpenSearch, Kafka, PostgreSQL, Redis, Prometheus (HTTP API + опциональная выгрузка в Kafka). В каждом бэкенде заложены **лимиты и безопасные сценарии** (см. `docs/CAPABILITIES.md`).

**Браузерный MCP:** [ma-pony/mcp-playwright](https://github.com/ma-pony/mcp-playwright) уже в зависимостях — после `pip install -e .` выполните **`playwright install chromium`**, затем **`stack-mcp-playwright`** (или Docker: `docker compose -f docker-compose.playwright.yml up -d --build`). URL **`http://127.0.0.1:8770/mcp`**. См. **[docs/MCP_PLAYWRIGHT.md](docs/MCP_PLAYWRIGHT.md)**.

## Промышленная эксплуатация

Каталог **`deploy/`**: production Dockerfile, `docker-compose.prod.yml`, примеры `env` и конфига, systemd unit для UI, чеклист безопасности. Эндпоинты **`/health`** (liveness) и **`/ready`** (конфиг читается) для оркестраторов. Переменные **`STACK_MCP_UI_WORKERS`**, **`STACK_MCP_LOG_LEVEL`**, **`STACK_MCP_UI_TRUSTED_HOSTS`** — см. `deploy/README.md`.

## Установка

**Вариант A — bash-инсталлятор** (рекомендуется на Linux/macOS/WSL):

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

Скопируйте `config.example.yaml` в `config.yaml` (или задайте `STACK_MCP_CONFIG` на абсолютный путь к файлу) и включите нужные `modules.*.enabled`.

### Релизные архивы (full + runtime с wheels + runtime-online без wheels)

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

В каталоге **`release/`** появятся три `.tar.gz`: **full**, **runtime** (с предзагруженными `wheels/`) и **runtime-online** (без wheels, только установка через PyPI). См. **`release/README.md`**. Установщик: **`install.sh`** в корне или **`scripts/install.sh`**. Подробности: **[docs/INSTALL_AND_RELEASE.md](docs/INSTALL_AND_RELEASE.md)**.

## Запуск MCP (только HTTP API)

По умолчанию **`stack-mcp`** слушает **Streamable HTTP** на **`0.0.0.0:8765`**, путь **`/mcp`**. Привязка к **localhost без флага разработки запрещена** — сервис рассчитан на выкладку за reverse proxy / firewall, не на «локальный stdio».

```bash
export STACK_MCP_CONFIG="$PWD/config.yaml"
# опционально: SSE вместо Streamable HTTP
# export STACK_MCP_TRANSPORT=sse
stack-mcp
# или: python -m stack_mcp
```

Переменные:

| Переменная | Значение по умолчанию | Смысл |
|------------|----------------------|--------|
| `STACK_MCP_TRANSPORT` | `streamable-http` | `streamable-http`, `sse` или `stdio` (только с `STACK_MCP_DEV_LOCAL=true`) |
| `STACK_MCP_HOST` | `0.0.0.0` | `127.0.0.1` / `localhost` / `::1` без `STACK_MCP_DEV_LOCAL=true` — **выход с ошибкой** |
| `STACK_MCP_PORT` | `8765` | Порт HTTP MCP |
| `STACK_MCP_DEV_LOCAL` | не задан | `true` — разрешить localhost и stdio **только для отладки** |

Клиент MCP должен подключаться по URL вида **`https://<хост>/mcp`** (Streamable HTTP) или к эндпоинту SSE — см. документацию вашего клиента к удалённому MCP.

### Один порт: веб UI + MCP (Docker / `stack-mcp-ui`)

Если задано **`STACK_MCP_EMBED_MCP=true`**, процесс **`stack-mcp-ui`** монтирует Streamable HTTP MCP на **`http://<хост>:<STACK_MCP_UI_PORT>/mcp`** (тот же порт, что и UI и `/metrics`). Отдельный **`stack-mcp`** на 8765 не нужен. Рекомендуется **`STACK_MCP_UI_WORKERS=1`**, иначе сессии MCP могут работать нестабильно.

**stdio и локальный Cursor с subprocess не являются режимом по умолчанию** и намеренно отключены без `STACK_MCP_DEV_LOCAL=true`.

## Инструмент `stack_mcp_status`

Всегда зарегистрирован: показывает, какие модули **включены** в конфиге (без секретов).

## Конфигурация

- **PostgreSQL**: только 10 фиксированных диагностических сценариев, без произвольного SQL.
- **Redis**: встроенный RESP2-клиент (без пакета `redis`); INFO/MEMORY STATS/DBSIZE/SLOWLOG/PING, ограниченное чтение ключей и `SETEX` с лимитами; опциональный `SCAN` по allowlist-префиксам.
- **Kafka**: топики только из `topic_allowlist`; потребление с лимитами сообщений и байт; produce/admin — отдельными флагами.
- **Почта (IMAP/SMTP)**: чтение и отправка при `modules.mail.enabled`; пароли через переменные окружения (`imap_password_env` и при необходимости SMTP).
- **OpenSearch**: базовые инструменты (`health`, `indices`, `mapping`, `search`, `count`) + расширенная диагностика (`cluster_stats`, `nodes_stats`, `pending_tasks`, `cat_shards`, `allocation_explain`); опционально `password_env` вместо пароля в YAML. Опционально **RAG** (`opensearch.rag`): общая память агента в allowlist-индексах с лимитами (`opensearch_rag_*` tools).

Подробная матрица возможностей и лимитов: `docs/CAPABILITIES.md`.

## Docker: Kafka, OpenSearch, Postgres, Redis + демо UI

1. Поднять инфраструктуру:

```bash
docker compose up -d
```

Сервисы на хосте: Postgres `localhost:5432`, Redis `6379`, OpenSearch `http://localhost:9200`, Kafka **bootstrap `localhost:9094`** (внутри сети compose — `kafka:9092`). Топик `demo.events` создаётся job-ом `kafka-init`.

2. Конфиг MCP для этого стенда: **`config.docker.yaml`**.

```bash
export STACK_MCP_CONFIG="$PWD/config.docker.yaml"
```

3. Веб-интерфейс (реальные проверки подключений + список MCP tools + вызовы через `FastMCP.call_tool`, без моков):

```bash
source .venv/bin/activate
pip install -e .
export STACK_MCP_CONFIG="$PWD/config.docker.yaml"
# Опционально (по умолчанию UI и /api/* без Bearer):
# export STACK_MCP_UI_TOKEN="change-me-strong-token"
# export STACK_MCP_METRICS_TOKEN="change-me-metrics-token"
stack-mcp-ui
```

Откройте [http://127.0.0.1:8888](http://127.0.0.1:8888). На главной: карточки всех проверок (включая Prometheus и очередь Kafka), превью `/metrics`, ссылка на `/status-page`. Кнопка **Seed** пишет строку в Postgres, ключ в Redis, документ в OpenSearch и сообщение в Kafka.

Чтобы **в том же демо-стенде** поднять MCP по HTTP на ноутбуке (только отладка): `export STACK_MCP_DEV_LOCAL=true STACK_MCP_HOST=127.0.0.1` и в другом терминале `stack-mcp` — эндпоинт `http://127.0.0.1:8765/mcp`.

Скрипт **`scripts/run-demo.sh`** поднимает compose, venv и UI с `config.docker.yaml` (токены по умолчанию выключены; см. комментарии в скрипте).

```bash
chmod +x scripts/run-demo.sh
./scripts/run-demo.sh
```

Для мониторинга:

- `http://127.0.0.1:8888/status-page` — человекочитаемая страница статусов/очередей (подгружает `/metrics`; при включённой защите метрик введите тот же секрет, что в `STACK_MCP_METRICS_TOKEN`, или используйте UI token если задан `STACK_MCP_METRICS_ACCEPT_UI_BEARER=true`).
- `http://127.0.0.1:8888/metrics` — Prometheus text exposition (scrape endpoint): `stack_mcp_module_up`, latency модулей, `stack_mcp_kafka_retained_messages`, метрики rate-limit/UI.

**Без IP whitelist:** доступ к `/metrics` закрывается shared secret (см. `STACK_MCP_METRICS_*` ниже). Prometheus может передать токен так:

```yaml
# предпочтительно: Bearer (не светится в URL)
authorization:
  type: Bearer
  credentials: "<STACK_MCP_METRICS_TOKEN>"
```

Либо query `?metrics_token=...` в `scrape_config.params` — проще, но секрет чаще попадает в прокси-логи.

Для `stack-mcp` и UI задайте `STACK_MCP_CONFIG` на **абсолютный путь** к `config.docker.yaml` или к своему `config.yaml`.

## Безопасный запуск UI

По умолчанию **`STACK_MCP_UI_TOKEN` не задан** — все `/api/*` доступны **без** Bearer (остаётся rate limit и audit). Чтобы включить проверку заголовка, задайте непустой `STACK_MCP_UI_TOKEN`.

Минимальный набор переменных:

```bash
# export STACK_MCP_UI_TOKEN="change-me-strong-token"
export STACK_MCP_UI_ENABLE_INVOKE="false"
export STACK_MCP_UI_ENABLE_SEED="false"
export STACK_MCP_UI_RATE_LIMIT_RPM="60"
export STACK_MCP_UI_AUDIT_LOG_PATH="$PWD/logs/ui-audit.log"
export STACK_MCP_UI_HOST="127.0.0.1"

export STACK_MCP_METRICS_TOKEN="change-me-metrics-secret"
export STACK_MCP_METRICS_REQUIRE_TOKEN="false"
export STACK_MCP_METRICS_ACCEPT_UI_BEARER="false"
export STACK_MCP_METRICS_RATE_LIMIT_RPM="120"
```

Audit log пишет JSONL-записи по событиям доступа/ошибок/лимитов:

- `access`
- `auth_failed`
- `rate_limit`
- `mcp_invoke_ok` / `mcp_invoke_error`
- `seed`
- `metrics_auth_failed` / `metrics_rate_limit`

## Автор и версионирование

**Автор:** Gos Stepan Ulievich.

**Версия** задаётся в `pyproject.toml` (поле `version`), дублируется в `src/stack_mcp/__init__.py` (`__version__`) и в метаданных FastAPI UI (`info_app.py`); теги образов по умолчанию — в `deploy/*`. Текущая версия: **0.2.5**. При каждом осмысленном изменении: поднять версию (патч/минор по [SemVer](https://semver.org/lang/ru/)), обновить `CHANGELOG.md`, зафиксировать изменения коммитом. Описание проекта для пользователей ведётся **только на русском языке** (в первую очередь этот `README.md` и `CHANGELOG.md`).
