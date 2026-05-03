# Аудит вызовов MCP tools в OpenSearch

## Зачем усечение `arguments_json` / `result_text`

Это **не** лимит самого OpenSearch: кластер по умолчанию принимает большие HTTP-тела (ограничение задаётся `http.max_content_length` и т.п.). Усечение делается **в приложении stack-mcp**, чтобы:

- не отправить по сети десятки мегабайт из одного ответа tool по ошибке;
- предсказуемо держать размер документа.

Пороги задаются в YAML: `tool_call_audit.max_arguments_json_chars` и `max_result_chars` (см. `config.example.yaml`). Верхняя граница в валидаторе конфига — до **10M** и **20M** символов соответственно; при необходимости поднимайте в пределах этих значений.

**Смена mapping:** поле `schema_version` в документе и в коде (`tool_audit_opensearch.py`). Если индекс уже создан со старым `strict` mapping, новые поля не примутся — создайте новый индекс (другое имя в `tool_call_audit.index`) или удалите старый и дайте `auto_create_index: true` создать заново.

---

## Кто сделал вызов (`caller_id`)

Протокол MCP **не передаёт** учётную запись конечного пользователя. Идентификатор вызывающей стороны собирается так:

1. **HTTP (встроенный MCP на `/mcp` или отдельный `stack-mcp` на streamable-http/SSE):** если в конфиге задано **`tool_call_audit.caller_http_header`** (например `X-Audit-Caller`), берётся значение этого заголовка. Его должен проставить **reverse proxy** (после OIDC/LDAP) или клиент, если политика это допускает.
2. Иначе **`STACK_MCP_AUDIT_CALLER_ID`** в окружении процесса.
3. Иначе **`tool_call_audit.default_caller_id`** из YAML.
4. Иначе в документ пишется **`unknown`**.

Опционально **`tool_call_audit.log_http_client_ip: true`** — в поле **`caller_client_ip`** попадает адрес из ASGI `scope["client"]` (часто это IP **последнего** TCP-узла, т.е. прокси; реальный клиент обычно в `X-Forwarded-For` на прокси — MCP его сам не разбирает).

**stdio:** middleware нет — используются только пункты 2–4 (типично один процесс MCP на пользователя/воркспейс и свой `STACK_MCP_AUDIT_CALLER_ID` при запуске).

---

## Десять признаков классификации (фасеты)


| #   | Поле в OpenSearch    | Смысл                                                                                                    |
| --- | -------------------- | -------------------------------------------------------------------------------------------------------- |
| 1   | `module`             | Семья бэкенда: `postgres`, `redis`, `kafka`, `mail`, `prometheus`, `opensearch`, `ssh`, `core`, `other`. |
| 2   | `category`           | `meta` (статус), `data_plane` (обычные tools), `rag` (имя содержит `opensearch_rag`).                    |
| 3   | `operation_kind`     | `read` | `write` | `admin` (по белым спискам имён tools в коде).                                         |
| 4   | `tool_family`        | Первый сегмент имени до `_` (`postgres` из `postgres_ping`) или `meta` для `stack_mcp_status`.           |
| 5   | `risk_tier`          | `low` | `medium` | `high` — эвристика: SSH, удаление индекса, Kafka produce/admin, SMTP → выше риск.     |
| 6   | `api_surface`        | Сейчас всегда `mcp_tool` (зарезервировано под другие входы).                                             |
| 7   | `rag_lane`           | `true`, если в имени tool есть подстрока `opensearch_rag`.                                               |
| 8   | `mutating`           | `true`, если `operation_kind` — `write` или `admin`.                                                     |
| 9   | `argument_key_count` | Число ключей в объекте аргументов вызова.                                                                |
| 10  | `duration_bucket`    | Корзина длительности: `lt_50ms`, `50ms_200ms`, `200ms_1s`, `1s_10s`, `gte_10s`.                          |


ML-классификации нет — только детерминированные правила по имени tool и метаданным вызова.

---

## Mapping индекса (`strict`)

При `auto_create_index: true` создаётся индекс с таким телом (см. `default_tool_audit_index_body()` в `tool_audit_opensearch.py`):

```json
{
  "settings": { "index": { "number_of_shards": 1, "number_of_replicas": 0 } },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "schema_version": { "type": "integer" },
      "ingested_at": { "type": "date" },
      "instance_id": { "type": "keyword" },
      "caller_id": { "type": "keyword" },
      "caller_client_ip": { "type": "keyword" },
      "tool_name": { "type": "keyword" },
      "module": { "type": "keyword" },
      "category": { "type": "keyword" },
      "operation_kind": { "type": "keyword" },
      "tool_family": { "type": "keyword" },
      "risk_tier": { "type": "keyword" },
      "api_surface": { "type": "keyword" },
      "rag_lane": { "type": "boolean" },
      "mutating": { "type": "boolean" },
      "argument_key_count": { "type": "integer" },
      "duration_bucket": { "type": "keyword" },
      "ok": { "type": "boolean" },
      "duration_ms": { "type": "float" },
      "error": { "type": "text", "index": false },
      "arguments_json": { "type": "text", "index": false },
      "arguments_truncated": { "type": "boolean" },
      "result_text": { "type": "text", "index": false },
      "result_truncated": { "type": "boolean" },
      "result_chars": { "type": "integer" }
    }
  }
}
```

Поля `arguments_json` и `result_text` **не индексируются** (`index: false`) — они для хранения и выгрузки, не для полнотекстового поиска по журналу.