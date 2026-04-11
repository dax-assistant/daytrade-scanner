from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from fastapi import WebSocket

from src.audit import websocket_actor

LOGGER = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._chart_subscriptions: Dict[WebSocket, Dict[str, str]] = {}
        self._alert_history: deque[Dict[str, Any]] = deque(maxlen=200)
        self._lock = asyncio.Lock()
        self._chart_snapshot_getter: Optional[Callable[[str, str], Awaitable[Dict[str, Any]]]] = None
        self._chart_symbol_subscriber: Optional[Callable[[str], Awaitable[None]]] = None

    def set_chart_snapshot_getter(
        self,
        getter: Callable[[str, str], Awaitable[Dict[str, Any]]],
    ) -> None:
        self._chart_snapshot_getter = getter

    def set_chart_symbol_subscriber(self, subscriber: Callable[[str], Awaitable[None]]) -> None:
        self._chart_symbol_subscriber = subscriber

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
            history = list(self._alert_history)
        if history:
            await ws.send_json({"event": "alert_history", "data": history})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
            self._chart_subscriptions.pop(ws, None)

    async def broadcast(self, event: str, data: Any) -> None:
        payload = {"event": event, "data": self._serialize(data)}
        dead: list[WebSocket] = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)

            for ws in dead:
                self._connections.discard(ws)
                self._chart_subscriptions.pop(ws, None)

    async def broadcast_scanner_status(self, status: Dict[str, Any]) -> None:
        await self.broadcast("scanner_status", status)

    async def broadcast_config_updated(self, section: str, values: Dict[str, Any]) -> None:
        await self.broadcast("config_updated", {"section": section, "values": values})

    async def broadcast_alert(self, alert: Dict[str, Any]) -> None:
        serial = self._serialize(alert)
        async with self._lock:
            self._alert_history.append(serial)
        await self.broadcast("web_alert", serial)

    async def broadcast_chart_candle(
        self,
        symbol: str,
        timeframe: str,
        candle: Dict[str, Any],
        indicators: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "event": "chart_candle_update",
            "data": {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "candle": candle,
                "indicators": indicators or {},
            },
        }

        dead: list[WebSocket] = []
        async with self._lock:
            for ws, sub in self._chart_subscriptions.items():
                if sub.get("symbol") != symbol.upper() or sub.get("timeframe") != timeframe:
                    continue
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)

            for ws in dead:
                self._connections.discard(ws)
                self._chart_subscriptions.pop(ws, None)

    async def broadcast_chart_setup(self, symbol: str, setup: Dict[str, Any]) -> None:
        payload = {
            "event": "chart_setup",
            "data": {"symbol": symbol.upper(), "setup": self._serialize(setup)},
        }
        dead: list[WebSocket] = []
        async with self._lock:
            for ws, sub in self._chart_subscriptions.items():
                if sub.get("symbol") != symbol.upper():
                    continue
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.append(ws)

            for ws in dead:
                self._connections.discard(ws)
                self._chart_subscriptions.pop(ws, None)

    async def handle_client_message(
        self,
        ws: WebSocket,
        message: Dict[str, Any],
        simulator: Any,
    ) -> Dict[str, Any]:
        action = str(message.get("action") or "").strip()

        if action == "subscribe_chart":
            symbol = str(message.get("symbol") or "").upper().strip()
            timeframe = str(message.get("timeframe") or "1m").lower()
            if timeframe not in {"1m", "5m"}:
                timeframe = "1m"
            if not symbol:
                return {"ok": False, "error": "missing_symbol"}

            async with self._lock:
                self._chart_subscriptions[ws] = {"symbol": symbol, "timeframe": timeframe}

            if self._chart_symbol_subscriber:
                await self._chart_symbol_subscriber(symbol)

            snapshot = {"candles": [], "overlays": {"vwap": [], "ema9": [], "ema20": [], "macd": []}}
            if self._chart_snapshot_getter:
                snapshot = await self._chart_snapshot_getter(symbol, timeframe)

            await ws.send_json(
                {
                    "event": "chart_snapshot",
                    "data": {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "candles": snapshot.get("candles", []),
                        "overlays": snapshot.get("overlays", {}),
                    },
                }
            )
            return {"ok": True, "action": action, "symbol": symbol, "timeframe": timeframe}

        if action == "change_timeframe":
            timeframe = str(message.get("timeframe") or "1m").lower()
            if timeframe not in {"1m", "5m"}:
                timeframe = "1m"

            async with self._lock:
                current = self._chart_subscriptions.get(ws, {}).copy()
                if not current.get("symbol"):
                    return {"ok": False, "error": "no_chart_subscription"}
                current["timeframe"] = timeframe
                self._chart_subscriptions[ws] = current

            snapshot = {"candles": [], "overlays": {"vwap": [], "ema9": [], "ema20": [], "macd": []}}
            if self._chart_snapshot_getter:
                snapshot = await self._chart_snapshot_getter(current["symbol"], timeframe)

            await ws.send_json(
                {
                    "event": "chart_snapshot",
                    "data": {
                        "symbol": current["symbol"],
                        "timeframe": timeframe,
                        "candles": snapshot.get("candles", []),
                        "overlays": snapshot.get("overlays", {}),
                    },
                }
            )
            return {"ok": True, "action": action, "timeframe": timeframe}

        if simulator is None:
            return {"ok": False, "error": "simulator_disabled"}

        if action == "close_trade":
            trade_id = int(message.get("trade_id"))
            trade_record = await simulator.db.get_trade_by_id(trade_id)
            if not trade_record or trade_record.status != "open":
                await self._audit(ws, "ws_trade_close_requested", "failure", {"trade_id": trade_id, "error": "trade_not_open"})
                return {"ok": False, "error": "trade_not_open", "trade_id": trade_id}

            current_price = await simulator._resolve_exit_market_price(trade_record)
            if simulator._use_alpaca_orders:
                blocked_reason = simulator.preview_broker_market_order(
                    symbol=trade_record.ticker,
                    qty=trade_record.quantity,
                    side="sell",
                    source="closed_manual",
                    estimated_price=current_price,
                )
                if blocked_reason:
                    await self._audit(ws, "ws_trade_close_requested", "blocked", {"trade_id": trade_id, "ticker": trade_record.ticker, "reason": blocked_reason})
                    return {"ok": False, "error": blocked_reason, "trade_id": trade_id}

            trade = await simulator.close_trade_by_id(trade_id)
            await self._audit(ws, "ws_trade_close_requested", "success" if trade else "failure", {"trade_id": trade_id, "ticker": trade_record.ticker})
            return {"ok": trade is not None, "trade_id": trade_id, "error": None if trade else "trade_not_closed"}

        if action == "reconcile_trade":
            trade_id = int(message.get("trade_id"))
            result = await simulator.reconcile_now(trade_id=trade_id)
            await self._audit(ws, "ws_trade_reconcile_requested", "success" if result.get("ok") else "failure", {"trade_id": trade_id, "error": result.get("error")})
            return result

        if action == "reconcile_now":
            result = await simulator.reconcile_now()
            await self._audit(ws, "ws_simulator_reconcile_requested", "success" if result.get("ok") else "failure", {"scope": result.get("scope"), "error": result.get("error")})
            return result

        if action == "change_profile":
            profile = str(message.get("profile") or "moderate")
            result = await simulator.change_profile(profile)
            await self._audit(ws, "ws_profile_changed", "success", {"profile": profile})
            return {"ok": True, **result}

        return {"ok": False, "error": "unknown_action"}

    async def _audit(self, ws: WebSocket, event: str, status: str, details: Dict[str, Any]) -> None:
        audit_logger = getattr(ws.app.state, "audit_logger", None)
        if audit_logger is None:
            return
        await audit_logger.log(event, {"status": status, "actor": websocket_actor(ws), "details": details})

    @staticmethod
    def _serialize(data: Any) -> Any:
        if hasattr(data, "to_dict"):
            return data.to_dict()
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                out[k] = WebSocketManager._serialize(v)
            return out
        if isinstance(data, list):
            return [WebSocketManager._serialize(x) for x in data]
        return data
