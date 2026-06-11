# S3 MCP — описание

## Назначение

**s3-mcp** — отдельный MCP-сервер в репозитории [MCP-ServerAllInOne](https://github.com/065191065191/MCP-ServerAllInOne), дополняющий **sdocs-mcp**.

Используется для операционной диагностики объектного хранилища **Ceph RGW / S3**:

- список bucket и статистика;
- последние загруженные объекты;
- тест записи;
- **проверка конкретного документа** по пути `bucket` + `key` — только метаданные через HTTP **HEAD** (размер, `Last-Modified`, `ETag`, `Content-Type`). **Тело объекта не читается и не возвращается.**

## Протокол

- **MCP:** Streamable HTTP (по умолчанию), путь `/mcp`
- **S3:** REST API с **AWS Signature Version 4** (`AWS4-HMAC-SHA256`)
- **Зависимости S3-слоя:** только стандартная библиотека Python (`urllib`, `hmac`, `ssl`)

## Отличие от sdocs-mcp

| | sdocs-mcp | s3-mcp |
|---|-----------|--------|
| Порт | 8765 | 8766 |
| Конфиг | YAML `mcp.conf` | env: `S3_*` |
| Модули | Postgres, Kafka, … | только S3 |
| Запуск | `sdocs-mcp` | `s3-mcp` |

Оба сервера можно поднять на одном хосте на разных портах.

## Tools записи (выключены по умолчанию)

| Tool | Конфиг | UI |
|------|--------|-----|
| `s3_put_object` | `modules.s3_mcp.allow_put: true` | Консоль → MCP → S3 MCP |
| `s3_delete_object` | `modules.s3_mcp.allow_delete: true` | то же |

После сохранения в UI процесс `s3-mcp` завершится (watch `S3_MCP_CONFIG_RELOAD_INTERVAL`) — K8s перезапустит под с новым набором tools.

`s3_put_object`: аргументы `bucket`, `key`, `content_base64` (лимит `max_put_bytes`).

## Tools чтения

### `s3_object_metadata(bucket, key)`

Основной сценарий «есть ли документ и когда изменён».

Параметры:

- `bucket` — имя bucket;
- `key` — ключ объекта (путь к файлу), например `reports/2026/q1.pdf`.

Успех (`exists: true`):

- `size_bytes`, `size_human`
- `last_modified` — из заголовка HTTP
- `etag`, `content_type`
- `content_returned: false` — явная гарантия, что содержимое не отдавалось

Отсутствие (`exists: false`, HTTP 404):

- `bucket`, `key` — без полей размера/даты

## Безопасность

- Секреты только через env (`S3_ACCESS_KEY`, `S3_SECRET_KEY`), в MCP-ответах не светятся.
- `s3_write_test` создаёт временный ключ `s3check_<uuid>.tmp` и удаляет его.
- Для продакшена рекомендуется TLS на endpoint и ограничение сетевого доступа к порту MCP.

## Связь с s3_checker

Логика S3-запросов перенесена из проверенного скрипта `s3_checker`:

- list buckets / objects;
- RGW HEAD stats (`X-RGW-Object-Count`, `X-RGW-Bytes-Used`);
- write test PUT→HEAD→DELETE.

Добавлено: **`get_object_metadata`** (HEAD одного объекта) и обёртка MCP tools.
