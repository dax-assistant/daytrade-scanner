from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytz
from fastapi import Request, WebSocket

from src.config import Settings


class AuditLogger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tz = pytz.timezone(settings.timezone)

    async def log(self, event: str, payload: Dict[str, Any]) -> None:
        entry = {
            "event": event,
            "recorded_at": datetime.now(self._tz).isoformat(),
            **payload,
        }
        await asyncio.to_thread(self._append_line_sync, self._daily_file(), json.dumps(entry, default=str))

    def _daily_file(self) -> Path:
        logs_dir = Path(self.settings.logging.directory)
        logs_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now(self._tz).strftime(self.settings.logging.audit_filename_pattern)
        return logs_dir / filename

    @staticmethod
    def _append_line_sync(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def request_actor(request: Request) -> Dict[str, Any]:
    auth_token = (request.cookies.get("scanner_auth") or "").strip()
    auth_record = request.app.state.http_auth_tokens.get(auth_token, {}) if auth_token else {}
    return {
        "type": "http",
        "username": auth_record.get("username"),
        "client": request.client.host if request.client else None,
        "path": request.url.path,
        "method": request.method,
    }


def websocket_actor(ws: WebSocket) -> Dict[str, Any]:
    token = (ws.query_params.get("token") or "").strip()
    auth_record = ws.app.state.ws_auth_tokens.get(token, {}) if token else {}
    return {
        "type": "websocket",
        "username": auth_record.get("username"),
        "client": ws.client.host if ws.client else None,
        "path": str(ws.url.path),
    }
