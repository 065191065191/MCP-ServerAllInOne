from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field, model_validator

from sdocs_mcp.backend_tls import validate_client_mtls_triplet_files
from sdocs_mcp.postgres_allowlist_sql import normalize_and_validate_allowlisted_sql


class OpenSearchRagConfig(BaseModel):
    """Контролируемое хранилище для RAG-памяти агента: только allowlist индексов и жёсткие лимиты."""

    enabled: bool = False
    index_allowlist: list[str] = Field(default_factory=list)
    text_field: str = "text"
    title_field: str = "title"
    ingested_at_field: str = "ingested_at"
    source_field: str = "source"
    session_id_field: str = "session_id"
    metadata_json_field: str = "metadata_json"
    max_text_bytes: int = 100_000
    max_title_bytes: int = 2048
    max_metadata_json_bytes: int = 8192
    max_metadata_keys: int = 32
    retrieval_size_cap: int = 20
    # 0 = не проверять верхнюю границу документов в индексе.
    max_docs_per_index: int = 0
    allow_delete_by_id: bool = False
    # Создавать индекс с фиксированным mapping при первом store, если индекса ещё нет.
    auto_create_index: bool = False
    source_tag: str = "sdocs-mcp-rag"

    @model_validator(mode="after")
    def _validate_rag(self) -> Self:
        if self.enabled and not self.index_allowlist:
            raise ValueError("opensearch.rag.index_allowlist must be non-empty when rag.enabled")
        for idx in self.index_allowlist:
            if not idx or not str(idx).strip() or len(str(idx).strip()) > 200:
                raise ValueError("each rag index_allowlist entry must be 1..200 non-whitespace characters")
        if self.retrieval_size_cap < 1 or self.retrieval_size_cap > 100:
            raise ValueError("opensearch.rag.retrieval_size_cap must be 1..100")
        if self.max_text_bytes < 1024 or self.max_text_bytes > 2_097_152:
            raise ValueError("opensearch.rag.max_text_bytes must be between 1024 and 2097152")
        if self.max_title_bytes < 0 or self.max_title_bytes > 16_384:
            raise ValueError("opensearch.rag.max_title_bytes out of range")
        if self.max_metadata_json_bytes < 0 or self.max_metadata_json_bytes > 65_536:
            raise ValueError("opensearch.rag.max_metadata_json_bytes out of range")
        if self.max_metadata_keys < 0 or self.max_metadata_keys > 64:
            raise ValueError("opensearch.rag.max_metadata_keys out of range")
        if self.max_docs_per_index < 0:
            raise ValueError("opensearch.rag.max_docs_per_index must be >= 0")
        for fname in (
            self.text_field,
            self.title_field,
            self.ingested_at_field,
            self.source_field,
            self.session_id_field,
            self.metadata_json_field,
        ):
            if not fname or len(fname) > 64:
                raise ValueError("rag field names must be 1..64 characters")
        if not self.source_tag or len(self.source_tag) > 128:
            raise ValueError("rag.source_tag must be 1..128 characters")
        return self


class ModuleClientMtlsMixin(BaseModel):
    """Опциональный клиентский mTLS к бэкенду: все три файла или ни одного."""

    mtls_cert_file: str | None = None
    mtls_key_file: str | None = None
    mtls_root_ca_file: str | None = None
    mtls_key_password: str | None = None

    @model_validator(mode="after")
    def _validate_mtls_file_paths(self) -> Self:
        validate_client_mtls_triplet_files(
            self.mtls_cert_file,
            self.mtls_key_file,
            self.mtls_root_ca_file,
        )
        return self


