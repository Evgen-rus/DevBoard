from __future__ import annotations

from pathlib import Path

import pytest

import storage as storage_mod


def test_save_and_read_file(tmp_path: Path) -> None:
    saved = storage_mod.save_bytes(
        tmp_path,
        "DEV-52",
        "My Shot.png",
        b"png-bytes",
        "image/png",
    )
    assert saved["filename"] == "My_Shot.png"
    assert saved["kind"] == "image"
    path = storage_mod.read_file(tmp_path, "DEV-52", saved["filename"])
    assert path.read_bytes() == b"png-bytes"


def test_unique_filename_on_collision(tmp_path: Path) -> None:
    first = storage_mod.save_bytes(tmp_path, "DEV-1", "voice.webm", b"one", "audio/webm")
    second = storage_mod.save_bytes(tmp_path, "DEV-1", "voice.webm", b"two", "audio/webm")
    assert first["filename"] != second["filename"]
    files = storage_mod.list_files(tmp_path, "DEV-1")
    assert len(files) == 2


def test_rejects_path_escape(tmp_path: Path) -> None:
    storage_mod.save_bytes(tmp_path, "DEV-1", "ok.txt", b"ok", "text/plain")
    with pytest.raises(storage_mod.StorageError):
        storage_mod.read_file(tmp_path, "DEV-1", "../secret.txt")
