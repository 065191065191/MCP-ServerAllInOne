# SDocsMCP — быстрый старт в контуре

Что внутри архива:

```
config.example.yaml                 ← минимальный YAML, скопировать и заполнить
deploy/                             ← Compose, OpenShift, systemd, Dockerfiles, env-пример
docs/                               ← обзор продукта, офлайн-установка, аудит, capabilities
src/sdocs_mcp/                      ← исходники Python-пакета (для пересборки образа)
Dockerfile                          ← shortcut: то же, что deploy/Dockerfile
docker-compose.yml                  ← демо-стенд (Postgres/Redis/Kafka/OpenSearch)
pyproject.toml                      ← дистрибутив sdocs-mcp 0.6.1
README.md, CHANGELOG.md
```

## 1. Образ

На машине-сборщике (с интернетом или с wheelhouse, см. `docs/OFFLINE_AND_PROXY_INSTALL.md`):

```bash
docker build -f deploy/Dockerfile -t sdocs-mcp-ui:0.6.1 .
docker save sdocs-mcp-ui:0.6.1 -o sdocs-mcp-ui-0.6.1.tar
```

На целевой машине:

```bash
docker load -i sdocs-mcp-ui-0.6.1.tar
```

## 2. Конфигурация

1. `cp config.example.yaml /etc/sdocs-mcp/config.yaml`
2. Откройте файл и подставьте реальные хосты/логины/пароли. Поля `*_env` берут значение из переменной окружения — пароли не обязаны лежать в YAML.

## 3. Docker / Docker Compose

1. `cp deploy/env.production.example deploy/.env`
2. В `deploy/.env` задайте `SDOCS_MCP_CONFIG_HOST_PATH`, `SDOCS_MCP_UI_TOKEN`, `SDOCS_MCP_METRICS_TOKEN`,
   при необходимости `SDOCS_MCP_STATELESS_HTTP=true`.
3. Запуск:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d
```

URL: UI `http://<host>:8888/`, MCP `http://<host>:8888/mcp`, метрики `/metrics`, проба `/health` и `/ready`.

## 4. OpenShift / Kubernetes

1. Замените `image:` в `deploy/openshift/sdocs-mcp-ui.deployment.yaml` на адрес из вашего реестра.
2. Положите содержимое `config.example.yaml` (с реальными значениями) в `ConfigMap sdocs-mcp-config` (ключ `config.yaml`); если в нём пароли — используйте `Secret` вместо ConfigMap.
3. Токены и пароли почты — отдельным `Secret sdocs-mcp-ui-env`, в Deployment добавьте `envFrom: - secretRef: name: sdocs-mcp-ui-env`.
4. Применить:

```bash
oc apply -f deploy/openshift/sdocs-mcp-ui.deployment.yaml
oc apply -f deploy/openshift/sdocs-mcp.deployment.yaml   # если нужен отдельный процесс MCP
```

Пробы заданы в манифесте: `startupProbe → /health`, `readinessProbe → /ready`, `livenessProbe → /health`.

## 5. Минимальные переменные процесса

| Переменная | Значение | Зачем |
|---|---|---|
| `SDOCS_MCP_CONFIG` | `/etc/sdocs-mcp/config.yaml` | путь к YAML внутри контейнера |
| `SDOCS_MCP_EMBED_MCP` | `true` | UI + MCP на одном порту (`/mcp`) |
| `SDOCS_MCP_UI_TOKEN` | случайная строка | Bearer на `/api/*` |
| `SDOCS_MCP_METRICS_TOKEN` | случайная строка | Bearer на `/metrics` |
| `SDOCS_MCP_METRICS_REQUIRE_TOKEN` | `true` | не отдавать метрики анонимно |
| `SDOCS_MCP_STATELESS_HTTP` | `true` (если `replicas > 1` или `UI_WORKERS > 1`) | без sticky-сессий |
| `SDOCS_MCP_UI_AUDIT_LOG_PATH` | `/app/data/logs/ui-audit.log` | журнал событий UI |

Полный набор и пояснения — `deploy/env.production.example`.

## 6. Закрытый контур / прокси-шлюз

См. `docs/OFFLINE_AND_PROXY_INSTALL.md`:

- сборка через `deploy/Dockerfile.buildkit-proxy` с `--secret id=build_proxy` (пароль прокси не попадает в слои образа);
- перенос образа `docker save` / `docker load`;
- `NO_PROXY` для внутренних бэкендов.

## 7. Что проверить после старта

```bash
curl -fsS http://<host>:8888/health
curl -fsS http://<host>:8888/ready
curl -fsS -H "Authorization: Bearer $SDOCS_MCP_METRICS_TOKEN" http://<host>:8888/metrics | head
```

Готово.