class OpenSearchSearchAuditLogConfig(BaseModel):
    """Опционально: фиксировать запросы search/count в отдельном индексе для статистики и разборов (несколько MCP — каждый пишет со своим uuid)."""

    enabled: bool = False
    index: str = "sdocs-mcp-search-audit"
    max_query_json_chars: int = 8000
    max_hits_preview: int = 5
    max_source_chars_per_hit: int = 2000

    @model_validator(mode="after")
    def _audit_index_ok(self) -> Self:
        if not self.enabled:
            return self
        idx = self.index.strip()
        if not idx or len(idx) > 255:
            raise ValueError(
                "opensearch.search_audit_log: при enabled=true задайте непустой index (до 255 символов)"
            )
        if any(ch in idx for ch in ("*", "?", " ", ",")):
            raise ValueError(
                "opensearch.search_audit_log.index: недопустимы символы *, ?, пробел, запятая"
            )
        if self.max_query_json_chars < 500 or self.max_query_json_chars > 100_000:
            raise ValueError("opensearch.search_audit_log.max_query_json_chars: допустимо 500..100000")
        if self.max_hits_preview < 0 or self.max_hits_preview > 50:
            raise ValueError("opensearch.search_audit_log.max_hits_preview: допустимо 0..50")
        if self.max_source_chars_per_hit < 200 or self.max_source_chars_per_hit > 50_000:
            raise ValueError("opensearch.search_audit_log.max_source_chars_per_hit: допустимо 200..50000")
        return self


class OpenSearchToolCallAuditConfig(BaseModel):
    """Журнал вызовов MCP tools в OpenSearch: аргументы, ответ MCP, классификация, длительность."""

    enabled: bool = False
    index: str = "sdocs-mcp-tool-audit"
    # Подпись экземпляра в документе; приоритет у переменной окружения SDOCS_MCP_AUDIT_INSTANCE_ID.
    instance_id: str = ""
    # Кто вызвал tool (для HTTP см. caller_http_header; иначе SDOCS_MCP_AUDIT_CALLER_ID или default_caller_id).
    default_caller_id: str = ""
    # Имя HTTP-заголовка с идентификатором клиента (напр. X-Audit-Caller). Задаётся прокси или клиентом.
    caller_http_header: str | None = None
    # Писать в индекс TCP-адрес клиента из ASGI (за reverse proxy может быть IP прокси — см. PROXY protocol / X-Forwarded-For вне scope MCP).
    log_http_client_ip: bool = False
    # Лимиты усечения только на стороне MCP (защита от случайно гигантских тел); OpenSearch обычно выдерживает больше.
    max_arguments_json_chars: int = 1_000_000
    max_result_chars: int = 5_000_000
    auto_create_index: bool = True
    exclude_tools: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _tool_audit_index_ok(self) -> Self:
        if not self.enabled:
            return self
        idx = self.index.strip()
        if not idx or len(idx) > 255:
            raise ValueError(
                "opensearch.tool_call_audit: при enabled=true задайте непустой index (до 255 символов)"
            )
        if any(ch in idx for ch in ("*", "?", " ", ",")):
            raise ValueError(
                "opensearch.tool_call_audit.index: недопустимы символы *, ?, пробел, запятая"
            )
        if self.max_arguments_json_chars < 500 or self.max_arguments_json_chars > 10_000_000:
            raise ValueError("opensearch.tool_call_audit.max_arguments_json_chars: допустимо 500..10000000")
        if self.max_result_chars < 1000 or self.max_result_chars > 20_000_000:
            raise ValueError("opensearch.tool_call_audit.max_result_chars: допустимо 1000..20000000")
        return self


class OpenSearchModuleConfig(ModuleClientMtlsMixin):
    enabled: bool = False
    hosts: list[str] = Field(default_factory=lambda: ["https://localhost:9200"])
    use_ssl: bool = True
    verify_certs: bool = True
    username: str | None = None
    password: str | None = None
    # Если задано — пароль берётся из os.environ[password_env], иначе из password.
    password_env: str | None = None
    request_timeout_seconds: int = 30
    search_max_size: int = 2000
    allow_write: bool = False
    rag: OpenSearchRagConfig = Field(default_factory=OpenSearchRagConfig)
    search_audit_log: OpenSearchSearchAuditLogConfig = Field(default_factory=OpenSearchSearchAuditLogConfig)
    tool_call_audit: OpenSearchToolCallAuditConfig = Field(default_factory=OpenSearchToolCallAuditConfig)

    @model_validator(mode="after")
    def _rag_requires_opensearch(self) -> Self:
        if self.rag.enabled and not self.enabled:
            raise ValueError("opensearch.rag.enabled requires opensearch.enabled")
        return self

    @model_validator(mode="after")
    def _tool_audit_requires_opensearch(self) -> Self:
        if self.tool_call_audit.enabled and not self.enabled:
            raise ValueError("opensearch.tool_call_audit.enabled requires opensearch.enabled")
        return self


