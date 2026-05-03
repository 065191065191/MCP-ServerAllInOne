# Возможности и лимиты

Общие правила:

- Процесс **`stack-mcp`**: транспорт по умолчанию **Streamable HTTP** (`/mcp`, порт **8765**, слушатель **0.0.0.0**). Альтернатива — **SSE**. **stdio** и привязка к localhost без **`STACK_MCP_DEV_LOCAL=true`** отключены (см. README).
- Секреты: в YAML и/или через имена переменных окружения (`*_env`, `password_env` у OpenSearch и почты); значения секретов в ответы tools не попадают.
- Каждый бэкенд регистрирует инструменты **только если** `modules.<name>.enabled: true`.

## Всегда доступно

| Tool | Описание |
|------|----------|
| `stack_mcp_status` | JSON с флагами включённых модулей. |
| `ssh_command_policy` | JSON: политика `ssh_run_command` — `forbidden_substrings`, **`merge_recommended_substring_blocklist`**, `forbidden_regex`, `allow_shell_operators`, `builtin_safety_filter`, лимит длины, правила на shell-операторы и список встроенных regex (`ssh_tools._BUILTIN_SAFETY`), если встроенный фильтр включён. |

## PostgreSQL (`modules.postgres`)

Встроенные **SELECT**-сценарии (фиксированный код в репозитории). Отдельно — **именованные запросы из конфига** (`allowlisted_queries`): произвольный текст SQL задаётся **только в YAML** администратором; MCP-клиенты и крон передают лишь **`query_id`**, не строку SQL.

| Tool | Назначение |
|------|------------|
| `postgres_connections_overview` | Сводка `pg_stat_activity` по `state` + total. |
| `postgres_long_running_queries` | Топ-N активных запросов, превью до 200 символов. |
| `postgres_blocking_chains` | Кто кого блокирует (лимит 50 строк). |
| `postgres_database_sizes` | Топ БД по размеру. |
| `postgres_table_sizes` | Топ таблиц в `schema_allowlist`. |
| `postgres_index_usage` | Индексы с низким `idx_scan` (кандидаты на разбор). |
| `postgres_cache_hit_ratio` | Буферный hit ratio по `pg_statio_user_tables`. |
| `postgres_replication_lag` | `pg_stat_replication` или сообщение об отсутствии реплик. |
| `postgres_autovacuum_health` | Мёртвые строки / метки autovacuum. |
| `postgres_statements_top` | Топ по `pg_stat_statements` (если расширение есть). |
| `postgres_allowlisted_query_catalog` | Только если `allowlisted_queries` не пуст: JSON со списком `id`, `description`, `max_rows` (**без** текста SQL). |
| `postgres_allowlisted_query` | Только если allowlist не пуст: выполнить запрос по `query_id`; выдача ограничена `max_rows` на запись + флаг `truncated`. |

Правила для записей `allowlisted_queries`: один оператор; только **SELECT** или **WITH …** (read-only); запрещены DML/DDL и ключевое слово **INTO**; размер текста SQL ограничен; `id` — `[a-zA-Z][-a-zA-Z0-9_]*`; дубликаты `id` недопустимы.

Лимиты конфигурации: `statement_timeout_seconds`, `long_query_limit`, `top_n_tables`, список `schema_allowlist`, опционально ограничение имени БД из DSN: **`allowed_databases`**, **`allowed_database_prefixes`** или **`allowed_database_regex`** (см. валидатор в `config.py`).

## Redis (`modules.redis`)

Подключение по `redis://` / `rediss://` через встроенный **RESP2**-клиент (отдельный PyPI-пакет `redis` не используется). Опциональный клиентский mTLS — как в README (`rediss://` + `mtls_*`).

| Tool | Назначение |
|------|------------|
| `redis_ping` | `PING`. |
| `redis_info` | Секции INFO: server, memory, stats, replication, cpu, commandstats. |
| `redis_memory_stats` | `MEMORY STATS` (если поддерживается). |
| `redis_dbsize` | `DBSIZE`. |
| `redis_slowlog_get` | `SLOWLOG GET` до `slowlog_max_entries`. |
| `redis_get` | `GET` одного ключа; обрезка значения по `get_max_value_bytes`. |
| `redis_mget` | До `mget_max_keys` ключей. |
| `redis_hgetall` | Hash с лимитами полей и суммарного размера. |
| `redis_setex` | `SETEX` с ограничениями на TTL и размер значения (для сидов/диагностики). |
| `redis_scan_prefix` | Только если `scan_enabled: true` и `prefix` начинается с одного из `scan_prefix_allowlist`; `SCAN` с `scan_max_iterations` и `scan_count`. |

