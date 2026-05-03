# Systemd

- **`sdocs-mcp-ui.service`** — веб-UI, `/health`, `/ready`, `/metrics`. Создайте пользователя `sdocsmcp`, каталоги `/opt/sdocs-mcp` (venv + код), `/etc/sdocs-mcp/` (config + `ui.env`), логи в `/var/log/sdocs-mcp`.
- **`sdocs-mcp.service`** — процесс **`sdocs-mcp`**, Streamable HTTP на **`/mcp`**, порт **8765**.
- **MCP (`sdocs-mcp`)** — **HTTP** (`streamable-http`, порт **8765**, путь **`/mcp`**), хост по умолчанию `0.0.0.0`. Localhost без `SDOCS_MCP_DEV_LOCAL=true` запрещён. Пример: `SDOCS_MCP_CONFIG=/etc/sdocs-mcp/config.yaml /opt/sdocs-mcp/.venv/bin/sdocs-mcp`.
- При нескольких воркерах UI или репликах за балансировщиком без sticky добавьте в `ui.env` / `mcp.env`: `SDOCS_MCP_STATELESS_HTTP=true` (см. корневой `README.md`).