class KafkaModuleConfig(ModuleClientMtlsMixin):
    enabled: bool = False
    bootstrap_servers: list[str] = Field(default_factory=lambda: ["localhost:9092"])
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: str | None = None
    topic_allowlist: list[str] = Field(default_factory=list)
    allow_produce: bool = False
    allow_admin: bool = False
    consume_max_messages: int = 200
    consume_max_bytes: int = 4_194_304
    consume_timeout_seconds: int = 10
    produce_max_messages: int = 50
    produce_max_message_bytes: int = 262_144
    list_topics_max: int = 500

    @model_validator(mode="after")
    def _validate_allowlist_when_needed(self) -> KafkaModuleConfig:
        if self.enabled and not self.topic_allowlist:
            raise ValueError("kafka.topic_allowlist must be non-empty when kafka is enabled")
        return self


class PostgresAllowlistedQuery(BaseModel):
    """Именованный SELECT из конфига; MCP-клиенты передают только id (не сырой SQL)."""

    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z][-a-zA-Z0-9_]*$",
        description="Стабильный идентификатор для postgres_allowlisted_query",
    )
    sql: str = Field(min_length=1, description="Один SELECT или WITH … SELECT; только read-only")
    description: str = Field(default="", max_length=500)
    max_rows: int = Field(default=500, ge=1, le=10_000)


class PostgresModuleConfig(ModuleClientMtlsMixin):
    enabled: bool = False
    dsn: str = "postgresql://user:pass@localhost:5432/dbname"
    # Пустой список = не ограничивать имя БД (достаточно dsn). Иначе только перечисленные имена.
    allowed_databases: list[str] = Field(default_factory=list)
    # Если allowed_databases пуст: можно задать префиксы имён БД (например tenant_) вместо списка из 50 имён.
    allowed_database_prefixes: list[str] = Field(default_factory=list)
    # Если оба списка пусты: опционально одно регулярное выражение (re.fullmatch) на имя БД из dsn.
    allowed_database_regex: str | None = None
    schema_allowlist: list[str] = Field(default_factory=lambda: ["public"])
    statement_timeout_seconds: int = 25
    long_query_limit: int = 20
    top_n_tables: int = 20
    allowlisted_queries: list[PostgresAllowlistedQuery] = Field(
        default_factory=list,
        description="Разрешённые по id запросы для postgres_allowlisted_query / каталога",
    )
    # Только если заданы все три mtls_* у postgres: режим libpq для проверки TLS сервера (сертификат клиента опционален — без файлов mTLS не включается).
    mtls_sslmode: Literal["require", "verify-ca", "verify-full"] = "verify-ca"

    @model_validator(mode="after")
    def _validate_postgres_allowlist(self) -> Self:
        rx = (self.allowed_database_regex or "").strip()
        if rx:
            try:
                re.compile(rx)
            except re.error as e:
                raise ValueError(f"postgres.allowed_database_regex invalid: {e}") from e
        if self.allowed_databases and self.allowed_database_prefixes:
            raise ValueError(
                "postgres: задайте либо allowed_databases, либо allowed_database_prefixes, не оба сразу"
            )
        if not self.allowlisted_queries:
            return self
        ids = [q.id for q in self.allowlisted_queries]
        if len(ids) != len(set(ids)):
            raise ValueError("postgres.allowlisted_queries: duplicate id")
        for q in self.allowlisted_queries:
            normalize_and_validate_allowlisted_sql(q.sql)
        return self


