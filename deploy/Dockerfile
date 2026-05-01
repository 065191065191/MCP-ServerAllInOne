# Образ: stack-mcp-ui (порт 8888) и stack-mcp по HTTP (по умолчанию 8765, /mcp).
# Сборка: docker build -f deploy/Dockerfile -t stack-mcp-ui:0.2.2 .
FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin stackmcp

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

USER stackmcp
ENV PYTHONUNBUFFERED=1 \
    STACK_MCP_UI_HOST=0.0.0.0 \
    STACK_MCP_UI_PORT=8888

EXPOSE 8888 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8888/health || exit 1

CMD ["stack-mcp-ui"]
