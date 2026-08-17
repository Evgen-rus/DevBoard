"""Тонкая обёртка над GitHub Issues API. Issues — source of truth для задач."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("devboard.github")

API_VERSION = "2022-11-28"
LABEL_COLORS = {
    "status:inbox": "8B8F9A",
    "status:next": "2563EB",
    "status:in-progress": "D97706",
    "status:done": "059669",
    "priority:low": "94A3B8",
    "priority:medium": "2563EB",
    "priority:high": "DC2626",
    "devboard:archived": "6B7280",
    "project": "6E40C9",
}


class GitHubError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    def __init__(self, token: str, repo: str, timeout: float = 30.0) -> None:
        if "/" not in repo:
            raise GitHubError("GITHUB_REPO должен быть в формате owner/repo")
        self.repo = repo.strip()
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "DevBoard",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            detail = response.text[:300]
            logger.warning("GitHub %s %s -> %s %s", method, path, response.status_code, detail)
            raise GitHubError(
                f"GitHub вернул ошибку {response.status_code}: {detail}",
                status_code=502 if response.status_code >= 500 else response.status_code,
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def list_labels(self) -> list[dict[str, Any]]:
        labels: list[dict[str, Any]] = []
        page = 1
        while True:
            chunk = self._request(
                "GET",
                f"/repos/{self.repo}/labels",
                params={"per_page": 100, "page": page},
            )
            if not chunk:
                break
            labels.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return labels

    def create_label(self, name: str, color: str, description: str = "") -> dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{self.repo}/labels",
            json={"name": name, "color": color, "description": description},
        )

    def ensure_labels(self, names: list[tuple[str, str, str]]) -> None:
        existing = {item["name"] for item in self.list_labels()}
        for name, color, description in names:
            if name in existing:
                continue
            try:
                self.create_label(name, color, description)
            except GitHubError as exc:
                if exc.status_code != 422:
                    raise

    def list_issues(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        page = 1
        while True:
            chunk = self._request(
                "GET",
                f"/repos/{self.repo}/issues",
                params={"state": "all", "per_page": 100, "page": page},
            )
            if not chunk:
                break
            issues.extend(item for item in chunk if "pull_request" not in item)
            if len(chunk) < 100:
                break
            page += 1
        return issues

    def get_issue(self, number: int) -> dict[str, Any]:
        issue = self._request("GET", f"/repos/{self.repo}/issues/{number}")
        if issue.get("pull_request"):
            raise GitHubError("Это pull request, а не задача", status_code=404)
        return issue

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{self.repo}/issues",
            json={"title": title, "body": body, "labels": labels},
        )

    def update_issue(self, number: int, **fields: Any) -> dict[str, Any]:
        payload = {key: value for key, value in fields.items() if value is not None}
        return self._request("PATCH", f"/repos/{self.repo}/issues/{number}", json=payload)

    def list_comments(self, number: int) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/repos/{self.repo}/issues/{number}/comments",
            params={"per_page": 100},
        ) or []

    def create_comment(self, number: int, body: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/repos/{self.repo}/issues/{number}/comments",
            json={"body": body},
        )
