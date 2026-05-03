# stack-mcp — обзор продукта (один слайд)

Модульный **MCP-сервер** для эксплуатации и диагностики: PostgreSQL, Redis, Kafka, Prometheus, OpenSearch (включая RAG), почта, SSH. Опционально **веб-UI** и встроенный MCP на одном порту.

## Схема потоков

```mermaid
flowchart TB
  subgraph clients[Клиенты]
    IDE[IDE / агент MCP]
    Browser[Браузер]
  end

  subgraph runtime[Процесс приложения]
    MCP[FastMCP tools]
    UI[FastAPI UI дашборд и API]
  end

  subgraph cfg[Конфигурация]
    YAML[STACK_MCP_CONFIG YAML]
    ENV[Переменные окружения]
  end

  subgraph backends[Внешние системы]
    PG[(PostgreSQL)]
    RD[(Redis)]
    KF[Kafka]
    PR[Prometheus]
    OS[OpenSearch]
    SMTP[SMTP / IMAP]
    SSHH[SSH хосты]
  end

  subgraph sidecar[Побочные записи]
    OSAudit[(OS: индекс tool_call_audit)]
    UIAudit[Файл UI JSONL]
  end

  IDE --> MCP
  Browser --> UI
  YAML --> runtime
  ENV --> runtime
  MCP --> PG
  MCP --> RD
  MCP --> KF
  MCP --> PR
  MCP --> OS
  MCP --> SMTP
  MCP --> SSHH
  MCP -.->|опционально| OSAudit
  UI -.->|опционально| UIAudit
```

## Модули: что ждёт, куда ходит, что пишет

| Модуль | Включение / вход | Что делает (кратко) | Куда пишет |
|--------|------------------|---------------------|------------|
| **Ядро** | всегда | `stack_mcp_status`, политика `ssh_command_policy` | только ответ MCP |
| **PostgreSQL** | `modules.postgres`, DSN, allowlist схем/БД; SQL в YAML для allowlisted | Диагностические SELECT + именованные запросы по `query_id` | нет (только чтение БД) |
| **Redis** | `modules.redis`, URL, лимиты | PING, INFO, GET/MGET/HGETALL, опц. SETEX, SCAN по allowlist | Redis при `redis_setex` |
| **Kafka** | `modules.kafka`, bootstrap, `topic_allowlist`, опц. produce/admin | list/describe/consume; produce/create при флагах | топики Kafka |
| **Prometheus** | `modules.prometheus`, `base_url`, auth | instant/range, targets, series, alerts… | опц. Kafka при `prometheus_export_instant_to_kafka` |
| **OpenSearch** | `modules.opensearch`, hosts, TLS, `allow_write` для мутаций | cluster/cat/search; RAG store/search/delete по политике | индексы OS; опц. **search_audit_log**; опц. **tool_call_audit** (журнал вызовов tools) |
| **Почта** | `modules.mail`, пароли через env | IMAP list/search/fetch; SMTP send | исходящие письма |
| **SSH** | `modules.ssh`, хосты и политика в конфиге | одна команда на хост после фильтров | stdout на удалённом хосте |
| **Веб-UI** | `stack-mcp-ui`, опц. `STACK_MCP_EMBED_MCP` | дашборд, `/api/*`, `/metrics` | опц. JSONL `STACK_MCP_UI_AUDIT_LOG_PATH` (в проде обычно `/app/data/logs/...`) |

## Аудит вызовов tools (OpenSearch)

Включается **`modules.opensearch.tool_call_audit`**. В индекс попадают классификация (10 фасетов), аргументы и результат с лимитами, **`caller_id`** / опц. IP, см. **[TOOL_CALL_AUDIT.md](TOOL_CALL_AUDIT.md)**.

## Транспорт MCP

| Режим | Где |
|--------|-----|
| Streamable HTTP / SSE | отдельный процесс `stack-mcp` или путь **`/mcp`** у UI |
| stdio | только при **`STACK_MCP_DEV_LOCAL=true`** |

Подробные таблицы tools: **[CAPABILITIES.md](CAPABILITIES.md)**.
