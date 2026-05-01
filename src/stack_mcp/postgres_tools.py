from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from stack_mcp.backend_tls import make_postgres_conninfo
from stack_mcp.config import PostgresModuleConfig


def _ensure_db_allowed(cfg: PostgresModuleConfig) -> None:
    info = conninfo_to_dict(cfg.dsn)
    dbname = info.get("dbname") or info.get("database")
    if cfg.allowed_databases and dbname and dbname not in cfg.allowed_databases:
        raise PermissionError(
            f"database {dbname!r} not in allowed_databases {cfg.allowed_databases!r}"
        )


def _connect(cfg: PostgresModuleConfig):
    _ensure_db_allowed(cfg)
    conn = psycopg.connect(make_postgres_conninfo(cfg), connect_timeout=10, row_factory=dict_row)
    ms = max(1000, min(cfg.statement_timeout_seconds * 1000, 120_000))
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (ms,))
    return conn


def _rows(cur) -> list[dict[str, Any]]:
    return list(cur.fetchall())


def postgres_connections_overview(cfg: PostgresModuleConfig) -> str:
    """Aggregate session counts by state; lightweight activity snapshot."""
    q = """
    SELECT state, count(*)::bigint AS count
    FROM pg_stat_activity
    GROUP BY state
    ORDER BY count DESC;
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            by_state = _rows(cur)
            cur.execute(
                """
                SELECT count(*)::bigint AS total
                FROM pg_stat_activity;
                """
            )
            total = cur.fetchone()
    return json.dumps({"by_state": by_state, "total": total}, indent=2, default=str)


def postgres_long_running_queries(cfg: PostgresModuleConfig) -> str:
    limit = max(1, min(cfg.long_query_limit, 50))
    q = """
    SELECT pid, usename, datname, state, wait_event_type, wait_event,
           now() - query_start AS duration,
           left(query, 200) AS query_preview
    FROM pg_stat_activity
    WHERE state <> 'idle'
      AND query NOT ILIKE '%pg_stat_activity%'
    ORDER BY query_start ASC NULLS LAST
    LIMIT %s;
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q, (limit,))
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)


def postgres_blocking_chains(cfg: PostgresModuleConfig) -> str:
    q = """
    SELECT
      blocked_locks.pid AS blocked_pid,
      blocking_locks.pid AS blocking_pid,
      blocked_activity.usename AS blocked_user,
      blocking_activity.usename AS blocking_user,
      blocked_activity.datname AS blocked_database,
      left(blocked_activity.query, 200) AS blocked_query_preview,
      left(blocking_activity.query, 200) AS blocking_query_preview
    FROM pg_catalog.pg_locks blocked_locks
    JOIN pg_catalog.pg_stat_activity blocked_activity
      ON blocked_activity.pid = blocked_locks.pid
    JOIN pg_catalog.pg_locks blocking_locks
      ON blocking_locks.locktype = blocked_locks.locktype AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
     AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
     AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
     AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
     AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
     AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
     AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
     AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
     AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
     AND blocking_locks.pid <> blocked_locks.pid
    JOIN pg_catalog.pg_stat_activity blocking_activity
      ON blocking_activity.pid = blocking_locks.pid
    WHERE NOT blocked_locks.granted
    LIMIT 50;
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)


def postgres_database_sizes(cfg: PostgresModuleConfig) -> str:
    top_n = max(1, min(cfg.top_n_tables, 100))
    q = """
    SELECT datname, pg_database_size(datname)::bigint AS size_bytes
    FROM pg_database
    WHERE datistemplate = false
    ORDER BY pg_database_size(datname) DESC
    LIMIT %s;
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q, (top_n,))
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)