class RedisModuleConfig(ModuleClientMtlsMixin):
    enabled: bool = False
    url: str = "redis://localhost:6379/0"
    socket_timeout_seconds: int = 10
    get_max_value_bytes: int = 262_144
    mget_max_keys: int = 10
    hgetall_max_fields: int = 100
    hgetall_max_total_bytes: int = 262_144
    slowlog_max_entries: int = 32
    scan_enabled: bool = False
    scan_prefix_allowlist: list[str] = Field(default_factory=list)
    scan_max_iterations: int = 10
    scan_count: int = 100

    @model_validator(mode="after")
    def _redis_mtls_requires_rediss_url(self) -> Self:
        c = (self.mtls_cert_file or "").strip()
        k = (self.mtls_key_file or "").strip()
        r = (self.mtls_root_ca_file or "").strip()
        if c and k and r and not self.url.strip().lower().startswith("rediss://"):
            raise ValueError("redis: при mtls_* в url нужен протокол rediss://")
        return self


class PrometheusModuleConfig(ModuleClientMtlsMixin):
    enabled: bool = False
    base_url: str = "http://localhost:9090"
    bearer_token: str | None = None
    bearer_token_path: str | None = None
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None
    verify_tls: bool = True
    timeout_seconds: int = 30
    max_query_range_seconds: int = 604_800
    max_step_points: int = 11_000
    min_step_seconds: float = 1.0
    # При false ответы instant/range/series не усекаются на стороне MCP (крупные дашборды и сотни таргетов — норма).
    truncate_responses: bool = False
    max_vector_samples: int = 500
    max_matrix_series: int = 100
    max_points_per_series: int = 5000
    max_series_matches: int = 500
    kafka_metrics_topic: str | None = None


class MailModuleConfig(BaseModel):
    enabled: bool = False
    imap_host: str = "localhost"
    imap_port: int = 993
    imap_ssl: bool = True
    imap_username: str = ""
    imap_username_env: str | None = None
    imap_password: str = ""
    imap_password_env: str = ""
    default_mailbox: str = "INBOX"
    # Имя переменной окружения с адресом From (опционально).
    default_from_env: str | None = None
    list_mailboxes_max: int = 200
    search_max_messages: int = 50
    fetch_max_bytes: int = 262_144
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_ssl: bool = False
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 30
    smtp_username: str = ""
    smtp_username_env: str | None = None
    smtp_password: str = ""
    smtp_password_env: str | None = None

    @model_validator(mode="after")
    def _validate_mail(self) -> Self:
        if not self.enabled:
            return self
        if not (self.imap_password or "").strip() and not (self.imap_password_env or "").strip():
            raise ValueError(
                "mail: задайте imap_password или imap_password_env при enabled: true"
            )
        if not (self.imap_host or "").strip():
            raise ValueError("mail.imap_host must be non-empty when mail is enabled")
        if not (self.smtp_host or "").strip():
            raise ValueError("mail.smtp_host must be non-empty when mail is enabled")
        return self


class SshHostEntry(BaseModel):
    """Один SSH-хост: идентификатор для агента, адрес и способ аутентификации."""

    id: str = Field(min_length=1, description="Стабильный id для выбора в ssh_run_command")
    hostname: str = Field(min_length=1, description="IP или DNS")
    port: int = 22
    username: str = Field(min_length=1)
    description: str = ""
    # Либо ключ, либо пароль из переменной окружения (имя переменной, не значение).
    private_key_path: str | None = None
    private_key_passphrase_env: str | None = None
    password_env: str | None = None


