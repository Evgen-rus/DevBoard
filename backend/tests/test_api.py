from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["DEVBOARD_PASSWORD"] = "test-password"
os.environ["DEVBOARD_API_TOKEN"] = "test-token"
os.environ["DEVBOARD_SECRET_KEY"] = "test-secret-key-for-unit-tests"
os.environ["GITHUB_TOKEN"] = "fake-token"
os.environ["GITHUB_REPO"] = "owner/dev-tasks"
os.environ["DEVBOARD_SKIP_BOOTSTRAP"] = "true"
os.environ["STORAGE_DIR"] = str(Path(__file__).resolve().parent / "_tmp_storage")

from fastapi.testclient import TestClient

from mapping import ARCHIVED_LABEL, render_issue_body
import main as main_mod


def _issue(number: int = 52, **overrides):
    body = render_issue_body("Короткое описание", "Расшифровка голоса", [])
    issue = {
        "number": number,
        "title": "Починить фильтр",
        "body": body,
        "state": "open",
        "labels": [
            {"name": "project:NeuroROP"},
            {"name": "status:inbox"},
            {"name": "priority:medium"},
        ],
        "created_at": "2026-08-17T02:00:00Z",
        "updated_at": "2026-08-17T03:00:00Z",
        "html_url": f"https://github.com/owner/dev-tasks/issues/{number}",
        "comments": 0,
        "user": {"login": "owner"},
    }
    issue.update(overrides)
    return issue


class FakeGitHub:
    def __init__(self) -> None:
        self.issues = {52: _issue()}
        self.labels = [
            {"name": "project:NeuroROP"},
            {"name": "project:LeadRecord"},
            {"name": "status:inbox"},
        ]
        self.comments = {52: []}
        self.next_number = 53

    def list_labels(self):
        return list(self.labels)

    def ensure_labels(self, names):
        existing = {item["name"] for item in self.labels}
        for name, _color, _description in names:
            if name not in existing:
                self.labels.append({"name": name})

    def list_issues(self):
        return list(self.issues.values())

    def get_issue(self, number: int):
        return self.issues[number]

    def create_issue(self, title: str, body: str, labels: list[str]):
        number = self.next_number
        self.next_number += 1
        issue = _issue(
            number,
            title=title,
            body=body,
            labels=[{"name": label} for label in labels],
        )
        self.issues[number] = issue
        return issue

    def update_issue(self, number: int, **fields):
        issue = dict(self.issues[number])
        if "title" in fields:
            issue["title"] = fields["title"]
        if "body" in fields:
            issue["body"] = fields["body"]
        if "labels" in fields:
            issue["labels"] = [{"name": label} for label in fields["labels"]]
        if "state" in fields:
            issue["state"] = fields["state"]
        self.issues[number] = issue
        return issue

    def list_comments(self, number: int):
        return list(self.comments.get(number, []))

    def create_comment(self, number: int, body: str):
        comment = {
            "id": 1,
            "user": {"login": "dev"},
            "body": body,
            "created_at": "2026-08-17T04:00:00Z",
        }
        self.comments.setdefault(number, []).append(comment)
        return comment


@pytest.fixture()
def client(tmp_path, monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    main_mod.app.dependency_overrides[main_mod.get_github] = lambda: fake
    main_mod.app.dependency_overrides[main_mod.get_settings] = lambda: main_mod.Settings(
        devboard_password="test-password",
        devboard_api_token="test-token",
        devboard_secret_key="test-secret-key-for-unit-tests",
        github_token="fake-token",
        github_repo="owner/dev-tasks",
        storage_dir=tmp_path,
        devboard_skip_bootstrap=True,
    )
    with TestClient(main_mod.app) as test_client:
        yield test_client, fake
    main_mod.app.dependency_overrides.clear()


def test_login_and_list_tasks(client) -> None:
    test_client, _fake = client
    denied = test_client.get("/api/tasks")
    assert denied.status_code == 401
    login = test_client.post("/api/login", json={"password": "test-password"})
    assert login.status_code == 200
    listed = test_client.get("/api/tasks")
    assert listed.status_code == 200
    tasks = listed.json()["tasks"]
    assert tasks[0]["id"] == "DEV-52"
    assert tasks[0]["project"] == "NeuroROP"


def test_agent_context_with_token(client) -> None:
    test_client, _fake = client
    response = test_client.get(
        "/api/tasks/DEV-52/agent-context",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "DEV-52"
    assert payload["transcript"] == "Расшифровка голоса"
    assert payload["project"] == "NeuroROP"
    assert "Возьми DEV-52" in payload["agent_prompt"]


def test_create_task_and_status_change(client) -> None:
    test_client, fake = client
    test_client.post("/api/login", json={"password": "test-password"})
    created = test_client.post(
        "/api/tasks",
        data={
            "project": "LeadRecord",
            "title": "Новая идея",
            "description": "Сделать экран",
            "priority": "high",
        },
        files=[("files", ("shot.png", b"png-data", "image/png"))],
    )
    assert created.status_code == 200
    task = created.json()["task"]
    assert task["id"] == "DEV-53"
    assert task["project"] == "LeadRecord"
    assert task["attachments"][0]["kind"] == "image"
    patched = test_client.patch("/api/tasks/DEV-53", json={"status": "in_progress"})
    assert patched.status_code == 200
    assert patched.json()["task"]["status"] == "in_progress"
    assert fake.issues[53]["state"] == "open"


def test_archive_hides_task_preserves_files_and_restore_returns_it(client) -> None:
    test_client, fake = client
    test_client.post("/api/login", json={"password": "test-password"})
    created = test_client.post(
        "/api/tasks",
        data={
            "project": "LeadRecord",
            "title": "Задача с архивом",
            "description": "Файлы должны сохраниться",
            "priority": "medium",
        },
        files=[("files", ("shot.png", b"png-data", "image/png"))],
    )
    task = created.json()["task"]
    settings = main_mod.app.dependency_overrides[main_mod.get_settings]()
    stored_file = settings.storage_dir / task["id"] / task["attachments"][0]["filename"]
    assert stored_file.is_file()

    archived = test_client.post(f"/api/tasks/{task['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["task"]["archived"] is True
    assert stored_file.is_file()
    assert all(item["id"] != task["id"] for item in test_client.get("/api/tasks").json()["tasks"])
    archived_tasks = test_client.get("/api/tasks?archived=true").json()["tasks"]
    assert [item["id"] for item in archived_tasks] == [task["id"]]

    restored = test_client.post(f"/api/tasks/{task['id']}/restore")
    assert restored.status_code == 200
    restored_task = restored.json()["task"]
    assert restored_task["archived"] is False
    assert restored_task["status"] == "inbox"
    assert restored_task["project"] == "LeadRecord"
    assert stored_file.is_file()
    assert ARCHIVED_LABEL not in {
        label["name"] for label in fake.issues[task["number"]]["labels"]
    }


def test_health_does_not_require_auth(client) -> None:
    test_client, _fake = client
    response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
