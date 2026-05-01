# Промышленная эксплуатация

## Готовый образ (архив)

После локальной сборки в каталоге может лежать **`stack-mcp-ui-0.2.2.tar`** (`docker save`). Файл в `.gitignore` из‑за размера. Импорт на целевой машине:

```bash
docker load -i stack-mcp-ui-0.2.2.tar
# затем, например:
docker run --rm -p 127.0.0.1:8888:8888 \
  -e STACK_MCP_CONFIG=/etc/stack-mcp/config.yaml \
  -v /path/on/host/config.yaml:/etc/stack-mcp/config.yaml:ro \
  stack-mcp-ui:0.2.2

# Отдельно MCP по HTTP (Streamable HTTP на /mcp):
docker run --rm -p 127.0.0.1:8765:8765 \
  -e STACK_MCP_CONFIG=/etc/stack-mcp/config.yaml \
  -e STACK_MCP_HOST=0.0.0.0 \
  -e STACK_MCP_PORT=8765 \
  -v /path/on/host/config.yaml:/etc/stack-mcp/config.yaml:ro \
  stack-mcp-ui:0.2.2 stack-mcp
```

Пересобрать архив из корня репозитория:

```bash
docker build -f deploy/Dockerfile -t stack-mcp-ui:0.2.2 .
docker save stack-mcp-ui:0.2.2 -o deploy/stack-mcp-ui-0.2.2.tar
```

## Состав

| Артефакт | Назначение |
|----------|------------|
| `Dockerfile` | Образ с **`stack-mcp-ui`** (8888) и **`stack-mcp`** по HTTP (8765, `/mcp`). |
| `docker-compose.prod.yml` | Пример: bind-mount конфига с хоста, том под audit-логи, порты только на localhost. |
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
- **`STACK_MCP_UI_ENABLE_INVOKE`** и **`STACK_MCP_UI_ENABLE_SEED`** оставьте `false`, если UI только для мониторинга.
- SSH-модуль: отдельный пользователь на хостах, без широкого `sudo`; см. встроенный `builtin_safety_filter` и `docs/CAPABILITIES.md`.
- Образ слушает `0.0.0.0` внутри контейнера; снаружи пробрасывайте **`127.0.0.1`** или сегмент доверенной сети.

## CI

В корне репозитория: `.github/workflows/ci.yml` — `ruff check` и `pytest`.
