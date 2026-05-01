# Журнал изменений

Формат основан на принципах [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Версии соответствуют [семантическому версионированию](https://semver.org/lang/ru/).

## [0.2.0] — 2026-05-02

### Добавлено

- Учёт автора проекта в метаданных пакета (`pyproject.toml`).
- Файл `CHANGELOG.md` и правило процесса релиза для агента (`.cursor/rules/`).
- Синхронизация `stack_mcp.__version__` с версией пакета **0.2.0**.

### Прочее

- Базовая линия кода: MCP по HTTP, модули OpenSearch, Kafka, PostgreSQL, Redis, Prometheus, опциональный браузерный MCP (Playwright), UI и Docker-окружение — см. `README.md`.
