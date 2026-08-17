#!/usr/bin/env python3
"""CLI для coding agent: получить полный контекст задачи по DEV-ID."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def load_env(path: str) -> None:
    env_path = os.path.abspath(path)
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Не удалось подключиться к DevBoard: {exc.reason}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Получить контекст задачи DevBoard")
    parser.add_argument("command", choices=["get"], help="get — полный контекст задачи")
    parser.add_argument("task_id", help="ID задачи, например DEV-52")
    parser.add_argument(
        "--url",
        default=os.environ.get("DEVBOARD_URL", "http://127.0.0.1:8080"),
        help="Базовый URL DevBoard",
    )
    parser.add_argument("--env-file", default=".env", help="Путь к .env")
    args = parser.parse_args()
    load_env(args.env_file)
    token = os.environ.get("DEVBOARD_API_TOKEN") or os.environ.get("DEVBOARD_PASSWORD")
    if not token:
        raise SystemExit("Задайте DEVBOARD_API_TOKEN или DEVBOARD_PASSWORD")
    payload = request_json(
        f"{args.url.rstrip('/')}/api/tasks/{args.task_id}/agent-context",
        token,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
