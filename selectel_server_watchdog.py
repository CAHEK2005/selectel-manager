#!/usr/bin/env python3
"""Watchdog for Selectel/OpenStack cloud servers.

Every N seconds checks server statuses and:
- starts servers in SHUTOFF state;
- unshelves servers in FROZEN/SHELVED_OFFLOADED state.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_INTERVAL = 30
TIMEOUT = 20


@dataclass
class OpenStackConfig:
    auth_url: str
    username: str
    password: str
    project_id: str | None
    project_name: str | None
    user_domain_name: str
    project_domain_name: str
    region_name: str | None
    compute_endpoint: str | None

    @classmethod
    def from_env(cls) -> "OpenStackConfig":
        auth_url = os.getenv("OS_AUTH_URL")
        username = os.getenv("OS_USERNAME")
        password = os.getenv("OS_PASSWORD")

        if not auth_url or not username or not password:
            raise ValueError(
                "OS_AUTH_URL, OS_USERNAME и OS_PASSWORD должны быть заданы в переменных окружения"
            )

        return cls(
            auth_url=auth_url.rstrip("/"),
            username=username,
            password=password,
            project_id=os.getenv("OS_PROJECT_ID"),
            project_name=os.getenv("OS_PROJECT_NAME"),
            user_domain_name=os.getenv("OS_USER_DOMAIN_NAME", "Default"),
            project_domain_name=os.getenv("OS_PROJECT_DOMAIN_NAME", "Default"),
            region_name=os.getenv("OS_REGION_NAME"),
            compute_endpoint=os.getenv("OS_COMPUTE_ENDPOINT"),
        )


class OpenStackClient:
    def __init__(self, cfg: OpenStackConfig) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        self.token: str | None = None
        self.compute_base_url: str | None = cfg.compute_endpoint

    def authenticate(self) -> None:
        auth_payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.cfg.username,
                            "domain": {"name": self.cfg.user_domain_name},
                            "password": self.cfg.password,
                        }
                    },
                },
            }
        }

        if self.cfg.project_id:
            auth_payload["auth"]["scope"] = {"project": {"id": self.cfg.project_id}}
        elif self.cfg.project_name:
            auth_payload["auth"]["scope"] = {
                "project": {
                    "name": self.cfg.project_name,
                    "domain": {"name": self.cfg.project_domain_name},
                }
            }
        else:
            raise ValueError("Нужен OS_PROJECT_ID или OS_PROJECT_NAME для scoped token")

        url = f"{self.cfg.auth_url}/auth/tokens"
        resp = self.session.post(url, json=auth_payload, timeout=TIMEOUT)
        resp.raise_for_status()

        self.token = resp.headers.get("X-Subject-Token")
        if not self.token:
            raise RuntimeError("Не удалось получить X-Subject-Token")

        catalog = resp.json().get("token", {}).get("catalog", [])
        if not self.compute_base_url:
            self.compute_base_url = self._find_compute_endpoint(catalog)

        if not self.compute_base_url:
            raise RuntimeError(
                "Не удалось определить endpoint compute. Укажите OS_COMPUTE_ENDPOINT"
            )

        self.compute_base_url = self.compute_base_url.rstrip("/")
        self.session.headers.update({"X-Auth-Token": self.token})

    def _find_compute_endpoint(self, catalog: list[dict[str, Any]]) -> str | None:
        for service in catalog:
            if service.get("type") != "compute":
                continue

            endpoints = service.get("endpoints", [])
            for ep in endpoints:
                if ep.get("interface") != "public":
                    continue
                if self.cfg.region_name and ep.get("region") != self.cfg.region_name:
                    continue
                return ep.get("url")
        return None

    def list_servers(self) -> list[dict[str, Any]]:
        url = f"{self.compute_base_url}/servers/detail"
        resp = self.session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("servers", [])

    def start_server(self, server_id: str) -> None:
        url = f"{self.compute_base_url}/servers/{server_id}/action"
        resp = self.session.post(url, json={"os-start": None}, timeout=TIMEOUT)
        resp.raise_for_status()

    def unshelve_server(self, server_id: str) -> None:
        url = f"{self.compute_base_url}/servers/{server_id}/action"
        resp = self.session.post(url, json={"unshelve": None}, timeout=TIMEOUT)
        resp.raise_for_status()


def process_servers(client: OpenStackClient, dry_run: bool = False) -> None:
    servers = client.list_servers()
    logging.info("Найдено серверов: %s", len(servers))

    for srv in servers:
        server_id = srv.get("id")
        name = srv.get("name", "<noname>")
        status = (srv.get("status") or "").upper()

        try:
            if status == "SHUTOFF":
                logging.warning("%s (%s) в SHUTOFF -> включаем", name, server_id)
                if not dry_run:
                    client.start_server(server_id)
            elif status in {"FROZEN", "SHELVED_OFFLOADED"}:
                logging.warning("%s (%s) в %s -> размораживаем", name, server_id, status)
                if not dry_run:
                    client.unshelve_server(server_id)
            else:
                logging.info("%s (%s) статус=%s, действий не требуется", name, server_id, status)
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else "<no body>"
            logging.error(
                "Ошибка API при обработке %s (%s), status=%s: %s | body=%s",
                name,
                server_id,
                status,
                exc,
                body,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Каждые N секунд проверяет статусы серверов в Selectel/OpenStack и включает SHUTOFF/FROZEN"
        )
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Интервал опроса в секундах (по умолчанию {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только логировать действия, без выполнения API-запросов на включение",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Сделать только один проход без бесконечного цикла",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if args.interval <= 0:
        logging.error("--interval должен быть больше 0")
        return 2

    try:
        cfg = OpenStackConfig.from_env()
        client = OpenStackClient(cfg)
        client.authenticate()
    except Exception as exc:
        logging.error("Ошибка инициализации клиента: %s", exc)
        return 1

    logging.info("Watchdog запущен, interval=%s sec dry_run=%s", args.interval, args.dry_run)

    while True:
        try:
            process_servers(client, dry_run=args.dry_run)
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else "<no body>"
            logging.error("Ошибка API: %s | body=%s", exc, body)
        except requests.RequestException as exc:
            logging.error("Сетевая ошибка: %s", exc)
        except Exception:
            logging.exception("Непредвиденная ошибка")

        if args.once:
            break
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
