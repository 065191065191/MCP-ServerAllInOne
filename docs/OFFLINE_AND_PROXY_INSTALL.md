# Сборка и установка в закрытом контуре и через прокси-шлюз

Инструкция покрывает два типичных сценария:


| Сценарий               | Суть                                                                                                                                |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **A. Прокси-шлюз**     | Прямого выхода в интернет нет, но есть **корпоративный HTTP(S)-прокси** (или аналог) к реестрам и PyPI.                             |
| **B. Полная изоляция** | Интернета нет даже через прокси; артефакты **заранее выносятся** на площадку (носитель, артефактный реестр, Git без внешних fetch). |


Версия в примерах: подставьте свою (см. `pyproject.toml`) вместо `**0.6.0`**.

---

## 1. Что в итоге нужно на целевой площадке

**Минимум для Docker-эксплуатации (рекомендуется в контуре B):**

- Файл `**sdocs-mcp-ui-0.6.0.tar`** (`docker save` готового образа).
- Ваш `**config.yaml**` (из `config.example.yaml` / `deploy/config.production.example.yaml`) и при необходимости `**deploy/.env**`.
- Docker (или containerd + nerdctl / podman по политике ИБ).

**Для установки в venv без Docker:**

- Каталог с исходниками (или минимальный архив репозитория).
- Каталог `**wheelhouse/`** со всеми wheels зависимостей (см. **§3.2**).
- Python **≥ 3.11** на целевой машине.

**Для сборки образа внутри контура B без готового tar:**

- Базовый образ `**python:3.12-slim-bookworm`** (или ваш `BASE_IMAGE`) уже загружен локально (`docker load`).
- Локальный `**wheelhouse**` и доработанный способ сборки (см. **§4**) — сложнее, чем перенос готового образа.

---

## 2. Сценарий A: сборка при доступе только через прокси

Задайте переменные (пример; хост и порт возьмите у сетевиков):

```bash
export HTTP_PROXY=http://proxy.example.corp:8080
export HTTPS_PROXY=http://proxy.example.corp:8080
export NO_PROXY=localhost,127.0.0.1,::1,.example.corp,.svc.cluster.local
```

### 2.1. Docker: pull базового образа и `docker build`

Чтобы **daemon** Docker тянул слои через прокси (Linux), в документации Docker описан файл `**/etc/systemd/system/docker.service.d/http-proxy.conf`** с `Environment=HTTP_PROXY=...` — настройте по регламенту вашей ОС.

Сборка с передачей прокси в этап `**RUN**` (на время установки `pip` и `apt`/`dnf` внутри Dockerfile):

```bash
cd /path/to/mcp-server
docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -f deploy/Dockerfile \
  -t sdocs-mcp-ui:0.6.0 .
```

Другой базовый образ (внутренний зеркальный реестр):

```bash
docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  --build-arg BASE_IMAGE=registry.example.corp/python:3.12-slim \
  -f deploy/Dockerfile \
  -t sdocs-mcp-ui:0.6.0 .
```

Сохраните образ для переноса в более жёсткий контур:

```bash
docker save sdocs-mcp-ui:0.6.0 -o sdocs-mcp-ui-0.6.0.tar
```

### 2.1.1. Прокси с логином и паролем (секреты при сборке)

**Не используйте** `--build-arg PROXY_PASSWORD=...` для пароля: значения build-arg часто попадают в **метаданные образа** и в кэш — это утечка.

Правильный способ — **BuildKit mount secret**: файл с URL прокси передаётся только на время шага `RUN`, в финальный слой не копируется.

1. В корне репозитория (файл в `**.gitignore`**, не коммитьте):
  ```bash
   # Одна строка; спецсимволы в логине/пароле (@, :, /, пробел) — URL-encode (%40, %3A, …)
   printf '%s' 'http://myuser:mypassword@proxy.example.corp:8080' > build-proxy.url
  ```
   Учётная запись вида `DOMAIN\user` в URL обычно задают как `http://DOMAIN%5Cuser:password@host:port` (уточните формат у ИБ).
2. Сборка с альтернативным Dockerfile (в репозитории: `**deploy/Dockerfile.buildkit-proxy**`):
  ```bash
   cd /path/to/mcp-server
   DOCKER_BUILDKIT=1 docker build \
     --secret id=build_proxy,src=build-proxy.url \
     -f deploy/Dockerfile.buildkit-proxy \
     -t sdocs-mcp-ui:0.6.0 .
  ```
   Параллельно **daemon** Docker по-прежнему должен уметь тянуть **базовый образ** (`FROM`): при необходимости настройте прокси для daemon (как в §2.1) **или** выполните `docker pull` / `docker load` базы заранее с той же машины, где уже есть образ.
3. **Docker Compose** (фрагмент, Compose v2 с BuildKit):
  ```yaml
   services:
     sdocs-mcp-ui:
       build:
         context: ..
         dockerfile: deploy/Dockerfile.buildkit-proxy
         secrets:
           - build_proxy
       # ...
   secrets:
     build_proxy:
       file: ../build-proxy.url
  ```
   Путь к `file:` задайте относительно расположения compose-файла; удобно хранить `build-proxy.url` **вне** репозитория и указать абсолютный путь, если политика ИБ запрещает файл рядом с клоном.

