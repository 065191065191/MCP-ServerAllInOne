# Журнал изменений

Формат основан на принципах [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Версии соответствуют [семантическому версионированию](https://semver.org/lang/ru/).

## [Unreleased]

## [0.6.5] — 2026-05-15

### Исправлено

- **Встроенный MCP (`SDOCS_MCP_EMBED_MCP`)**: при `app.mount(…/mcp)` запускается `session_manager.run()` в lifespan FastAPI — устранён `500 RuntimeError: Task group is not initialized`. Mount с завершающим `/` (`/sdocs/mcp/`).

## [0.6.4] — 2026-05-15

### Исправлено

- **Консоль /ops:** вызовы tools показывают текст ошибки (не зависают на «…»); подсказка про `SDOCS_MCP_UI_ENABLE_INVOKE`.
- **Дашборд:** кнопка «Тест почты» по `id=mail` (раньше проверялся `type=Почта`); счётчик обращений — HTTP к MCP, не `/api/*` UI.
- **Консоль:** кнопка «Тест почты (себе)» на вкладке MCP.

### Добавлено

- Счётчик `sdocs_mcp_mcp_http_requests_total` (Prometheus и `/api/dashboard-stats`).

## [0.6.3] — 2026-05-15

### Исправлено

- **PostgreSQL mTLS:** при подключении с `mtls_*` используется `modules.postgres.mtls_sslmode` из конфига (по умолчанию `verify-ca`), а не принудительный `verify-full` — устранена ошибка «certificate … do not match host name» при коннекте по IP.

## [0.6.2] — 2026-05-15

### Добавлено

- **Почта:** `imap_password` / `smtp_password` в YAML (альтернатива `*_env`).
- **Access log:** секция `logging` в конфиге — combined-формат как у nginx, в консоль и в файл (`logging.directory`, `logging.filename`).
- **UI:** `POST /api/mail/test-send` и кнопка «Тест (себе)» на дашборде для модуля mail.
- **PostgreSQL mTLS:** при широких правах на `mtls_key_file` ключ копируется во временный файл `0600` для libpq (без требования chmod на исходнике).

### Исправлено

- **Дашборд:** переключатель MCP больше не обнуляет «сэкономлено чел·ч» и деньги; кнопка «Сброс» сбрасывает период на месяц и обновляет данные.
- Убран блок «База для месяца (модель)» на главной панели.

## [0.6.1] — 2026-05-13

### Исправлено

- **`src/sdocs_mcp/server.py`**: отключено чтение dotenv-файла **`.env`** для настроек **FastMCP** (pydantic-settings), чтобы **`SDOCS_MCP_EMBED_MCP=true`** не приводил к **`PermissionError`** при недоступном `.env` в рабочем каталоге (Docker/OpenShift).

### Изменено

- **`Dockerfile`**, **`deploy/Dockerfile`**: в образ добавляется пустой читаемый **`/app/.env`**, чтобы снизить риск ошибок `stat` для старых путей загрузки настроек.
- Версия пакета, метаданные UI и теги образов по умолчанию — **0.6.1** (`pyproject.toml`, `deploy/*`, `README.md`, документация с примерами сборки).

### Документация и примеры

- **`config.example.yaml`**: минимальный шаблон с mail и комментариями «зачем».
- **`deploy/env.production.example`**: переменные почты **`SDOCS_MCP_MAIL_*`**, пояснения **`SDOCS_MCP_EMBED_MCP`**, **`SDOCS_MCP_STATELESS_HTTP`**, безопасность и аудит.
- **`release/DEPLOY_QUICKSTART.md`**: краткая инструкция для переноса в закрытый контур.

## [0.6.0] — 2026-05-12

### Изменено

- Версия пакета, метаданные UI и теги образов по умолчанию — **0.6.0** (синхронизация с линейкой релизов после **v0.5.0** на GitHub: тег **v0.5.0** указывал на коммит переименования в SDocsMCP; далее следуют изменения из записи **[0.4.0]** ниже — функционально они входят в продуктовую линию **0.6.0**).

## [0.4.0] — 2026-05-12

### Добавлено

- **`SDOCS_MCP_UI_BASE_PATH`**: единый префикс для маршрутов веб-UI и JSON API (`/api/*`, `/health`, `/ready`, `/metrics`) и для встроенного MCP (`…/mcp`); реализация в `ui_paths.normalize_ui_base_path`, роутер FastAPI с `include_router(..., prefix=…)`.
- **`modules.prometheus.truncate_responses`** (по умолчанию `false`): не усекать ответы instant/range/series на стороне MCP; при `true` сохраняется прежнее поведение с лимитами `max_*`.
- Увеличен дефолт **`modules.opensearch.search_max_size`** до **2000** для крупных выборок логов и count.

### Изменено

- Конфиг **опционален**: при отсутствии файла или `SDOCS_MCP_CONFIG` используется пустой YAML и дефолты `AppConfig`; UI и `/ready` не падают из‑за отсутствия файла; **`/ready`** возвращает `200`, если валидация конфига успешна.
- **`ssh_command_policy`** регистрируется **только** при **`modules.ssh.enabled`** (вместе с остальными SSH tools); убран из allowlist вызовов из UI.
- Документация: OpenSearch по умолчанию read-only (`allow_write: false`); разграничение **tool_call_audit** (журнал вызовов MCP) и **RAG**; Prometheus и префикс UI.

### Удалено

- Страницы и маршруты **`/cron-page`**, **`/cron`** и весь связанный с кроном UI/текст.

### Изменено (версионирование)

- Версия пакета и теги образов по умолчанию — **0.4.0** (`pyproject.toml`, Docker, OpenShift, `deploy/*`, README, офлайн-док).

## [0.3.2] — 2026-05-02

### Добавлено

- **`docs/PRODUCT_OVERVIEW.md`**: обзор продукта «одним слайдом» — диаграмма Mermaid, таблица модулей (входы, действия, куда пишет), ссылки на детальную документацию.

### Изменено

- Версия пакета и теги образов по умолчанию — **0.3.2** (синхронизация `pyproject.toml`, Docker, OpenShift, `deploy/*`, README).

## [0.3.1] — 2026-05-03

### Добавлено

- **`modules.opensearch.tool_call_audit`**: запись **каждого вызова MCP tool** в индекс OpenSearch (имя tool, классификация `module` / `category` / `operation_kind`, JSON аргументов, текст ответа с лимитами, `duration_ms`, ошибка). Подкласс **`AuditedFastMCP`**, переменная **`SDOCS_MCP_AUDIT_INSTANCE_ID`**, поле **`opensearch_tool_call_audit`** в **`sdocs_mcp_status`**.
- Аудит: поля **`caller_id`**, **`caller_client_ip`** (`schema_version` **3**), конфиг **`caller_http_header`**, **`default_caller_id`**, **`log_http_client_ip`**, env **`SDOCS_MCP_AUDIT_CALLER_ID`**; ASGI-middleware для HTTP MCP (встроенный UI и отдельный сервер).
- Тесты: `tests/test_tool_audit.py`.

### Изменено

- Версия пакета и теги образов по умолчанию — **0.3.1**.
- Docker: каталог данных приложения **`/app/data`** (volume в compose), **`BASE_IMAGE`** + установка **curl** через **apt-get** / **microdnf** / **dnf**; UI audit log по умолчанию в прод-compose: **`/app/data/logs/ui-audit.log`**.

## [0.3.0] — 2026-05-03

### Добавлено

- **`sdocs_mcp.ui_nav`**: единая верхняя навигация веб-UI (инжект в HTML дашборда).
- Postgres: ограничение имён БД из DSN — **`allowed_databases`**, **`allowed_database_prefixes`** или **`allowed_database_regex`** (взаимоисключение с префиксами/списком по правилам валидатора).
- SSH: флаг **`merge_recommended_substring_blocklist`** и рекомендованный набор подстрок; расширен встроенный слой **`_BUILTIN_SAFETY`**.
- Тесты: политика имён БД Postgres (`tests/test_postgres_database_policy.py`), доработки SSH и allowlist SQL.

### Удалено

- Встроенная обёртка **`sdocs-mcp-playwright`** (`playwright_http.py`), зависимость **`mcp-playwright`**, Docker/документация и скрипты vendor Chromium под этот сценарий. Браузерный MCP при необходимости запускайте отдельно ([mcp-playwright](https://github.com/ma-pony/mcp-playwright)).

### Изменено

- **`README.md`**, **`pyproject.toml`**: описание пакета без встроенного браузерного MCP.
- Версия пакета и теги образов по умолчанию — **0.3.0**.

## [0.2.9] — 2026-05-02

### Добавлено

- Переменная окружения **`SDOCS_MCP_STATELESS_HTTP`**: stateless Streamable HTTP в FastMCP (балансировка без sticky, несколько воркеров UI с **`SDOCS_MCP_EMBED_MCP`**).
- В **`sdocs_mcp_status`** возвращается поле **`stateless_http`**.
- Примеры **`deploy/openshift/`** (Deployment/Service для UI и отдельного `sdocs-mcp`).
- Тесты: включение stateless через env (`tests/test_embed_mcp_path.py`).

### Изменено

- **`README.md`**: разделы про два процесса, транспорт и stateless; таблица переменных.
- **Деплой**: комментарии в Dockerfiles, `deploy/env.production.example`, `docker-compose.prod.yml`, `docker-compose.mcp.yml`, `deploy/config.production.example.yaml`, `deploy/README.md`, `deploy/systemd/README.md`.
- Предупреждение в **`sdocs-mcp-ui`**: при **`SDOCS_MCP_STATELESS_HTTP`** не ругаемся на воркеры >1 так же, как без stateless.
- Версия пакета и теги образов по умолчанию — **0.2.9**.

## [0.2.8] — 2026-05-02

### Исправлено

- В `deploy/BUNDLE.md` в таблице «Что входит» версия образа была **0.2.6** при релизе 0.2.7 — приведена к актуальной линейке.

### Изменено

- Версия пакета и теги образов по умолчанию — **0.2.8**.

## [0.2.7] — 2026-05-02

### Добавлено

- Главная страница веб-UI: дашборд **MCP Метрики** (`/`, дублируется `/dashboard`) с данными через **`GET /api/dashboard-stats`** (проверки модулей, сводка UI).
- Консоль прежней главной вынесена на **`/ops`**; модуль разметки `executive_dashboard_html.py`.
- Тесты: дашборд и JSON API статистики (`tests/test_health.py`).

### Изменено

- Документация в `README.md`: раздел Docker/UI обновлён под новые маршруты.
- Версия пакета и теги образов по умолчанию — **0.2.7**.

## [0.2.6] — 2026-05-02

### Изменено

- Версия пакета и теги образов по умолчанию — **0.2.6**.
- Журнал: раздел **0.2.5** дополнен фактическим перечнем изменений из того релиза (первоначальное сообщение коммита описывало только правки версий Docker).

## [0.2.5] — 2026-05-02

### Добавлено

- **PostgreSQL:** опциональные запросы из белого списка (`allowlisted_queries`) с проверкой SQL на read-only в `postgres_allowlist_sql.py`, интеграция в `postgres_tools`, тесты `tests/test_postgres_allowlist.py`.
- **Тесты:** путь Streamable HTTP MCP (`/mcp` и кастомный путь) — `tests/test_embed_mcp_path.py`; валидация SSH-команд — `tests/test_ssh_command_validate.py` (пустые команды, shell-операторы, встроенный safety filter).

### Изменено

- **Веб-UI** (`info_app.py`): существенные доработки интерфейса и связанной логики.
- **MCP-сервер** (`server.py`), **конфиг** (`config.py`), примеры **`config.example.yaml`** / **`deploy/config.production.example.yaml`**, **`docs/CAPABILITIES.md`**, прод **`deploy/docker-compose.prod.yml`**, **`deploy/README.md`**, **`deploy/env.production.example`**, тест **`tests/test_health.py`**.

### Исправлено

- Устаревшие номера **0.3.0** приведены к линейке релиза: `LABEL` в корневом `Dockerfile`, `image` в `docker-compose.mcp.yml`, тексты и имена архивов в `deploy/BUNDLE.md`. В `docker-compose.mcp.yml` и `BUNDLE.md` имя образа выровнено с прод-сборкой: **`sdocs-mcp-ui`** (как в `deploy/Dockerfile`).

## [0.2.4] — 2026-05-02

### Удалено

- Каталог **`.cursor/rules/`** больше не входит в репозиторий; локальные настройки Cursor не коммитятся (игнор в `.gitignore`).
- Файл **`docs/presentation-leadership-4slides.html`** — в проекте нигде не ссылался, удалён как лишний.

### Изменено

- Версия пакета и теги образов по умолчанию — **0.2.4**.

## [0.2.3] — 2026-05-02

### Исправлено

- Имя автора в метаданных и документации: **Gos Stepan Ulievich** (ранее было ошибочно написано «Sepat»).

### Изменено

- Версия пакета и теги образов по умолчанию — **0.2.3**.

## [0.2.2] — 2026-05-02

### Добавлено

- В `README.md` указан канонический репозиторий: [github.com/065191065191/MCP-ServerAllInOne](https://github.com/065191065191/MCP-ServerAllInOne).

### Изменено

- В документации зафиксированы удалённый `origin`, публикация на GitHub и **тегирование** аннотированными тегами `vX.Y.Z` при появлении нового функционала, заметных улучшений или важных исправлений для пользователей.
- Версия пакета и теги образов по умолчанию — **0.2.2**.

## [0.2.1] — 2026-05-02

### Изменено

- Описание пакета в `pyproject.toml` (`description`) переведено на русский язык.
- Версия образов и тегов по умолчанию в `deploy/*` обновлена до **0.2.1** (согласовано с версией пакета).

### Исправлено

- Комментарий с примером тега в корневом `Dockerfile` приведён к версии **0.2.1** (ранее был устаревший номер).

## [0.2.0] — 2026-05-02

### Добавлено

- Учёт автора проекта в метаданных пакета (`pyproject.toml`).
- Файл `CHANGELOG.md` и описание процесса релизов (версии, журнал, коммиты).
- Синхронизация `sdocs_mcp.__version__` с версией пакета **0.2.0**.

### Прочее

- Базовая линия кода: MCP по HTTP, модули OpenSearch, Kafka, PostgreSQL, Redis, Prometheus, опциональный браузерный MCP (Playwright), UI и Docker-окружение — см. `README.md`.
