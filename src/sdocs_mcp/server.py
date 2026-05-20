from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as _FastMCPSettings
from pydantic_settings import SettingsConfigDict

# FastMCP по умолчанию включает pydantic-settings с env_file=".env" (cwd).
# В контейнерах/OpenShift файл .env часто отсутствует или недоступен для stat() → падение при EMBED_MCP.
# Отключаем чтение dotenv-файла; настройки FASTMCP_* по-прежнему берутся из os.environ.
_fast_cfg = dict(_FastMCPSettings.model_config)
_fast_cfg["env_file"] = None
_FastMCPSettings.model_config = SettingsConfigDict(**_fast_cfg)

from sdocs_mcp import (
    kafka_tools,
    mail_tools,
    opensearch_rag_tools,
    opensearch_tools,
    postgres_tools,
    prometheus_tools,
    redis_tools,
    ssh_tools,
)
from sdocs_mcp.audited_fastmcp import AuditedFastMCP
from sdocs_mcp.backend_tls import resolve_client_mtls
from sdocs_mcp.config import (
    AppConfig,
    KafkaModuleConfig,
    MailModuleConfig,
    OpenSearchModuleConfig,
    PostgresModuleConfig,
    PrometheusModuleConfig,
    RedisModuleConfig,
    SshModuleConfig,
    config_path_for_display,
    config_yaml_diagnose,
    load_config,
)
from sdocs_mcp.http_access_log import install_access_logging
from sdocs_mcp.mcp_telemetry import wrap_mcp_http_app
from sdocs_mcp.alerts_kafka_resolve import alerts_kafka_ready, resolve_alerts_kafka
from sdocs_mcp.alerts_kafka_sync import is_alert_leader
from sdocs_mcp.config_runtime import public_config_status, refresh_config_state_from_disk
from sdocs_mcp.mcp_agent_guide import build_capabilities_payload, build_mcp_instructions, capabilities_json
from sdocs_mcp.mtls import resolve_mcp_mtls_uvicorn_kwargs
from sdocs_mcp.tool_audit_http_context import ToolAuditCallerMiddleware


def _env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _register_postgres(mcp: FastMCP, cfg: PostgresModuleConfig) -> None:
    @mcp.tool()
    def postgres_connections_overview() -> str:
        """Safe diagnostics: session counts grouped by state + total."""
        return postgres_tools.postgres_connections_overview(cfg)

    @mcp.tool()
    def postgres_long_running_queries() -> str:
        """Safe diagnostics: top active queries by duration (preview only)."""
        return postgres_tools.postgres_long_running_queries(cfg)

    @mcp.tool()
    def postgres_blocking_chains() -> str:
        """Safe diagnostics: blocked vs blocking sessions (row cap)."""
        return postgres_tools.postgres_blocking_chains(cfg)

    @mcp.tool()
    def postgres_database_sizes() -> str:
        """Safe diagnostics: largest databases by on-disk size."""
        return postgres_tools.postgres_database_sizes(cfg)

    @mcp.tool()
    def postgres_table_sizes() -> str:
        """Safe diagnostics: largest tables within schema_allowlist."""
        return postgres_tools.postgres_table_sizes(cfg)

    @mcp.tool()
    def postgres_index_usage() -> str:
        """Safe diagnostics: indexes ordered by low idx_scan (candidates for review)."""
        return postgres_tools.postgres_index_usage(cfg)

    @mcp.tool()
    def postgres_cache_hit_ratio() -> str:
        """Safe diagnostics: buffer cache hit ratio from pg_statio_user_tables."""
        return postgres_tools.postgres_cache_hit_ratio(cfg)

    @mcp.tool()
    def postgres_replication_lag() -> str:
        """Safe diagnostics: pg_stat_replication rows if this is a primary."""
        return postgres_tools.postgres_replication_lag(cfg)

    @mcp.tool()
    def postgres_autovacuum_health() -> str:
        """Safe diagnostics: dead tuples / autovacuum timestamps (top-N)."""
        return postgres_tools.postgres_autovacuum_health(cfg)

    @mcp.tool()
    def postgres_statements_top() -> str:
        """Safe diagnostics: top statements by total time (requires pg_stat_statements)."""
        return postgres_tools.postgres_statements_top(cfg)

    if cfg.allowlisted_queries:

        @mcp.tool()
        def postgres_allowlisted_query_catalog() -> str:
            """Allowlisted SQL query ids and descriptions (no SQL text); use before postgres_allowlisted_query."""
            return postgres_tools.postgres_allowlisted_query_catalog(cfg)

        @mcp.tool()
        def postgres_allowlisted_query(query_id: str) -> str:
            """Run one SELECT from config allowlist by query_id (clients pass id only, not raw SQL)."""
            return postgres_tools.postgres_allowlisted_query(cfg, query_id)


