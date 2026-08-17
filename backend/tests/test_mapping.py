from __future__ import annotations

import mapping as mapping


ISSUE = {
    "number": 52,
    "title": "Починить фильтр",
    "body": "",
    "state": "open",
    "labels": [
        {"name": "project:NeuroROP"},
        {"name": "status:inbox"},
        {"name": "priority:high"},
    ],
    "created_at": "2026-08-17T02:00:00Z",
    "updated_at": "2026-08-17T03:00:00Z",
    "html_url": "https://github.com/owner/dev-tasks/issues/52",
    "comments": 1,
}


def test_format_and_parse_task_id() -> None:
    assert mapping.format_task_id(52) == "DEV-52"
    assert mapping.parse_task_id("DEV-52") == 52
    assert mapping.parse_task_id("dev-52") == 52


def test_parse_task_id_rejects_wrong_prefix() -> None:
    try:
        mapping.parse_task_id("TASK-52")
    except mapping.MappingError:
        return
    raise AssertionError("ожидалась ошибка")


def test_resolve_title_from_transcript() -> None:
    assert mapping.resolve_title("", "", "Нужно починить фильтр сделок") == "Нужно починить фильтр сделок"
    assert mapping.resolve_title("  ", "Первая строка\nвторая", "") == "Первая строка"


def test_issue_body_roundtrip() -> None:
    attachments = [
        {
            "id": "shot-1.png",
            "filename": "shot-1.png",
            "kind": "image",
            "content_type": "image/png",
            "size": 12,
            "storage_path": "storage/DEV-52/shot-1.png",
        }
    ]
    body = mapping.render_issue_body("Короткое описание", "Голосовая расшифровка", attachments)
    description, transcript, parsed = mapping.parse_issue_body(body)
    assert description == "Короткое описание"
    assert transcript == "Голосовая расшифровка"
    assert parsed[0]["filename"] == "shot-1.png"


def test_issue_to_task_uses_labels() -> None:
    body = mapping.render_issue_body("Текст", "Голос", [])
    issue = {**ISSUE, "body": body}
    task = mapping.issue_to_task(issue)
    assert task["id"] == "DEV-52"
    assert task["project"] == "NeuroROP"
    assert task["status"] == "inbox"
    assert task["priority"] == "high"
    assert task["transcript"] == "Голос"


def test_closed_issue_is_done() -> None:
    issue = {**ISSUE, "state": "closed", "labels": [{"name": "project:LeadRecord"}]}
    task = mapping.issue_to_task(issue)
    assert task["status"] == "done"
    assert task["project"] == "LeadRecord"


def test_labels_for_update_replaces_status_and_keeps_others() -> None:
    existing = ["project:NeuroROP", "status:inbox", "priority:medium", "custom"]
    updated = mapping.labels_for_update(existing, status="in_progress")
    assert "status:in-progress" in updated
    assert "status:inbox" not in updated
    assert "custom" in updated
    assert "project:NeuroROP" in updated


def test_archive_label_preserves_status_project_and_priority() -> None:
    existing = ["project:NeuroROP", "status:in_progress", "priority:high", "custom"]
    archived = mapping.labels_for_archive(existing, True)
    assert mapping.ARCHIVED_LABEL in archived
    assert "status:in_progress" in archived
    assert "project:NeuroROP" in archived
    assert "priority:high" in archived
    assert mapping.labels_for_archive(archived, False) == existing


def test_issue_to_task_marks_archived_issue() -> None:
    issue = {
        **ISSUE,
        "labels": [*ISSUE["labels"], {"name": mapping.ARCHIVED_LABEL}],
    }
    assert mapping.issue_to_task(issue)["archived"] is True


def test_detect_kind() -> None:
    assert mapping.detect_kind("note.webm", "video/webm") == "audio"
    assert mapping.detect_kind("ui.png", "image/png") == "image"
    assert mapping.detect_kind("spec.pdf", "application/pdf") == "file"


def test_github_state_for_status() -> None:
    assert mapping.github_state_for_status("done") == "closed"
    assert mapping.github_state_for_status("next") == "open"
