# Тот же pyproject, что и stack-mcp: один pip install -e . + браузеры.
FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

RUN playwright install chromium

ENV MCP_PLAYWRIGHT_HOST=0.0.0.0
ENV MCP_PLAYWRIGHT_PORT=8770

EXPOSE 8770

CMD ["stack-mcp-playwright"]