def _register_redis(mcp: FastMCP, cfg: RedisModuleConfig) -> None:
    @mcp.tool()
    def redis_ping() -> str:
        """Redis PING."""
        return redis_tools.redis_ping(cfg)

    @mcp.tool()
    def redis_info() -> str:
        """Redis INFO for fixed sections (server,memory,stats,replication,cpu,commandstats)."""
        return redis_tools.redis_info(cfg)

    @mcp.tool()
    def redis_memory_stats() -> str:
        """Redis MEMORY STATS (if supported)."""
        return redis_tools.redis_memory_stats(cfg)

    @mcp.tool()
    def redis_dbsize() -> str:
        """Redis DBSIZE."""
        return redis_tools.redis_dbsize(cfg)

    @mcp.tool()
    def redis_slowlog_get() -> str:
        """Redis SLOWLOG GET with configured max entries."""
        return redis_tools.redis_slowlog_get(cfg)

    @mcp.tool()
    def redis_get(key: str) -> str:
        """GET a single key; value truncated to get_max_value_bytes."""
        return redis_tools.redis_get(cfg, key)

    @mcp.tool()
    def redis_mget(keys: list[str]) -> str:
        """MGET up to mget_max_keys keys; each value truncated."""
        return redis_tools.redis_mget(cfg, keys)

    @mcp.tool()
    def redis_hgetall(key: str) -> str:
        """HGETALL with field count / total byte caps."""
        return redis_tools.redis_hgetall(cfg, key)

    @mcp.tool()
    def redis_setex(key: str, seconds: int, value: str) -> str:
        """SETEX key seconds value (bounded TTL and value size)."""
        return redis_tools.redis_setex(cfg, key, seconds, value)

    if cfg.scan_enabled:
        @mcp.tool()
        def redis_scan_prefix(prefix: str) -> str:
            """SCAN keys by prefix; requires scan_enabled and allowlisted prefix."""
            return redis_tools.redis_scan_prefix(cfg, prefix)


def _register_kafka(mcp: FastMCP, cfg: KafkaModuleConfig) -> None:
    @mcp.tool()
    def kafka_list_topics() -> str:
        """List cluster topics (truncated to list_topics_max)."""
        return kafka_tools.kafka_list_topics(cfg)

    @mcp.tool()
    def kafka_describe_topic(topic: str) -> str:
        """Partition IDs for a topic (must be in topic_allowlist)."""
        return kafka_tools.kafka_describe_topic(cfg, topic)

    @mcp.tool()
    def kafka_consume_recent(topic: str, partition: int, max_messages: int | None = None) -> str:
        """Read up to N recent messages from a single partition (byte + count caps)."""
        return kafka_tools.kafka_consume_recent(cfg, topic, partition, max_messages)

    if cfg.allow_produce:
        @mcp.tool()
        def kafka_produce(topic: str, messages: list[dict[str, str]]) -> str:
            """Produce a small batch to an allowlisted topic (requires allow_produce)."""
            return kafka_tools.kafka_produce(cfg, topic, messages)

    if cfg.allow_admin:
        @mcp.tool()
        def kafka_create_topic(
            topic: str,
            num_partitions: int = 1,
            replication_factor: int = 1,
        ) -> str:
            """Create topic (requires allow_admin + allowlisted name)."""
            return kafka_tools.kafka_create_topic(cfg, topic, num_partitions, replication_factor)