Иные write-команды, `KEYS`, `EVAL`, админ-команды через общий интерфейс недоступны.

## Kafka (`modules.kafka`)

Требуется непустой `topic_allowlist`. Любой `topic` в tool должен входить в allowlist.

| Tool | Назначение |
|------|------------|
| `kafka_list_topics` | Список топиков кластера, обрезка `list_topics_max`. |
| `kafka_describe_topic` | Множество partition id для топика. |
| `kafka_consume_recent` | До `consume_max_messages` сообщений с **одной** партиции, «хвост» оффсета; стоп по `consume_max_bytes` или таймауту poll. |
| `kafka_produce` | Только если `allow_produce: true`; batch ≤ `produce_max_messages`, размер значения ≤ `produce_max_message_bytes`. |
| `kafka_create_topic` | Только если `allow_admin: true`. |

## Prometheus (`modules.prometheus`)

Доступ к **HTTP API** Prometheus (`base_url`, опционально Bearer из `bearer_token` / `bearer_token_path` или Basic auth). Ответы instant/range и список series обрезаются по лимитам конфига; широкие range-запросы могут автоматически увеличивать `step` до `max_step_points`.

| Tool | Назначение |
|------|------------|
| `prometheus_query_instant` | `/api/v1/query` (мгновенный вектор). |
| `prometheus_query_range` | `/api/v1/query_range` (матрица во времени). |
| `prometheus_targets` | `/api/v1/targets` (скрейп-таргеты). |
| `prometheus_metadata` | `/api/v1/metadata`. |
| `prometheus_series` | `/api/v1/series` (`match_queries` = список селекторов `match[]`). |
| `prometheus_labels` | `/api/v1/labels`. |
| `prometheus_rules` | `/api/v1/rules`. |
| `prometheus_alerts` | `/api/v1/alerts`. |
| `prometheus_export_instant_to_kafka` | Только если включён **Kafka** с `allow_produce: true`: выполняет instant query и публикует JSON-конверт в топик из аргумента `topic` или `prometheus.kafka_metrics_topic`; имя топика должно быть в `kafka.topic_allowlist`. |

## Почта (`modules.mail`)

Включение: `modules.mail.enabled: true` и непустой `imap_password_env` (имя переменной окружения с паролем IMAP). Опционально `imap_username` или `imap_username_env`; для SMTP при необходимости — `smtp_username_env` / `smtp_password_env` (если пароль SMTP не задан отдельно, используется IMAP-пароль). Отправитель: `default_from_env` или IMAP/SMTP-пользователь.

| Tool | Назначение |
|------|------------|
| `mail_imap_list_mailboxes` | `LIST` ящиков (с лимитом). |
| `mail_imap_search` | `SEARCH` по ящику (по умолчанию только `UNSEEN`), UID с потолком. |
| `mail_imap_fetch_rfc822` | `FETCH` тела по UID (превью обрезается `fetch_max_bytes`). |
| `mail_smtp_send` | Отправка письма (SMTP с `smtp_ssl` или `STARTTLS`). |

## SSH (`modules.ssh`)

| Tool | Назначение |
|------|------------|
| `ssh_command_policy` | Всегда зарегистрирован: политика блокировок для `ssh_run_command` (см. таблицу «Всегда доступно»). |
| `ssh_hosts_overview` | Список хостов из конфига (без секретов). Только если `modules.ssh.enabled`. |
| `ssh_run_command` | Одна команда на хост после проверок `forbidden_*` и shell-правил. Только если `modules.ssh.enabled`. |

## OpenSearch (`modules.opensearch`)

Опционально **`modules.opensearch.tool_call_audit`**: каждый вызов MCP tool в индекс (10 признаков, **`caller_id`** / опционально IP, аргументы и ответ с лимитами, `duration_ms`, ошибка). Кто вызвал: заголовок **`caller_http_header`**, либо **`STACK_MCP_AUDIT_CALLER_ID`**, либо **`default_caller_id`**. Подробности: **[`docs/TOOL_CALL_AUDIT.md`](TOOL_CALL_AUDIT.md)**.


Аутентификация: `username` + `password` в YAML или, если задано `password_env`, пароль только из `os.environ[password_env]`.

