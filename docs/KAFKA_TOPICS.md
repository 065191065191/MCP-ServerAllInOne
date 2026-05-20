# Топики Kafka для SDocsMCP

Создайте в кластере и добавьте в `modules.kafka.topic_allowlist` (и `allow_produce: true` где нужна запись).

| Топик | Partition (рекомендация) | Назначение |
|-------|--------------------------|------------|
| `sdocs.prometheus.metrics` | 3+ | Cron/UI: снимки PromQL → Kafka |
| `sdocs.alerts.rules` | 3 | Синхронизация правил и групп Alert между подами |
| `sdocs.alerts.events` | 3 | Сработавшие алерты (`dedup_key` — анти-спам) |
| `sdocs.alerts.lock` | **1** | Consumer group `sdocs-mcp-alerts-leader` — только один под выполняет проверки |

Пример `kafka-topics.sh`:

```bash
kafka-topics.sh --create --topic sdocs.prometheus.metrics --partitions 3 --replication-factor 3
kafka-topics.sh --create --topic sdocs.alerts.rules --partitions 3 --replication-factor 3
kafka-topics.sh --create --topic sdocs.alerts.events --partitions 3 --replication-factor 3
kafka-topics.sh --create --topic sdocs.alerts.lock --partitions 1 --replication-factor 3
```

Проверка в UI: `GET /sdocs/api/kafka/topics-required` (с Bearer при включённом `SDOCS_MCP_UI_TOKEN`).
