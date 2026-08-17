from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

CLI_PATH = Path(__file__).resolve().parents[2] / "cli" / "devtask.py"


def load_devtask():
    spec = importlib.util.spec_from_file_location("devtask_cli", CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def devtask():
    return load_devtask()


def test_safe_filename_strips_path(devtask) -> None:
    assert devtask.safe_filename("../secret.txt") == "secret.txt"
    assert devtask.safe_filename("..") == "file"
    assert devtask.safe_filename("My Shot.PNG") == "My_Shot.png"


def test_destination_file_rejects_escape(devtask, tmp_path: Path) -> None:
    folder = tmp_path / "DEV-1"
    folder.mkdir()
    with pytest.raises(devtask.MaterializeError):
        devtask.destination_file(folder, "..")


def test_materialize_writes_json_and_files(devtask, tmp_path: Path) -> None:
    payload = {
        "id": "DEV-52",
        "title": "Починить фильтр",
        "description": "Короткое описание",
        "attachments": [
            {
                "filename": "shot.png",
                "kind": "image",
                "url": "/api/tasks/DEV-52/attachments/shot.png",
            },
            {
                "filename": "voice.webm",
                "kind": "audio",
                "url": "/api/tasks/DEV-52/attachments/voice.webm",
            },
        ],
    }
    files = {"shot.png": b"png-bytes", "voice.webm": b"audio-bytes"}

    def download(url: str) -> bytes:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        return files[name]

    result = devtask.materialize_context(
        payload,
        dest_root=tmp_path / ".devboard",
        download=download,
        base_url="http://127.0.0.1:8080",
    )
    task_dir = tmp_path / ".devboard" / "DEV-52"
    assert result["task_dir"] == task_dir
    assert (task_dir / "shot.png").read_bytes() == b"png-bytes"
    assert (task_dir / "voice.webm").read_bytes() == b"audio-bytes"
    saved = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    assert saved["title"] == "Починить фильтр"
    assert saved["attachments"][0]["local_path"] == str((task_dir / "shot.png").resolve())
    assert saved["attachments"][1]["local_path"] == str((task_dir / "voice.webm").resolve())
    assert all(item["downloaded"] is True for item in saved["attachments"])
    assert "Починить" in (task_dir / "task.json").read_text(encoding="utf-8")


def test_materialize_removes_stale_files(devtask, tmp_path: Path) -> None:
    dest_root = tmp_path / ".devboard"
    task_dir = dest_root / "DEV-1"
    task_dir.mkdir(parents=True)
    stale = task_dir / "old-shot.png"
    stale.write_bytes(b"obsolete")
    leftover_dir = task_dir / "junk"
    leftover_dir.mkdir()
    (leftover_dir / "extra.txt").write_text("nope", encoding="utf-8")

    payload = {
        "id": "DEV-1",
        "attachments": [
            {"filename": "note.txt", "kind": "file", "url": "/api/tasks/DEV-1/attachments/note.txt"},
        ],
    }
    result = devtask.materialize_context(
        payload,
        dest_root=dest_root,
        download=lambda _url: b"fresh",
        base_url="http://127.0.0.1:8080",
    )
    names = {path.name for path in result["task_dir"].iterdir()}
    assert names == {"task.json", "note.txt"}
    assert (result["task_dir"] / "note.txt").read_bytes() == b"fresh"


def test_materialize_without_attachments(devtask, tmp_path: Path) -> None:
    result = devtask.materialize_context(
        {"id": "DEV-7", "title": "Без файлов", "attachments": []},
        dest_root=tmp_path / ".devboard",
        download=lambda _url: b"unused",
        base_url="http://127.0.0.1:8080",
    )
    assert result["files"] == []
    saved = json.loads(result["task_json"].read_text(encoding="utf-8"))
    assert saved["attachments"] == []


def test_materialize_can_skip_audio_but_keeps_metadata(devtask, tmp_path: Path) -> None:
    requested: list[str] = []
    result = devtask.materialize_context(
        {
            "id": "DEV-7",
            "transcript": "Готовая расшифровка",
            "attachments": [
                {"filename": "shot.png", "kind": "image"},
                {"filename": "voice.ogg", "kind": "audio"},
            ],
        },
        dest_root=tmp_path / "cache",
        download=lambda url: requested.append(url) or b"image",
        base_url="https://board.example",
        include_audio=False,
    )
    saved = json.loads(result["task_json"].read_text(encoding="utf-8"))
    assert requested == ["https://board.example/api/tasks/DEV-7/attachments/shot.png"]
    assert result["skipped"] == ["voice.ogg"]
    assert saved["attachments"][1]["downloaded"] is False
    assert saved["attachments"][1]["local_path"] is None


def test_default_cache_root_uses_local_app_data(devtask, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert devtask.default_cache_root() == tmp_path / "DevBoard" / "tasks"


def test_parse_task_id_rejects_path(devtask) -> None:
    with pytest.raises(devtask.MaterializeError):
        devtask.parse_task_id("../DEV-1")
    assert devtask.parse_task_id("DEV-1") == "DEV-1"


def test_unique_filename_on_collision(devtask) -> None:
    used = {"note.txt"}
    assert devtask.unique_filename("note.txt", used) == "note-2.txt"