**Время работы контейнера** (приложение ходит в интернет через прокси): задайте `HTTP_PROXY` / `HTTPS_PROXY` в `environment` или `env_file` compose — это уже **не** Dockerfile, секреты подставляйте из vault/CI, не печатайте в compose в репозитории.

### 2.2. Установка в venv через прокси (`pip`)

```bash
export HTTP_PROXY=... HTTPS_PROXY=... NO_PROXY=...
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

При внутреннем **PyPI-зеркале**:

```bash
pip install -e . --index-url https://pypi-mirror.example.corp/simple --trusted-host pypi-mirror.example.corp
```

### 2.3. Важно: прокси не должен «ломать» доступ к вашим бэкендам

В **контейнере** или на хосте, если заданы `HTTP_PROXY`/`HTTPS_PROXY`, часть HTTP-клиентов может пытаться ходить к **OpenSearch / Prometheus** через прокси. Для внутренних имен и подсетей добавьте их в `**NO_PROXY`** (список хостов IP ваших кластеров БД, OpenSearch, Kafka bootstrap).

Пример для `docker run` / compose:

```yaml
environment:
  HTTP_PROXY: http://proxy.example.corp:8080
  HTTPS_PROXY: http://proxy.example.corp:8080
  NO_PROXY: localhost,127.0.0.1,opensearch.internal,kafka.internal,10.0.0.0/8
```

(Точный синтаксис CIDR в `NO_PROXY` зависит от библиотек; при сомнениях перечисляйте **конкретные FQDN**.)

---

## 3. Сценарий B: закрытый контур без интернета

### 3.1. Рекомендуемый путь: готовый образ

На машине **с доступом** (или по сценарию A через прокси):

1. Соберите образ: см. раздел 2 или `[deploy/README.md](../deploy/README.md)`.
2. Выполните:
  `docker save sdocs-mcp-ui:0.6.0 -o sdocs-mcp-ui-0.6.0.tar`
3. Перенесите `**tar`**, конфиги и `.env` на изолированную площадку.
4. На целевой машине:
  `docker load -i sdocs-mcp-ui-0.6.0.tar`
5. Запуск: как в `[deploy/README.md](../deploy/README.md)` (`docker run` или `docker compose -f deploy/docker-compose.prod.yml`).

Интернет и прокси на площадке **не нужны**.

### 3.2. Без Docker: venv и wheelhouse

На машине с доступом к PyPI (или к внутреннему зеркалу), из корня репозитория:

```bash
mkdir -p wheelhouse
pip wheel --wheel-dir wheelhouse -e .
```

При необходимости укажите зеркало:  
`pip wheel --wheel-dir wheelhouse -e . --index-url https://pypi-mirror.example.corp/simple`

Дополнительно зафиксируйте dev-инструменты, если нужны тесты на площадке:

```bash
pip wheel --wheel-dir wheelhouse -e ".[dev]"
```

Упакуйте `**wheelhouse/**`, каталог `**src/**`, `**pyproject.toml**`, `**README.md**`, скрипты `**scripts/install.sh**` — переносите архивом.

На **изолированной** машине (только Python, без сети на PyPI):

```bash
./scripts/install.sh --offline ./wheelhouse
# или: . .venv/bin/activate && pip install --no-index --find-links=wheelhouse -e .
```

Запуск: `**sdocs-mcp**` / `**sdocs-mcp-ui**`, конфиг через `**SDOCS_MCP_CONFIG**`.

---

## 4. Сборка образа уже внутри изоляции (если нельзя перенести готовый tar)

Имеет смысл только при жёсткой политике «собирать только здесь».

1. Перенесите на площадку базовый образ: на связанной машине
  `docker pull python:3.12-slim-bookworm` → `docker save` → на изолированной `docker load`.
2. Перенесите исходники и `**wheelhouse**`, собранный как в §3.2.
3. Локально в контуре добавьте в Dockerfile этап: скопировать каталог `wheelhouse` в образ и выполнить
  `pip install --no-index --find-links=/wheelhouse .` вместо обычного `pip install .` из интернета. Удобнее держать такой вариант как отдельный файл (например `deploy/Dockerfile.offline`) в вашей системе контроля версий контура, не обязательно в апстриме.

Проще и типичнее для ИБ: **один раз** собрать образ в DMZ и передавать только `**docker save`**.

---

## 5. Проксирование «шлюзом» к бэкендам (не путать с HTTP_PROXY)

Если доступ к OpenSearch/Kafka идёт **через отдельный шлюз** (reverse proxy, SSH tunnel, service mesh), это настраивается в `**config.yaml`**: `hosts`, URL Prometheus, `bootstrap_servers` — указываете **имя/порт шлюза**, как принято в вашем контуре. Это не требует `HTTP_PROXY` для MCP, если клиенты ходят напрямую на шлюз по разрешённому маршруту.

---

## 6. Чеклист после установки

- `docker run ...` или compose: `**curl -fsS http://127.0.0.1:8888/health`** (порт из вашего bind).
- MCP: `**curl**` к `**/mcp**` по вашему транспорту или проверка из IDE.
- Логи контейнера без ошибок импорта и подключения к `**SDOCS_MCP_CONFIG**`.

Детали прод-деплоя: `**[deploy/README.md](../deploy/README.md)**`, возможности модулей: `**[CAPABILITIES.md](CAPABILITIES.md)**`.