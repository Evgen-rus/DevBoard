#!/usr/bin/env python3
"""CLI для coding agent: получить полный контекст задачи по DEV-ID."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

TASK_ID_PATTERN = re.compile(r"^([A-Za-z]+)-(\d+)$")
SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
MAX_FILE_BYTES = 25 * 1024 * 1024
JSON_TIMEOUT = 30
FILE_TIMEOUT = 120


class MaterializeError(ValueError):
    """Нельзя сохранить локальную копию задачи."""


def default_client_config() -> Path:
    return Path.home() / ".devboard" / "client.env"


def default_cache_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "DevBoard" / "tasks"
    return Path.home() / ".cache" / "devboard" / "tasks"


def load_env(path: str | Path | None) -> None:
    if path is None:
        return
    env_path = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_task_id(task_id: str) -> str:
    raw = (task_id or "").strip()
    if not TASK_ID_PATTERN.match(raw):
        raise MaterializeError("Ожидался ID вида DEV-52")
    return raw


def safe_filename(name: str) -> str:
    original = Path(name or "").name.strip() or "file"
    if original in {".", ".."}:
        original = "file"
    stem = Path(original).stem
    suffix = Path(original).suffix[:12]
    cleaned = SAFE_NAME.sub("_", stem).strip("._") or "file"
    return f"{cleaned[:80]}{suffix.lower()}"


def unique_filename(name: str, used: set[str]) -> str:
    candidate = safe_filename(name)
    if candidate not in used:
        return candidate
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    index = 2
    while True:
        next_name = f"{stem}-{index}{suffix}"
        if next_name not in used:
            return next_name
        index += 1


def destination_file(directory: Path, filename: str) -> Path:
    folder = directory.resolve()
    path = (folder / Path(filename).name).resolve()
    if folder not in path.parents:
        raise MaterializeError("Некорректное имя файла")
    return path


def request_json(url: str, token: str) -> dict:
    payload = _request(url, token, timeout=JSON_TIMEOUT)
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("DevBoard вернул не JSON") from exc


def request_bytes(url: str, token: str) -> bytes:
    return _request(url, token, timeout=FILE_TIMEOUT)


def _request(url: str, token: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, */*",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Не удалось подключиться к DevBoard: {exc.reason}") from exc
    if len(data) > MAX_FILE_BYTES:
        raise SystemExit("Файл больше 25 МБ")
    return data


def resolve_attachment_url(base_url: str, task_id: str, item: dict[str, Any]) -> str:
    filename = Path(str(item.get("filename") or "file")).name
    relative = item.get("url")
    if isinstance(relative, str) and relative.startswith(("http://", "https://")):
        return relative
    if isinstance(relative, str) and relative.startswith("/"):
        prefix, separator, name = relative.rpartition("/")
        if separator:
            return base_url.rstrip("/") + prefix + "/" + quote(name)
    return (
        f"{base_url.rstrip('/')}/api/tasks/{quote(task_id)}/attachments/{quote(filename)}"
    )


def local_attachment_path(task_dir: Path, filename: str) -> str:
    return str((task_dir / filename).resolve())


def materialize_context(
    payload: dict[str, Any],
    *,
    dest_root: Path,
    download: Callable[[str], bytes],
    base_url: str,
    include_audio: bool = True,
) -> dict[str, Any]:
    """Сохраняет agent-context и вложения в dest_root/<task_id>/."""
    task_id = parse_task_id(str(payload.get("id") or ""))
    dest_root.mkdir(parents=True, exist_ok=True)
    final_dir = dest_root / task_id
    staging = dest_root / f".incoming-{task_id}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    used_names = {"task.json"}
    attachments: list[dict[str, Any]] = []
    downloaded: list[str] = []
    skipped: list[str] = []
    for item in payload.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        original_name = str(item.get("filename") or "file")
        stored_name = unique_filename(original_name, used_names)
        used_names.add(stored_name)
        entry = dict(item)
        entry["filename"] = stored_name
        if str(item.get("kind") or "") == "audio" and not include_audio:
            entry["local_path"] = None
            entry["downloaded"] = False
            attachments.append(entry)
            skipped.append(stored_name)
            continue
        target = destination_file(staging, stored_name)
        data = download(resolve_attachment_url(base_url, task_id, item))
        if not data:
            raise MaterializeError(f"Пустое вложение: {original_name}")
        target.write_bytes(data)
        entry["local_path"] = local_attachment_path(final_dir, stored_name)
        entry["downloaded"] = True
        attachments.append(entry)
        downloaded.append(stored_name)

    context = dict(payload)
    context["attachments"] = attachments
    task_json = staging / "task.json"
    task_json.write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if final_dir.exists():
        shutil.rmtree(final_dir)
    staging.rename(final_dir)
    return {
        "task_id": task_id,
        "task_dir": final_dir,
        "task_json": final_dir / "task.json",
        "files": downloaded,
        "skipped": skipped,
        "context": context,
    }


def print_materialize_summary(result: dict[str, Any]) -> None:
    lines = [
        f"Контекст сохранён: {result['task_json'].resolve()}",
    ]
    files = result["files"]
    if files:
        lines.append("Файлы:")
        for name in files:
            lines.append(f"  {(result['task_dir'] / name).resolve()}")
    else:
        lines.append("Скачанных вложений нет.")
    if result["skipped"]:
        lines.append("Не скачаны по выбранной политике:")
        for name in result["skipped"]:
            lines.append(f"  {name}")
    sys.stdout.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Получить контекст задачи DevBoard")
    parser.add_argument("command", choices=["get"], help="get — полный контекст задачи")
    parser.add_argument("task_id", help="ID задачи, например DEV-52")
    parser.add_argument("--url", default=None, help="Базовый URL DevBoard")
    parser.add_argument(
        "--config",
        default=str(default_client_config()),
        help="Клиентский env-файл (по умолчанию ~/.devboard/client.env)",
    )
    parser.add_argument("--env-file", default=None, help="Дополнительный env-файл")
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="Скачать JSON и вложения в локальный кэш",
    )
    parser.add_argument("--dest-root", default=None, help="Корень локального кэша")
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="Не скачивать аудио, если для работы достаточно транскрипта",
    )
    args = parser.parse_args()
    load_env(args.config)
    load_env(args.env_file)
    base_url = (
        args.url
        or os.environ.get("DEVBOARD_URL")
        or "http://127.0.0.1:8080"
    ).rstrip("/")
    token = os.environ.get("DEVBOARD_API_TOKEN") or os.environ.get("DEVBOARD_PASSWORD")
    if not token:
        raise SystemExit("Задайте DEVBOARD_API_TOKEN или DEVBOARD_PASSWORD")
    try:
        task_id = parse_task_id(args.task_id)
    except MaterializeError as exc:
        raise SystemExit(str(exc)) from exc
    payload = request_json(
        f"{base_url}/api/tasks/{quote(task_id)}/agent-context",
        token,
    )
    if not isinstance(payload, dict):
        raise SystemExit("Некорректный ответ agent-context")
    payload.setdefault("id", task_id)
    if args.materialize:
        def download(url: str) -> bytes:
            return request_bytes(url, token)

        try:
            result = materialize_context(
                payload,
                dest_root=Path(args.dest_root).expanduser() if args.dest_root else default_cache_root(),
                download=download,
                base_url=base_url,
                include_audio=not args.skip_audio,
            )
        except MaterializeError as exc:
            raise SystemExit(str(exc)) from exc
        print_materialize_summary(result)
        return
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
