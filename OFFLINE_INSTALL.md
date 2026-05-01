# Установка без интернета

В архиве **`dist/stack-mcp-server-offline.zip`** (после сборки) лежит исходный код и папка **`offline-wheels/`** со всеми зависимостями (версии — как разрешит pip на момент сборки, без кэша: `--no-cache-dir`).

## Требования на целевой машине

- **Python 3.11+** (должен быть в PATH).
- Интернет **не** нужен для `pip install`.

### Важно: платформа

Колёса в `offline-wheels/` **платформенные** (например `cp314-win_amd64` для Windows + Python 3.14).
Архив с **этой** машины без доработки подойдёт только **той же связке: та же минорная версия Python, та же ОС и разрядность**.

В архиве есть файл **`dist/BUNDLE_INFO.txt`** — там зафиксированы версия Python и ОС сборки.
Для Linux / macOS / другой версии Python пересоберите архив **на такой же целевой системе** (с интернетом) командой ниже.

## Шаги

1. Распаковать архив в любую папку, перейти в корень проекта (где `pyproject.toml`).

2. Создать окружение и установить только из локальных колёс:

   **Windows (PowerShell):**

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install --no-index --find-links=offline-wheels -e .
   ```

   Чтобы офлайн ещё и **pytest / ruff** (как при сборке архива):

   ```powershell
   pip install --no-index --find-links=offline-wheels -e ".[dev]"
   ```

   **Linux / macOS:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --no-index --find-links=offline-wheels -e .
   ```

   С dev-зависимостями:

   ```bash
   pip install --no-index --find-links=offline-wheels -e ".[dev]"
   ```

3. Конфиг: скопировать `config.example.yaml` → `config.yaml`, выставить переменную:

   ```text
   STACK_MCP_CONFIG=<полный путь к config.yaml>
   ```

4. Запуск MCP и UI — как в `README.md` (`stack-mcp`, `stack-mcp-ui`).

## Пересборка архива (на машине с интернетом)

Из корня репозитория:

```powershell
python scripts\build_offline_bundle.py
```

Без dev-зависимостей (меньше размер):

```powershell
python scripts\build_offline_bundle.py --no-dev
```

Свой путь к ZIP:

```powershell
python scripts\build_offline_bundle.py -o D:\out\mcp-offline.zip
```
