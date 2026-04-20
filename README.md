# Selectel server watchdog

Скрипт проверяет облачные серверы каждые 30 секунд (или другой интервал) через OpenStack API Selectel и:

- включает серверы со статусом `SHUTOFF`;
- размораживает серверы со статусом `FROZEN` / `SHELVED_OFFLOADED`.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Переменные окружения

Обязательные:

- `OS_AUTH_URL`
- `OS_USERNAME`
- `OS_PASSWORD`
- `OS_PROJECT_ID` **или** `OS_PROJECT_NAME`

Опциональные:

- `OS_USER_DOMAIN_NAME` (по умолчанию `Default`)
- `OS_PROJECT_DOMAIN_NAME` (по умолчанию `Default`)
- `OS_REGION_NAME`
- `OS_COMPUTE_ENDPOINT` (если endpoint compute не удаётся найти через service catalog)

## Запуск

Обычный режим (бесконечный цикл):

```bash
python3 selectel_server_watchdog.py
```

Только один проход (для cron/systemd test):

```bash
python3 selectel_server_watchdog.py --once
```

Проверка без реальных действий:

```bash
python3 selectel_server_watchdog.py --dry-run
```

Свой интервал, например 30 секунд:

```bash
python3 selectel_server_watchdog.py --interval 30
```
