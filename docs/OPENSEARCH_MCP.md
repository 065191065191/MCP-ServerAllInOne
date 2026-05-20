# OpenSearch в SDocsMCP

## Что настроить в `mcp.conf`

```yaml
modules:
  opensearch:
    enabled: true
    hosts:
      - https://opensearch.internal:9200
    use_ssl: true
    verify_certs: true
    username: sdocs_mcp
    password_env: OPENSEARCH_PASSWORD   # или password: "..."
```

Без `enabled: true` tools OpenSearch недоступны (серый статус в Alert UI).

## Имена индексов

- В tools передаётся **точное имя индекса**, например `ms-logs`, `ms-eda-2025.05`, не «произвольный текст».
- Список индексов: tool **`opensearch_list_indices`** с `pattern` (например `ms-*`).
- Глобального `index_allowlist` для поиска **нет** — доступ ограничивается учёткой OpenSearch и сетью.

## Вызов tools (важно для LLM)

| Tool | Параметры |
|------|-----------|
| `opensearch_search` | **`index`** — строка; **`query_json`** — JSON DSL (не `query`) |
| `opensearch_count` | `index`, опционально `query_json` |
| `opensearch_cluster_health` | без аргументов |
| `opensearch_list_indices` | `pattern` (по умолчанию `*`) |

Пример `opensearch_search`:

```json
{
  "index": "ms-logs",
  "query_json": "{\"query\":{\"bool\":{\"must\":[{\"term\":{\"level\":\"ERROR\"}}]}},\"size\":10}"
}
```

Минимальный запрос:

```json
{"index": "ms-logs", "query_json": "{\"query\":{\"match_all\":{}},\"size\":5}"}
```

## Alert UI (источник OpenSearch)

В поле **параметры** правила:

```text
index ms-logs; query level:ERROR AND message:*404*
```

- `index` — имя индекса с логами;
- `query` — строка Query DSL / Lucene (как в OpenSearch Dashboards).

Порог и окно задаются в форме (threshold, window_hours).

## RAG (отдельно)

Долговременная память агента — подсекция **`opensearch.rag`** с **`index_allowlist`** (другие индексы, не смешивать с логами без необходимости).

## Нужно ли что-то ещё?

| Задача | Действие |
|--------|----------|
| Просто искать в логах | `enabled` + hosts + учётка; вызывать `opensearch_list_indices` → `opensearch_search` |
| Алерт по ERROR | Правило Alert, `mcp_source: opensearch`, параметры `index …; query …` |
| RAG память | Включить `opensearch.rag` + свой `index_allowlist` |
