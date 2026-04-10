from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import Settings
from src.db.manager import DatabaseManager
from src.event_bus import EventBus
from src.web.routes import create_routes
from src.web.ws_manager import WebSocketManager


def create_app(
    settings: Settings,
    event_bus: EventBus,
    db: DatabaseManager,
    simulator=None,
    ws_manager: WebSocketManager | None = None,
    scanner=None,
    config_path: Path | None = None,
    alpaca_client=None,
) -> FastAPI:
    app = FastAPI(title="Day Trade Scanner v3")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.state.settings = settings
    app.state.event_bus = event_bus
    app.state.db = db
    app.state.scanner = scanner
    app.state.simulator = simulator
    app.state.ws_manager = ws_manager or WebSocketManager()
    app.state.static_dir = static_dir
    app.state.config_path = config_path
    app.state.alpaca_client = alpaca_client

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_routes())

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await app.state.ws_manager.connect(websocket)
        try:
            while True:
                message = await websocket.receive_json()
                result = await app.state.ws_manager.handle_client_message(websocket, message, app.state.simulator)
                await websocket.send_json({"event": "ack", "data": result})
        except WebSocketDisconnect:
            await app.state.ws_manager.disconnect(websocket)
        except Exception:
            await app.state.ws_manager.disconnect(websocket)

    return app
