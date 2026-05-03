# SSH: много хостов (десятки / сотни)

## Лимиты

- В одном процессе `sdocs-mcp` список хостов хранится в памяти; **100–300** записей — обычно нормально. `ssh_hosts_overview` отдаёт полный список (без пагинации).
- При **очень больших** инвентарях разбейте парк на несколько инстансов MCP (разные конфиги / разные `SDOCS_MCP_CONFIG`).

## Два способа задать хосты

1. **Один YAML** — секция `modules.ssh.hosts` со всеми серверами.
2. **Базовый конфиг + фрагмент** — в основном файле общие настройки SSH и, при необходимости, часть хостов; полный список дополняется файлом из переменной **`SDOCS_MCP_SSH_HOSTS_FILE`** (YAML: массив объектов или `{ hosts: [ ... ] }`). Записи **дописываются** к `hosts` из основного конфига.

## Генерация из CSV

```bash
python scripts/generate_ssh_hosts_yaml.py deploy/examples/ssh_inventory.csv -o /etc/sdocs-mcp/ssh_hosts.yaml
export SDOCS_MCP_SSH_HOSTS_FILE=/etc/sdocs-mcp/ssh_hosts.yaml
```

Колонки CSV: `id`, `hostname`, `username`, опционально `port` (по умолчанию 22), `auth` (`key` или `password`), `private_key_path`, `password_env`, `description`.

При **`auth=key`** и пустом `private_key_path` на хосте используется **`modules.ssh.default_private_key_path`** из основного конфига.

## Docker

Смонтируйте второй файл и передайте переменную (см. `deploy/docker-compose.prod.yml` и `deploy/env.production.example`).
