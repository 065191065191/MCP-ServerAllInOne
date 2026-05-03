"""Проверка SQL для modules.postgres.allowlisted_queries: один read-only запрос (SELECT / WITH … SELECT)."""
from __future__ import annotations

import re

MAX_ALLOWLISTED_SQL_BYTES = 32_768

# Запрещены конструкции записи и DDL; отдельно режем INTO (SELECT INTO / CREATE … AS).
# VACUUM/REINDEX/CLUSTER и т.п. — не read-only; NOTIFY — побочный эффект.
_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|"
    r"COPY|CALL|EXECUTE|DO|LISTEN|NOTIFY|PREPARE|"
    r"SET\s+ROLE|SET\s+SESSION\s+AUTHORIZATION|"
    r"VACUUM|CLUSTER|REINDEX|DISCARD\s+ALL|RESET\s+ALL|"
    r"LOCK\s+TABLE|LOCK\s+DATABASE|LOCK\s+SCHEMA|"
    r"REFRESH\s+MATERIALIZED\s+VIEW|"
    r"COMMENT\s+ON|SECURITY\s+LABEL|"
    r"IMPORT\s+FOREIGN\s+SCHEMA|"
    r"ALTER\s+SYSTEM"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)

# Опасные функции / расширения в read-only allowlist не допускаем.
_FORBIDDEN_FUNCTIONS = re.compile(
    r"\b("
    r"pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|lo_export|"
    r"dblink_connect|dblink_exec|dblink_open|"
    r"pg_sleep|pg_advisory_lock|pg_advisory_xact_lock"
    r")\s*\(",
    re.IGNORECASE,
)

_INTO_FORBIDDEN = re.compile(r"\bINTO\b", re.IGNORECASE)


def _contains_unquoted_semicolon(s: str) -> bool:
    """`;` только вне строковых литералов '..' и идентификаторов "..". Упрощённо для прод-allowlist."""
    i = 0
    n = len(s)
    in_single = False
    in_double = False
    while i < n:
        c = s[i]
        if in_single:
            if c == "'" and i + 1 < n and s[i + 1] == "'":
                i += 2
                continue
            if c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if c == '"' and i + 1 < n and s[i + 1] == '"':
                i += 2
                continue
            if c == '"':
                in_double = False
            i += 1
            continue
        if c == "'":
            in_single = True
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        if c == ";":
            return True
        i += 1
    return False


def normalize_and_validate_allowlisted_sql(sql: str) -> None:
    """Проверяет текст SQL из конфига; при ошибке — ValueError.

    Точка с запятой учитывается только вне '..' и ".." (литералы/идентификаторы).
    Строки с dollar-quoting ($tag$...$tag$) не разбираются — при необходимости избегайте `;` внутри тела.
    """
    if not sql or not str(sql).strip():
        raise ValueError("allowlisted query sql must be non-empty")
    raw = str(sql).strip()
    if len(raw.encode("utf-8")) > MAX_ALLOWLISTED_SQL_BYTES:
        raise ValueError(f"allowlisted sql exceeds {MAX_ALLOWLISTED_SQL_BYTES} bytes")
    core = raw.rstrip().rstrip(";").strip()
    if _contains_unquoted_semicolon(core):
        raise ValueError("allowlisted sql must be a single statement (no unquoted semicolons)")
    upper = core.lstrip().upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("allowlisted sql must start with SELECT or WITH")
    if _FORBIDDEN.search(core):
        raise ValueError("allowlisted sql contains a forbidden keyword (DML/DDL/etc.)")
    if _FORBIDDEN_FUNCTIONS.search(core):
        raise ValueError("allowlisted sql contains a forbidden function call")
    if _INTO_FORBIDDEN.search(core):
        raise ValueError("allowlisted sql must not contain INTO")
