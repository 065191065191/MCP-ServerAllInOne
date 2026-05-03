# Журнал изменений

Формат основан на принципах [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Версии соответствуют [семантическому версионированию](https://semver.org/lang/ru/).

## [Unreleased]

### Изменено

- Проект переименован в **SDocsMCP**: пакет Python `sdocs_mcp`, дистрибутив и CLI `sdocs-mcp` / `sdocs-mcp-ui`, переменные окружения с префиксом **`SDOCS_MCP_`**, systemd/OpenShift-манифесты `sdocs-mcp*`, пользователь ОС/контейнера `sdocsmcp`.

### Добавлено

- **`docs/OFFLINE_AND_PROXY_INSTALL.md`**: сборка и установка в закрытом контуре, через корпоративный HTTP(S)-прокси, перенос `docker save` / wheelhouse; **`NO_PROXY`** для бэкендов; отдельно — доступ к данным через шлюз в `config.yaml`.
- **`deploy/Dockerfile.buildkit-proxy`**: пример сборки с **прокси Basic URL** через BuildKit `--secret` (без пароля в слоях образа); §2.1.1 в офлайн-доке; **`build-proxy.url`** в `.gitignore`.
- **`README.md`**: оглавление, блок «слайд» (`PRODUCT_OVERVIEW` + executive one-pager + Canvas), таблица документации, прокси/секреты при `docker build`, упорядоченная структура.
- **`docs/EXECUTIVE_ONEPAGER.html`**: автономная визуальная витрина для совета / ТОП (браузер, без внешних картинок; SVG и сценарий на странице).
- **`docs/EXECUTIVE_ONEPAGER.md`**: текстовый сценарий показа, тайминг и структура того же one-pager.

### Удалено

- **`docs/PRODUCT_OVERVIEW.html`**, **`docs/PRODUCT_OVERVIEW_SPEAKER_NOTES.html`**: дублировали материал; витрина и сценарий сведены в **`EXECUTIVE_ONEPAGER.*`**.

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
