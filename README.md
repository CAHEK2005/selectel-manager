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

## Запуск вручную

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

## Запуск как системный сервис (systemd)

Ниже шаги для Linux с systemd. В таком режиме watchdog работает в фоне и не зависит от SSH-сессии.

1. Создайте директорию приложения:

```bash
sudo mkdir -p /opt/selectel-server-watchdog
```

2. Скопируйте файлы:

```bash
sudo cp selectel_server_watchdog.py requirements.txt /opt/selectel-server-watchdog/
sudo cp selectel-server-watchdog.service /etc/systemd/system/
sudo cp selectel-server-watchdog.env.example /etc/selectel-server-watchdog.env
```

3. Установите зависимость `requests` в системный Python:

```bash
sudo python3 -m pip install -r /opt/selectel-server-watchdog/requirements.txt
```

4. Отредактируйте `/etc/selectel-server-watchdog.env` и заполните реальные креды Selectel.

5. Включите и запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now selectel-server-watchdog.service
```

6. Проверка статуса и логов:

```bash
sudo systemctl status selectel-server-watchdog.service
sudo journalctl -u selectel-server-watchdog.service -f
```

### Обновление конфигурации

После изменения `/etc/selectel-server-watchdog.env` перезапустите сервис:

```bash
sudo systemctl restart selectel-server-watchdog.service
```
