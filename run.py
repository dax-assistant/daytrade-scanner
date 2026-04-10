from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytz
import uvicorn

from src.alerts import TelegramAlerter
from src.config import load_settings
from src.data.alpaca_client import AlpacaClient
from src.data.finnhub_client import FinnhubClient
from src.db.manager import DatabaseManager
from src.event_bus import EventBus
from src.indicators import compute_overlays
from src.notifications import NotificationRouter
from src.ohlcv_aggregator import CandleBuilder
from src.scanner import DayTradeScanner
from src.simulator.engine import PaperTradingSimulator
from src.simulator.reports import ReportGenerator
from src.utils import get_market_session
from src.web.app import create_app
from src.web.ws_manager import WebSocketManager


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def _main_async(config_path: Path) -> None:
    settings = load_settings(config_path)
    configure_logging(settings.logging.level)

    event_bus = EventBus()
    db = DatabaseManager(settings.database.path)
    await db.initialize()

    alpaca_client = AlpacaClient(settings)
    finnhub_client = FinnhubClient(settings)

    ws_manager = WebSocketManager()
    telegram_alerter = TelegramAlerter(settings)
    notification_router = NotificationRouter(
        telegram_alerter=telegram_alerter,
        ws_manager=ws_manager,
        telegram_enabled=settings.telegram_enabled,
    )

    candle_1m = CandleBuilder(interval_sec=60, max_candles=500)
    candle_5m = CandleBuilder(interval_sec=300, max_candles=500)

    scanner = DayTradeScanner(
        settings=settings,
        alpaca_client=alpaca_client,
        finnhub_client=finnhub_client,
        alerter=notification_router,
        event_bus=event_bus,
        db=db,
    )

    simulator = PaperTradingSimulator(
        settings=settings,
        event_bus=event_bus,
        db=db,
        alpaca_client=alpaca_client,
    )

    reports = ReportGenerator(db=db, notifier=notification_router, timezone_name=settings.timezone)

    async def _chart_snapshot(symbol: str, timeframe: str) -> Dict[str, Any]:
        builder = candle_1m if timeframe == "1m" else candle_5m
        snapshot = builder.get_snapshot(symbol)
        if not snapshot:
            tf = "1Min" if timeframe == "1m" else "5Min"
            try:
                bars = await alpaca_client.get_stock_bars(symbol, timeframe=tf, limit=200)
                for bar in bars:
                    builder.ingest_bar(
                        symbol=symbol,
                        open_price=float(bar.get("open", 0) or 0),
                        high_price=float(bar.get("high", 0) or 0),
                        low_price=float(bar.get("low", 0) or 0),
                        close_price=float(bar.get("close", 0) or 0),
                        volume=int(bar.get("volume", 0) or 0),
                        timestamp=bar.get("time") or datetime.now(timezone.utc).isoformat(),
                    )
            except Exception:
                pass
            snapshot = builder.get_snapshot(symbol)

        return {"candles": snapshot, "overlays": compute_overlays(snapshot)}

    ws_manager.set_chart_snapshot_getter(_chart_snapshot)
    ws_manager.set_chart_symbol_subscriber(scanner.subscribe_stream_symbol)

    app = create_app(
        settings=settings,
        event_bus=event_bus,
        db=db,
        simulator=simulator if settings.simulator.enabled else None,
        ws_manager=ws_manager,
        scanner=scanner,
        config_path=config_path,
        alpaca_client=alpaca_client,
    )
    app.state.notification_router = notification_router

    event_bus.on("scanner_hit", lambda data: ws_manager.broadcast("scanner_hit", data))
    event_bus.on("alert_sent", lambda data: ws_manager.broadcast("alert_sent", data))
    event_bus.on("trade_opened", lambda data: ws_manager.broadcast("trade_opened", data))
    event_bus.on("trade_closed", lambda data: ws_manager.broadcast("trade_closed", data))
    event_bus.on("trade_updated", lambda data: ws_manager.broadcast("trade_updated", data))
    event_bus.on("position_update", lambda data: ws_manager.broadcast("position_update", data))
    event_bus.on("entry_rejected", lambda data: ws_manager.broadcast("entry_rejected", data))

    async def _on_entry_rejected(payload: Dict[str, Any]) -> None:
        await ws_manager.broadcast_alert(
            {
                "type": "entry_rejected",
                "message": f"{payload.get('ticker', '')} entry rejected: entry signals not met",
                "data": payload,
                "timestamp": datetime.now(timezone.utc).timestamp(),
            }
        )

    async def _on_price_update(payload: Dict[str, Any]) -> None:
        symbol = str(payload.get("symbol") or "").upper()
        if not symbol:
            return

        timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
        open_price = float(payload.get("open", payload.get("price", 0)) or 0)
        high_price = float(payload.get("high", payload.get("price", 0)) or 0)
        low_price = float(payload.get("low", payload.get("price", 0)) or 0)
        close_price = float(payload.get("close", payload.get("price", 0)) or 0)
        volume = int(payload.get("volume", 0) or 0)

        c1 = candle_1m.ingest_bar(symbol, open_price, high_price, low_price, close_price, volume, timestamp)
        c5 = candle_5m.ingest_bar(symbol, open_price, high_price, low_price, close_price, volume, timestamp)

        snap1 = candle_1m.get_snapshot(symbol)
        snap5 = candle_5m.get_snapshot(symbol)
        overlays1 = compute_overlays(snap1)
        overlays5 = compute_overlays(snap5)

        indicators_1m = {
            "vwap": (overlays1.get("vwap") or [{}])[-1].get("value", 0),
            "ema9": (overlays1.get("ema9") or [{}])[-1].get("value", 0),
            "ema20": (overlays1.get("ema20") or [{}])[-1].get("value", 0),
            "macd": (overlays1.get("macd") or [{}])[-1] if overlays1.get("macd") else {"macd": 0, "signal": 0, "histogram": 0},
        }
        indicators_5m = {
            "vwap": (overlays5.get("vwap") or [{}])[-1].get("value", 0),
            "ema9": (overlays5.get("ema9") or [{}])[-1].get("value", 0),
            "ema20": (overlays5.get("ema20") or [{}])[-1].get("value", 0),
            "macd": (overlays5.get("macd") or [{}])[-1] if overlays5.get("macd") else {"macd": 0, "signal": 0, "histogram": 0},
        }

        await asyncio.gather(
            ws_manager.broadcast_chart_candle(symbol, "1m", c1, indicators=indicators_1m),
            ws_manager.broadcast_chart_candle(symbol, "5m", c5, indicators=indicators_5m),
            ws_manager.broadcast("chart_indicators", {"symbol": symbol, "timeframe": "1m", **indicators_1m}),
        )

    async def _on_trade_opened(trade):
        await notification_router.send_trade_alert(trade, "opened")
        setup = {
            "entry": trade.entry_price,
            "stop": trade.stop_loss,
            "target": trade.take_profit,
            "trailing_stop": (
                trade.max_price_seen * (1 - trade.trailing_stop_pct / 100.0)
                if trade.trailing_stop_pct
                else None
            ),
        }
        await ws_manager.broadcast_chart_setup(trade.ticker, setup)

    async def _on_trade_closed(trade):
        await notification_router.send_trade_alert(trade, "closed")

    async def _on_trade_updated(trade):
        setup = {
            "entry": trade.entry_price,
            "stop": trade.stop_loss,
            "target": trade.take_profit,
            "trailing_stop": (
                trade.max_price_seen * (1 - trade.trailing_stop_pct / 100.0)
                if trade.trailing_stop_pct
                else None
            ),
        }
        await ws_manager.broadcast_chart_setup(trade.ticker, setup)

    event_bus.on("price_update", _on_price_update)
    event_bus.on("trade_opened", _on_trade_opened)
    event_bus.on("trade_closed", _on_trade_closed)
    event_bus.on("trade_updated", _on_trade_updated)
    event_bus.on("entry_rejected", _on_entry_rejected)

    await scanner.start()
    if settings.simulator.enabled:
        await simulator.start()

    server = uvicorn.Server(
        uvicorn.Config(app, host=settings.web.host, port=settings.web.port, log_level="warning")
    )

    async def _scanner_status_loop() -> None:
        while True:
            try:
                await ws_manager.broadcast_scanner_status(scanner.get_status())
            except Exception:
                pass
            await asyncio.sleep(10)

    async def _eod_loop() -> None:
        if not settings.simulator.enabled:
            return

        last_sent_date: str | None = None
        while True:
            await asyncio.sleep(300)
            status = simulator.get_status()
            now_local = datetime.now(timezone.utc).astimezone(pytz.timezone(settings.timezone))
            eod_ready = now_local.hour > 16 or (now_local.hour == 16 and now_local.minute >= 5)
            today = now_local.date().isoformat()

            if not eod_ready or last_sent_date == today:
                continue
            if status.get("open_positions", 0) != 0:
                continue

            summary = await simulator.generate_eod_summary()
            await ws_manager.broadcast("daily_pnl", summary)
            if settings.simulator.eod_summary_telegram:
                await reports.send_eod_summary(summary)
            if settings.simulator.weekly_report_telegram and now_local.weekday() == 4:
                await reports.send_weekly_report()
            if settings.simulator.monthly_report_telegram and now_local.day >= 28:
                await reports.send_monthly_report()
            last_sent_date = today

    async def _watchlist_monitor_loop() -> None:
        """Poll watchlist items every 60s, emit watchlist_alert events on threshold breaches."""
        while True:
            try:
                items = await db.get_watchlist_items()
                if items:
                    tickers = [i["ticker"] for i in items]
                    quotes = await alpaca_client.get_snapshots(tickers)
                    for item in items:
                        snap = quotes.get(item["ticker"], {})
                        daily = snap.get("dailyBar", {}) or {}
                        prev = snap.get("prevDailyBar", {}) or {}
                        price = float(daily.get("c", 0) or 0)
                        prev_close = float(prev.get("c", 0) or 0)
                        threshold = item.get("alert_threshold_pct") or 0
                        if prev_close and threshold:
                            change = abs((price - prev_close) / prev_close * 100)
                            if change >= threshold:
                                payload = {
                                    "ticker": item["ticker"],
                                    "change_pct": round(change, 2),
                                    "price": price,
                                    "threshold": threshold,
                                }
                                await ws_manager.broadcast("watchlist_alert", payload)
                                await ws_manager.broadcast_alert(
                                    {
                                        "type": "watchlist_alert",
                                        "message": (
                                            f"{item['ticker']} moved {round(change, 2)}% "
                                            f"(threshold {threshold}%)"
                                        ),
                                        "data": payload,
                                        "timestamp": datetime.now(timezone.utc).timestamp(),
                                    }
                                )
            except Exception:
                pass
            await asyncio.sleep(60)

    async def _extended_hours_poll_loop() -> None:
        """Poll extended-hours quotes for watchlist items when market is not in regular session."""
        while True:
            try:
                session = get_market_session(settings.timezone)
                if session != "regular":
                    items = await db.get_watchlist_items()
                    if items:
                        tickers = [i["ticker"] for i in items]
                        snapshots = await alpaca_client.get_snapshots(tickers)
                        quote_data = {}
                        for t in tickers:
                            snap = snapshots.get(t, {}) or {}
                            latest = snap.get("latestTrade", {}) or {}
                            daily = snap.get("dailyBar", {}) or {}
                            quote_data[t] = {
                                "price": float(latest.get("p", 0) or daily.get("c", 0) or 0),
                                "volume": int(daily.get("v", 0) or 0),
                            }
                        await ws_manager.broadcast(
                            "extended_quotes",
                            {
                                "session": session,
                                "quotes": quote_data,
                            },
                        )
            except Exception:
                pass
            await asyncio.sleep(60)

    scanner_status_task = asyncio.create_task(_scanner_status_loop())
    eod_task = asyncio.create_task(_eod_loop())
    watchlist_task = asyncio.create_task(_watchlist_monitor_loop())
    extended_task = asyncio.create_task(_extended_hours_poll_loop())

    try:
        if settings.web.enabled:
            await asyncio.gather(scanner.run_forever(), server.serve())
        else:
            await scanner.run_forever()
    finally:
        scanner_status_task.cancel()
        eod_task.cancel()
        watchlist_task.cancel()
        extended_task.cancel()
        await scanner.stop()
        if settings.simulator.enabled:
            await simulator.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Day trading momentum scanner")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to scanner config YAML (default: config.yaml)",
    )
    args = parser.parse_args()

    asyncio.run(_main_async(Path(args.config)))


if __name__ == "__main__":
    main()
