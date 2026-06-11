"""
Развёрнутые описания MCP tools для LLM (единый источник для server.py и mcp_agent_guide).

SDocsMCP — только чтение метрик / логов / состояний. Не для деплоя и не для правки прод-данных,
если tool явно не помечен как запись и не включён в конфиге.
"""

from __future__ import annotations

# Краткая миссия сервера (instructions + capabilities).
SERVER_MISSION_RU = (
    "SDocsMCP — MCP для наблюдаемости: метрики подов (Prometheus), логи микросервисов (OpenSearch), "
    "очереди данных (Kafka), здоровье PostgreSQL, кэш Redis, SSH-диагностика. "
    "Tools информативные: собирают снимок состояния «на сейчас», без ручного подключения к системам. "
    "Порядок: 1) sdocs_mcp_status 2) sdocs_mcp_capabilities 3) нужный tool по модулю."
)

_TOOL_DOCS: dict[str, str] = {
    "sdocs_mcp_status": (
        "ПЕРВЫЙ ВЫЗОВ в сессии. Показывает какие модули включены (postgres, prometheus, opensearch, kafka, …), "
        "версию сервера, загрузку конфига. Не ходит в бэкенды — только флаги. "
        "Если модуль false — его tools недоступны."
    ),
    "sdocs_mcp_capabilities": (
        "ПЕРВЫЙ ВЫЗОВ вместе со status. Полный список доступных tools по модулям, сценарии (workflows) "
        "и подсказки когда что вызывать. Используй как оглавление перед любым расследованием."
    ),
    "sdocs_alerting_status": (
        "Статус Alert (отдельный Kafka modules.alerting.kafka). Не путать с kafka_* для ms-eda. "
        "Tools alerting_* не существуют — только этот статус и UI /api/alerts/*."
    ),
    # --- PostgreSQL: 10 диагностических tools ---
    "postgres_connections_overview": (
        "PostgreSQL — снимок сессий СЕЙЧАС: сколько подключений в каждом state (active, idle, …) и total. "
        "Когда: «БД тормозит?», «много коннектов?». Не требует ручного psql. Только чтение pg_stat_activity."
    ),
    "postgres_long_running_queries": (
        "PostgreSQL — долгие АКТИВНЫЕ запросы (не idle), превью текста SQL до 200 символов. "
        "Когда: «что сейчас грузит БД?». Сортировка по длительности. Не выполняет произвольный SQL."
    ),
    "postgres_blocking_chains": (
        "PostgreSQL — кто кого блокирует (blocked_pid → blocking_pid). "
        "Когда: транзакции зависли, lock timeout. Только чтение lock-цепочек."
    ),
    "postgres_database_sizes": (
        "PostgreSQL — размеры всех баз на диске (от больших к меньшим). "
        "Когда: «какая БД раздулась?». Снимок на момент вызова."
    ),
    "postgres_table_sizes": (
        "PostgreSQL — крупнейшие таблицы в разрешённых схемах (schema_allowlist, обычно public). "
        "Когда: рост данных, планирование vacuum. Только метрики размера."
    ),
    "postgres_index_usage": (
        "PostgreSQL — индексы с низким idx_scan (кандидаты «не используются»). "
        "Когда: оптимизация, лишние индексы. Только статистика pg_stat_user_indexes."
    ),
    "postgres_cache_hit_ratio": (
        "PostgreSQL — hit ratio буферного кэша по таблицам. "
        "Когда: «БД читает с диска?», низкий cache hit. Только pg_statio_user_tables."
    ),
    "postgres_replication_lag": (
        "PostgreSQL — лаг репликации с primary (pg_stat_replication). "
        "Когда: replica отстаёт, DR. Пустой ответ если это не primary."
    ),
    "postgres_autovacuum_health": (
        "PostgreSQL — dead tuples и время последнего autovacuum по таблицам. "
        "Когда: bloat, «таблица не чистится». Только диагностика."
    ),
    "postgres_statements_top": (
        "PostgreSQL — топ тяжёлых запросов из pg_stat_statements (если расширение есть). "
        "Когда: «какие запросы чаще всего грузят CPU/IO?». Агрегаты, не сырой лог."
    ),
    "postgres_allowlisted_query_catalog": (
        "PostgreSQL — список id разрешённых SELECT из конфига (без текста SQL). "
        "Вызови перед postgres_allowlisted_query если нужен кастомный отчёт из allowlist."
    ),
    "postgres_allowlisted_query": (
        "PostgreSQL — выполнить ОДИН заранее одобренный SELECT по query_id из конфига. "
        "Аргумент: query_id (строка, например health-ping). НЕ передавай сырой SQL."
    ),
    # --- Prometheus ---
    "prometheus_mcp_guide": (
        "ОБЯЗАТЕЛЬНО прочитай перед prometheus_*. Объясняет: tools ходят в ваш Prometheus (base_url), "
        "где лежат ВСЕ метрики подов/K8s. Это НЕ GET /metrics на SDocsMCP (там только счётчики самого MCP)."
    ),
    "prometheus_query_instant": (
        "Prometheus — instant PromQL СЕЙЧАС. Все метрики подов что scrape'ит Prometheus: CPU, memory, up, "
        "http_requests, custom metrics. Аргумент: query (строка PromQL), опционально at_time. "
        "Пример: query='up', query='container_memory_working_set_bytes'. Не путать с /metrics SDocsMCP."
    ),
    "prometheus_query_range": (
        "Prometheus — PromQL за интервал времени (график/тренд). Аргументы: query, start, end, step (RFC3339 / duration). "
        "Когда: «как росла нагрузка за час?», алерты по тренду."
    ),
    "prometheus_targets": (
        "Prometheus — список scrape targets (поды, endpoints): кто up/down. "
        "Когда: «метрики пода не собираются?». state опционально: active|dropped|any."
    ),
    "prometheus_metadata": (
        "Prometheus — описания метрик (help, type). Аргумент metric опционален. "
        "Когда: непонятно что означает имя метрики."
    ),
    "prometheus_series": (
        "Prometheus — какие time series существуют по match[] (label filters). "
        "Когда: найти все series с label pod=..., namespace=...."
    ),
    "prometheus_labels": (
        "Prometheus — все имена labels в TSDB. Когда: узнать доступные label для PromQL."
    ),
    "prometheus_rules": (
        "Prometheus — recording и alerting rules. Когда: какие правила алертов настроены."
    ),
    "prometheus_alerts": (
        "Prometheus — активные firing/pending алерты СЕЙЧАС. Когда: «что горит в мониторинге?»."
    ),
    "prometheus_export_instant_to_kafka": (
        "Prometheus instant → JSON в Kafka (нужен kafka.allow_produce). Редкий сценарий экспорта снимка метрик."
    ),
    # --- OpenSearch / логи ---
    "opensearch_cluster_health": (
        "OpenSearch — health кластера (green/yellow/red). Первый шаг перед поиском логов."
    ),
    "opensearch_cluster_health_debug": (
        "OpenSearch — расширенный health: шарды, pending tasks. Когда yellow/red."
    ),
    "opensearch_cluster_stats": (
        "OpenSearch — статистика кластера: docs, store, nodes. Общая нагрузка индексации/поиска."
    ),
    "opensearch_nodes_stats": (
        "OpenSearch — JVM, CPU, FS, thread pools по нодам. Когда: «нода лежит / OOM?»."
    ),
    "opensearch_pending_tasks": (
        "OpenSearch — очередь cluster pending tasks. Когда: медленные операции с индексами."
    ),
    "opensearch_cluster_settings": (
        "OpenSearch — настройки кластера (persistent/transient). Только чтение."
    ),
    "opensearch_cat_shards": (
        "OpenSearch — таблица шардов (state, node, docs). index по умолчанию *."
    ),
    "opensearch_allocation_explain": (
        "OpenSearch — почему шард не размещён. Для расследования unassigned shards."
    ),
    "opensearch_list_indices": (
        "OpenSearch — список индексов и data streams по pattern. "
        "Логи микросервисов обычно в индексах/стримах: *ds*, ms-*, *istio*, *ingress*, *sowa*, *iam*, kube*, filebeat*. "
        "Аргумент pattern (строка), пример: 'ms-*', '*ds*', 'logs-*'. Сначала list_indices — потом search."
    ),
    "opensearch_get_mapping": (
        "OpenSearch — mapping полей индекса. Когда: как называется поле с сообщением лога (@timestamp, message, log)."
    ),
    "opensearch_search": (
        "OpenSearch — поиск ЛОГОВ и документов. ОБЯЗАТЕЛЬНО: query_json — СТРОКА с JSON DSL (не query!). "
        "Пример query_json: '{\"query\":{\"match\":{\"message\":\"error\"}},\"size\":10}'. "
        "index — имя индекса или data stream из list_indices. "
        "Для логов ms-* / *ds* / istio / ingress: сначала list_indices, уточни mapping, потом search с фильтром по времени."
    ),
    "opensearch_count": (
        "OpenSearch — число документов в индексе. query_json опционален (фильтр). "
        "Когда: «сколько ошибок за период?» без выгрузки тел логов."
    ),
    "opensearch_delete_index": (
        "OpenSearch — УДАЛЕНИЕ индекса. Только если allow_write в конфиге. Осторожно на проде."
    ),
    # --- Kafka ---
    "kafka_list_topics": (
        "Kafka — список топиков кластера. Первый шаг: есть ли нужный топик, жив ли брокер."
    ),
    "kafka_describe_topic": (
        "Kafka — партиции топика. Топик ДОЛЖЕН быть в topic_allowlist конфига. "
        "Когда: перед consume_recent — узнать partition id."
    ),
    "kafka_consume_recent": (
        "Kafka — прочитать ПОСЛЕДНИЕ N сообщений с хвоста партиции (не с начала истории). "
        "Когда: «пишутся ли данные в топик?», «какое последнее сообщение?», «как давно был event?». "
        "Аргументы: topic (в allowlist), partition (int), max_messages опционально. "
        "Смотри timestamp/key/value в ответе — оцени свежесть потока данных."
    ),
    "kafka_produce": (
        "Kafka — запись в топик (только allow_produce + topic в allowlist). Не для чтения логов."
    ),
    "kafka_create_topic": (
        "Kafka — создать топик (allow_admin). Редко на проде."
    ),
}

