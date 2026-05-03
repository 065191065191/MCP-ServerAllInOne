# Промышленная эксплуатация

**Закрытый контур / прокси-шлюз / сборка без интернета:** см. **[`docs/OFFLINE_AND_PROXY_INSTALL.md`](../docs/OFFLINE_AND_PROXY_INSTALL.md)**.

## Готовый образ (архив)

После локальной сборки в каталоге может лежать **`stack-mcp-ui-0.3.2.tar`** (`docker save`). Файл в `.gitignore` из‑за размера. Импорт на целевой машине:

```bash
docker load -i stack-mcp-ui-0.3.2.tar
# Один порт: UI + MCP Streamable HTTP на http://127.0.0.1:8888/mcp
docker run --rm -p 127.0.0.1:8888:8888 \
  -e STACK_MCP_CONFIG=/etc/stack-mcp/config.yaml \
  -e STACK_MCP_EMBED_MCP=true \
  -v /path/on/host/config.yaml:/etc/stack-mcp/config.yaml:ro \
  stack-mcp-ui:0.3.2
# Несколько реплик без sticky: добавьте -e STACK_MCP_STATELESS_HTTP=true

# Отдельный процесс только MCP (другой порт), без UI — при STACK_MCP_EMBED_MCP=false:
docker run --rm -p 127.0.0.1:8765:8765 \
  -e STACK_MCP_CONFIG=/etc/stack-mcp/config.yaml \
  -e STACK_MCP_HOST=0.0.0.0 \
  -e STACK_MCP_PORT=8765 \
  -v /path/on/host/config.yaml:/etc/stack-mcp/config.yaml:ro \
  stack-mcp-ui:0.3.2 stack-mcp
```

Пересобрать архив из корня репозитория:

```bash
docker build -f deploy/Dockerfile -t stack-mcp-ui:0.3.2 .
docker save stack-mcp-ui:0.3.2 -o deploy/stack-mcp-ui-0.3.2.tar
```

## Состав

| Артефакт | Назначение |
|----------|------------|
| `Dockerfile` | Образ: **`stack-mcp-ui`** на **8888**; при **`STACK_MCP_EMBED_MCP=true`** MCP на том же порту, путь **`/mcp`**. |
| `Dockerfile.buildkit-proxy` | Тот же образ, сборка за **прокси с паролем** через BuildKit `--secret` (см. **`docs/OFFLINE_AND_PROXY_INSTALL.md`** §2.1.1). |
| `openshift/*.yaml` | Примеры Deployment/Service (при необходимости задайте свой image из реестра). |
| `docker-compose.prod.yml` | Один сервис, один проброшенный порт (UI + встроенный MCP). |
| `env.production.example` | Шаблон переменных окружения → скопировать в `deploy/.env`. |
| `config.production.example.yaml` | Шаблон YAML (секреты подставлять при деплое; `${VAR}` в файле не раскрывается). |
| `systemd/stack-mcp-ui.service` | Unit для UI. |
| `systemd/stack-mcp.service` | Unit для MCP по HTTP (`0.0.0.0:8765`). |

## Быстрый старт (Docker)

1. Подготовьте на хосте файл конфигурации (права `0640`, владелец root или отдельный пользователь).
2. `cp deploy/env.production.example deploy/.env` — задайте `STACK_MCP_CONFIG_HOST_PATH`, токены, `STACK_MCP_UI_BIND`.
3. `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env build`
4. `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d`
5. Проверка: `curl -fsS http://127.0.0.1:8888/health` и `curl -fsS http://127.0.0.1:8888/ready` (порт см. `.env`).

За reverse proxy включите `STACK_MCP_UI_TRUSTED_HOSTS` (список Host через запятую).

## Безопасность (минимум)

- Обязательные **`STACK_MCP_UI_TOKEN`** и секрет на **`/metrics`** в проде при доступе из сети (`STACK_MCP_METRICS_REQUIRE_TOKEN=true`).
- **`STACK_MCP_EMBED_MCP=true`**: MCP доступен на **`/mcp`** на том же порту, что UI — защищайте **весь** фронт (и `/mcp`) через reverse proxy, **`STACK_MCP_UI_TRUSTED_HOSTS`**, и/или **`STACK_MCP_MTLS_*`** (TLS + обязательный клиентский сертификат на uvicorn).
- При встроенном MCP держите **`STACK_MCP_UI_WORKERS=1`**, либо включите **`STACK_MCP_STATELESS_HTTP=true`** (stateless Streamable HTTP — без серверной привязки сессии; удобно при нескольких репликах или воркерах за балансировщиком без sticky).
- **`STACK_MCP_UI_ENABLE_INVOKE`** и **`STACK_MCP_UI_ENABLE_SEED`** оставьте `false`, если UI только для мониторинга.
- Секреты только в env / смонтированных файлах; в репозитории — только примеры без реальных паролей.
- **`modules.postgres.allowlisted_queries`**: SQL задаётся только в YAML администратором; клиенты передают лишь `query_id`.
- SSH-модуль: отдельный пользователь на хостах, без широкого `sudo`; см. встроенный `builtin_safety_filter` и `docs/CAPABILITIES.md`.
- Образ слушает `0.0.0.0` внутри контейнера; снаружи пробрасывайте **`127.0.0.1`** или сегмент доверенной сети.

## CI

В корне репозитория: `.github/workflows/ci.yml` — `ruff check` и `pytest`.
