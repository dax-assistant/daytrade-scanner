from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytz
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from src.audit import request_actor
from src.indicators import compute_overlays, evaluate_entry_signals
from src.trading.policy import TradingPolicy
from src.utils import get_primary_window_info, get_session_info
from src.web.auth import AUTH_COOKIE_NAME, AuthError, get_auth_status, login as auth_login, logout as auth_logout


def create_routes() -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------ #
    # Static / Health                                                       #
    # ------------------------------------------------------------------ #

    @router.get("/")
    async def root(request: Request) -> FileResponse:
        return FileResponse(request.app.state.static_dir / "index.html")

    @router.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @router.get("/api/auth/status")
    async def auth_status(request: Request) -> dict:
        return get_auth_status(request)

    @router.post("/api/auth/login")
    async def auth_login_route(request: Request):
        body = await request.json()
        username = str((body or {}).get("username") or "").strip()
        password = str((body or {}).get("password") or "")
        try:
            result = auth_login(request, username=username, password=password)
            auth_token = result.pop("auth_token")
            response = JSONResponse(result)
            response.set_cookie(
                AUTH_COOKIE_NAME,
                auth_token,
                httponly=True,
                samesite="lax",
                secure=False,
                path="/",
            )
            await _audit(
                request,
                "auth_login",
                status="success",
                details={"username": result.get("username"), "websocket_auth_enabled": result.get("ws_token") is not None},
            )
            return response
        except AuthError as exc:
            await _audit(request, "auth_login", status="failure", details={"username": username, "error": str(exc)})
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=401)

    @router.post("/api/auth/logout")
    async def auth_logout_route(request: Request):
        await _audit(request, "auth_logout", status="success", details={})
        auth_logout(request)
        response = JSONResponse({"ok": True})
        response.delete_cookie(AUTH_COOKIE_NAME, path="/")
        return response

    @router.get("/api/config")
    async def config(request: Request) -> dict:
        settings = request.app.state.settings
        trading_status = TradingPolicy(settings).get_guard_status()
        return {
            "environment": settings.environment,
            "timezone": settings.timezone,
            "web": {
                "enabled": settings.web.enabled,
                "host": settings.web.host,
                "port": settings.web.port,
                "websocket_auth_enabled": settings.web.websocket_auth_enabled,
            },
            "simulator": {
                "enabled": settings.simulator.enabled,
                "default_risk_profile": settings.simulator.default_risk_profile,
                "max_positions": settings.simulator.max_positions,
                "max_daily_loss": settings.simulator.max_daily_loss,
                "use_alpaca_orders": settings.simulator.use_alpaca_orders,
            },
            "trading": {
                "mode": settings.trading.mode,
                "broker": settings.trading.broker,
                "execution_allowed": trading_status.allowed,
                "guard_reason": trading_status.reason,
                "live_enabled": settings.trading.live.enabled,
                "active_trading_base_url": trading_status.details.get("active_trading_base_url", ""),
            },
            "notifications": {
                "telegram_enabled": request.app.state.notification_router.get_settings().get("telegram_enabled", True)
                if getattr(request.app.state, "notification_router", None)
                else settings.telegram_enabled,
            },
        }

    @router.get("/api/settings")
    async def get_settings(request: Request) -> dict:
        notifier = getattr(request.app.state, "notification_router", None)
        enabled = notifier.get_settings().get("telegram_enabled", True) if notifier else True
        return {"telegram_enabled": enabled}

    @router.get("/api/trading/status")
    async def trading_status(request: Request) -> dict:
        settings = request.app.state.settings
        status = TradingPolicy(settings).get_guard_status()
        return {
            "mode": status.mode,
            "broker": status.broker,
            "execution_allowed": status.allowed,
            "guard_reason": status.reason,
            "details": status.details,
        }

    @router.post("/api/settings/telegram")
    async def toggle_telegram(request: Request) -> dict:
        notifier = getattr(request.app.state, "notification_router", None)
        if notifier is None:
            return {"ok": False, "error": "notification_router_unavailable"}
        body = await request.json()
        enabled = bool((body or {}).get("enabled", False))
        notifier.set_telegram_enabled(enabled)
        await _save_config(request)
        await request.app.state.ws_manager.broadcast_config_updated("notifications", notifier.get_settings())
        await _audit(request, "settings_telegram_updated", status="success", details={"telegram_enabled": enabled})
        return {"ok": True, "telegram_enabled": notifier.get_settings().get("telegram_enabled", False)}

    # ------------------------------------------------------------------ #
    # Scanner                                                               #
    # ------------------------------------------------------------------ #

    @router.get("/api/scanner/hits")
    async def scanner_hits(
        request: Request, min_score: int = 0, limit: int = 100, offset: int = 0
    ) -> dict:
        db = request.app.state.db
        tz = pytz.timezone(request.app.state.settings.timezone)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).isoformat()
        end = now.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(pytz.utc).isoformat()
        data = await db.search_hits(
            ticker=None,
            date_from=start,
            date_to=end,
            min_score=min_score,
            limit=limit,
            offset=offset,
        )
        return {"items": data}

    @router.get("/api/scanner/hits/search")
    async def scanner_hits_search(
        request: Request,
        ticker: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        min_score: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        db = request.app.state.db
        data = await db.search_hits(
            ticker=ticker,
            date_from=date_from,
            date_to=date_to,
            min_score=min_score,
            limit=limit,
            offset=offset,
        )
        return {"items": data}

    @router.get("/api/scanner/watchlist")
    async def scanner_watchlist(request: Request) -> dict:
        scanner = request.app.state.scanner
        return {"items": scanner.get_watchlist() if scanner else []}

    @router.get("/api/scanner/status")
    async def scanner_status(request: Request) -> dict:
        scanner = request.app.state.scanner
        if not scanner:
            return {"state": "unavailable"}
        status = scanner.get_status()
        if "primary_window" not in status:
            t = scanner.get_thresholds()
            status["primary_window"] = get_primary_window_info(
                request.app.state.settings.timezone,
                t.get("primary_window_start_hour_et", 7),
                t.get("primary_window_end_hour_et", 10),
            )
        return status

    @router.get("/api/scanner/thresholds")
    async def scanner_thresholds(request: Request) -> dict:
        scanner = request.app.state.scanner
        return scanner.get_thresholds() if scanner else {}

    @router.put("/api/scanner/thresholds")
    async def update_scanner_thresholds(request: Request) -> dict:
        scanner = request.app.state.scanner
        if not scanner:
            return {"ok": False, "error": "scanner_unavailable"}
        body = await request.json()
        try:
            thresholds = await scanner.update_thresholds(body or {})
        except Exception as exc:
            await _audit(request, "scanner_thresholds_updated", status="failure", details={"error": str(exc)})
            return {"ok": False, "error": str(exc)}

        await _save_config(request)
        await request.app.state.ws_manager.broadcast_config_updated("scanner", thresholds)
        await _audit(request, "scanner_thresholds_updated", status="success", details={"fields": sorted((body or {}).keys())})
        return {"ok": True, "thresholds": thresholds}

    @router.get("/api/indicators/{symbol}")
    async def get_indicators(request: Request, symbol: str, timeframe: str = "1m", limit: int = 120) -> dict:
        alpaca = request.app.state.alpaca_client
        if not alpaca:
            return {"symbol": symbol.upper(), "error": "alpaca_unavailable"}

        tf_map = {"1m": "1Min", "5m": "5Min", "1Min": "1Min", "5Min": "5Min"}
        tf = tf_map.get(timeframe, "1Min")
        bars = await alpaca.get_stock_bars(symbol.upper(), tf, limit=max(30, min(limit, 500)))
        if not bars:
            return {"symbol": symbol.upper(), "error": "no_bars"}

        signals = evaluate_entry_signals(bars)
        latest = bars[-1]
        return {
            "symbol": symbol.upper(),
            "macd": signals.get("macd", {}),
            "vwap": {
                "value": signals.get("vwap", 0.0),
                "price_above": float(latest.get("close", 0) or 0) > float(signals.get("vwap", 0.0) or 0),
            },
            "ema9": {
                "value": signals.get("ema9", 0.0),
                "price_above": float(latest.get("close", 0) or 0) >= float(signals.get("ema9", 0.0) or 0),
            },
            "ema20": {
                "value": signals.get("ema20", 0.0),
                "price_above": float(latest.get("close", 0) or 0) >= float(signals.get("ema20", 0.0) or 0),
            },
            "volume_profile": signals.get("volume_profile", {}),
            "entry_signals": {
                "macd_positive": bool(signals.get("macd_positive", False)),
                "above_vwap": bool(signals.get("above_vwap", False)),
                "above_ema9": bool(signals.get("above_ema9", False)),
                "volume_bullish": bool(signals.get("volume_bullish", False)),
                "all_clear": bool(signals.get("all_clear", False)),
            },
        }

    # ------------------------------------------------------------------ #
    # Trades / Simulator                                                    #
    # ------------------------------------------------------------------ #

    @router.get("/api/trades")
    async def list_trades(
        request: Request,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        db = request.app.state.db
        trades = await db.get_trades(
            status=status, date_from=date_from, date_to=date_to, limit=limit, offset=offset
        )
        return {"items": [t.to_dict() for t in trades]}

    @router.get("/api/trades/open")
    async def list_open_trades(request: Request) -> dict:
        db = request.app.state.db
        trades = await db.get_open_trades()
        return {"items": [t.to_dict() for t in trades]}

    @router.get("/api/trades/{trade_id}")
    async def trade_detail(request: Request, trade_id: int) -> dict:
        db = request.app.state.db
        trade = await db.get_trade_by_id(trade_id)
        return {"item": trade.to_dict() if trade else None}

    @router.post("/api/trades/{trade_id}/close")
    async def close_trade(request: Request, trade_id: int) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}

        trade_record = await request.app.state.db.get_trade_by_id(trade_id)
        if not trade_record or trade_record.status != "open":
            await _audit(request, "trade_close_requested", status="failure", details={"trade_id": trade_id, "error": "trade_not_open"})
            return {"ok": False, "error": "trade_not_open"}

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
                await _audit(request, "trade_close_requested", status="blocked", details={"trade_id": trade_id, "ticker": trade_record.ticker, "reason": blocked_reason})
                return {"ok": False, "error": blocked_reason}

        trade = await simulator.close_trade_by_id(trade_id)
        await _audit(request, "trade_close_requested", status="success" if trade else "failure", details={"trade_id": trade_id, "ticker": trade_record.ticker, "reason": None if trade else "trade_not_closed"})
        return {"ok": trade is not None, "trade": trade.to_dict() if trade else None, "error": None if trade else "trade_not_closed"}

    @router.post("/api/trades/{trade_id}/reconcile")
    async def reconcile_trade(request: Request, trade_id: int) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        result = await simulator.reconcile_now(trade_id=trade_id)
        await _audit(
            request,
            "trade_reconcile_requested",
            status="success" if result.get("ok") else "failure",
            details={"trade_id": trade_id, "error": result.get("error")},
        )
        return result

    @router.post("/api/simulator/enter")
    async def manual_enter_trade(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        body = await request.json()
        result = await simulator.enter_manual_trade(body or {})
        await _audit(
            request,
            "trade_enter_requested",
            status="success" if result.get("ok") else "failure",
            details={"ticker": str((body or {}).get("ticker") or "").upper(), "error": result.get("error")},
        )
        return result

    @router.get("/api/simulator/positions")
    async def simulator_positions(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {
                "items": [],
                "account_size": 0.0,
                "starting_balance": 0.0,
                "current_balance": 0.0,
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
            }
        return await simulator.get_positions_with_prices()

    @router.get("/api/simulator/history")
    async def simulator_history(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"items": [], "stats": {}}
        return await simulator.get_history_with_stats()

    @router.get("/api/simulator/alltime")
    async def simulator_alltime(request: Request) -> dict:
        db = request.app.state.db
        trades = await db.get_trades(date_from=None, date_to=None, limit=100000)
        closed = [t for t in trades if t.status != "open" and t.pnl is not None]
        wins = [t for t in closed if (t.pnl or 0) > 0]
        losses = [t for t in closed if (t.pnl or 0) <= 0]
        total_pnl = sum(float(t.pnl or 0) for t in closed)
        total_trades = len(closed)
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        return {
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
        }

    @router.get("/api/simulator/trades")
    async def simulator_trades(request: Request) -> dict:
        db = request.app.state.db
        trades = await db.get_trades(date_from=None, date_to=None, limit=100000)
        return {"items": [t.to_dict() for t in trades]}

    @router.put("/api/simulator/account")
    async def simulator_account(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        body = await request.json()
        account_size = float((body or {}).get("account_size", 0) or 0)
        if account_size <= 0:
            await _audit(request, "simulator_account_updated", status="failure", details={"error": "account_size_must_be_positive"})
            return {"ok": False, "error": "account_size_must_be_positive"}

        await simulator.update_run_settings({"account_size": account_size})
        await _save_config(request)
        await request.app.state.ws_manager.broadcast_config_updated("simulator", {"account_size": account_size})
        await _audit(request, "simulator_account_updated", status="success", details={"account_size": account_size})
        return {"ok": True, "account_size": account_size}

    # ------------------------------------------------------------------ #
    # Simulator status / profile / settings / emergency-stop              #
    # ------------------------------------------------------------------ #

    @router.get("/api/simulator/status")
    async def simulator_status(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"enabled": False}
        return simulator.get_status()

    @router.post("/api/simulator/reconcile")
    async def simulator_reconcile(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        result = await simulator.reconcile_now()
        await _audit(
            request,
            "simulator_reconcile_requested",
            status="success" if result.get("ok") else "failure",
            details={"scope": result.get("scope"), "error": result.get("error")},
        )
        return result

    @router.post("/api/simulator/profile")
    async def simulator_profile(request: Request) -> dict:
        """Switch active profile, or update an existing profile's fields."""
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        body = await request.json()
        profile_name = str((body or {}).get("profile") or "moderate")
        fields = body.get("fields")

        if fields:
            result = await simulator.save_profile_fields(profile_name, fields)
            if result.get("ok"):
                await _save_config(request)
            await _audit(request, "simulator_profile_updated", status="success" if result.get("ok") else "failure", details={"profile": profile_name, "fields": sorted(fields.keys()) if isinstance(fields, dict) else []})
            return result
        else:
            result = await simulator.change_profile(profile_name)
            await _audit(request, "simulator_profile_switched", status="success", details={"profile": profile_name})
            return {"ok": True, **result}

    @router.post("/api/simulator/profile/create")
    async def create_profile(request: Request) -> dict:
        """Create a new custom risk profile."""
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        body = await request.json()
        name = str(body.get("name", "")).strip().lower()
        if not name or not name.replace("_", "").isalnum():
            await _audit(request, "simulator_profile_created", status="failure", details={"error": "invalid_name"})
            return {"ok": False, "error": "invalid_name"}
        fields = {
            "position_size_pct": float(body.get("position_size_pct", 5.0)),
            "stop_loss_pct": float(body.get("stop_loss_pct", 5.0)),
            "take_profit_pct": float(body.get("take_profit_pct", 10.0)),
            "trailing_stop": bool(body.get("trailing_stop", False)),
            "trailing_stop_pct": float(body.get("trailing_stop_pct", 0.0)),
            "max_hold_minutes": int(body.get("max_hold_minutes", 60)),
        }
        await simulator.create_profile(name, fields)
        await _save_config(request)
        await _audit(request, "simulator_profile_created", status="success", details={"profile": name})
        return {"ok": True, "profile": name}

    @router.put("/api/simulator/settings")
    async def update_sim_settings(request: Request) -> dict:
        """Update run-level controls. Persists to config.yaml and updates live runtime."""
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        body = await request.json()
        await simulator.update_run_settings(body)
        await _save_config(request)
        await request.app.state.ws_manager.broadcast_config_updated("simulator", body)
        await _audit(request, "simulator_settings_updated", status="success", details={"fields": sorted((body or {}).keys())})
        return {"ok": True, "settings": body}

    @router.post("/api/simulator/emergency-stop")
    async def emergency_stop(request: Request) -> dict:
        """Close all open positions immediately and pause the simulator."""
        simulator = request.app.state.simulator
        if not simulator:
            return {"ok": False, "error": "simulator_disabled"}
        closed = await simulator.emergency_stop()
        await _audit(request, "simulator_emergency_stop", status="success", details={"closed_trades": len(closed) if isinstance(closed, list) else closed})
        return {"ok": True, "closed_trades": closed, "simulator_paused": True}

    # ------------------------------------------------------------------ #
    # Account equity                                                        #
    # ------------------------------------------------------------------ #

    @router.get("/api/account/equity")
    async def account_equity(request: Request) -> dict:
        alpaca = request.app.state.alpaca_client
        if not alpaca:
            return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0, "portfolio_value": 0.0}
        try:
            account = await alpaca.get_account()
            return {
                "equity": float(account.get("equity", 0) or 0),
                "cash": float(account.get("cash", 0) or 0),
                "buying_power": float(account.get("buying_power", 0) or 0),
                "portfolio_value": float(account.get("portfolio_value", 0) or 0),
            }
        except Exception:
            return {"equity": 0.0, "cash": 0.0, "buying_power": 0.0, "portfolio_value": 0.0}

    # ------------------------------------------------------------------ #
    # Custom Watchlist                                                       #
    # ------------------------------------------------------------------ #

    @router.get("/api/watchlist")
    async def get_watchlist(request: Request) -> dict:
        db = request.app.state.db
        alpaca = request.app.state.alpaca_client
        items = await db.get_watchlist_items()
        if not items:
            return {"items": []}

        tickers = [item["ticker"] for item in items]
        quotes: dict = {}
        if alpaca:
            try:
                quotes = await alpaca.get_snapshots(tickers)
            except Exception:
                quotes = {}

        result = []
        for item in items:
            ticker = item["ticker"]
            snap = quotes.get(ticker, {}) or {}
            latest = snap.get("latestTrade", {}) or {}
            daily = snap.get("dailyBar", {}) or {}
            prev = snap.get("prevDailyBar", {}) or {}

            last_price = float(latest.get("p", 0) or daily.get("c", 0) or 0)
            prev_close = float(prev.get("c", 0) or 0)
            change_pct = ((last_price - prev_close) / prev_close * 100) if prev_close else 0.0

            result.append({
                "ticker": ticker,
                "last_price": last_price,
                "change_pct": round(change_pct, 2),
                "volume": int(daily.get("v", 0) or 0),
                "float_shares": None,   # would need Finnhub
                "week52_high": None,
                "week52_low": None,
                "notes": item.get("notes", ""),
                "alert_threshold_pct": item.get("alert_threshold_pct", 5.0),
                "added_at": item.get("added_at"),
            })
        return {"items": result}

    @router.post("/api/watchlist")
    async def add_watchlist(request: Request) -> dict:
        body = await request.json()
        ticker = str(body.get("ticker") or "").strip().upper()
        if not ticker or len(ticker) > 10:
            return {"ok": False, "error": "invalid_ticker"}
        db = request.app.state.db
        item = await db.add_watchlist_item(
            ticker,
            notes=str(body.get("notes", "")),
            alert_threshold_pct=float(body.get("alert_threshold_pct", 5.0)),
        )
        return {"ok": True, "item": item}

    @router.delete("/api/watchlist/{ticker}")
    async def remove_watchlist(request: Request, ticker: str) -> dict:
        db = request.app.state.db
        ok = await db.remove_watchlist_item(ticker)
        return {"ok": ok}

    @router.patch("/api/watchlist/{ticker}")
    async def update_watchlist(request: Request, ticker: str) -> dict:
        body = await request.json()
        db = request.app.state.db
        ok = await db.update_watchlist_item(ticker, body)
        return {"ok": ok}

    # ------------------------------------------------------------------ #
    # Market Session                                                        #
    # ------------------------------------------------------------------ #

    @router.get("/api/market/session")
    async def market_session(request: Request) -> dict:
        tz_name = request.app.state.settings.timezone
        info = get_session_info(tz_name)
        scanner = request.app.state.scanner
        if scanner:
            th = scanner.get_thresholds()
            info["primary_window"] = get_primary_window_info(
                tz_name,
                th.get("primary_window_start_hour_et", 7),
                th.get("primary_window_end_hour_et", 10),
            )
        return info

    # ------------------------------------------------------------------ #
    # Historical Bars + Extended Hours Quotes                              #
    # ------------------------------------------------------------------ #

    @router.get("/api/bars")
    async def get_bars(request: Request, symbol: str, timeframe: str = "1m", limit: int = 200) -> dict:
        alpaca = request.app.state.alpaca_client
        if not alpaca:
            return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": []}

        tf_map = {"1m": "1Min", "5m": "5Min", "1Min": "1Min", "5Min": "5Min"}
        tf = tf_map.get(timeframe, "1Min")
        bars = await alpaca.get_stock_bars(symbol.upper(), tf, limit=max(10, min(limit, 500)))
        normalized = [
            {
                "time": b.get("time"),
                "open": float(b.get("open", 0) or 0),
                "high": float(b.get("high", 0) or 0),
                "low": float(b.get("low", 0) or 0),
                "close": float(b.get("close", 0) or 0),
                "volume": int(b.get("volume", 0) or 0),
            }
            for b in bars
        ]
        return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": normalized}

    @router.get("/api/quotes/extended")
    async def quotes_extended(request: Request, symbols: str = "") -> dict:
        tickers = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not tickers:
            return {"quotes": {}}

        alpaca = request.app.state.alpaca_client
        if not alpaca:
            return {"quotes": {t: {} for t in tickers}}

        try:
            snapshots = await alpaca.get_snapshots(tickers)
        except Exception:
            snapshots = {}

        tz_name = request.app.state.settings.timezone
        session_info = get_session_info(tz_name)
        current_session = session_info["session"]

        quotes = {}
        for ticker in tickers:
            snap = snapshots.get(ticker, {}) or {}
            latest = snap.get("latestTrade", {}) or {}
            daily = snap.get("dailyBar", {}) or {}
            prev = snap.get("prevDailyBar", {}) or {}

            last_price = float(latest.get("p", 0) or daily.get("c", 0) or 0)
            prev_close = float(prev.get("c", 0) or 0)
            change_pct = ((last_price - prev_close) / prev_close * 100) if prev_close else 0.0

            quotes[ticker] = {
                "last_price": last_price,
                "change_pct": round(change_pct, 2),
                "volume": int(daily.get("v", 0) or 0),
                "premarket_price": last_price if current_session == "premarket" else None,
                "premarket_change_pct": round(change_pct, 2) if current_session == "premarket" else None,
                "afterhours_price": last_price if current_session == "afterhours" else None,
                "afterhours_change_pct": round(change_pct, 2) if current_session == "afterhours" else None,
                "session": current_session,
            }
        return {"quotes": quotes}

    # ------------------------------------------------------------------ #
    # Trade Journal                                                         #
    # ------------------------------------------------------------------ #

    @router.get("/api/journal")
    async def list_journal(request: Request) -> dict:
        db = request.app.state.db
        entries = await db.get_all_journal_entries()
        return {"items": entries}

    @router.get("/api/trades")
    async def list_trades(
        request: Request,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        db = request.app.state.db
        trades = await db.get_trades(
            date_from=date_from,
            date_to=date_to,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {"items": [t.to_dict() for t in trades]}

    @router.get("/api/journal/{trade_id}")
    async def get_journal(request: Request, trade_id: int) -> dict:
        db = request.app.state.db
        entry = await db.get_journal_entry(trade_id)
        return {"entry": entry}

    @router.post("/api/journal/{trade_id}")
    async def upsert_journal(request: Request, trade_id: int) -> dict:
        db = request.app.state.db
        body = await request.json()
        entry = await db.upsert_journal_entry(trade_id, body or {})
        return {"ok": True, "entry": entry}

    # ------------------------------------------------------------------ #
    # Analytics                                                             #
    # ------------------------------------------------------------------ #

    def _resolve_analytics_range(request: Request, range: str = "alltime") -> tuple[Optional[str], Optional[str]]:
        tz = pytz.timezone(request.app.state.settings.timezone)
        now = datetime.now(tz)

        date_from: Optional[str] = None
        date_to: Optional[str] = None
        normalized = (range or "alltime").lower()

        if normalized == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_from, date_to = start.isoformat(), end.isoformat()
        elif normalized == "week":
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_from, date_to = start.isoformat(), end.isoformat()
        elif normalized == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_from, date_to = start.isoformat(), end.isoformat()

        return date_from, date_to

    @router.get("/api/analytics/summary")
    async def analytics_summary(request: Request, range: str = "alltime") -> dict:
        db = request.app.state.db
        date_from, date_to = _resolve_analytics_range(request, range)
        return await db.get_analytics_summary(date_from=date_from, date_to=date_to)

    @router.get("/api/analytics/grades")
    async def analytics_grades(request: Request, range: str = "alltime") -> dict:
        db = request.app.state.db
        date_from, date_to = _resolve_analytics_range(request, range)
        return {"items": await db.get_grade_analytics(date_from=date_from, date_to=date_to)}

    # ------------------------------------------------------------------ #
    # Performance                                                           #
    # ------------------------------------------------------------------ #

    @router.get("/api/performance/today")
    async def perf_today(request: Request) -> dict:
        simulator = request.app.state.simulator
        if not simulator:
            return {"total_pnl": 0.0, "total_trades": 0}
        summary = await simulator.generate_eod_summary()
        return summary.to_dict()

    @router.get("/api/performance/daily")
    async def perf_daily(request: Request, date_from: str, date_to: str) -> dict:
        db = request.app.state.db
        rows = await db.get_summaries_range(date_from, date_to)
        return {"items": [r.to_dict() for r in rows]}

    @router.get("/api/performance/weekly")
    async def perf_weekly(request: Request, weeks_back: int = 4) -> dict:
        db = request.app.state.db
        tz = pytz.timezone(request.app.state.settings.timezone)
        end = datetime.now(tz).date()
        start = end - timedelta(days=max(1, weeks_back) * 7)
        rows = await db.get_summaries_range(start.isoformat(), end.isoformat())
        return {"items": [r.to_dict() for r in rows]}

    @router.get("/api/performance/monthly")
    async def perf_monthly(request: Request, months_back: int = 3) -> dict:
        db = request.app.state.db
        tz = pytz.timezone(request.app.state.settings.timezone)
        end = datetime.now(tz).date()
        start = end - timedelta(days=max(1, months_back) * 31)
        rows = await db.get_summaries_range(start.isoformat(), end.isoformat())
        return {"items": [r.to_dict() for r in rows]}

    return router


# ------------------------------------------------------------------ #
# Config persistence helper                                            #
# ------------------------------------------------------------------ #


async def _audit(request: Request, event: str, status: str, details: dict) -> None:
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if audit_logger is None:
        return
    await audit_logger.log(event, {"status": status, "actor": request_actor(request), "details": details})


async def _save_config(request: Request) -> None:
    """Write current simulator/scanner settings and risk profiles back to config.yaml."""
    config_path: Path | None = getattr(request.app.state, "config_path", None)
    if not config_path or not Path(config_path).exists():
        return  # config_path not set — skip persistence

    simulator = request.app.state.simulator
    scanner = request.app.state.scanner

    try:
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}

        notifier = getattr(request.app.state, "notification_router", None)
        if notifier is not None:
            raw["TELEGRAM_ENABLED"] = bool(notifier.get_settings().get("telegram_enabled", True))

        if scanner:
            thresholds = scanner.get_thresholds()
            raw.setdefault("scanner", {}).setdefault("thresholds", {}).update(
                {
                    "min_gap_percent": thresholds["min_gap_percent"],
                    "min_price": thresholds["min_price"],
                    "max_price": thresholds["max_price"],
                    "min_relative_volume": thresholds["min_relative_volume"],
                    "max_float_shares": thresholds["max_float_shares"],
                    "min_pillars_for_alert": thresholds["min_pillars_for_alert"],
                    "relative_volume_lookback_days": thresholds["relative_volume_lookback_days"],
                    "universe_scan_multiplier": thresholds["universe_scan_multiplier"],
                }
            )
            raw.setdefault("scanner", {}).setdefault("active_hours", {}).update(
                {
                    "start_hour_et": thresholds["start_hour_et"],
                    "end_hour_et": thresholds["end_hour_et"],
                    "primary_window_start_hour_et": thresholds["primary_window_start_hour_et"],
                    "primary_window_end_hour_et": thresholds["primary_window_end_hour_et"],
                }
            )

        if simulator:
            raw["simulator"] = {
                "enabled": simulator._enabled,
                "default_risk_profile": simulator._active_profile_name,
                "account_size": simulator._account_size,
                "max_positions": simulator._max_positions,
                "max_daily_loss": simulator._max_daily_loss,
                "entry_delay_seconds": simulator._entry_delay_seconds,
                "use_alpaca_orders": simulator._use_alpaca_orders,
                "eod_summary_telegram": simulator._eod_summary_telegram,
                "weekly_report_telegram": getattr(simulator.settings.simulator, "weekly_report_telegram", True),
                "monthly_report_telegram": getattr(simulator.settings.simulator, "monthly_report_telegram", True),
                "simulated_slippage_bps": simulator._simulated_slippage_bps,
                "reconcile_interval_seconds": simulator._reconcile_interval_seconds,
            }

            raw["risk_profiles"] = {}
            for name, profile in simulator._profiles.items():
                raw["risk_profiles"][name] = {
                    "position_size_pct": profile.position_size_pct,
                    "stop_loss_pct": profile.stop_loss_pct,
                    "take_profit_pct": profile.take_profit_pct,
                    "trailing_stop": profile.trailing_stop,
                    "trailing_stop_pct": profile.trailing_stop_pct,
                    "max_hold_minutes": profile.max_hold_minutes,
                }

        if "api" in raw and isinstance(raw.get("api"), dict) and isinstance(raw["api"].get("telegram"), dict):
            raw["api"]["telegram"]["enabled"] = bool(raw.get("TELEGRAM_ENABLED", True))

        with open(config_path, "w") as f:
            yaml.dump(raw, f, default_flow_style=False, sort_keys=False)
    except Exception:
        pass  # Best-effort — don't crash the request