class SshModuleConfig(BaseModel):
    enabled: bool = False
    hosts: list[SshHostEntry] = Field(default_factory=list)
    # Если на хосте нет private_key_path и password_env — подставляется этот ключ (см. docs/SSH_SCALE.md).
    default_private_key_path: str | None = None
    # Подстроки (без учёта регистра): если входят в команду — выполнение запрещено.
    forbidden_substrings: list[str] = Field(default_factory=list)
    # Подмешать рекомендованный набор «средней опасности» (rm -rf, /etc/shadow, …) к forbidden_substrings.
    merge_recommended_substring_blocklist: bool = True
    # Регулярные выражения (Python re): любое совпадение — запрет.
    forbidden_regex: list[str] = Field(default_factory=list)
    # Если false — отклонять команды с ; | && || переносами, обратными кавычками, $( ... ).
    allow_shell_operators: bool = False
    # Доп. встроенные regex (sudo, reboot, dd, curl/wget, интерпретаторы -c/-e и т.д.) — см. ssh_tools.
    builtin_safety_filter: bool = True
    strict_host_key_checking: bool = False
    command_timeout_seconds: int = 120
    max_output_bytes: int = 262_144
    connect_timeout_seconds: int = 30

    @model_validator(mode="after")
    def _apply_default_ssh_key(self) -> Self:
        d = (self.default_private_key_path or "").strip()
        if not d:
            return self
        new_hosts: list[SshHostEntry] = []
        for h in self.hosts:
            if h.private_key_path or h.password_env:
                new_hosts.append(h)
            else:
                new_hosts.append(h.model_copy(update={"private_key_path": d}))
        return self.model_copy(update={"hosts": new_hosts})

    @model_validator(mode="after")
    def _validate_ssh(self) -> SshModuleConfig:
        if not self.enabled:
            return self
        if not self.hosts:
            raise ValueError("ssh.hosts must be non-empty when ssh is enabled")
        for h in self.hosts:
            if h.private_key_path and h.password_env:
                raise ValueError(f"ssh host {h.id!r}: set only one of private_key_path or password_env")
            if not h.private_key_path and not h.password_env:
                raise ValueError(f"ssh host {h.id!r}: need private_key_path or password_env")
        for i, pattern in enumerate(self.forbidden_regex):
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"ssh.forbidden_regex[{i}] invalid: {e}") from e
        return self


class AccessLogConfig(BaseModel):
    """Combined access log (формат nginx) в консоль и файл."""

    enabled: bool = False
    directory: str = "logs"
    filename: str = "mcp-access.log"


class ModulesConfig(BaseModel):
    opensearch: OpenSearchModuleConfig = Field(default_factory=OpenSearchModuleConfig)
    kafka: KafkaModuleConfig = Field(default_factory=KafkaModuleConfig)
    postgres: PostgresModuleConfig = Field(default_factory=PostgresModuleConfig)
    redis: RedisModuleConfig = Field(default_factory=RedisModuleConfig)
    prometheus: PrometheusModuleConfig = Field(default_factory=PrometheusModuleConfig)
    mail: MailModuleConfig = Field(default_factory=MailModuleConfig)
    ssh: SshModuleConfig = Field(default_factory=SshModuleConfig)


class AppConfig(BaseModel):
    modules: ModulesConfig = Field(default_factory=ModulesConfig)
    logging: AccessLogConfig = Field(default_factory=AccessLogConfig)


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _load_ssh_hosts_extra(path: Path) -> list[dict]:
    """Фрагмент для SDOCS_MCP_SSH_HOSTS_FILE: список хостов или { hosts: [...] }."""
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        h = raw.get("hosts")
        if isinstance(h, list):
            return [x for x in h if isinstance(x, dict)]
    return []


def load_config() -> AppConfig:
    path_env = os.environ.get("SDOCS_MCP_CONFIG")
    default_path = Path.cwd() / "config.yaml"
    path = Path(path_env) if path_env else default_path
    data = _load_yaml(path) if path.is_file() else {}
    extra_path = (os.environ.get("SDOCS_MCP_SSH_HOSTS_FILE") or "").strip()
    if extra_path:
        extra_hosts = _load_ssh_hosts_extra(Path(extra_path))
        if extra_hosts:
            modules = data.setdefault("modules", {})
            ssh = modules.setdefault("ssh", {})
            base_hosts = ssh.get("hosts")
            if not isinstance(base_hosts, list):
                base_hosts = []
            ssh["hosts"] = [*base_hosts, *extra_hosts]
    return AppConfig.model_validate(data)
