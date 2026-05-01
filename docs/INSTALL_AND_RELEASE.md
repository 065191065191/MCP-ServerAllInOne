# Установка и релизные сборки

Документ описывает установку **stack-mcp-server**, офлайн-режим и **три** готовых **архивных сборки** (`build-release.sh` / `build-release.ps1`).

## Требования

- **Python 3.11+**
- Linux / macOS / **WSL** (bash-скрипты ориентированы на Unix; venv с `bin/pip`)
- Для сборки: `tar`, `python3`; сеть для `pip download` нужна **только** если включена сборка **runtime** с каталогом `wheels/` (офлайн-пакет). Сборка **runtime-online** качает зависимости уже на целевой машине при `install.sh`.

## Быстрая установка из клона репозитория

```bash
chmod +x scripts/install.sh
./scripts/install.sh
source .venv/bin/activate
cp config.example.yaml config.yaml
export STACK_MCP_CONFIG="$PWD/config.yaml"
stack-mcp
```

UI (отдельный процесс):

```bash
stack-mcp-ui
```

## Скрипт `scripts/install.sh`

| Режим | Команда |
|--------|---------|
| Онлайн, venv `.venv` | `./scripts/install.sh` |
| Другой каталог venv | `./scripts/install.sh --venv myenv` |
| Офлайн (только wheel из каталога) | `./scripts/install.sh --offline ./wheels` |
| Справка | `./scripts/install.sh --help` |

Скрипт сам находит корень проекта: либо рядом лежит `pyproject.toml` (как в минимальной сборке), либо скрипт в `scripts/` и корень на уровень выше.

**Офлайн:** виртуальное окружение всё равно нужно создать один раз (`python3 -m venv .venv`); в изолированных средах без сети убедитесь, что в venv есть `pip` (`python3 -m ensurepip`).

## Три сборки: `scripts/build-release.sh` / `build-release.ps1`

Из корня репозитория:

**Windows (PowerShell):**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build-release.ps1
```

**Linux / macOS / Git Bash:**

```bash
chmod +x scripts/build-release.sh
./scripts/build-release.sh
```

В каталоге **`release/`** появятся **три** `.tar.gz` (сами архивы в `.gitignore`, папка и `README` в репозитории):

### 1. Полная сборка (`stack-mcp-server-full-<version>-<stamp>.tar.gz`)

Входит **весь проект**, пригодный для разработки и CI:

- исходники `src/`, `tests/`, `docs/`, `deploy/`, `docker/`, `scripts/`
- `pyproject.toml`, `docker-compose.yml`, `.github/workflows`, примеры конфигов

**Не входит:** `.git`, `.venv`, кэши тестов/линтера, `dist/`, `build/`, `release/`, `logs/*.log`.

### 2. Минимальная runtime-сборка (`stack-mcp-server-runtime-<version>-<stamp>.tar.gz`)

Только то, что нужно **поставить и запустить** MCP/UI на сервере:

| Путь | Назначение |
|------|------------|
| `src/` | код пакета |
| `pyproject.toml` | метаданные и зависимости |
| `README.md` | обзор и быстрый старт |
| `config.example.yaml` | шаблон конфигурации |
| `docs/CAPABILITIES.md` | матрица инструментов и лимитов |
| `wheels/` | зависимости + `pip`, `setuptools`, `wheel` для офлайн-установки |
| `install.sh` | установщик (копия из репозитория) |
| `BUNDLE.txt` | краткое описание состава |

**Не входит:** тесты, Docker-файлы, CI, демо-compose (их берите из полной сборки при необходимости).

### 3. Runtime-online (`stack-mcp-server-runtime-online-<version>-<stamp>.tar.gz`)

Тот же состав, что у п. 2, но **без каталога `wheels/`** — никаких заранее скачанных wheel на этапе сборки. Установка только **`./install.sh`** при доступе к **PyPI**. Размер архива намного меньше.

### Распаковка runtime / runtime-online и установка

```bash
# с wheels (офлайн по желанию)
tar -xzf stack-mcp-server-runtime-*.tar.gz
cd stack-mcp-server-runtime-*
./install.sh
# ./install.sh --offline ./wheels

# без wheels — только онлайн
tar -xzf stack-mcp-server-runtime-online-*.tar.gz
cd stack-mcp-server-runtime-online-*
./install.sh

source .venv/bin/activate
```

## Проверка после установки

```bash
python -m stack_mcp --help
# тесты — только в полной сборке:
# pip install -e ".[dev]" && pytest
```

## Гигиена репозитория

В **`.gitignore`**: `release/*.tar.gz`, кэши `.pytest_cache`/`.ruff_cache`, артефакты `dist/`/`build/`, логи в `logs/*.log`. Каталог `logs/` сохраняется с `.gitkeep`.

## См. также

- [README.md](../README.md) — обзор, переменные окружения, Docker-стенд
- [CAPABILITIES.md](CAPABILITIES.md) — инструменты MCP и ограничения
- [deploy/README.md](../deploy/README.md) — продакшен-выкладка
