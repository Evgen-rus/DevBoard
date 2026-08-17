"""Локальное хранение вложений. GitHub хранит только ссылки и метаданные."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from mapping import detect_kind

SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")
MAX_FILE_BYTES = 25 * 1024 * 1024


class StorageError(ValueError):
    """Файл нельзя сохранить или прочитать."""


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_dir(root: Path, task_id: str) -> Path:
    return ensure_dir(root / task_id)


def safe_filename(name: str) -> str:
    original = Path(name or "").name.strip() or "file"
    stem = Path(original).stem
    suffix = Path(original).suffix[:12]
    cleaned = SAFE_NAME.sub("_", stem).strip("._") or "file"
    return f"{cleaned[:80]}{suffix.lower()}"


def unique_filename(directory: Path, filename: str) -> str:
    candidate = safe_filename(filename)
    if not (directory / candidate).exists():
        return candidate
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    token = uuid.uuid4().hex[:6]
    return f"{stem}-{token}{suffix}"


def save_bytes(
    root: Path,
    task_id: str,
    filename: str,
    data: bytes,
    content_type: str = "",
) -> dict:
    if not data:
        raise StorageError("Пустой файл нельзя сохранить")
    if len(data) > MAX_FILE_BYTES:
        raise StorageError("Файл больше 25 МБ")
    directory = task_dir(root, task_id)
    stored_name = unique_filename(directory, filename)
    path = directory / stored_name
    path.write_bytes(data)
    return {
        "id": stored_name,
        "filename": stored_name,
        "original_filename": Path(filename).name,
        "kind": detect_kind(stored_name, content_type),
        "content_type": (content_type or "application/octet-stream").split(";", 1)[0],
        "size": len(data),
        "storage_path": f"storage/{task_id}/{stored_name}",
    }


def read_file(root: Path, task_id: str, filename: str) -> Path:
    directory = root / task_id
    path = (directory / Path(filename).name).resolve()
    if directory.resolve() not in path.parents:
        raise StorageError("Некорректный путь к файлу")
    if not path.is_file():
        raise StorageError("Файл не найден")
    return path


def list_files(root: Path, task_id: str) -> list[Path]:
    directory = root / task_id
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file())
