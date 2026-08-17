"""DevBoard API: человеческий ввод -> GitHub Issue + локальные файлы -> контекст для агента."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from auth import require_auth
from github_client import LABEL_COLORS, GitHubClient, GitHubError
from mapping import (
    ARCHIVED_LABEL,
    PRIORITIES,
    STATUSES,
    github_state_for_status,
    issue_to_task,
    labels_for_update,
    labels_for_archive,
    parse_task_id,
    render_issue_body,
    required_labels,
    resolve_title,
    normalize_project_name,
    parse_project_label,
    project_label,
    MappingError,
    Priority,
    Status,
)
from settings import Settings, get_settings
from storage import StorageError, read_file, save_bytes
from transcription import TranscriptionError, transcribe_audio

logger = logging.getLogger("devboard")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

AuthDep = Annotated[None, Depends(require_auth)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class LoginBody(BaseModel):
    password: str


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = None
    transcript: str | None = None
    status: Status | None = None
    priority: Priority | None = None
    project: str | None = None


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def get_github(settings: SettingsDep):
    if not settings.github_configured:
        raise HTTPException(
            status_code=503,
            detail="Не настроен GitHub: задайте GITHUB_TOKEN и GITHUB_REPO=owner/repo",
        )
    client = GitHubClient(settings.github_token, settings.github_repo)
    try:
        yield client
    finally:
        client.close()


GitHubDep = Annotated[GitHubClient, Depends(get_github)]


def bootstrap_labels(client: GitHubClient, projects: list[str]) -> None:
    specs: list[tuple[str, str, str]] = [
        ("status:inbox", LABEL_COLORS["status:inbox"], "DevBoard: Inbox"),
        ("status:next", LABEL_COLORS["status:next"], "DevBoard: Next"),
        ("status:in-progress", LABEL_COLORS["status:in-progress"], "DevBoard: In Progress"),
        ("status:done", LABEL_COLORS["status:done"], "DevBoard: Done"),
        ("priority:low", LABEL_COLORS["priority:low"], "DevBoard: low priority"),
        ("priority:medium", LABEL_COLORS["priority:medium"], "DevBoard: medium priority"),
        ("priority:high", LABEL_COLORS["priority:high"], "DevBoard: high priority"),
        (ARCHIVED_LABEL, LABEL_COLORS[ARCHIVED_LABEL], "DevBoard: archived task"),
    ]
    for name in projects:
        specs.append((project_label(name), LABEL_COLORS["project"], f"DevBoard project {name}"))
    client.ensure_labels(specs)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.github_configured and not settings.devboard_skip_bootstrap:
        client = GitHubClient(settings.github_token, settings.github_repo)
        try:
            bootstrap_labels(client, settings.default_projects)
            logger.info("GitHub labels проверены для %s", settings.github_repo)
        except GitHubError as exc:
            logger.warning("Не удалось подготовить GitHub labels: %s", exc)
        finally:
            client.close()
    elif not settings.github_configured:
        logger.warning("GitHub не настроен. Доска не сможет создавать задачи.")
    yield


app = FastAPI(title="DevBoard", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().devboard_secret_key,
    same_site="lax",
    https_only=get_settings().devboard_cookie_secure,
    max_age=60 * 60 * 24 * 14,
)


@app.exception_handler(GitHubError)
async def github_error_handler(_request: Request, exc: GitHubError) -> JSONResponse:
    status = 502 if exc.status_code >= 500 or exc.status_code == 401 else exc.status_code
    if exc.status_code == 401:
        status = 503
    return JSONResponse({"detail": str(exc)}, status_code=status)


@app.exception_handler(MappingError)
async def mapping_error_handler(_request: Request, exc: MappingError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(StorageError)
async def storage_error_handler(_request: Request, exc: StorageError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/health")
def health(settings: SettingsDep) -> dict[str, Any]:
    storage_ok = False
    try:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        storage_ok = settings.storage_dir.is_dir()
    except OSError:
        storage_ok = False
    return {
        "ok": True,
        "github": settings.github_configured,
        "storage": storage_ok,
        "transcription": settings.transcription_configured,
    }


@app.post("/api/login")
def login(body: LoginBody, request: Request, settings: SettingsDep) -> dict[str, bool]:
    from auth import passwords_match

    if not settings.devboard_password:
        raise HTTPException(status_code=503, detail="DEVBOARD_PASSWORD не задан")
    if not passwords_match(body.password, settings.devboard_password):
        raise HTTPException(status_code=401, detail="Неверный пароль")
    request.session["auth"] = True
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(_: AuthDep) -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/projects")
def list_projects(_: AuthDep, github: GitHubDep, settings: SettingsDep) -> dict[str, list[str]]:
    names = _project_names(github, settings)
    return {"projects": names}


@app.post("/api/projects")
def create_project(body: ProjectBody, _: AuthDep, github: GitHubDep) -> dict[str, str]:
    name = normalize_project_name(body.name)
    github.ensure_labels(
        [(project_label(name), LABEL_COLORS["project"], f"DevBoard project {name}")]
    )
    return {"project": name}


@app.get("/api/tasks")
def list_tasks(
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
    project: str | None = None,
    archived: bool = False,
) -> dict[str, Any]:
    tasks = [issue_to_task(issue, settings.devboard_id_prefix) for issue in github.list_issues()]
    tasks = [task for task in tasks if task["archived"] is archived]
    if project and project != "all":
        tasks = [task for task in tasks if task["project"] == project]
    return {"tasks": tasks}


@app.post("/api/tasks")
async def create_task(
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
    project: str = Form(...),
    title: str = Form(""),
    description: str = Form(""),
    priority: Priority = Form("medium"),
    transcript: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
) -> dict[str, Any]:
    if priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail="Некорректный приоритет")
    project_name = normalize_project_name(project)
    file_payloads = await _read_uploads(files or [])
    audio_bytes, audio_name, audio_type = _first_audio(file_payloads)
    final_transcript = transcript.strip()
    if audio_bytes and not final_transcript:
        if settings.transcription_configured:
            try:
                final_transcript = transcribe_audio(
                    audio_bytes,
                    filename=audio_name,
                    content_type=audio_type,
                    api_key=settings.openai_api_key,
                    model=settings.openai_transcribe_model,
                    language=settings.openai_transcribe_language,
                )
            except TranscriptionError as exc:
                logger.warning("Транскрибация не удалась при создании задачи: %s", exc)
        else:
            logger.warning("Аудио приложено, но OPENAI_API_KEY не задан")
    if not (title.strip() or description.strip() or file_payloads or final_transcript):
        raise HTTPException(status_code=400, detail="Добавьте текст, файл или аудио")
    resolved_title = resolve_title(title, description, final_transcript)
    github.ensure_labels(
        [(project_label(project_name), LABEL_COLORS["project"], f"DevBoard project {project_name}")]
    )
    created = github.create_issue(
        title=resolved_title,
        body=render_issue_body(description, final_transcript, []),
        labels=required_labels(project_name, "inbox", priority),
    )
    task_id = issue_to_task(created, settings.devboard_id_prefix)["id"]
    attachments = _store_uploads(settings.storage_dir, task_id, file_payloads)
    updated = github.update_issue(
        created["number"],
        body=render_issue_body(description, final_transcript, attachments),
        state="open",
    )
    task = issue_to_task(updated, settings.devboard_id_prefix)
    task["transcription_error"] = None
    if audio_bytes and not final_transcript:
        task["transcription_error"] = (
            "Аудио сохранено, но транскрипт не получен. Проверьте OPENAI_API_KEY."
        )
    return {"task": task}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, _: AuthDep, github: GitHubDep, settings: SettingsDep) -> dict[str, Any]:
    issue = github.get_issue(parse_task_id(task_id, settings.devboard_id_prefix))
    return {"task": issue_to_task(issue, settings.devboard_id_prefix)}


@app.patch("/api/tasks/{task_id}")
def patch_task(
    task_id: str,
    body: TaskPatch,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    number = parse_task_id(task_id, settings.devboard_id_prefix)
    issue = github.get_issue(number)
    task = issue_to_task(issue, settings.devboard_id_prefix)
    title = task["title"] if body.title is None else resolve_title(body.title, body.description or task["description"])
    description = task["description"] if body.description is None else body.description
    transcript = task["transcript"] if body.transcript is None else body.transcript
    status = task["status"] if body.status is None else body.status
    priority = task["priority"] if body.priority is None else body.priority
    project = task["project"] if body.project is None else normalize_project_name(body.project)
    if status not in STATUSES or priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail="Некорректный статус или приоритет")
    existing_labels = [
        label["name"] if isinstance(label, dict) else str(label)
        for label in issue.get("labels") or []
    ]
    if body.project is not None:
        github.ensure_labels(
            [(project_label(project), LABEL_COLORS["project"], f"DevBoard project {project}")]
        )
    updated = github.update_issue(
        number,
        title=title,
        body=render_issue_body(description, transcript, task["attachments"]),
        labels=labels_for_update(
            existing_labels,
            project=project,
            status=status,
            priority=priority,
        ),
        state=github_state_for_status(status),
    )
    return {"task": issue_to_task(updated, settings.devboard_id_prefix)}


def _set_task_archived(
    task_id: str,
    archived: bool,
    github: GitHubClient,
    settings: Settings,
) -> dict[str, Any]:
    number = parse_task_id(task_id, settings.devboard_id_prefix)
    issue = github.get_issue(number)
    existing_labels = [
        label["name"] if isinstance(label, dict) else str(label)
        for label in issue.get("labels") or []
    ]
    updated = github.update_issue(
        number,
        labels=labels_for_archive(existing_labels, archived),
    )
    return {"task": issue_to_task(updated, settings.devboard_id_prefix)}


@app.post("/api/tasks/{task_id}/archive")
def archive_task(
    task_id: str,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    return _set_task_archived(task_id, True, github, settings)


@app.post("/api/tasks/{task_id}/restore")
def restore_task(
    task_id: str,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    return _set_task_archived(task_id, False, github, settings)


@app.get("/api/tasks/{task_id}/agent-context")
def agent_context(
    task_id: str,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    number = parse_task_id(task_id, settings.devboard_id_prefix)
    issue = github.get_issue(number)
    task = issue_to_task(issue, settings.devboard_id_prefix)
    comments = [
        {
            "author": (item.get("user") or {}).get("login") or "",
            "body": item.get("body") or "",
            "created_at": item.get("created_at") or "",
        }
        for item in github.list_comments(number)
    ]
    attachments = [
        {
            **item,
            "url": f"/api/tasks/{task['id']}/attachments/{item.get('filename')}",
        }
        for item in task["attachments"]
    ]
    return {
        "id": task["id"],
        "github_issue": number,
        "github_url": task["github_url"],
        "project": task["project"],
        "title": task["title"],
        "description": task["description"],
        "priority": task["priority"],
        "status": task["status"],
        "transcript": task["transcript"],
        "attachments": attachments,
        "comments": comments,
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "archived": task["archived"],
        "agent_prompt": (
            f"Возьми {task['id']}, изучи задачу и текущий проект {task['project']}, "
            "составь план и реализуй."
        ),
    }


@app.get("/api/tasks/{task_id}/attachments/{filename}")
def download_attachment(
    task_id: str,
    filename: str,
    _: AuthDep,
    settings: SettingsDep,
) -> FileResponse:
    parse_task_id(task_id, settings.devboard_id_prefix)
    path = read_file(settings.storage_dir, task_id, filename)
    return FileResponse(path, filename=path.name)


@app.post("/api/tasks/{task_id}/attachments")
async def add_attachments(
    task_id: str,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
    files: list[UploadFile] | None = File(default=None),
) -> dict[str, Any]:
    number = parse_task_id(task_id, settings.devboard_id_prefix)
    issue = github.get_issue(number)
    task = issue_to_task(issue, settings.devboard_id_prefix)
    payloads = await _read_uploads(files or [])
    if not payloads:
        raise HTTPException(status_code=400, detail="Нет файлов для загрузки")
    added = _store_uploads(settings.storage_dir, task_id, payloads)
    attachments = list(task["attachments"]) + added
    updated = github.update_issue(
        number,
        body=render_issue_body(task["description"], task["transcript"], attachments),
    )
    return {"task": issue_to_task(updated, settings.devboard_id_prefix)}


@app.get("/api/tasks/{task_id}/comments")
def list_comments(
    task_id: str,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    number = parse_task_id(task_id, settings.devboard_id_prefix)
    comments = [
        {
            "id": item.get("id"),
            "author": (item.get("user") or {}).get("login") or "",
            "body": item.get("body") or "",
            "created_at": item.get("created_at") or "",
        }
        for item in github.list_comments(number)
    ]
    return {"comments": comments}


@app.post("/api/tasks/{task_id}/comments")
def add_comment(
    task_id: str,
    body: CommentBody,
    _: AuthDep,
    github: GitHubDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    number = parse_task_id(task_id, settings.devboard_id_prefix)
    created = github.create_comment(number, body.body.strip())
    return {
        "comment": {
            "id": created.get("id"),
            "author": (created.get("user") or {}).get("login") or "",
            "body": created.get("body") or "",
            "created_at": created.get("created_at") or "",
        }
    }


@app.post("/api/transcribe")
async def transcribe_endpoint(
    _: AuthDep,
    settings: SettingsDep,
    audio: UploadFile = File(...),
) -> dict[str, str]:
    if not settings.transcription_configured:
        raise HTTPException(
            status_code=503,
            detail="Транскрибация не настроена: задайте OPENAI_API_KEY",
        )
    data = await audio.read()
    try:
        text = transcribe_audio(
            data,
            filename=audio.filename or "audio.webm",
            content_type=audio.content_type or "",
            api_key=settings.openai_api_key,
            model=settings.openai_transcribe_model,
            language=settings.openai_transcribe_language,
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"text": text}


async def _read_uploads(files: list[UploadFile] | None) -> list[tuple[str, bytes, str]]:
    payloads: list[tuple[str, bytes, str]] = []
    for upload in files or []:
        if upload is None:
            continue
        data = await upload.read()
        if not data:
            continue
        payloads.append(
            (
                upload.filename or "file",
                data,
                upload.content_type or "application/octet-stream",
            )
        )
    if len(payloads) > 20:
        raise HTTPException(status_code=400, detail="Слишком много файлов за один раз")
    return payloads


def _first_audio(
    payloads: list[tuple[str, bytes, str]],
) -> tuple[bytes, str, str] | tuple[None, str, str]:
    from mapping import detect_kind

    for name, data, content_type in payloads:
        if detect_kind(name, content_type) == "audio":
            return data, name, content_type
    return None, "", ""


def _store_uploads(
    root: Path,
    task_id: str,
    payloads: list[tuple[str, bytes, str]],
) -> list[dict[str, Any]]:
    stored: list[dict[str, Any]] = []
    for name, data, content_type in payloads:
        stored.append(save_bytes(root, task_id, name, data, content_type))
    return stored


def _project_names(github: GitHubClient, settings: Settings) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for label in github.list_labels():
        parsed = parse_project_label(label.get("name") or "")
        if parsed and parsed not in seen:
            seen.add(parsed)
            names.append(parsed)
    for default in settings.default_projects:
        if default not in seen:
            names.append(default)
    return names
