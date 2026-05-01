# Сборки (архивы)

После `.\scripts\build-release.ps1` или `./scripts/build-release.sh` здесь появляются **три** файла:

| Файл | Описание |
|------|----------|
| `stack-mcp-server-full-*.tar.gz` | Полный проект (без `.venv`, кэшей, `.git`) |
| `stack-mcp-server-runtime-*.tar.gz` | Минимум для продакшена **+ каталог `wheels/`** (можно `./install.sh --offline ./wheels`) |
| `stack-mcp-server-runtime-online-*.tar.gz` | Тот же минимум **без** заранее скачанных пакетов — только `./install.sh` с доступом к **PyPI** |

**Создать архивы**

- Windows: `.\scripts\build-release.ps1`
- Linux / macOS / Git Bash: `./scripts/build-release.sh`

Файлы `*.tar.gz` не коммитятся (`.gitignore`).

**Установка**

- Из **runtime** (с wheels): `./install.sh` или `./install.sh --offline ./wheels`
- Из **runtime-online**: только `./install.sh` (нужен интернет к PyPI)

Корневой **`install.sh`** в репозитории — обёртка над `scripts/install.sh`.
