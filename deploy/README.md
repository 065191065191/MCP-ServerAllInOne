# Промышленная эксплуатация

**Закрытый контур / прокси-шлюз / сборка без интернета:** см. **[`docs/OFFLINE_AND_PROXY_INSTALL.md`](../docs/OFFLINE_AND_PROXY_INSTALL.md)**.

## Готовый образ (архив)

После локальной сборки в каталоге может лежать **`sdocs-mcp-ui-0.6.1.tar`** (`docker save`). Файл в `.gitignore` из‑за размера. Импорт на целевой машине:

```bash
docker load -i sdocs-mcp-ui-0.6.1.tar
# Один порт: UI + MCP Streamable HTTP на http://127.0.0.1:8888/mcp
docker run --rm -p 127.0.0.1:8888:8888 \
  -e SDOCS_MCP_CONFIG=/etc/sdocs-mcp/config.yaml \
  -e SDOCS_MCP_EMBED_MCP=true \
  -v /path/on/host/config.yaml:/etc/sdocs-mcp/config.yaml:ro \
  sdocs-mcp-ui:0.6.1
# Несколько реплик без sticky: добавьте -e SDOCS_MCP_STATELESS_HTTP=true

# Отдельный процесс только MCP (другой порт), без UI: переопределение CMD на sdocs-mcp
# (тот же образ, что и UI; в образе по умолчанию SDOCS_MCP_EMBED_MCP=true — для явности задайте false):
docker run --rm -p 127.0.0.1:8765:8765 \
  -e SDOCS_MCP_CONFIG=/etc/sdocs-mcp/config.yaml \
  -e SDOCS_MCP_EMBED_MCP=false \
  -e SDOCS_MCP_HOST=0.0.0.0 \
  -e SDOCS_MCP_PORT=8765 \
  -v /path/on/host/config.yaml:/etc/sdocs-mcp/config.yaml:ro \
  sdocs-mcp-ui:0.6.1 sdocs-mcp
```

Пересобрать архив из корня репозитория:

```bash
docker build -f deploy/Dockerfile -t sdocs-mcp-ui:0.6.1 .
docker save sdocs-mcp-ui:0.6.1 -o deploy/sdocs-mcp-ui-0.6.1.tar
```

## Состав

| Артефакт | Назначение |
|----------|------------|
| `Dockerfile` | Образ: **`sdocs-mcp-ui`** на **8888**; при **`SDOCS_MCP_EMBED_MCP=true`** MCP на том же порту, путь **`/mcp`**. |
| `Dockerfile.buildkit-proxy` | Тот же образ, сборка за **прокси с паролем** через BuildKit `--secret` (см. **`docs/OFFLINE_AND_PROXY_INSTALL.md`** §2.1.1). |
| `openshift/*.yaml` | Примеры Deployment/Service (при необходимости задайте свой image из реестра). |
| `docker-compose.prod.yml` | Один сервис, один проброшенный порт (UI + встроенный MCP). |
| `env.production.example` | Шаблон переменных окружения → скопировать в `deploy/.env`. |
| `config.production.example.yaml` | Шаблон YAML (секреты подставлять при деплое; `${VAR}` в файле не раскрывается). |
| `systemd/sdocs-mcp-ui.service` | Unit для UI. |
| `systemd/sdocs-mcp.service` | Unit для MCP по HTTP (`0.0.0.0:8765`). |

## Быстрый старт (Docker)

1. Подготовьте на хосте файл конфигурации (права `0640`, владелец root или отдельный пользователь).
2. `cp deploy/env.production.example deploy/.env` — задайте `SDOCS_MCP_CONFIG_HOST_PATH`, токены, `SDOCS_MCP_UI_BIND`.
3. `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env build`
4. `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d`
5. Проверка: `curl -fsS http://127.0.0.1:8888/health` и `curl -fsS http://127.0.0.1:8888/ready` (порт см. `.env`).

За reverse proxy включите `SDOCS_MCP_UI_TRUSTED_HOSTS` (список Host через запятую).

## Безопасность (минимум)

- Обязательные **`SDOCS_MCP_UI_TOKEN`** и секрет на **`/metrics`** в проде при доступе из сети (`SDOCS_MCP_METRICS_REQUIRE_TOKEN=true`).
- **`SDOCS_MCP_EMBED_MCP=true`**: MCP доступен на **`/mcp`** на том же порту, что UI — защищайте **весь** фронт (и `/mcp`) через reverse proxy, **`SDOCS_MCP_UI_TRUSTED_HOSTS`**, и/или **`SDOCS_MCP_MTLS_*`** (TLS + обязательный клиентский сертификат на uvicorn).
- При встроенном MCP держите **`SDOCS_MCP_UI_WORKERS=1`**, либо включите **`SDOCS_MCP_STATELESS_HTTP=true`** (stateless Streamable HTTP — без серверной привязки сессии; удобно при нескольких репликах или воркерах за балансировщиком без sticky).
- **`SDOCS_MCP_UI_ENABLE_INVOKE`** и **`SDOCS_MCP_UI_ENABLE_SEED`** оставьте `false`, если UI только для мониторинга.
- Секреты только в env / смонтированных файлах; в репозитории — только примеры без реальных паролей.
- **`modules.postgres.allowlisted_queries`**: SQL задаётся только в YAML администратором; клиенты передают лишь `query_id`.
- SSH-модуль: отдельный пользователь на хостах, без широкого `sudo`; см. встроенный `builtin_safety_filter` и `docs/CAPABILITIES.md`.
- Образ слушает `0.0.0.0` внутри контейнера; снаружи пробрасывайте **`127.0.0.1`** или сегмент доверенной сети.

## CI

В корне репозитория: `.github/workflows/ci.yml` — `ruff check` и `pytest`.
