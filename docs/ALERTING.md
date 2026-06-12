# Алертинг по логам OpenSearch

SDocsMCP умеет следить за логами в OpenSearch и отправлять оповещения, когда срабатывает
правило. Управление — через веб-UI (`/alerts-page`). Реализация рассчитана на **несколько
подов** и **не вводит новых Kafka-топиков**.

## Как это работает (несколько подов)

```
UI (любой под) ──POST /api/alerts/rules──► alerts_store + Kafka sdocs.alerts.rules
                                                     │
                  все поды синхронизируют правила в память (sdocs.alerts.rules)
                                                     │
        ЛИДЕР (consumer-group на sdocs.alerts.lock) ─┴─► опрос OpenSearch
                                                          │
                                       срабатывание ──► доставка (email/webhook/telegram)
                                                          └─► Kafka sdocs.alerts.events
```

- **Проверки и доставку выполняет только лидер** — поэтому при N репликах уведомление
  отправляется **один раз** (нет дублей).
- Топики прежние: `sdocs.alerts.rules`, `sdocs.alerts.events`, `sdocs.alerts.lock`.
- Анти-спам: `cooldown_sec` на правило + `dedup_key` в событии.

## Правило

| Поле | Описание |
|------|----------|
| `name` | Название правила |
| `enabled` | Включено/выключено |
| `mcp_source` | Источник; для логов — `opensearch` |
| `index` | Индекс OpenSearch (например `ms-logs`, или `*`) |
| `query` | Условие в синтаксисе `query_string` (например `level:ERROR AND message:*404*`) |
| `condition` | `count_threshold` — количество ≥ порога; `no_logs` — нет логов за окно |
| `threshold` | Порог для `count_threshold` |
| `window_hours` | Окно поиска (часы) |
| `time_field` | Поле времени, обычно `@timestamp` |
| `interval_sec` | Период проверки |
| `cooldown_sec` | Минимальный интервал между уведомлениями |
| `group_id` | Группа получателей (для email) |
| `notify_channel` | `email` / `webhook` / `telegram` / `none` |
| `notify_target` | Получатель: e-mail, URL webhook или `chat_id`; пусто → из группы/конфига |

## Куда слать (конфиг)

```yaml
modules:
  alerting:
    enabled: true
    kafka:
      enabled: true
      bootstrap_servers: [kafka-alerts.internal:9092]
      topic_allowlist: [sdocs.alerts.rules, sdocs.alerts.events, sdocs.alerts.lock]
      allow_produce: true
    notify:
      default_channel: email      # email | webhook | telegram | none
      webhook_url: "https://hooks.example/alerts"
      webhook_timeout_seconds: 10
      telegram_bot_token_env: TELEGRAM_BOT_TOKEN   # имя env, не сам токен
      telegram_chat_id: "-100123456789"
  mail:
    enabled: true                 # требуется для канала email
    smtp_host: smtp.internal
    smtp_port: 587
    smtp_starttls: true
    smtp_username: sdocs_mcp
    smtp_password_env: SMTP_PASSWORD
```

Канал и получателя из `notify` можно переопределить в каждом правиле
(`notify_channel` / `notify_target`).

### Каналы доставки

- **email** — через `modules.mail` (SMTP). Получатель: `notify_target` правила, иначе
  `emails` из группы (`group_id`). Несколько адресов — через запятую/точку с запятой.
- **webhook** — `POST` JSON `{subject, text, alert}` на `notify_target` или
  `notify.webhook_url`.
- **telegram** — `sendMessage` ботом `notify.telegram_bot_token[_env]` в чат
  `notify_target` или `notify.telegram_chat_id`.
- **none** — не слать (только журнал и событие в Kafka).

## Журнал и логирование

- В UI — таблица **«Журнал доставки»** (последние попытки на поде-лидере: успех/ошибка,
  канал, получатель, деталь).
- API: `GET /api/alerts/notify-log?limit=50`.
- В логах процесса (`sdocs_mcp.alerts_notify`): `INFO` при успехе, `WARNING` при ошибке.

## Группы получателей (JSON в UI)

```json
[
  { "id": "support", "name": "Сопровождение", "emails": "oncall@example.com", "hours_msk": "08:00-18:00" }
]
```

## Пример

| Поле | Значение |
|------|----------|
| Индекс | `ms-logs` |
| Запрос | `level:ERROR AND message:*404*` |
| Условие | количество ≥ 2 за 1 ч |
| Канал | email |
| Получатель | пусто → `emails` группы `support` |
