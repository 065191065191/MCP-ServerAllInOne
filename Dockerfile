# См. deploy/Dockerfile — канонический прод-образ (UI + бинарники MCP).
# Сборка из корня: docker build -f deploy/Dockerfile -t stack-mcp:0.3.2 .

ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
      apt-get update; \
      apt-get install -y --no-install-recommends curl; \
      rm -rf /var/lib/apt/lists/*; \
    elif command -v microdnf >/dev/null 2>&1; then \
      microdnf install -y curl; \
      microdnf clean all; \
    elif command -v dnf >/dev/null 2>&1; then \
      dnf install -y curl; \
      dnf clean all; \
    else \
      echo "BASE_IMAGE: нет apt-get/microdnf/dnf — установите curl вручную или смените BASE_IMAGE." >&2; \
      exit 1; \
    fi

RUN set -eux; \
    if id -u stackmcp >/dev/null 2>&1; then \
      :; \
    else \
      NOLOGIN="$(command -v nologin || true)"; \
      if [ -z "$NOLOGIN" ]; then NOLOGIN=/bin/false; fi; \
      useradd --system --uid 10001 --home-dir /app --create-home --shell "$NOLOGIN" stackmcp; \
    fi

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && mkdir -p /app/data/logs \
    && chown -R stackmcp:stackmcp /app

USER stackmcp
LABEL org.opencontainers.image.title="stack-mcp-server"
LABEL org.opencontainers.image.version="0.3.2"

# Опционально при запуске контейнера: STACK_MCP_STATELESS_HTTP=true — см. README.
ENV PYTHONUNBUFFERED=1 \
    STACK_MCP_UI_HOST=0.0.0.0 \
    STACK_MCP_UI_PORT=8888 \
    STACK_MCP_EMBED_MCP=true

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8888/health || exit 1

CMD ["stack-mcp-ui"]
