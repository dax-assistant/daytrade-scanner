from __future__ import annotations

import hmac
import secrets
from typing import Any, Dict, Optional

from fastapi import Request, WebSocket

from src.config import Settings

AUTH_COOKIE_NAME = "scanner_auth"


class AuthError(RuntimeError):
    pass


def auth_enabled(settings: Settings) -> bool:
    return bool(settings.web_auth.enabled)


def websocket_auth_enabled(settings: Settings) -> bool:
    return bool(settings.web.websocket_auth_enabled)


def _get_auth_record(request: Request) -> Optional[Dict[str, Any]]:
    token = (request.cookies.get(AUTH_COOKIE_NAME) or "").strip()
    if not token:
        return None
    return request.app.state.http_auth_tokens.get(token)


def is_authenticated(request: Request) -> bool:
    if not auth_enabled(request.app.state.settings):
        return True
    return _get_auth_record(request) is not None


def require_authenticated(request: Request) -> None:
    if not is_authenticated(request):
        raise AuthError("authentication_required")


def _issue_websocket_token(request: Request, username: str) -> str:
    token = secrets.token_urlsafe(32)
    request.app.state.ws_auth_tokens[token] = {"username": username}
    return token


def login(request: Request, username: str, password: str) -> Dict[str, Any]:
    settings = request.app.state.settings
    if auth_enabled(settings):
        if not hmac.compare_digest(username, settings.web_auth.username):
            raise AuthError("invalid_credentials")
        if not hmac.compare_digest(password, settings.web_auth.password):
            raise AuthError("invalid_credentials")
    elif not username:
        username = "admin"

    auth_token = secrets.token_urlsafe(32)
    ws_token = _issue_websocket_token(request, username)
    request.app.state.http_auth_tokens[auth_token] = {
        "username": username,
        "ws_token": ws_token,
    }
    return {
        "ok": True,
        "authenticated": True,
        "username": username,
        "ws_token": ws_token,
        "auth_token": auth_token,
    }


def logout(request: Request) -> None:
    token = (request.cookies.get(AUTH_COOKIE_NAME) or "").strip()
    if not token:
        return
    record = request.app.state.http_auth_tokens.pop(token, None) or {}
    ws_token = record.get("ws_token")
    if ws_token:
        request.app.state.ws_auth_tokens.pop(ws_token, None)


def get_auth_status(request: Request) -> Dict[str, Any]:
    settings = request.app.state.settings
    record = _get_auth_record(request)
    authenticated = record is not None or not auth_enabled(settings)
    return {
        "enabled": auth_enabled(settings),
        "authenticated": authenticated,
        "username": record.get("username") if record else None,
        "websocket_auth_enabled": websocket_auth_enabled(settings),
        "ws_token": record.get("ws_token") if record else None,
    }


async def authorize_websocket(websocket: WebSocket) -> None:
    settings: Settings = websocket.app.state.settings
    if not websocket_auth_enabled(settings):
        return

    token = (websocket.query_params.get("token") or "").strip()
    if not token:
        raise AuthError("websocket_auth_required")

    if token not in websocket.app.state.ws_auth_tokens:
        raise AuthError("invalid_websocket_token")