def postgres_table_sizes(cfg: PostgresModuleConfig) -> str:
    top_n = max(1, min(cfg.top_n_tables, 100))
    if not cfg.schema_allowlist:
        raise ValueError("schema_allowlist must be non-empty")
    schema_sql = sql.SQL(", ").join(sql.Identifier(s) for s in cfg.schema_allowlist)
    q = sql.SQL(
        """
        SELECT n.nspname AS schema, c.relname AS table,
               pg_total_relation_size(c.oid)::bigint AS total_bytes,
               pg_relation_size(c.oid)::bigint AS table_bytes,
               pg_indexes_size(c.oid)::bigint AS indexes_bytes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
          AND n.nspname IN ({schemas})
        ORDER BY pg_total_relation_size(c.oid) DESC
        LIMIT %s;
        """
    ).format(schemas=schema_sql)
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q, (top_n,))
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)


def postgres_index_usage(cfg: PostgresModuleConfig) -> str:
    top_n = max(1, min(cfg.top_n_tables, 100))
    if not cfg.schema_allowlist:
        raise ValueError("schema_allowlist must be non-empty")
    schema_sql = sql.SQL(", ").join(sql.Identifier(s) for s in cfg.schema_allowlist)
    q = sql.SQL(
        """
        SELECT schemaname, relname AS table, indexrelname AS index,
               idx_scan::bigint, pg_relation_size(indexrelid)::bigint AS index_bytes
        FROM pg_stat_user_indexes
        WHERE schemaname IN ({schemas})
        ORDER BY idx_scan ASC, pg_relation_size(indexrelid) DESC
        LIMIT %s;
        """
    ).format(schemas=schema_sql)
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q, (top_n,))
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)


def postgres_cache_hit_ratio(cfg: PostgresModuleConfig) -> str:
    q = """
    SELECT
      sum(heap_blks_read)::bigint AS heap_blks_read,
      sum(heap_blks_hit)::bigint AS heap_blks_hit,
      CASE WHEN coalesce(sum(heap_blks_hit) + sum(heap_blks_read), 0) = 0 THEN NULL
 ELSE sum(heap_blks_hit)::float / nullif(sum(heap_blks_hit) + sum(heap_blks_read), 0)
      END AS buffer_hit_ratio
    FROM pg_statio_user_tables;
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            row = cur.fetchone()
    return json.dumps(row, indent=2, default=str)


def postgres_replication_lag(cfg: PostgresModuleConfig) -> str:
    q = """
    SELECT pid, usename, application_name, client_addr, state,
           sent_lsn, write_lsn, flush_lsn, replay_lsn,
           write_lag, flush_lag, replay_lag
    FROM pg_stat_replication;
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q)
            rows = _rows(cur)
    if not rows:
        return json.dumps({"replication": "no rows in pg_stat_replication (not a primary or no replicas)"}, indent=2)
    return json.dumps(rows, indent=2, default=str)


def postgres_autovacuum_health(cfg: PostgresModuleConfig) -> str:
    top_n = max(1, min(cfg.top_n_tables, 100))
    if not cfg.schema_allowlist:
        raise ValueError("schema_allowlist must be non-empty")
    schema_sql = sql.SQL(", ").join(sql.Identifier(s) for s in cfg.schema_allowlist)
    q = sql.SQL(
        """
        SELECT schemaname, relname,
               n_live_tup::bigint, n_dead_tup::bigint,
               last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname IN ({schemas})
        ORDER BY n_dead_tup DESC NULLS LAST
        LIMIT %s;
        """
    ).format(schemas=schema_sql)
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(q, (top_n,))
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)


def postgres_statements_top(cfg: PostgresModuleConfig) -> str:
    top_n = max(1, min(cfg.long_query_limit, 50))
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') AS has_ext;"
            )
            flag = cur.fetchone()
            if not flag or not flag.get("has_ext"):
                return json.dumps(
                    {
                        "error": "pg_stat_statements extension not installed",
                        "hint": "CREATE EXTENSION pg_stat_statements; (superuser)",
                    },
                    indent=2,
                )
            cur.execute(
                """
                SELECT queryid::text, calls::bigint, total_exec_time::double precision,
                       mean_exec_time::double precision, rows::bigint AS rows_returned,
                       left(query, 200) AS query_preview
                FROM pg_stat_statements
                ORDER BY total_exec_time DESC
                LIMIT %s;
                """,
                (top_n,),
            )
            rows = _rows(cur)
    return json.dumps(rows, indent=2, default=str)
