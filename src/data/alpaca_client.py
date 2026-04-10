from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from src.config import Settings

LOGGER = logging.getLogger(__name__)


class AsyncRateLimiter:
    def __init__(self, calls_per_minute: int) -> None:
        self._min_interval = 60.0 / max(1, calls_per_minute)
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            wait_for = self._min_interval - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_call = time.monotonic()


class AlpacaWebSocketClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.url = settings.alpaca.websocket_url
        self.key = settings.alpaca.key_id
        self.secret = settings.alpaca.secret_key
        self.max_backoff = settings.runtime.websocket.reconnect_max_seconds

        self._ws = None
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
        self._subscribed_bars: set[str] = set()
        self._subscribed_statuses: set[str] = set()
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], Awaitable[None]]]] = defaultdict(list)

    def on(self, event_name: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        self._handlers[event_name].append(handler)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._listener_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def subscribe(self, bars: Sequence[str] = (), statuses: Sequence[str] = ()) -> None:
        if bars:
            self._subscribed_bars.update(s.upper() for s in bars)
        if statuses:
            self._subscribed_statuses.update(s.upper() for s in statuses)
        await self._send_subscriptions()

    async def _send_subscriptions(self) -> None:
        if not self._ws:
            return
        payload = {
            "action": "subscribe",
            "bars": sorted(self._subscribed_bars),
            "statuses": sorted(self._subscribed_statuses),
        }
        await self._ws.send(json.dumps(payload))

    async def _run(self) -> None:
        backoff = 1
        while self._running:
            try:
                LOGGER.info("Connecting to Alpaca websocket: %s", self.url)
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    await self._authenticate()
                    await self._send_subscriptions()
                    backoff = 1

                    async for raw_message in ws:
                        await self._handle_message(raw_message)
            except (ConnectionClosedError, ConnectionClosedOK, OSError) as exc:
                LOGGER.warning("Alpaca websocket disconnected: %s", exc)
            except Exception as exc:
                LOGGER.exception("Unexpected Alpaca websocket failure: %s", exc)
            finally:
                self._ws = None

            if not self._running:
                break

            sleep_for = min(self.max_backoff, backoff)
            LOGGER.info("Reconnecting Alpaca websocket in %ss", sleep_for)
            await asyncio.sleep(sleep_for)
            backoff = min(self.max_backoff, backoff * 2)

    async def _authenticate(self) -> None:
        assert self._ws is not None
        payload = {"action": "auth", "key": self.key, "secret": self.secret}
        await self._ws.send(json.dumps(payload))

    async def _handle_message(self, raw_message: str) -> None:
        try:
            messages = json.loads(raw_message)
            if not isinstance(messages, list):
                messages = [messages]
        except json.JSONDecodeError:
            LOGGER.debug("Could not parse websocket message: %s", raw_message)
            return

        for message in messages:
            msg_type = message.get("T")
            if msg_type == "b":
                await self._dispatch("bar", message)
            elif msg_type == "s":
                await self._dispatch("status", message)

    async def _dispatch(self, event_name: str, payload: Dict[str, Any]) -> None:
        handlers = self._handlers.get(event_name, [])
        if not handlers:
            return
        await asyncio.gather(*(h(payload) for h in handlers), return_exceptions=True)


class AlpacaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._rate_limiter = AsyncRateLimiter(settings.runtime.rate_limits.alpaca_calls_per_minute)
        self._session: Optional[aiohttp.ClientSession] = None
        self._cached_symbols: tuple[datetime, List[str]] | None = None

    async def start(self) -> None:
        if self._session:
            return
        timeout = aiohttp.ClientTimeout(total=self.settings.alpaca.request_timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.settings.alpaca.key_id,
            "APCA-API-SECRET-KEY": self.settings.alpaca.secret_key,
        }

    async def get_active_symbols(self) -> List[str]:
        if self._cached_symbols:
            cached_at, symbols = self._cached_symbols
            if datetime.now(timezone.utc) - cached_at < timedelta(hours=24):
                return symbols

        path = "/v2/assets"
        params = {"status": "active", "asset_class": "us_equity"}
        response = await self._request_json(self.settings.alpaca.trading_base_url, path, params=params)

        symbols = []
        for asset in response:
            if not isinstance(asset, dict):
                continue
            if not asset.get("tradable", False):
                continue
            sym = str(asset.get("symbol", "")).upper()
            if sym and "." not in sym:
                symbols.append(sym)

        self._cached_symbols = (datetime.now(timezone.utc), symbols)
        return symbols

    async def get_snapshots(self, symbols: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}

        path = "/v2/stocks/snapshots"
        params = {
            "symbols": ",".join(symbols),
            "feed": self.settings.alpaca.feed,
        }
        response = await self._request_json(self.settings.alpaca.data_base_url, path, params=params)
        if not isinstance(response, dict):
            return {}
        return response

    async def get_snapshots_chunked(self, symbols: Sequence[str], chunk_size: int = 200) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}

        snapshots: Dict[str, Dict[str, Any]] = {}
        chunks = math.ceil(len(symbols) / max(1, chunk_size))

        for i in range(chunks):
            chunk = list(symbols[i * chunk_size : (i + 1) * chunk_size])
            if not chunk:
                continue
            try:
                part = await self.get_snapshots(chunk)
                snapshots.update(part)
            except Exception as exc:
                LOGGER.warning("Snapshot chunk %s failed: %s", i + 1, exc)

        return snapshots

    async def get_universe_snapshots(self, max_candidates: int) -> Dict[str, Dict[str, Any]]:
        symbols = await self.get_active_symbols()
        symbols = symbols[: max_candidates * 3]
        return await self.get_snapshots_chunked(symbols)

    async def get_average_volume(self, symbol: str, period_days: int = 20) -> float:
        profile = await self.get_average_volume_profile(symbol, lookback_days=period_days)
        return float(profile.get("average_volume") or 0.0)

    async def get_average_volume_profile(self, symbol: str, lookback_days: int = 20) -> Dict[str, Any]:
        bars = await self.get_stock_bars(symbol, timeframe="1Day", limit=max(lookback_days, 2))
        volumes = [float(bar.get("volume", 0) or 0) for bar in bars if float(bar.get("volume", 0) or 0) > 0]
        if volumes:
            window = volumes[-lookback_days:]
            return {
                "average_volume": sum(window) / len(window),
                "basis": f"alpaca_daily_bars_{len(window)}d",
                "sample_days": len(window),
            }

        path = f"/v2/stocks/{symbol.upper()}/snapshot"
        params = {"feed": self.settings.alpaca.feed}
        response = await self._request_json(self.settings.alpaca.data_base_url, path, params=params)
        if not isinstance(response, dict):
            return {
                "average_volume": 0.0,
                "basis": "unavailable",
                "sample_days": 0,
            }

        daily_bar = response.get("dailyBar") or {}
        prev_daily_bar = response.get("prevDailyBar") or {}
        fallback_volumes = [
            float(bar.get("v") or 0)
            for bar in (daily_bar, prev_daily_bar)
            if isinstance(bar, dict) and float(bar.get("v") or 0) > 0
        ]
        if fallback_volumes:
            return {
                "average_volume": sum(fallback_volumes) / len(fallback_volumes),
                "basis": f"snapshot_fallback_{len(fallback_volumes)}d",
                "sample_days": len(fallback_volumes),
            }

        return {
            "average_volume": 0.0,
            "basis": "unavailable",
            "sample_days": 0,
        }

    async def get_stock_bars(self, symbol: str, timeframe: str = "1Min", limit: int = 200) -> List[Dict[str, Any]]:
        path = f"/v2/stocks/{symbol.upper()}/bars"
        params = {
            "timeframe": timeframe,
            "limit": str(max(1, min(limit, 500))),
            "adjustment": "raw",
            "feed": self.settings.alpaca.feed,
        }
        response = await self._request_json(self.settings.alpaca.data_base_url, path, params=params)
        raw_bars = response.get("bars") if isinstance(response, dict) else []
        bars = raw_bars if isinstance(raw_bars, list) else []
        out: List[Dict[str, Any]] = []
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            out.append(
                {
                    "time": bar.get("t"),
                    "open": float(bar.get("o", 0) or 0),
                    "high": float(bar.get("h", 0) or 0),
                    "low": float(bar.get("l", 0) or 0),
                    "close": float(bar.get("c", 0) or 0),
                    "volume": int(bar.get("v", 0) or 0),
                }
            )
        return out

    async def submit_market_order(self, symbol: str, qty: int, side: str = "buy") -> Dict[str, Any]:
        path = "/v2/orders"
        payload = {
            "symbol": symbol.upper(),
            "qty": str(max(1, int(qty))),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        response = await self._post_json(self.settings.alpaca.trading_base_url, path, payload)
        return response if isinstance(response, dict) else {}

    async def get_positions(self) -> List[Dict[str, Any]]:
        path = "/v2/positions"
        response = await self._request_json(self.settings.alpaca.trading_base_url, path)
        return response if isinstance(response, list) else []

    async def get_account(self) -> Dict[str, Any]:
        path = "/v2/account"
        response = await self._request_json(self.settings.alpaca.trading_base_url, path)
        return response if isinstance(response, dict) else {}

    async def get_latest_trade_price(self, symbol: str) -> Optional[float]:
        snapshot = await self._request_json(
            self.settings.alpaca.data_base_url,
            f"/v2/stocks/{symbol.upper()}/snapshot",
            params={"feed": self.settings.alpaca.feed},
        )
        if not isinstance(snapshot, dict):
            return None

        latest_trade = snapshot.get("latestTrade") or {}
        daily_bar = snapshot.get("dailyBar") or {}
        prev_daily_bar = snapshot.get("prevDailyBar") or {}
        for candidate in (
            latest_trade.get("p"),
            daily_bar.get("c"),
            prev_daily_bar.get("c"),
        ):
            if candidate is None:
                continue
            price = float(candidate or 0)
            if price > 0:
                return price
        return None

    async def _request_json(
        self,
        base_url: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        max_attempts: int = 4,
    ) -> Any:
        if not self._session:
            raise RuntimeError("AlpacaClient.start() must be called before requests")

        url = f"{base_url.rstrip('/')}{path}"
        for attempt in range(1, max_attempts + 1):
            await self._rate_limiter.wait()
            try:
                async with self._session.get(url, headers=self.headers, params=params) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "2"))
                        LOGGER.warning("Alpaca rate limited. Retrying in %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as exc:
                if attempt == max_attempts:
                    raise
                LOGGER.warning("Alpaca request failed (%s). Attempt %s/%s", exc.status, attempt, max_attempts)
                await asyncio.sleep(attempt)
            except asyncio.TimeoutError:
                if attempt == max_attempts:
                    raise
                LOGGER.warning("Alpaca request timeout. Attempt %s/%s", attempt, max_attempts)
                await asyncio.sleep(attempt)

        raise RuntimeError(f"Failed Alpaca request after {max_attempts} attempts: {url}")

    async def _post_json(
        self,
        base_url: str,
        path: str,
        payload: Dict[str, Any],
        max_attempts: int = 3,
    ) -> Any:
        if not self._session:
            raise RuntimeError("AlpacaClient.start() must be called before requests")

        url = f"{base_url.rstrip('/')}{path}"
        for attempt in range(1, max_attempts + 1):
            await self._rate_limiter.wait()
            try:
                async with self._session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "2"))
                        LOGGER.warning("Alpaca POST rate limited. Retrying in %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as exc:
                if attempt == max_attempts:
                    raise
                LOGGER.warning("Alpaca POST failed (%s). Attempt %s/%s", exc.status, attempt, max_attempts)
                await asyncio.sleep(attempt)
            except asyncio.TimeoutError:
                if attempt == max_attempts:
                    raise
                LOGGER.warning("Alpaca POST timeout. Attempt %s/%s", attempt, max_attempts)
                await asyncio.sleep(attempt)

        raise RuntimeError(f"Failed Alpaca POST after {max_attempts} attempts: {url}")
