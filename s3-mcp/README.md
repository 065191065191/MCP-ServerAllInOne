# S3 MCP (`s3-mcp`)

Отдельный **MCP-сервер** для диагностики **Ceph / S3** (AWS Signature V4, только Python stdlib для S3-запросов).

Работает **рядом** с основным [`sdocs-mcp`](../README.md), на отдельном порту по умолчанию **8766**.

---

## Возможности

| Tool | Назначение |
|------|------------|
| `s3_mcp_status` | Конфигурация (без секретов) |
| `s3_list_buckets` | Список всех bucket |
| `s3_bucket_stats` | Объекты и размер bucket |
| `s3_bucket_latest_files` | Последние N файлов (метаданные) |
| `s3_write_test` | PUT 1MB → HEAD → DELETE |
| **`s3_object_metadata`** | **Проверка конкретного документа: есть/нет, размер, дата** (HEAD, без содержимого) |

---

## Переменные окружения

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `S3_ENDPOINT` | да | `https://host:port` или `http://...` |
| `S3_ACCESS_KEY` | да | Access key |
| `S3_SECRET_KEY` | да | Secret key |
| `S3_VERIFY_SSL` | нет | `true` — проверять TLS (по умолчанию `false` для Ceph) |
| `S3_MCP_HOST` | нет | `0.0.0.0` |
| `S3_MCP_PORT` | нет | `8766` |
| `S3_MCP_TRANSPORT` | нет | `streamable-http` (по умолчанию), `sse`, `stdio` |
| `S3_MCP_STATELESS_HTTP` | нет | `true` — stateless Streamable HTTP |

---

## Установка и запуск

Из корня репозитория:

```bash
pip install -e .
export S3_ENDPOINT="https://ceph.example.com"
export S3_ACCESS_KEY="..."
export S3_SECRET_KEY="..."
s3-mcp
```

MCP endpoint: `http://<host>:8766/mcp`

---

## Пример: проверка документа (curl)

```bash
BASE="http://localhost:8766/mcp/"
curl -sS -N -D /tmp/s3.head "$BASE" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
SID=$(grep -i '^mcp-session-id:' /tmp/s3.head | awk '{print $2}' | tr -d '\r')
curl -sS -N "$BASE" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Mcp-Session-Id: $SID" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
curl -sS -N "$BASE" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Mcp-Session-Id: $SID" -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"s3_object_metadata","arguments":{"bucket":"my-bucket","key":"path/to/document.pdf"}}}'
```

Ответ — только метаданные:

```json
{
  "exists": true,
  "bucket": "my-bucket",
  "key": "path/to/document.pdf",
  "size_bytes": 1048576,
  "size_human": "1.00 MB",
  "last_modified": "Mon, 08 Jun 2026 10:00:00 GMT",
  "etag": "abc123",
  "content_type": "application/pdf",
  "content_returned": false
}
```

---

## Cursor / Claude Desktop

```json
{
  "mcpServers": {
    "s3-mcp": {
      "url": "http://your-host:8766/mcp",
      "transport": "streamable-http"
    }
  }
}
```

---

## Подсказка для LLM

```
Используй MCP s3-mcp: сначала s3_mcp_status, затем s3_object_metadata(bucket, key)
для проверки документа (размер и дата, без содержимого).
```

---

## Документация

- [`docs/S3_MCP.md`](../docs/S3_MCP.md) — полное описание tools и архитектуры
- Исходный проверенный скрипт: `s3_checker` (AWS Sig V4, list/stats/write test)

---

## Версия

**0.7.0** — тег **`v0.7.0`** (общий с репозиторием, как `v0.6.14`)
