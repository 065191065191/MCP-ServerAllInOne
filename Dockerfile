# См. deploy/Dockerfile — канонический прод-образ (UI + бинарники MCP), тег sdocs-mcp-ui:0.6.0.
# Из корня: docker build -f deploy/Dockerfile -t sdocs-mcp-ui:0.6.0 .  |  из этого файла: docker build -t sdocs-mcp-ui:0.6.0 .

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
    if id -u sdocsmcp >/dev/null 2>&1; then \
      :; \
    else \
      NOLOGIN="$(command -v nologin || true)"; \
      if [ -z "$NOLOGIN" ]; then NOLOGIN=/bin/false; fi; \
      useradd --system --uid 10001 --home-dir /app --create-home --shell "$NOLOGIN" sdocsmcp; \
    fi

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && mkdir -p /app/data/logs \
    && chown -R sdocsmcp:sdocsmcp /app

USER sdocsmcp
LABEL org.opencontainers.image.title="SDocsMCP"
LABEL org.opencontainers.image.version="0.6.0"

# Опционально при запуске контейнера: SDOCS_MCP_STATELESS_HTTP=true — см. README.
ENV PYTHONUNBUFFERED=1 \
    SDOCS_MCP_UI_HOST=0.0.0.0 \
    SDOCS_MCP_UI_PORT=8888 \
    SDOCS_MCP_EMBED_MCP=true

EXPOSE 8888

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8888/health || exit 1

CMD ["sdocs-mcp-ui"]
