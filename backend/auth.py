"""Минимальный доступ: общий пароль для UI и токен для API агентов."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from settings import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def passwords_match(received: str, expected: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(received.encode("utf-8"), expected.encode("utf-8"))


def is_authenticated(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> bool:
    if request.session.get("auth") is True:
        return True
    token = ""
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
    header_token = (request.headers.get("X-DevBoard-Token") or "").strip()
    supplied = token or header_token
    if supplied and passwords_match(supplied, settings.api_token):
        return True
    return False


def require_auth(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not is_authenticated(request, credentials, settings):
        raise HTTPException(status_code=401, detail="Нужна авторизация")
