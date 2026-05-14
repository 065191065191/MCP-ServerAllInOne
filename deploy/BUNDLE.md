# Готовый комплект `sdocs-mcp` (релиз 0.6.1)

## Что входит

| Путь | Назначение |
|------|------------|
| `src/` | Код MCP (HTTP), UI, модули БД/SSH. |
| `deploy/Dockerfile` | Образ `sdocs-mcp-ui:0.6.1`: `sdocs-mcp-ui`, `sdocs-mcp`. |
| `deploy/docker-compose.prod.yml` | UI + MCP, bind-mount конфига. |
| `deploy/docker-compose.prod.ssh-extra.yml` | Override: большой список SSH из второго YAML. |
| `deploy/env.production.example` → `.env` | Переменные окружения. |
| `deploy/config.production.example.yaml` | Шаблон основного конфига. |
| `deploy/examples/` | Пример CSV, фрагмент SSH, инвентарь. |
| `scripts/generate_ssh_hosts_yaml.py` | CSV → YAML для сотен SSH-хостов. |
| `docs/SSH_SCALE.md` | Масштаб SSH, `SDOCS_MCP_SSH_HOSTS_FILE`. |
| `docs/CAPABILITIES.md` | Матрица tools и лимитов. |
| `deploy/systemd/` | Units для Linux без Docker. |

## Сборка образа и архива

Из корня репозитория (`E:\git\mcp-server` или клон):

```bash
docker build -f deploy/Dockerfile -t sdocs-mcp-ui:0.6.1 .
docker save sdocs-mcp-ui:0.6.1 -o deploy/sdocs-mcp-ui-0.6.1.tar
```

На целевой машине: `docker load -i deploy/sdocs-mcp-ui-0.6.1.tar`.

## Сотни SSH-серверов

1. В основном конфиге — `modules.ssh.default_private_key_path` и при необходимости несколько хостов.
2. Сгенерируйте остальное:  
   `python scripts/generate_ssh_hosts_yaml.py inventory.csv -o ssh_hosts_extra.yaml`
3. Укажите **`SDOCS_MCP_SSH_HOSTS_FILE`** на абсолютный путь к этому файлу (на хосте или в контейнере + volume из `docker-compose.prod.ssh-extra.yml`).

Подробнее: **`docs/SSH_SCALE.md`**.