_WORKFLOWS_RU: dict[str, str] = {
    "postgres": (
        "Здоровье PostgreSQL без psql: connections_overview → (long_running_queries | blocking_chains) → "
        "table_sizes / autovacuum_health / cache_hit_ratio. Все 10 tools — снимок «на сейчас»."
    ),
    "prometheus": (
        "Метрики подов: prometheus_mcp_guide → query_instant('up') → targets → нужный PromQL. "
        "Не вызывай HTTP /metrics SDocsMCP — там только счётчики MCP."
    ),
    "opensearch": (
        "Логи микросервисов: cluster_health → list_indices('ms-*' или '*ds*' или '*istio*') → "
        "get_mapping → search(index, query_json) с фильтром по @timestamp. "
        "query_json — строка JSON, не поле query."
    ),
    "kafka": (
        "Поток данных: list_topics → describe_topic → consume_recent (хвост партиции). "
        "По timestamp сообщений суди: пишутся ли данные и как давно."
    ),
}


def tool_doc(name: str) -> str:
    return _TOOL_DOCS.get(name, "")


def tool_hint(name: str) -> str:
    """Короткая подсказка для capabilities (первая строка doc)."""
    doc = _TOOL_DOCS.get(name, "")
    if not doc:
        return name
    first = doc.split(".")[0].strip()
    return first if len(first) <= 200 else first[:197] + "…"
