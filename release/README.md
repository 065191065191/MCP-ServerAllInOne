# Сборки (архивы)

После `.\scripts\build-release.ps1` или `./scripts/build-release.sh` здесь появляются **три** файла:

| Файл | Описание |
|------|----------|
| `sdocs-mcp-full-*.tar.gz` | Полный проект (без `.venv`, кэшей, `.git`) |
| `sdocs-mcp-runtime-*.tar.gz` | Минимум для продакшена **+ каталог `wheels/`** (можно `./install.sh --offline ./wheels`) |
| `sdocs-mcp-runtime-online-*.tar.gz` | Тот же минимум **без** заранее скачанных пакетов — только `./install.sh` с доступом к **PyPI** |

**Создать архивы**

- Windows: `.\scripts\build-release.ps1`
- Linux / macOS / Git Bash: `./scripts/build-release.sh`

Файлы `*.tar.gz` не коммитятся (`.gitignore`).

**Установка**

- Из **runtime** (с wheels): `./install.sh` или `./install.sh --offline ./wheels`
- Из **runtime-online**: только `./install.sh` (нужен интернет к PyPI)

Корневой **`install.sh`** в репозитории — обёртка над `scripts/install.sh`.