def _register_mail(mcp: FastMCP, cfg: MailModuleConfig) -> None:
    @mcp.tool()
    def mail_imap_list_mailboxes() -> str:
        """IMAP LIST mailboxes (truncated per config)."""
        return mail_tools.mail_imap_list_mailboxes(cfg)

    @mcp.tool()
    def mail_imap_search(
        folder: str | None = None,
        unseen_only: bool = True,
        max_messages: int | None = None,
    ) -> str:
        """IMAP SEARCH UNSEEN or ALL; returns UIDs (capped)."""
        return mail_tools.mail_imap_search(cfg, folder, unseen_only, max_messages)

    @mcp.tool()
    def mail_imap_fetch_rfc822(folder: str, uid: str) -> str:
        """IMAP FETCH BODY.PEEK[] by UID; preview capped by fetch_max_bytes."""
        return mail_tools.mail_imap_fetch_rfc822(cfg, folder, uid)

    @mcp.tool()
    def mail_smtp_send(
        to_addr: str,
        subject: str,
        body_text: str,
        from_addr: str | None = None,
    ) -> str:
        """SMTP: аргументы to_addr, subject, body_text (не to/body). from_addr опционально."""
        return mail_tools.mail_smtp_send(cfg, to_addr, subject, body_text, from_addr)