| Tool | Назначение |
|------|------------|
| `opensearch_cluster_health` | Health кластера. |
| `opensearch_cluster_health_debug` | Расширенный health: shard-level health + pending tasks + cat shards. |
| `opensearch_cluster_stats` | Статистика кластера (индексы, документы, нагрузка, ноды). |
| `opensearch_nodes_stats` | Метрики нод: OS/JVM/process/fs/indices/thread_pool/http/transport. |
| `opensearch_pending_tasks` | Очередь pending cluster tasks. |
| `opensearch_cluster_settings` | Cluster settings (persistent/transient/defaults). |
| `opensearch_cat_shards` | Таблица шардов: state/node/docs/store/unassigned reason. |
| `opensearch_allocation_explain` | Объяснение аллокации/неаллокации shard. |
| `opensearch_list_indices` | `cat.indices` в JSON, шаблон `pattern`. |
| `opensearch_get_mapping` | Mapping индекса. |
| `opensearch_search` | Поиск; `size` в теле ограничивается `search_max_size`. |
| `opensearch_count` | Count; опциональный JSON-фильтр. |
| `opensearch_delete_index` | Только при `allow_write: true`. |

### RAG-память (`modules.opensearch.rag`)

Включается, если **`opensearch.enabled`** и **`opensearch.rag.enabled`**. Запись и поиск разрешены **только** по индексам из **`rag.index_allowlist`**. Лимиты: размер текста/заголовка/метаданных, потолок **`max_docs_per_index`** (0 = не проверять), **`retrieval_size_cap`** для выдачи поиска. Удаление по id — только при **`rag.allow_delete_by_id`**. При **`rag.auto_create_index: true`** при первой записи создаётся индекс с фиксированным `strict` mapping (text + keyword + служебные поля). Поиск: **BM25** (`multi_match` по полям текста и заголовка), не векторный knn (его можно добавить в кластере отдельно под ваш mapping). В выдачу попадают только документы с **`source` = `rag.source_tag`** (общий индекс с чужими документами не «засоряет» RAG-поиск). Счётчики и лимит **`max_docs_per_index`** считают только такие документы.

| Tool | Назначение |
|------|------------|
| `opensearch_rag_policy` | JSON: allowlist, лимиты, имена полей, подсказка агенту (без секретов). |
| `opensearch_rag_stats` | `count` по каждому индексу из allowlist. |
| `opensearch_rag_store` | Индексировать один документ (`text`, опционально `title`, `session_id`, `doc_id`, `metadata`). |
| `opensearch_rag_search` | Полнотекстовый поиск + highlight; опциональный фильтр `session_id`. |
| `opensearch_rag_delete_document` | Только если `rag.allow_delete_by_id: true`. |

## Демо UI (`stack-mcp-ui`)

Веб-интерфейс для проверки конфигурации и бэкендов (см. `README.md`). Сам протокол MCP в `stack-mcp` — **HTTP** (Streamable HTTP или SSE), не stdio по умолчанию.

| Путь | Назначение |
|------|------------|
| `/health` | Liveness: `200` и тело `ok`, без загрузки конфига (Docker/Kubernetes). |
| `/ready` | Readiness: `200` если `STACK_MCP_CONFIG` указывает на файл и YAML парсится; иначе `503`. |
| `/` | Главная: флаги всех модулей MCP (как в `stack_mcp_status`), проверки доступности по каждому бэкенду (включая почту и SSH TCP), очередь Kafka, превью `/metrics`, список tools, allowlist-вызовы. |
| `/status-page` | Текст экспозиции Prometheus с `/metrics` (при защите метрик — поле для секрета). |
| `/api/*` | JSON API: Bearer **опционально** — если задан `STACK_MCP_UI_TOKEN`, без него `401`; иначе запросы принимаются. Rate limit по IP, audit JSONL. |
| `/api/auth-config` | Публично: `ui_bearer_enabled`, `metrics_auth_required` (подсказки для браузера). |
| `/metrics` | Prometheus text exposition: `stack_mcp_module_up`, задержки проверок, `stack_mcp_kafka_retained_messages*`, счётчики UI и `stack_mcp_metrics_auth_failed_total`. |

Защита `/metrics` без IP whitelist: `STACK_MCP_METRICS_TOKEN` (и опционально `STACK_MCP_METRICS_ACCEPT_UI_BEARER`, `STACK_MCP_METRICS_REQUIRE_TOKEN`, лимит `STACK_MCP_METRICS_RATE_LIMIT_RPM`). Подробнее — в `README.md`.

Прод: `STACK_MCP_UI_WORKERS`, `STACK_MCP_LOG_LEVEL`, `STACK_MCP_UI_TRUSTED_HOSTS` (список Host через запятую), артефакты в `deploy/`.
