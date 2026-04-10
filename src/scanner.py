from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz

from src.config import Settings
from src.data.alpaca_client import AlpacaClient, AlpacaWebSocketClient
from src.data.finnhub_client import FinnhubClient
from src.data.models import PillarEvaluation, StockCandidate
from src.db.manager import DatabaseManager
from src.event_bus import EventBus
from src.indicators import evaluate_entry_signals
from src.utils import get_primary_window_info

LOGGER = logging.getLogger(__name__)


class DayTradeScanner:
    def __init__(
        self,
        settings: Settings,
        alpaca_client: AlpacaClient,
        finnhub_client: FinnhubClient,
        alerter: Any,
        event_bus: Optional[EventBus] = None,
        db: Optional[DatabaseManager] = None,
    ) -> None:
        self.settings = settings
        self.alpaca_client = alpaca_client
        self.finnhub_client = finnhub_client
        self.alerter = alerter
        self.event_bus = event_bus
        self.db = db

        self._et = pytz.timezone(settings.timezone)
        self._avg_volume_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self._alert_cache: Dict[str, Dict[str, Any]] = {}

        self._universe: List[Tuple[str, Dict[str, Any]]] = []
        self._universe_last_refresh: Optional[datetime] = None
        self._universe_scan_offset: int = 0
        self._universe_stats: Dict[str, Any] = {
            "active_symbols": 0,
            "window_symbols": 0,
            "scan_offset": 0,
            "coverage_pct": 0.0,
        }

        self._bars_stream: Dict[str, Dict[str, Any]] = {}
        self._ws: Optional[AlpacaWebSocketClient] = None

        self._scanner_hits_file: Optional[Path] = None
        self._alerts_file: Optional[Path] = None
        self._latest_candidates: List[StockCandidate] = []
        self._scanner_state: str = "idle"
        self._last_scan_at: Optional[datetime] = None

        # Mutable threshold/runtime overlay
        th = settings.scanner.thresholds
        ah = settings.scanner.active_hours
        self._min_gap_percent = float(th.min_gap_percent)
        self._min_price = float(th.min_price)
        self._max_price = float(th.max_price)
        self._min_relative_volume = float(th.min_relative_volume)
        self._max_float_shares = int(th.max_float_shares)
        self._min_pillars_for_alert = int(th.min_pillars_for_alert)

        self._start_hour_et = int(ah.start_hour_et)
        self._end_hour_et = int(ah.end_hour_et)
        self._primary_window_start = int(ah.primary_window_start_hour_et)
        self._primary_window_end = int(ah.primary_window_end_hour_et)

    async def start(self) -> None:
        await self.alpaca_client.start()
        await self.finnhub_client.start()
        await self.alerter.start()

        if self.settings.runtime.websocket.enabled:
            self._ws = AlpacaWebSocketClient(self.settings)
            self._ws.on("bar", self._on_ws_bar)
            self._ws.on("status", self._on_ws_status)
            await self._ws.start()

    async def stop(self) -> None:
        if self._ws:
            await self._ws.stop()
        await self.alpaca_client.close()
        await self.finnhub_client.close()
        await self.alerter.close()

    async def run_forever(self) -> None:
        LOGGER.info(
            "Scanner started. Active window: %s:00-%s:00 ET",
            self._start_hour_et,
            self._end_hour_et,
        )
        while True:
            try:
                if not self._is_active_hours():
                    self._scanner_state = "sleeping"
                    await asyncio.sleep(30)
                    continue

                self._scanner_state = "scanning"
                self._last_scan_at = datetime.now(timezone.utc)

                await self._refresh_universe_if_needed()
                candidates = await self._scan_universe()
                self._latest_candidates = candidates
                await self._process_candidates(candidates)

                self._scanner_state = "waiting"
                await asyncio.sleep(self._current_scan_interval_seconds())
            except Exception:
                self._scanner_state = "error"
                LOGGER.exception("Unhandled scanner loop error")
                await asyncio.sleep(5)

    def get_watchlist(self) -> List[Dict[str, Any]]:
        return [candidate.to_dict() for candidate in self._latest_candidates]

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self._scanner_state,
            "session": self._session_label(),
            "candidates_count": len(self._latest_candidates),
            "next_scan_seconds": self._current_scan_interval_seconds(),
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "primary_window": get_primary_window_info(
                self.settings.timezone,
                self._primary_window_start,
                self._primary_window_end,
            ),
            "universe": self._universe_stats,
        }

    def get_thresholds(self) -> Dict[str, Any]:
        return {
            "min_gap_percent": self._min_gap_percent,
            "min_price": self._min_price,
            "max_price": self._max_price,
            "min_relative_volume": self._min_relative_volume,
            "max_float_shares": self._max_float_shares,
            "min_pillars_for_alert": self._min_pillars_for_alert,
            "relative_volume_lookback_days": self.settings.scanner.thresholds.relative_volume_lookback_days,
            "universe_scan_multiplier": self.settings.scanner.thresholds.universe_scan_multiplier,
            "primary_window_start_hour_et": self._primary_window_start,
            "primary_window_end_hour_et": self._primary_window_end,
            "start_hour_et": self._start_hour_et,
            "end_hour_et": self._end_hour_et,
        }

    async def update_thresholds(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        if "min_gap_percent" in updates:
            self._min_gap_percent = float(updates["min_gap_percent"])
        if "min_price" in updates:
            self._min_price = float(updates["min_price"])
        if "max_price" in updates:
            self._max_price = float(updates["max_price"])
        if "min_relative_volume" in updates:
            self._min_relative_volume = float(updates["min_relative_volume"])
        if "max_float_shares" in updates:
            self._max_float_shares = int(updates["max_float_shares"])
        if "min_pillars_for_alert" in updates:
            self._min_pillars_for_alert = int(updates["min_pillars_for_alert"])
        if "start_hour_et" in updates:
            self._start_hour_et = int(updates["start_hour_et"])
        if "end_hour_et" in updates:
            self._end_hour_et = int(updates["end_hour_et"])
        if "primary_window_start_hour_et" in updates:
            self._primary_window_start = int(updates["primary_window_start_hour_et"])
        if "primary_window_end_hour_et" in updates:
            self._primary_window_end = int(updates["primary_window_end_hour_et"])

        if self._min_price >= self._max_price:
            raise ValueError("min_price must be < max_price")
        if not (1 <= self._min_pillars_for_alert <= 5):
            raise ValueError("min_pillars_for_alert must be between 1 and 5")
        if self._start_hour_et >= self._end_hour_et:
            raise ValueError("start_hour_et must be before end_hour_et")
        if self._primary_window_start >= self._primary_window_end:
            raise ValueError("primary_window_start_hour_et must be before primary_window_end_hour_et")

        return self.get_thresholds()

    async def subscribe_stream_symbol(self, symbol: str) -> None:
        if self._ws:
            sym = symbol.upper().strip()
            if sym:
                await self._ws.subscribe(bars=[sym], statuses=[sym])

    async def _refresh_universe_if_needed(self) -> None:
        now = datetime.now(timezone.utc)
        refresh_seconds = self.settings.scanner.intervals_seconds.universe_refresh

        if self._universe_last_refresh and (now - self._universe_last_refresh).total_seconds() < refresh_seconds:
            return

        LOGGER.info("Refreshing scanner universe")
        t = self.settings.scanner.thresholds
        active_symbols = await self.alpaca_client.get_active_symbols()
        total_symbols = len(active_symbols)
        if total_symbols == 0:
            self._universe = []
            self._universe_stats = {
                "active_symbols": 0,
                "window_symbols": 0,
                "scan_offset": 0,
                "coverage_pct": 0.0,
            }
            self._universe_last_refresh = now
            return

        window_size = min(total_symbols, max(t.max_candidates_per_cycle * t.universe_scan_multiplier, t.max_candidates_per_cycle))
        offset = self._universe_scan_offset % total_symbols
        selected_symbols = [active_symbols[(offset + i) % total_symbols] for i in range(window_size)]
        raw = await self.alpaca_client.get_snapshots_chunked(selected_symbols)

        prepared: List[Tuple[str, Dict[str, Any]]] = []
        for symbol, snap in raw.items():
            metrics = self._extract_snapshot_metrics(symbol, snap)
            if not metrics:
                continue
            if metrics["price"] <= 0 or metrics["prev_close"] <= 0:
                continue
            if metrics["volume"] < t.prefilter_min_volume:
                continue
            if metrics["gap_percent"] < t.prefilter_min_gap_percent:
                continue
            prepared.append((symbol, metrics))

        prepared.sort(key=lambda x: x[1]["gap_percent"], reverse=True)
        self._universe = prepared[: t.max_candidates_per_cycle]
        self._universe_last_refresh = now
        self._universe_scan_offset = (offset + window_size) % total_symbols
        self._universe_stats = {
            "active_symbols": total_symbols,
            "window_symbols": window_size,
            "scan_offset": offset,
            "coverage_pct": round((window_size / total_symbols) * 100.0, 2),
        }

        if self._ws and self._universe:
            top_symbols = [s for s, _ in self._universe[: self.settings.runtime.websocket.max_symbols]]
            await self._ws.subscribe(bars=top_symbols, statuses=top_symbols)

        LOGGER.info(
            "Universe refreshed: %s candidates from %s/%s symbols",
            len(self._universe),
            window_size,
            total_symbols,
        )

    async def _scan_universe(self) -> List[StockCandidate]:
        if not self._universe:
            return []

        semaphore = asyncio.Semaphore(self.settings.runtime.worker.max_concurrent_symbol_checks)
        tasks = [self._build_candidate(symbol, metrics, rank + 1, semaphore) for rank, (symbol, metrics) in enumerate(self._universe)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: List[StockCandidate] = []
        for result in results:
            if isinstance(result, Exception):
                LOGGER.warning("Candidate build failed: %s", result)
                continue
            if result is not None:
                candidates.append(result)

        candidates.sort(key=lambda c: c.gap_percent, reverse=True)
        return candidates

    async def _build_candidate(
        self,
        symbol: str,
        metrics: Dict[str, Any],
        rank: int,
        semaphore: asyncio.Semaphore,
    ) -> Optional[StockCandidate]:
        async with semaphore:
            t = self.settings.scanner.thresholds
            price = float(metrics["price"])
            gap_percent = float(metrics["gap_percent"])
            volume = int(metrics["volume"])

            avg_volume_profile = await self._get_avg_volume(symbol)
            avg_volume = max(float(t.min_avg_volume_floor), float(avg_volume_profile.get("average_volume") or 0.0))
            relative_volume = volume / avg_volume if avg_volume > 0 else 0.0

            float_shares = await self.finnhub_client.get_float_shares(symbol)
            news = await self.finnhub_client.get_recent_news(symbol, max_age_hours=t.max_news_age_hours)

            pillars = PillarEvaluation(
                price=(self._min_price <= price <= self._max_price),
                gap_percent=(gap_percent >= self._min_gap_percent),
                relative_volume=(relative_volume >= self._min_relative_volume),
                float_shares=(float_shares is not None and float_shares <= self._max_float_shares),
                news_catalyst=(news is not None),
            )

            session = self._session_label()
            entry_signals = await self._evaluate_entry_signals(symbol)

            candidate = StockCandidate(
                ticker=symbol,
                price=price,
                gap_percent=gap_percent,
                volume=volume,
                avg_volume=avg_volume,
                relative_volume=relative_volume,
                avg_volume_basis=str(avg_volume_profile.get("basis") or "unknown"),
                float_shares=float_shares,
                float_tier=self._float_tier(float_shares),
                news=news,
                market_rank=rank,
                session_label=session,
                scanned_at=datetime.now(timezone.utc),
                pillars=pillars,
                entry_signals=entry_signals,
            )

            await self._log_scanner_hit(candidate)

            if self.db:
                candidate.db_id = await self.db.insert_scanner_hit(candidate)
            if self.event_bus:
                await self.event_bus.emit("scanner_hit", candidate)

            return candidate

    async def _process_candidates(self, candidates: List[StockCandidate]) -> None:
        min_score = self._min_pillars_for_alert
        for candidate in candidates:
            if not candidate.pillars:
                continue
            if candidate.pillars.score < min_score:
                continue
            if not self._should_alert(candidate):
                continue

            send_result = await self.alerter.send_scanner_hit(candidate)
            await self._log_alert(candidate, send_result)
            if self.db:
                await self.db.insert_alert(
                    scanner_hit_id=candidate.db_id,
                    ticker=candidate.ticker,
                    status=send_result.get("status", "unknown"),
                    message_id=send_result.get("message_id", ""),
                    sent_at=send_result.get("sent_at"),
                )
            if self.event_bus:
                await self.event_bus.emit("alert_sent", {"candidate": candidate, "send_result": send_result})
            self._remember_alert(candidate)
            LOGGER.info(
                "Alert sent for %s (score=%s, status=%s)",
                candidate.ticker,
                candidate.pillars.score,
                send_result.get("status"),
            )

    def _extract_snapshot_metrics(self, symbol: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            latest_trade = snapshot.get("latestTrade") or {}
            daily = snapshot.get("dailyBar") or {}
            prev = snapshot.get("prevDailyBar") or {}

            price = float(latest_trade.get("p") or daily.get("c") or 0)
            prev_close = float(prev.get("c") or 0)
            volume = int(daily.get("v") or 0)
            gap = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

            stream_bar = self._bars_stream.get(symbol, {})
            if stream_bar:
                price = float(stream_bar.get("c") or price)
                volume = max(volume, int(stream_bar.get("v") or 0))
                gap = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else gap

            return {
                "symbol": symbol,
                "price": price,
                "prev_close": prev_close,
                "volume": volume,
                "gap_percent": gap,
            }
        except Exception:
            return None

    async def _get_avg_volume(self, symbol: str) -> Dict[str, Any]:
        cached = self._avg_volume_cache.get(symbol)
        now = datetime.now(timezone.utc)
        if cached and (now - cached[1]) < timedelta(hours=24):
            return cached[0]

        avg_profile = await self.alpaca_client.get_average_volume_profile(
            symbol,
            lookback_days=self.settings.scanner.thresholds.relative_volume_lookback_days,
        )
        self._avg_volume_cache[symbol] = (avg_profile, now)
        return avg_profile

    async def _evaluate_entry_signals(self, symbol: str) -> Dict[str, Any]:
        try:
            bars = await self.alpaca_client.get_stock_bars(symbol.upper(), timeframe="1Min", limit=60)
            if not bars:
                return {
                    "macd_positive": False,
                    "above_vwap": False,
                    "above_ema9": False,
                    "volume_bullish": False,
                    "all_clear": False,
                }
            return evaluate_entry_signals(bars)
        except Exception:
            return {
                "macd_positive": False,
                "above_vwap": False,
                "above_ema9": False,
                "volume_bullish": False,
                "all_clear": False,
            }

    def _float_tier(self, float_shares: Optional[int]) -> str:
        if float_shares is None:
            return "unknown"
        if float_shares < 2_000_000:
            return "ideal"
        if float_shares < 5_000_000:
            return "great"
        if float_shares < 10_000_000:
            return "good"
        if float_shares < 20_000_000:
            return "acceptable"
        return "poor"

    def _should_alert(self, candidate: StockCandidate) -> bool:
        cooldown_minutes = self.settings.scanner.alert.cooldown_minutes
        breakout_pct = self.settings.scanner.alert.new_high_realert_percent / 100.0

        cached = self._alert_cache.get(candidate.ticker)
        if not cached:
            return True

        last_time: datetime = cached["ts"]
        last_price: float = cached["price"]

        age_minutes = (datetime.now(timezone.utc) - last_time).total_seconds() / 60.0
        if age_minutes >= cooldown_minutes:
            return True

        return candidate.price >= last_price * (1 + breakout_pct)

    def _remember_alert(self, candidate: StockCandidate) -> None:
        self._alert_cache[candidate.ticker] = {
            "ts": datetime.now(timezone.utc),
            "price": candidate.price,
        }

    async def _on_ws_bar(self, message: Dict[str, Any]) -> None:
        symbol = str(message.get("S") or "").upper()
        if not symbol:
            return
        self._bars_stream[symbol] = message

        if self.event_bus:
            await self.event_bus.emit(
                "price_update",
                {
                    "symbol": symbol,
                    "price": float(message.get("c", 0) or 0),
                    "open": float(message.get("o", 0) or 0),
                    "high": float(message.get("h", 0) or 0),
                    "low": float(message.get("l", 0) or 0),
                    "close": float(message.get("c", 0) or 0),
                    "volume": int(message.get("v", 0) or 0),
                    "timestamp": message.get("t"),
                },
            )

    async def _on_ws_status(self, message: Dict[str, Any]) -> None:
        symbol = str(message.get("S") or "").upper()
        if not symbol:
            return

        reason = str(message.get("sm") or "status update")
        code = str(message.get("sc") or "")
        text = f"🛑 HALT/STATUS: ${symbol}\nReason: {reason} ({code})"
        await self.alerter.send_system_message(text)

    def _is_active_hours(self) -> bool:
        now_et = datetime.now(timezone.utc).astimezone(self._et)
        # Weekends off — US stock market doesn't trade Sat/Sun
        if now_et.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return False
        hour = now_et.hour + (now_et.minute / 60)
        return self._start_hour_et <= hour < self._end_hour_et

    def _session_label(self) -> str:
        now_et = datetime.now(timezone.utc).astimezone(self._et)
        if now_et.weekday() >= 5:
            return "weekend"
        hour_decimal = now_et.hour + (now_et.minute / 60)
        if hour_decimal < self._primary_window_start:
            return "pre_scan"
        if hour_decimal < self._primary_window_end:
            return "primary_window"
        return "extended"

    def _current_scan_interval_seconds(self) -> int:
        session = self._session_label()
        i = self.settings.scanner.intervals_seconds
        if session == "pre_scan":
            return i.premarket
        if session == "primary_window":
            return i.market_open
        return i.late_day

    async def _log_scanner_hit(self, candidate: StockCandidate) -> None:
        path = self._daily_file(self.settings.logging.scanner_hits_filename_pattern)
        payload = candidate.to_dict()
        payload["event"] = "scanner_hit"
        await self._append_jsonl(path, payload)

    async def _log_alert(self, candidate: StockCandidate, send_result: Dict[str, str]) -> None:
        path = self._daily_file(self.settings.logging.alerts_filename_pattern)
        payload = {
            "event": "telegram_alert",
            "ticker": candidate.ticker,
            "scanned_at": candidate.scanned_at.isoformat(),
            "score": candidate.pillars.score if candidate.pillars else 0,
            "send_result": send_result,
            "candidate": candidate.to_dict(),
        }
        await self._append_jsonl(path, payload)

    def _daily_file(self, pattern: str) -> Path:
        logs_dir = Path(self.settings.logging.directory)
        logs_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now(self._et).strftime(pattern)
        return logs_dir / filename

    async def _append_jsonl(self, path: Path, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, default=str)
        await asyncio.to_thread(self._append_line_sync, path, line)

    @staticmethod
    def _append_line_sync(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
