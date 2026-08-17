"""Преобразование GitHub Issue <-> задача DevBoard.

Это чистая логика без сети: её можно тестировать отдельно от API.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

Status = Literal["inbox", "next", "in_progress", "done"]
Priority = Literal["low", "medium", "high"]
AttachmentKind = Literal["image", "audio", "file"]

STATUSES: tuple[Status, ...] = ("inbox", "next", "in_progress", "done")
PRIORITIES: tuple[Priority, ...] = ("low", "medium", "high")

STATUS_LABEL = {
    "inbox": "status:inbox",
    "next": "status:next",
    "in_progress": "status:in-progress",
    "done": "status:done",
}
PRIORITY_LABEL = {
    "low": "priority:low",
    "medium": "priority:medium",
    "high": "priority:high",
}
STATUS_FROM_LABEL = {value: key for key, value in STATUS_LABEL.items()}
PRIORITY_FROM_LABEL = {value: key for key, value in PRIORITY_LABEL.items()}

PROJECT_LABEL_PREFIX = "project:"
ARCHIVED_LABEL = "devboard:archived"
META_START = "<!--devboard-meta"
META_END = "-->"

ID_PATTERN = re.compile(r"^([A-Za-z]+)-(\d+)$")
META_PATTERN = re.compile(
    r"<!--devboard-meta\s+(.*?)\s*-->",
    re.DOTALL,
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
AUDIO_EXTENSIONS = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".opus", ".aac", ".flac", ".mp4"}


class MappingError(ValueError):
    """Некорректный идентификатор или метаданные задачи."""


def format_task_id(number: int, prefix: str = "DEV") -> str:
    if int(number) < 1:
        raise MappingError("Номер задачи должен быть положительным")
    return f"{prefix.strip().upper()}-{int(number)}"


def parse_task_id(task_id: str, prefix: str = "DEV") -> int:
    raw = (task_id or "").strip()
    match = ID_PATTERN.match(raw)
    expected = prefix.strip().upper()
    if not match or match.group(1).upper() != expected:
        raise MappingError(f"Ожидался ID вида {expected}-52")
    return int(match.group(2))


def project_label(project: str) -> str:
    name = normalize_project_name(project)
    return f"{PROJECT_LABEL_PREFIX}{name}"


def normalize_project_name(project: str) -> str:
    name = re.sub(r"\s+", " ", (project or "").strip())
    if not name:
        raise MappingError("Название проекта не должно быть пустым")
    if len(name) > 50:
        raise MappingError("Название проекта слишком длинное")
    if any(char in name for char in ":/\\"):
        raise MappingError("Название проекта не должно содержать : / \\")
    return name


def parse_project_label(label: str) -> str | None:
    if label.startswith(PROJECT_LABEL_PREFIX):
        name = label[len(PROJECT_LABEL_PREFIX) :].strip()
        return name or None
    return None


def detect_kind(filename: str, content_type: str = "") -> AttachmentKind:
    lower_name = filename.lower()
    lower_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = ""
    if "." in lower_name:
        suffix = "." + lower_name.rsplit(".", 1)[1]
    if lower_type.startswith("image/") or suffix in IMAGE_EXTENSIONS:
        return "image"
    if (
        lower_type.startswith("audio/")
        or lower_type in {"video/webm", "video/mp4"}
        or suffix in AUDIO_EXTENSIONS
    ):
        return "audio"
    return "file"


def resolve_title(title: str, description: str = "", transcript: str = "") -> str:
    cleaned = (title or "").strip()
    if cleaned:
        return cleaned[:120]
    for source in (description, transcript):
        first_line = (source or "").strip().splitlines()
        if first_line and first_line[0].strip():
            return first_line[0].strip()[:80]
    return "Без названия"


def required_labels(project: str, status: Status, priority: Priority) -> list[str]:
    return [project_label(project), STATUS_LABEL[status], PRIORITY_LABEL[priority]]


def labels_for_update(
    existing: list[str],
    *,
    project: str | None = None,
    status: Status | None = None,
    priority: Priority | None = None,
) -> list[str]:
    kept: list[str] = []
    for label in existing:
        is_status = label in STATUS_FROM_LABEL
        is_priority = label in PRIORITY_FROM_LABEL
        is_project = parse_project_label(label) is not None
        if status is not None and is_status:
            continue
        if priority is not None and is_priority:
            continue
        if project is not None and is_project:
            continue
        kept.append(label)
    if project is not None:
        kept.append(project_label(project))
    if status is not None:
        kept.append(STATUS_LABEL[status])
    if priority is not None:
        kept.append(PRIORITY_LABEL[priority])
    return kept


def labels_for_archive(existing: list[str], archived: bool) -> list[str]:
    labels = [label for label in existing if label != ARCHIVED_LABEL]
    if archived:
        labels.append(ARCHIVED_LABEL)
    return labels


def archived_from_issue(issue: dict[str, Any]) -> bool:
    return ARCHIVED_LABEL in _label_names(issue)


def status_from_issue(issue: dict[str, Any]) -> Status:
    names = _label_names(issue)
    found = [STATUS_FROM_LABEL[name] for name in names if name in STATUS_FROM_LABEL]
    if "done" in found or issue.get("state") == "closed":
        if "done" in found or not found:
            return "done"
    for candidate in ("in_progress", "next", "inbox"):
        if candidate in found:
            return candidate
    return "inbox"


def priority_from_issue(issue: dict[str, Any]) -> Priority:
    names = _label_names(issue)
    for name in names:
        if name in PRIORITY_FROM_LABEL:
            return PRIORITY_FROM_LABEL[name]
    return "medium"


def project_from_issue(issue: dict[str, Any], default: str = "Other") -> str:
    names = _label_names(issue)
    for name in names:
        parsed = parse_project_label(name)
        if parsed:
            return parsed
    return default


def render_issue_body(
    description: str,
    transcript: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    attachments = attachments or []
    parts: list[str] = [(description or "").strip()]
    if (transcript or "").strip():
        parts.append("\n### Транскрипт\n")
        parts.append(transcript.strip())
    if attachments:
        parts.append("\n### Вложения\n")
        for item in attachments:
            filename = item.get("filename", "")
            kind = item.get("kind", "file")
            parts.append(f"- `{filename}` ({kind})")
    meta = {
        "version": 1,
        "transcript": (transcript or "").strip(),
        "attachments": attachments,
    }
    encoded = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("-->", "--\\>")
    parts.append(f"\n{META_START} {encoded} {META_END}")
    return "\n".join(part for part in parts if part is not None).strip() + "\n"


def parse_issue_body(body: str | None) -> tuple[str, str, list[dict[str, Any]]]:
    text = body or ""
    match = META_PATTERN.search(text)
    transcript = ""
    attachments: list[dict[str, Any]] = []
    description = text
    if match:
        raw = match.group(1).replace("--\\>", "-->")
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MappingError("Не удалось прочитать метаданные задачи") from exc
        transcript = str(meta.get("transcript") or "")
        attachments = list(meta.get("attachments") or [])
        description = text[: match.start()].strip()
        description = _strip_generated_sections(description, transcript, attachments)
    return description.strip(), transcript, attachments


def issue_to_task(issue: dict[str, Any], prefix: str = "DEV") -> dict[str, Any]:
    if issue.get("pull_request"):
        raise MappingError("Pull request не является задачей DevBoard")
    number = int(issue["number"])
    description, transcript, attachments = parse_issue_body(issue.get("body") or "")
    status = status_from_issue(issue)
    return {
        "id": format_task_id(number, prefix),
        "number": number,
        "project": project_from_issue(issue),
        "title": issue.get("title") or "Без названия",
        "description": description,
        "status": status,
        "priority": priority_from_issue(issue),
        "created_at": issue.get("created_at") or "",
        "updated_at": issue.get("updated_at") or "",
        "transcript": transcript,
        "attachments": attachments,
        "github_url": issue.get("html_url") or "",
        "comments_count": int(issue.get("comments") or 0),
        "closed": issue.get("state") == "closed",
        "archived": archived_from_issue(issue),
    }


def github_state_for_status(status: Status) -> str:
    return "closed" if status == "done" else "open"


def _strip_generated_sections(
    description: str,
    transcript: str,
    attachments: list[dict[str, Any]],
) -> str:
    text = description
    if transcript and "### Транскрипт" in text:
        text = text.split("### Транскрипт", 1)[0]
    if attachments and "### Вложения" in text:
        text = text.split("### Вложения", 1)[0]
    return text.strip()


def _label_names(issue: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for label in issue.get("labels") or []:
        if isinstance(label, str):
            names.append(label)
        elif isinstance(label, dict) and label.get("name"):
            names.append(str(label["name"]))
    return names
