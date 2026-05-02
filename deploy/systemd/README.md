# Systemd

- **`stack-mcp-ui.service`** — веб-UI, `/health`, `/ready`, `/metrics`. Создайте пользователя `stackmcp`, каталоги `/opt/stack-mcp` (venv + код), `/etc/stack-mcp/` (config + `ui.env`), логи в `/var/log/stack-mcp`.
- **`stack-mcp.service`** — процесс **`stack-mcp`**, Streamable HTTP на **`/mcp`**, порт **8765**.
- **MCP (`stack-mcp`)** — **HTTP** (`streamable-http`, порт **8765**, путь **`/mcp`**), хост по умолчанию `0.0.0.0`. Localhost без `STACK_MCP_DEV_LOCAL=true` запрещён. Пример: `STACK_MCP_CONFIG=/etc/stack-mcp/config.yaml /opt/stack-mcp/.venv/bin/stack-mcp`.
- При нескольких воркерах UI или репликах за балансировщиком без sticky добавьте в `ui.env` / `mcp.env`: `STACK_MCP_STATELESS_HTTP=true` (см. корневой `README.md`).