def _register_prometheus(
    mcp: FastMCP,
    prom: PrometheusModuleConfig,
    kafka: KafkaModuleConfig | None,
) -> None:
    default_topic = prom.kafka_metrics_topic

    @mcp.tool()
    def prometheus_mcp_guide() -> str:
        """Справка: как вызывать MCP Prometheus (не путать с /metrics SDocsMCP)."""
        export_tools = (
            ["prometheus_export_instant_to_kafka"]
            if kafka and kafka.enabled and kafka.allow_produce
            else []
        )
        return json.dumps(
            {
                "what_this_is": (
                    "HTTP-клиент к вашему Prometheus (modules.prometheus.base_url), "
                    "не scrape метрик самого SDocsMCP."
                ),
                "not_this": (
                    "GET /metrics на хосте UI/MCP — только внутренние счётчики sdocs_mcp_*; "
                    "для PromQL используйте tools ниже."
                ),
                "query_tools": [
                    "prometheus_query_instant",
                    "prometheus_query_range",
                    "prometheus_targets",
                    "prometheus_metadata",
                    "prometheus_series",
                    "prometheus_labels",
                    "prometheus_rules",
                    "prometheus_alerts",
                ],
                "kafka_export_tools": export_tools,
                "default_kafka_topic": default_topic,
                "kafka_export_topic_arg": (
                    "topic в prometheus_export_instant_to_kafka опционален — "
                    f"по умолчанию {default_topic!r}"
                ),
                "background_cron": (
                    "UI Консоль → вкладка Cron: опрос Prometheus → Kafka, "
                    f"интервал по умолчанию {prom.metrics_cron.interval_seconds}s, "
                    f"PromQL {prom.metrics_cron.query!r}"
                ),
                "example_instant": 'prometheus_query_instant(query="up")',
                "example_kafka": (
                    f'prometheus_export_instant_to_kafka(query="up")  # topic → {default_topic!r}'
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    def prometheus_query_instant(query: str, at_time: str | None = None) -> str:
        """Instant PromQL к modules.prometheus.base_url (/api/v1/query). Не /metrics SDocsMCP."""
        return prometheus_tools.prometheus_query_instant(prom, query, at_time)

    @mcp.tool()
    def prometheus_query_range(query: str, start: str, end: str, step: str) -> str:
        """Range PromQL (/api/v1/query_range) к удалённому Prometheus."""
        return prometheus_tools.prometheus_query_range(prom, query, start, end, step)

    @mcp.tool()
    def prometheus_targets(state: str | None = None) -> str:
        """Цели scrape (/api/v1/targets) удалённого Prometheus."""
        return prometheus_tools.prometheus_targets(prom, state)

    @mcp.tool()
    def prometheus_metadata(metric: str | None = None) -> str:
        """Метаданные метрик (/api/v1/metadata)."""
        return prometheus_tools.prometheus_metadata(prom, metric)

    @mcp.tool()
    def prometheus_series(
        match_queries: list[str],
        start: str | None = None,
        end: str | None = None,
    ) -> str:
        """Серии по match[] (/api/v1/series)."""
        return prometheus_tools.prometheus_series(prom, match_queries, start, end)

    @mcp.tool()
    def prometheus_labels() -> str:
        """Имена лейблов (/api/v1/labels)."""
        return prometheus_tools.prometheus_labels(prom)

    @mcp.tool()
    def prometheus_rules() -> str:
        """Recording/alerting rules (/api/v1/rules)."""
        return prometheus_tools.prometheus_rules(prom)

    @mcp.tool()
    def prometheus_alerts() -> str:
        """Активные алерты (/api/v1/alerts)."""
        return prometheus_tools.prometheus_alerts(prom)

    if kafka and kafka.enabled and kafka.allow_produce:
        @mcp.tool()
        def prometheus_export_instant_to_kafka(
            query: str,
            topic: str | None = None,
            message_key: str | None = None,
        ) -> str:
            f"""Instant query → JSON в Kafka.

            Запрос к modules.prometheus.base_url, не к /metrics SDocsMCP.
            topic: опционально; иначе kafka_metrics_topic (сейчас {default_topic!r}).
            Нужны kafka.allow_produce и топик в topic_allowlist.
            """
            return prometheus_tools.prometheus_export_instant_to_kafka(
                prom,
                kafka,
                query,
                topic,
                message_key,
            )


def _register_opensearch(mcp: FastMCP, cfg: OpenSearchModuleConfig) -> None:
    @mcp.tool()
    def opensearch_cluster_health() -> str:
        """GET _cluster/health."""
        return opensearch_tools.opensearch_cluster_health(cfg)

    @mcp.tool()
    def opensearch_cluster_health_debug() -> str:
        """Extended health: shard-level health + pending tasks + cat shards."""
        return opensearch_tools.opensearch_cluster_health_debug(cfg)

    @mcp.tool()
    def opensearch_cluster_stats() -> str:
        """Cluster-wide stats (docs, store, nodes, indices, query load)."""
        return opensearch_tools.opensearch_cluster_stats(cfg)

    @mcp.tool()
    def opensearch_nodes_stats() -> str:
        """Node stats: os/jvm/process/fs/indices/thread_pool/http/transport."""
        return opensearch_tools.opensearch_nodes_stats(cfg)

    @mcp.tool()
    def opensearch_pending_tasks() -> str:
        """Cluster pending tasks queue."""
        return opensearch_tools.opensearch_pending_tasks(cfg)

    @mcp.tool()
    def opensearch_cluster_settings() -> str:
        """Cluster settings (persistent/transient/defaults)."""
        return opensearch_tools.opensearch_cluster_settings(cfg)

    @mcp.tool()
    def opensearch_cat_shards(index: str = "*") -> str:
        """Shard-level table: state, node, docs, store, unassigned reason."""
        return opensearch_tools.opensearch_cat_shards(cfg, index)

    @mcp.tool()
    def opensearch_allocation_explain(
        index: str | None = None,
        shard: int | None = None,
        primary: bool | None = None,
    ) -> str:
        """Explain why a shard is (or is not) allocated."""
        return opensearch_tools.opensearch_allocation_explain(cfg, index, shard, primary)

    @mcp.tool()
    def opensearch_list_indices(pattern: str = "*") -> str:
        """cat indices (JSON) with pattern."""
        return opensearch_tools.opensearch_list_indices(cfg, pattern)

    @mcp.tool()
    def opensearch_get_mapping(index: str) -> str:
        """Get index mapping JSON."""
        return opensearch_tools.opensearch_get_mapping(cfg, index)

    @mcp.tool()
    def opensearch_search(index: str, query_json: str) -> str:
        """Поиск: query_json — строка JSON DSL (не query). Пример: {"query":{"match_all":{}}}."""
        return opensearch_tools.opensearch_search(cfg, index, query_json)

    @mcp.tool()
    def opensearch_count(index: str, query_json: str | None = None) -> str:
        """Count docs; optional query JSON filter."""
        return opensearch_tools.opensearch_count(cfg, index, query_json)

    if cfg.allow_write:
        @mcp.tool()
        def opensearch_delete_index(index: str) -> str:
            """Delete index (requires allow_write)."""
            return opensearch_tools.opensearch_delete_index(cfg, index)

    if cfg.rag.enabled:
        @mcp.tool()
        def opensearch_rag_policy() -> str:
            """RAG: политика хранения (allowlist индексов, лимиты, поля). Вызывайте перед записью в память."""
            return opensearch_rag_tools.opensearch_rag_policy(cfg)

        @mcp.tool()
        def opensearch_rag_stats() -> str:
            """RAG: число документов в каждом разрешённом индексе."""
            return opensearch_rag_tools.opensearch_rag_stats(cfg)

        @mcp.tool()
        def opensearch_rag_store(
            index: str,
            text: str,
            title: str | None = None,
            session_id: str | None = None,
            doc_id: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> str:
            """RAG: сохранить фрагмент в общее хранилище (только индексы из rag.index_allowlist)."""
            return opensearch_rag_tools.opensearch_rag_store(
                cfg, index, text, title, session_id, doc_id, metadata
            )

        @mcp.tool()
        def opensearch_rag_search(
            index: str,
            query_text: str,
            session_id: str | None = None,
            size: int | None = None,
        ) -> str:
            """RAG: полнотекстовый поиск по индексу (BM25), выдача ограничена rag.retrieval_size_cap."""
            return opensearch_rag_tools.opensearch_rag_search(cfg, index, query_text, session_id, size)

        if cfg.rag.allow_delete_by_id:
            @mcp.tool()
            def opensearch_rag_delete_document(index: str, doc_id: str) -> str:
                """RAG: удалить документ по id (только при rag.allow_delete_by_id)."""
                return opensearch_rag_tools.opensearch_rag_delete_document(cfg, index, doc_id)


def _register_ssh(mcp: FastMCP, cfg: SshModuleConfig) -> None:
    @mcp.tool()
    def ssh_command_policy() -> str:
        """Политика ssh_run_command: forbidden_substrings, forbidden_regex, правила shell-операторов, лимит длины (из config + кода)."""
        return ssh_tools.ssh_command_policy(cfg)

    @mcp.tool()
    def ssh_hosts_overview() -> str:
        """Список SSH-хостов из конфига: id, hostname, port, username, description (без секретов)."""
        return ssh_tools.ssh_hosts_overview(cfg)

    @mcp.tool()
    def ssh_run_command(host_id: str, command: str) -> str:
        """Выполнить команду по SSH после проверки forbidden_substrings / forbidden_regex и ограничений на shell-операторы."""
        return ssh_tools.ssh_run_command(cfg, host_id, command)


def build_mcp(
    app: AppConfig,
    *,
    host: str = "0.0.0.0",
    port: int = 8765,
    streamable_http_path: str | None = None,
) -> FastMCP:
    _fm_kw: dict[str, Any] = {
        "name": "sdocs-mcp",
        "instructions": build_mcp_instructions(app),
        "host": host,
        "port": port,
    }
    if streamable_http_path is not None:
        _fm_kw["streamable_http_path"] = streamable_http_path
    if _env_truthy("SDOCS_MCP_STATELESS_HTTP"):
        _fm_kw["stateless_http"] = True
    if app.modules.opensearch.enabled and app.modules.opensearch.tool_call_audit.enabled:
        mcp = AuditedFastMCP(**_fm_kw, app_config=app)
    else:
        mcp = FastMCP(**_fm_kw)

    @mcp.tool()
    def sdocs_mcp_capabilities() -> str:
        """Путеводитель для агента: все tools по модулям, сценарии, типичные ошибки. Вызовите в начале сессии вместе с sdocs_mcp_status."""
        return capabilities_json(app)

    def _module_flags(cfg: AppConfig) -> dict[str, bool]:
        m = cfg.modules
        return {
            "postgres": m.postgres.enabled,
            "redis": m.redis.enabled,
            "kafka": m.kafka.enabled,
            "prometheus": m.prometheus.enabled,
            "mail": m.mail.enabled,
            "opensearch": m.opensearch.enabled,
            "ssh": m.ssh.enabled,
        }

    @mcp.tool()
    def sdocs_mcp_status() -> str:
        """Какие модули enabled в конфиге (без секретов). Для полного списка tools — sdocs_mcp_capabilities."""
        cap = build_capabilities_payload(app)
        try:
            refresh_config_state_from_disk()
        except Exception:
            pass
        cfg_pub = public_config_status()
        disk = load_config()
        disk_flags = _module_flags(disk)
        mcp_flags = _module_flags(app)
        cap_disk = build_capabilities_payload(disk)
        stale = disk_flags != mcp_flags
        hint = "Каталог tools: sdocs_mcp_capabilities. config_load — статус YAML для LLM (без пути к файлу)."
        if stale:
            hint += " modules_active_in_mcp устарели — ждите reload или перезапуск пода."
        return json.dumps(
            {
                "stateless_http": mcp.settings.stateless_http,
                "tools_total": cap["tools_total"],
                "tools_total_on_disk": cap_disk["tools_total"],
                "mcp_stale_vs_disk": stale,
                "hint": hint,
                "config_load": cfg_pub,
                "config_diagnose": config_yaml_diagnose(),
                "modules_enabled_on_disk": disk_flags,
                "modules_active_in_mcp": mcp_flags,
                "postgres": mcp_flags["postgres"],
                "postgres_allowlisted_query_ids": (
                    [q.id for q in app.modules.postgres.allowlisted_queries]
                    if app.modules.postgres.enabled
                    else []
                ),
                "redis": mcp_flags["redis"],
                "kafka": mcp_flags["kafka"],
                "prometheus": mcp_flags["prometheus"],
                "mail": mcp_flags["mail"],
                "opensearch": mcp_flags["opensearch"],
                "opensearch_rag": app.modules.opensearch.enabled and app.modules.opensearch.rag.enabled,
                "opensearch_tool_call_audit": (
                    app.modules.opensearch.enabled and app.modules.opensearch.tool_call_audit.enabled
                ),
                "ssh": mcp_flags["ssh"],
                "mcp_http_mtls": resolve_mcp_mtls_uvicorn_kwargs() is not None,
                "backend_mtls": {
                    "postgres": resolve_client_mtls(app.modules.postgres) is not None,
                    "redis": resolve_client_mtls(app.modules.redis) is not None,
                    "kafka": resolve_client_mtls(app.modules.kafka) is not None,
                    "prometheus": resolve_client_mtls(app.modules.prometheus) is not None,
                    "opensearch": resolve_client_mtls(app.modules.opensearch) is not None,
                },
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    def sdocs_alerting_status() -> str:
        """Alert: отдельный Kafka (modules.alerting.kafka), лидер, готовность sync. Не tools alerting_*."""
        try:
            disk = load_config()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        ready, kafka_src = alerts_kafka_ready(disk)
        k, _ = resolve_alerts_kafka(disk)
        return json.dumps(
            {
                "alerting_module_in_config": disk.modules.alerting.enabled,
                "alerting_kafka_enabled": disk.modules.alerting.kafka.enabled,
                "alerting_kafka_source": kafka_src,
                "alerting_kafka_ready": ready,
                "alerting_kafka_bootstrap": k.bootstrap_servers if k else [],
                "this_pod_is_leader": is_alert_leader(),
                "hint": "Правила Alert — UI /api/alerts/*; MCP tools alerting_* не существуют.",
            },
            indent=2,
            ensure_ascii=False,
        )

    if app.modules.postgres.enabled:
        _register_postgres(mcp, app.modules.postgres)
    if app.modules.redis.enabled:
        _register_redis(mcp, app.modules.redis)
    if app.modules.kafka.enabled:
        _register_kafka(mcp, app.modules.kafka)
    if app.modules.mail.enabled:
        _register_mail(mcp, app.modules.mail)
    if app.modules.opensearch.enabled:
        _register_opensearch(mcp, app.modules.opensearch)
    if app.modules.prometheus.enabled:
        _register_prometheus(
            mcp,
            app.modules.prometheus,
            app.modules.kafka if app.modules.kafka.enabled else None,
        )
    if app.modules.ssh.enabled:
        _register_ssh(mcp, app.modules.ssh)
    return mcp


_STDIO_DISABLED = (
    "Транспорт stdio отключён. По умолчанию используется HTTP (SDOCS_MCP_TRANSPORT=streamable-http). "
    "Для отладки stdio задайте SDOCS_MCP_DEV_LOCAL=true."
)
_LOCALHOST_DISABLED = (
    "Привязка MCP к localhost запрещена (SDOCS_MCP_HOST=127.0.0.1 / localhost / ::1). "
    "Слушайте 0.0.0.0 за reverse proxy и firewall или задайте SDOCS_MCP_DEV_LOCAL=true только для разработки."
)


async def _run_mcp_http_server(
    mcp: FastMCP,
    transport: str,
    ssl_kwargs: dict[str, Any] | None,
    app_cfg: AppConfig,
) -> None:
    """То же, что FastMCP.run_sse_async / run_streamable_http_async, но с опциональным mTLS для uvicorn."""
    if transport == "sse":
        starlette_app = mcp.sse_app(None)
    else:
        starlette_app = mcp.streamable_http_app()
    os_mod = app_cfg.modules.opensearch
    if os_mod.enabled and os_mod.tool_call_audit.enabled:
        starlette_app = ToolAuditCallerMiddleware(
            starlette_app,
            audit_cfg=os_mod.tool_call_audit,
            path_prefix=None,
        )
    starlette_app = wrap_mcp_http_app(starlette_app)
    install_access_logging(starlette_app, app_cfg.logging)
    kw: dict[str, Any] = {
        "host": mcp.settings.host,
        "port": mcp.settings.port,
        "log_level": mcp.settings.log_level.lower(),
    }
    if ssl_kwargs:
        kw.update(ssl_kwargs)
    await uvicorn.Server(uvicorn.Config(starlette_app, **kw)).serve()


def main() -> None:
    log = logging.getLogger("sdocs_mcp")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    cfg = load_config()
    dev_local = os.environ.get("SDOCS_MCP_DEV_LOCAL", "").strip().lower() in ("1", "true", "yes")
    transport = (os.environ.get("SDOCS_MCP_TRANSPORT") or "streamable-http").strip().lower()

    if transport == "stdio":
        if not dev_local:
            log.error(_STDIO_DISABLED)
            sys.exit(_STDIO_DISABLED)
        mcp = build_mcp(cfg)
        mcp.run(transport="stdio")
        return

    if transport not in ("streamable-http", "sse"):
        log.error("Unknown SDOCS_MCP_TRANSPORT=%r (use streamable-http, sse, or stdio)", transport)
        sys.exit(2)

    host = (os.environ.get("SDOCS_MCP_HOST") or "0.0.0.0").strip()
    port = int(os.environ.get("SDOCS_MCP_PORT", "8765"))
    if host in ("127.0.0.1", "localhost", "::1") and not dev_local:
        log.error(_LOCALHOST_DISABLED)
        sys.exit(_LOCALHOST_DISABLED)

    mcp = build_mcp(cfg, host=host, port=port)
    if _env_truthy("SDOCS_MCP_STATELESS_HTTP"):
        log.info(
            "MCP Streamable HTTP: stateless mode (SDOCS_MCP_STATELESS_HTTP) — подходит для балансировки без sticky."
        )
    ssl_kwargs = resolve_mcp_mtls_uvicorn_kwargs(log)
    scheme = "https" if ssl_kwargs else "http"
    if transport == "streamable-http":
        path = mcp.settings.streamable_http_path
        log.info("MCP Streamable HTTP on %s://%s:%s%s", scheme, host, port, path)
    else:
        log.info("MCP SSE on %s://%s:%s%s", scheme, host, port, mcp.settings.sse_path)
    if ssl_kwargs:
        log.info("mTLS: клиентские сертификаты обязательны (SDOCS_MCP_MTLS_* + ssl.CERT_REQUIRED).")
    anyio.run(_run_mcp_http_server, mcp, transport, ssl_kwargs, cfg)


if __name__ == "__main__":
    main()
