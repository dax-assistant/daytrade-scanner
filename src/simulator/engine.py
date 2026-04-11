from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timezone, timedelta
from typing import Any, Dict, Optional

import pytz

from src.config import Settings
from src.data.alpaca_client import AlpacaClient
from src.data.models import DailySummary, PillarEvaluation, RiskProfile, StockCandidate, Trade
from src.db.manager import DatabaseManager
from src.event_bus import EventBus
from src.indicators import evaluate_entry_signals
from src.simulator.risk_profiles import get_profile, load_risk_profiles
from src.trading.models import OrderIntent, TradingPolicyError
from src.trading.policy import TradingPolicy

LOGGER = logging.getLogger(__name__)


class PaperTradingSimulator:
    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db: DatabaseManager,
        alpaca_client: AlpacaClient,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.db = db
        self.alpaca_client = alpaca_client

        self._open_trades: Dict[str, Trade] = {}
        self._daily_pnl: float = 0.0
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._enabled: bool = settings.simulator.enabled
        self._active_profile_name = settings.simulator.default_risk_profile
        self._profiles = load_risk_profiles(settings)
        self._tz = pytz.timezone(settings.timezone)

        # Mutable runtime copies of simulator settings (Settings dataclass is frozen)
        self._account_size: float = settings.simulator.account_size
        # _starting_balance is always the original account inception value (never changes)
        self._starting_balance: float = settings.simulator.account_size
        # _all_time_realized_pnl = cumulative realized P&L across ALL sessions (persisted to DB)
        self._all_time_realized_pnl: float = 0.0
        self._realized_pnl_today: float = 0.0
        self._max_positions: int = settings.simulator.max_positions
        self._max_daily_loss: float = settings.simulator.max_daily_loss
        self._entry_delay_seconds: int = settings.simulator.entry_delay_seconds
        self._use_alpaca_orders: bool = settings.simulator.use_alpaca_orders
        self._eod_summary_telegram: bool = settings.simulator.eod_summary_telegram
        self._simulated_slippage_bps: float = settings.simulator.simulated_slippage_bps
        self._reconcile_interval_seconds: int = settings.simulator.reconcile_interval_seconds
        self._pending_order_stale_seconds: int = settings.simulator.pending_order_stale_seconds
        self._reconciliation_position_mismatch_seconds: int = settings.simulator.reconciliation_position_mismatch_seconds
        self._latest_price_by_symbol: Dict[str, float] = {}
        self._latest_price_at_by_symbol: Dict[str, datetime] = {}
        self._last_reconciled_at: Optional[datetime] = None
        self._reconciliation_issues: list[str] = []
        self._broker_position_symbols: list[str] = []
        self._last_account_snapshot: Dict[str, float] = {}
        self._symbol_missing_since: Dict[str, datetime] = {}
        self._trading_policy = TradingPolicy(settings)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        await self._load_persisted_balance()
        await self._restore_daily_state()

        active_trades = await self.db.get_active_trades()
        self._open_trades = {trade.ticker.upper(): trade for trade in active_trades}

        self.event_bus.on("scanner_hit", self.on_scanner_hit)
        self.event_bus.on("price_update", self.on_price_update)

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        LOGGER.info("PaperTradingSimulator started (open_trades=%s)", len(self._open_trades))

    async def _load_persisted_balance(self) -> None:
        """Load the persisted current_balance from DB. Derive all_time_realized_pnl from it."""
        persisted = await self.db.get_simulator_state("current_balance")
        if persisted is not None:
            # All-time realized P&L = persisted balance minus starting balance
            self._all_time_realized_pnl = persisted - self._starting_balance
            LOGGER.info(
                "Loaded persisted balance from DB: $%.2f (all-time P&L: $%.2f)",
                persisted,
                self._all_time_realized_pnl,
            )
        else:
            # First-ever run: seed from all closed trades in DB (backward compat)
            all_closed = await self.db.get_closed_trades_by_exit_time(limit=10000)
            seed_pnl = sum(float(t.pnl or 0.0) for t in all_closed)
            self._all_time_realized_pnl = seed_pnl
            persisted_balance = self._starting_balance + seed_pnl
            await self.db.set_simulator_state("current_balance", persisted_balance)
            LOGGER.info(
                "Seeded persisted balance from %d closed trades: $%.2f",
                len(all_closed),
                persisted_balance,
            )

    async def _restore_daily_state(self) -> None:
        now_local = datetime.now(timezone.utc).astimezone(self._tz)
        day_start_local = self._tz.localize(datetime.combine(now_local.date(), time.min))
        next_day_start_local = day_start_local + timedelta(days=1)
        day_end_local = next_day_start_local - timedelta(microseconds=1)

        day_start_utc = day_start_local.astimezone(timezone.utc).isoformat()
        day_end_utc = day_end_local.astimezone(timezone.utc).isoformat()

        closed_trades = await self.db.get_closed_trades_by_exit_time(
            date_from=day_start_utc,
            date_to=day_end_utc,
            limit=500,
        )
        restored_pnl = sum(float(trade.pnl or 0.0) for trade in closed_trades)
        trade_count = len(closed_trades)

        self._daily_pnl = restored_pnl
        self._realized_pnl_today = restored_pnl

        LOGGER.info("Restored daily P&L from DB: $%.2f (%d trades)", restored_pnl, trade_count)

    async def stop(self) -> None:
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    async def on_scanner_hit(self, candidate: StockCandidate) -> None:
        if not self._enabled:
            return
        if len(self._open_trades) >= self._max_positions:
            return

        symbol = candidate.ticker.upper()
        if symbol in self._open_trades:
            return

        if self._daily_pnl <= -abs(self._max_daily_loss):
            return

        if not self._is_active_hours():
            return

        required_pillars = int(self.settings.scanner.thresholds.min_pillars_for_alert)
        actual_pillars = int(candidate.pillars.score if candidate.pillars else 0)
        if actual_pillars < required_pillars:
            await self.event_bus.emit(
                "entry_rejected",
                {
                    "ticker": candidate.ticker,
                    "reason": "pillar_score_below_threshold",
                    "signals": {},
                    "actual_pillars": actual_pillars,
                    "required_pillars": required_pillars,
                },
            )
            return

        if candidate.pillars and not candidate.pillars.price:
            await self.event_bus.emit(
                "entry_rejected",
                {
                    "ticker": candidate.ticker,
                    "reason": "price_pillar_failed",
                    "signals": {},
                },
            )
            return

        if self._entry_delay_seconds > 0:
            await asyncio.sleep(self._entry_delay_seconds)

        if symbol in self._open_trades:
            return

        entry_signals = candidate.entry_signals or await self._evaluate_entry_signals(candidate.ticker)
        if not bool(entry_signals.get("all_clear", False)):
            await self.event_bus.emit(
                "entry_rejected",
                {
                    "ticker": candidate.ticker,
                    "reason": "entry_signals_not_met",
                    "signals": entry_signals,
                },
            )
            return

        await self._enter_trade(candidate, source="scanner_auto")

    async def _evaluate_entry_signals(self, symbol: str) -> Dict[str, Any]:
        try:
            bars = await self.alpaca_client.get_stock_bars(symbol.upper(), timeframe="1Min", limit=60)
            return evaluate_entry_signals(bars)
        except Exception:
            return {
                "macd_positive": False,
                "above_vwap": False,
                "above_ema9": False,
                "volume_bullish": False,
                "all_clear": False,
            }

    def _apply_slippage(self, price: float, side: str) -> float:
        bps = max(0.0, float(self._simulated_slippage_bps)) / 10000.0
        if side == "buy":
            return max(0.01, price * (1 + bps))
        return max(0.01, price * (1 - bps))

    async def _get_market_reference_price(self, symbol: str) -> Optional[float]:
        sym = symbol.upper()
        cached = self._latest_price_by_symbol.get(sym)
        if cached and cached > 0:
            return cached
        try:
            return await self.alpaca_client.get_latest_trade_price(sym)
        except Exception as exc:
            LOGGER.warning("Failed to fetch market reference price for %s: %s", sym, exc)
            return None

    async def _resolve_exit_market_price(self, trade: Trade) -> float:
        reference = await self._get_market_reference_price(trade.ticker)
        if reference is None or reference <= 0:
            reference = trade.entry_price
        return self._apply_slippage(float(reference), side="sell")

    async def _reconcile_state(self) -> None:
        self._last_reconciled_at = datetime.now(timezone.utc)
        try:
            positions = await self.alpaca_client.get_positions()
            self._broker_position_symbols = sorted(
                {
                    str(position.get("symbol") or "").upper()
                    for position in positions
                    if float(position.get("qty") or 0) != 0
                }
            )
        except Exception as exc:
            LOGGER.warning("Failed broker position reconciliation: %s", exc)
            self._append_reconciliation_issue(f"broker_positions_unavailable:{exc}")
            self._broker_position_symbols = []

        try:
            account = await self.alpaca_client.get_account()
            self._last_account_snapshot = {
                "equity": float(account.get("equity", 0) or 0),
                "cash": float(account.get("cash", 0) or 0),
                "buying_power": float(account.get("buying_power", 0) or 0),
                "portfolio_value": float(account.get("portfolio_value", 0) or 0),
            }
        except Exception as exc:
            LOGGER.warning("Failed broker account reconciliation: %s", exc)
            self._append_reconciliation_issue(f"broker_account_unavailable:{exc}")
            self._last_account_snapshot = {}

        for trade in list(self._open_trades.values()):
            if trade.status in {"pending_entry", "pending_exit"}:
                await self._reconcile_trade_order(trade)

        app_symbols = sorted(symbol for symbol, trade in self._open_trades.items() if trade.status == "open")
        missing_in_broker = [symbol for symbol in app_symbols if symbol not in self._broker_position_symbols]
        unexpected_in_broker = [symbol for symbol in self._broker_position_symbols if symbol not in app_symbols]

        now = datetime.now(timezone.utc)
        for symbol in missing_in_broker:
            first_missing_at = self._symbol_missing_since.setdefault(symbol, now)
            if (now - first_missing_at).total_seconds() < self._reconciliation_position_mismatch_seconds:
                continue
            trade = self._open_trades.get(symbol)
            if trade and trade.status == "open":
                self._append_reconciliation_issue(f"reconciliation_hold:{symbol}")
                await self._quarantine_trade_for_mismatch(trade, "missing_broker_position")
        for symbol, trade in list(self._open_trades.items()):
            if symbol in self._broker_position_symbols:
                self._symbol_missing_since.pop(symbol, None)
                if trade.status == "reconciliation_hold" and trade.close_reason == "missing_broker_position":
                    trade.status = "open"
                    trade.close_reason = None
                    await self.db.update_trade(trade)

        if missing_in_broker:
            self._append_reconciliation_issue(f"missing_in_broker:{','.join(missing_in_broker)}")
        if unexpected_in_broker:
            self._append_reconciliation_issue(f"unexpected_in_broker:{','.join(unexpected_in_broker)}")

    def _build_order_intent(
        self,
        *,
        symbol: str,
        qty: int,
        side: str,
        source: str,
        estimated_price: float,
    ) -> OrderIntent:
        normalized_qty = max(1, int(qty))
        normalized_price = float(estimated_price)
        return OrderIntent(
            symbol=symbol.upper(),
            side=side,
            qty=normalized_qty,
            estimated_price=normalized_price,
            estimated_notional=float(normalized_qty) * normalized_price,
            source=source,
        )

    def preview_broker_market_order(
        self,
        *,
        symbol: str,
        qty: int,
        side: str,
        source: str,
        estimated_price: float,
    ) -> Optional[str]:
        intent = self._build_order_intent(
            symbol=symbol,
            qty=qty,
            side=side,
            source=source,
            estimated_price=estimated_price,
        )
        try:
            self._trading_policy.assert_order_allowed(intent)
        except TradingPolicyError as exc:
            return str(exc)
        return None

    async def _submit_broker_market_order(
        self,
        *,
        symbol: str,
        qty: int,
        side: str,
        source: str,
        estimated_price: float,
    ) -> Dict[str, Any]:
        intent = self._build_order_intent(
            symbol=symbol,
            qty=qty,
            side=side,
            source=source,
            estimated_price=estimated_price,
        )
        self._trading_policy.assert_order_allowed(intent)
        return await self.alpaca_client.submit_market_order(symbol=symbol, qty=qty, side=side)

    def _append_reconciliation_issue(self, issue: str) -> None:
        self._reconciliation_issues = (self._reconciliation_issues + [issue])[-20:]

    def _order_age_seconds(self, trade: Trade) -> float:
        reference_time = trade.broker_updated_at or trade.entry_time
        return max(0.0, (datetime.now(timezone.utc) - reference_time).total_seconds())

    def _is_partial_fill(self, trade: Trade) -> bool:
        state = (trade.broker_order_state or "").lower()
        filled_qty = int(trade.broker_filled_qty or 0)
        return state in {"partially_filled", "partial_fill"} or (0 < filled_qty < int(trade.quantity))

    async def _quarantine_trade_for_mismatch(self, trade: Trade, reason: str) -> None:
        trade.status = "reconciliation_hold"
        trade.close_reason = reason
        await self.db.update_trade(trade)

    def _apply_broker_order_to_trade(self, trade: Trade, order: Dict[str, Any]) -> None:
        trade.alpaca_order_id = str(order.get("id") or trade.alpaca_order_id or "") or None
        trade.broker_order_state = self.alpaca_client.normalize_order_state(order)
        trade.broker_client_order_id = str(order.get("client_order_id") or trade.broker_client_order_id or "") or None
        filled_qty = self.alpaca_client.order_filled_qty(order)
        trade.broker_filled_qty = filled_qty if filled_qty > 0 else None
        filled_avg_price = self.alpaca_client.order_filled_avg_price(order)
        trade.broker_filled_avg_price = filled_avg_price if filled_avg_price > 0 else None
        broker_updated_raw = order.get("updated_at") or order.get("filled_at") or order.get("submitted_at")
        if broker_updated_raw:
            trade.broker_updated_at = datetime.fromisoformat(str(broker_updated_raw).replace("Z", "+00:00"))

    async def _finalize_trade_close(self, trade: Trade, exit_price: float, reason: str) -> None:
        trade.exit_price = float(exit_price)
        trade.exit_time = trade.broker_updated_at or datetime.now(timezone.utc)
        trade.status = reason
        trade.close_reason = reason
        trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
        trade.pnl_percent = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100.0

        await self.db.update_trade(trade)
        self._daily_pnl += trade.pnl
        self._realized_pnl_today += trade.pnl
        self._all_time_realized_pnl += trade.pnl
        await self.db.set_simulator_state(
            "current_balance", self._starting_balance + self._all_time_realized_pnl
        )
        self._open_trades.pop(trade.ticker, None)
        await self.event_bus.emit("trade_closed", trade)

    async def _open_trade_from_broker_fill(self, trade: Trade) -> None:
        if trade.broker_filled_qty:
            trade.quantity = trade.broker_filled_qty
        if trade.broker_filled_avg_price:
            trade.entry_price = trade.broker_filled_avg_price
            profile = get_profile(self._profiles, trade.risk_profile)
            trade.stop_loss = trade.entry_price * (1 - profile.stop_loss_pct / 100.0)
            trade.take_profit = (
                trade.entry_price * (1 + profile.take_profit_pct / 100.0)
                if profile.take_profit_pct > 0
                else None
            )
            trade.max_price_seen = trade.entry_price
        trade.status = "open"
        trade.close_reason = None
        await self.db.update_trade(trade)
        await self.event_bus.emit("trade_opened", trade)

    async def _reconcile_held_trade_order(self, trade: Trade) -> None:
        reason = trade.close_reason or ""
        state = trade.broker_order_state or "unknown"

        # Held trades only move when broker state makes the next state explicit.
        if reason == "partial_entry_fill_stale":
            if state == "filled":
                await self._open_trade_from_broker_fill(trade)
            else:
                await self.db.update_trade(trade)
            return

        if reason == "partial_exit_fill_stale":
            if state == "filled":
                exit_price = trade.broker_filled_avg_price or trade.exit_price or trade.entry_price
                await self._finalize_trade_close(trade, exit_price, "closed_manual")
            else:
                trade.exit_price = None
                trade.exit_time = None
                await self.db.update_trade(trade)
            return

        await self.db.update_trade(trade)

    async def _reconcile_trade_order(self, trade: Trade) -> None:
        if not self._use_alpaca_orders or not trade.alpaca_order_id:
            return
        try:
            order = await self.alpaca_client.get_order(trade.alpaca_order_id)
        except Exception as exc:
            self._append_reconciliation_issue(f"broker_order_unavailable:{trade.ticker}:{exc}")
            return

        self._apply_broker_order_to_trade(trade, order)
        state = trade.broker_order_state or "unknown"
        is_partial_fill = self._is_partial_fill(trade)

        if trade.status == "reconciliation_hold":
            await self._reconcile_held_trade_order(trade)
            return

        if trade.status == "pending_entry":
            if state == "filled":
                await self._open_trade_from_broker_fill(trade)
            elif state in {"canceled", "expired", "rejected"}:
                trade.status = "entry_failed"
                trade.close_reason = state
                await self.db.update_trade(trade)
                self._open_trades.pop(trade.ticker, None)
            else:
                if self._order_age_seconds(trade) >= self._pending_order_stale_seconds:
                    if is_partial_fill:
                        await self._quarantine_trade_for_mismatch(trade, "partial_entry_fill_stale")
                        self._append_reconciliation_issue(f"stale_partial_pending_entry:{trade.ticker}")
                    else:
                        trade.status = "entry_failed"
                        trade.close_reason = "stale_entry_order"
                        await self.db.update_trade(trade)
                        self._open_trades.pop(trade.ticker, None)
                        self._append_reconciliation_issue(f"stale_pending_entry:{trade.ticker}")
                else:
                    await self.db.update_trade(trade)
            return

        if trade.status == "pending_exit":
            if state == "filled":
                exit_price = trade.broker_filled_avg_price or trade.exit_price or trade.entry_price
                await self._finalize_trade_close(trade, exit_price, trade.close_reason or "closed_manual")
            elif state in {"canceled", "expired", "rejected"}:
                trade.status = "open"
                trade.exit_price = None
                trade.exit_time = None
                trade.close_reason = None
                await self.db.update_trade(trade)
            else:
                if self._order_age_seconds(trade) >= self._pending_order_stale_seconds:
                    if is_partial_fill:
                        trade.exit_price = None
                        trade.exit_time = None
                        await self._quarantine_trade_for_mismatch(trade, "partial_exit_fill_stale")
                        self._append_reconciliation_issue(f"stale_partial_pending_exit:{trade.ticker}")
                    else:
                        self._append_reconciliation_issue(f"stale_pending_exit:{trade.ticker}")
                        await self.db.update_trade(trade)
                else:
                    await self.db.update_trade(trade)

    async def reconcile_now(self, trade_id: Optional[int] = None) -> Dict[str, Any]:
        if trade_id is None:
            await self._reconcile_state()
            for trade in list(self._open_trades.values()):
                await self.event_bus.emit("trade_updated", trade)
            return {
                "ok": True,
                "scope": "all",
                "trade_id": None,
                "reconciliation": self.get_status().get("reconciliation", {}),
            }

        trade = await self.db.get_trade_by_id(trade_id)
        if not trade:
            return {"ok": False, "error": "trade_not_found", "trade_id": trade_id}

        live_trade = self._open_trades.get(trade.ticker.upper())
        if live_trade and live_trade.id == trade.id:
            trade = live_trade

        if trade.status not in {"open", "pending_entry", "pending_exit", "reconciliation_hold"}:
            return {"ok": False, "error": "trade_not_active", "trade_id": trade_id}

        if (
            trade.status == "reconciliation_hold"
            and trade.close_reason in {"partial_entry_fill_stale", "partial_exit_fill_stale"}
            and trade.alpaca_order_id
        ):
            await self._reconcile_trade_order(trade)

        await self._reconcile_state()
        refreshed = await self.db.get_trade_by_id(trade_id)
        if refreshed is not None:
            active_trade = self._open_trades.get(refreshed.ticker.upper())
            if active_trade and active_trade.id == refreshed.id:
                await self.event_bus.emit("trade_updated", active_trade)

        return {
            "ok": True,
            "scope": "trade",
            "trade_id": trade_id,
            "trade": refreshed.to_dict() if refreshed else None,
            "reconciliation": self.get_status().get("reconciliation", {}),
        }

    async def _enter_trade(self, candidate: StockCandidate, source: str = "scanner_auto") -> Optional[Trade]:
        profile = get_profile(self._profiles, self._active_profile_name)

        market_reference_price = await self._get_market_reference_price(candidate.ticker)
        if market_reference_price is None:
            market_reference_price = float(candidate.price)

        entry_price = self._apply_slippage(
            max(float(candidate.price), float(market_reference_price), 0.01),
            side="buy",
        )
        position_budget = self.get_current_balance() * (profile.position_size_pct / 100.0)
        quantity = int(position_budget / entry_price)
        if quantity < 1:
            return None

        stop_loss = entry_price * (1 - profile.stop_loss_pct / 100.0)
        take_profit = entry_price * (1 + profile.take_profit_pct / 100.0) if profile.take_profit_pct > 0 else None
        trailing_stop_pct = profile.trailing_stop_pct if profile.trailing_stop else None

        initial_order: Optional[Dict[str, Any]] = None
        alpaca_order_id: Optional[str] = None
        initial_status = "open"
        if self._use_alpaca_orders:
            try:
                order = await self._submit_broker_market_order(
                    symbol=candidate.ticker,
                    qty=quantity,
                    side="buy",
                    source=source,
                    estimated_price=entry_price,
                )
                initial_order = order
                alpaca_order_id = str(order.get("id") or "") or None
                broker_state = self.alpaca_client.normalize_order_state(order)
                filled_avg_price = float(order.get("filled_avg_price") or 0.0)
                if broker_state != "filled":
                    initial_status = "pending_entry"
                if filled_avg_price > 0:
                    entry_price = filled_avg_price
                    stop_loss = entry_price * (1 - profile.stop_loss_pct / 100.0)
                    take_profit = entry_price * (1 + profile.take_profit_pct / 100.0) if profile.take_profit_pct > 0 else None
            except TradingPolicyError as exc:
                LOGGER.warning("Execution blocked for %s buy order: %s", candidate.ticker, exc)
                self._append_reconciliation_issue(f"execution_blocked:{candidate.ticker}:{exc}")
                await self.event_bus.emit(
                    "execution_blocked",
                    {"ticker": candidate.ticker, "side": "buy", "reason": str(exc), "source": "scanner_auto"},
                )
                return None
            except Exception as exc:
                LOGGER.warning("Failed to submit Alpaca paper buy order for %s: %s", candidate.ticker, exc)
                self._append_reconciliation_issue(f"buy_order_failed:{candidate.ticker}")
                return None

        trade = Trade(
            id=None,
            scanner_hit_id=candidate.db_id,
            ticker=candidate.ticker.upper(),
            side="buy",
            risk_profile=profile.name,
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc),
            exit_price=None,
            exit_time=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct,
            quantity=quantity,
            status=initial_status,
            pnl=None,
            pnl_percent=None,
            alpaca_order_id=alpaca_order_id,
            broker_order_state=None,
            broker_client_order_id=None,
            broker_filled_qty=None,
            broker_filled_avg_price=None,
            broker_updated_at=None,
            close_reason=None,
            max_price_seen=entry_price,
        )
        if initial_order:
            self._apply_broker_order_to_trade(trade, initial_order)
        trade.id = await self.db.insert_trade(trade)
        self._open_trades[trade.ticker] = trade
        self._latest_price_by_symbol[trade.ticker] = entry_price
        self._latest_price_at_by_symbol[trade.ticker] = datetime.now(timezone.utc)

        if trade.status == "open":
            await self.event_bus.emit("trade_opened", trade)
        return trade

    async def on_price_update(self, data: Dict[str, Any]) -> None:
        symbol = str(data.get("symbol") or "").upper()
        current_price = float(data.get("price") or 0)
        if current_price > 0:
            self._latest_price_by_symbol[symbol] = current_price
            self._latest_price_at_by_symbol[symbol] = datetime.now(timezone.utc)

        if symbol not in self._open_trades:
            return

        trade = self._open_trades[symbol]
        if current_price <= 0:
            return
        if trade.status != "open":
            return

        if current_price > trade.max_price_seen:
            trade.max_price_seen = current_price
            await self.db.update_trade(trade)
            await self.event_bus.emit("trade_updated", trade)

        if current_price <= trade.stop_loss:
            await self._close_trade(trade, current_price, "closed_stop")
            return

        if trade.take_profit is not None and current_price >= trade.take_profit:
            await self._close_trade(trade, current_price, "closed_target")
            return

        if trade.trailing_stop_pct and trade.trailing_stop_pct > 0:
            trailing_stop_price = trade.max_price_seen * (1 - trade.trailing_stop_pct / 100.0)
            if current_price <= trailing_stop_price:
                await self._close_trade(trade, current_price, "closed_trailing")
                return

        unrealized_pnl = (current_price - trade.entry_price) * trade.quantity
        await self.event_bus.emit(
            "position_update",
            {
                "symbol": trade.ticker,
                "unrealized_pnl": unrealized_pnl,
                "current_price": current_price,
                "entry_price": trade.entry_price,
                "quantity": trade.quantity,
            },
        )

    async def _monitor_loop(self) -> None:
        last_date = datetime.now(timezone.utc).astimezone(self._tz).date()
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                # Reset daily P&L at midnight local time
                today = now.astimezone(self._tz).date()
                if today != last_date:
                    LOGGER.info("New trading day detected (%s → %s). Resetting daily P&L.", last_date, today)
                    self._daily_pnl = 0.0
                    self._realized_pnl_today = 0.0
                    last_date = today
                to_close: list[tuple[Trade, float, str]] = []
                for trade in list(self._open_trades.values()):
                    if trade.status != "open":
                        continue
                    profile = get_profile(self._profiles, trade.risk_profile)
                    hold_minutes = (now - trade.entry_time).total_seconds() / 60.0
                    current_price = await self._resolve_exit_market_price(trade)
                    if hold_minutes >= profile.max_hold_minutes:
                        to_close.append((trade, current_price, "closed_time"))
                        continue

                    if self._is_near_market_close():
                        to_close.append((trade, current_price, "closed_eod"))

                for trade, exit_price, reason in to_close:
                    await self._close_trade(trade, exit_price, reason)

                if self._daily_pnl <= -abs(self._max_daily_loss):
                    for trade in list(self._open_trades.values()):
                        if trade.status != "open":
                            continue
                        current_price = await self._resolve_exit_market_price(trade)
                        await self._close_trade(trade, current_price, "closed_risk")

                if (self._last_reconciled_at is None) or (
                    (now - self._last_reconciled_at).total_seconds() >= self._reconcile_interval_seconds
                ):
                    await self._reconcile_state()

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Simulator monitor loop error")
                await asyncio.sleep(1)

    async def _close_trade(self, trade: Trade, exit_price: float, reason: str) -> None:
        if trade.ticker not in self._open_trades:
            return

        if self._use_alpaca_orders:
            try:
                order = await self._submit_broker_market_order(
                    symbol=trade.ticker,
                    qty=trade.quantity,
                    side="sell",
                    source=reason,
                    estimated_price=exit_price,
                )
                self._apply_broker_order_to_trade(trade, order)
                trade.close_reason = reason
                if trade.broker_order_state != "filled":
                    trade.status = "pending_exit"
                    trade.exit_price = None
                    trade.exit_time = None
                    await self.db.update_trade(trade)
                    return
                if trade.broker_filled_avg_price:
                    exit_price = trade.broker_filled_avg_price
            except TradingPolicyError as exc:
                LOGGER.warning("Execution blocked for %s sell order: %s", trade.ticker, exc)
                self._append_reconciliation_issue(f"execution_blocked:{trade.ticker}:{exc}")
                await self.event_bus.emit(
                    "execution_blocked",
                    {"ticker": trade.ticker, "side": "sell", "reason": str(exc), "source": reason},
                )
                return
            except Exception as exc:
                LOGGER.warning("Failed to submit Alpaca paper sell order for %s: %s", trade.ticker, exc)
                self._append_reconciliation_issue(f"sell_order_failed:{trade.ticker}")
                return

        await self._finalize_trade_close(trade, exit_price, reason)

    async def close_trade_by_id(self, trade_id: int) -> Optional[Trade]:
        trade = await self.db.get_trade_by_id(trade_id)
        if not trade or trade.status != "open":
            return None

        current_price = await self._resolve_exit_market_price(trade)
        await self._close_trade(trade, current_price, "closed_manual")
        return trade if trade.status != "open" else None

    async def enter_manual_trade(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self._enabled:
            return {"ok": False, "error": "simulator_disabled"}

        symbol = str(data.get("ticker") or "").strip().upper()
        price = float(data.get("price") or 0.0)
        if not symbol:
            return {"ok": False, "error": "ticker_required"}
        if price <= 0:
            return {"ok": False, "error": "invalid_price"}
        if len(self._open_trades) >= self._max_positions:
            return {"ok": False, "error": "max_positions_reached"}
        if symbol in self._open_trades:
            return {"ok": False, "error": "position_already_open"}
        if self._daily_pnl <= -abs(self._max_daily_loss):
            return {"ok": False, "error": "daily_loss_limit_reached"}
        if not self._is_active_hours():
            return {"ok": False, "error": "outside_active_hours"}

        raw_pillars = data.get("pillars") or {}
        pillars = None
        if raw_pillars:
            pillars = PillarEvaluation(
                price=bool(raw_pillars.get("price", False)),
                gap_percent=bool(raw_pillars.get("gap_percent", False)),
                relative_volume=bool(raw_pillars.get("relative_volume", False)),
                float_shares=bool(raw_pillars.get("float_shares", False)),
                news_catalyst=bool(raw_pillars.get("news_catalyst", False)),
            )

        candidate = StockCandidate(
            ticker=symbol,
            price=price,
            gap_percent=float(data.get("gap_percent") or 0.0),
            volume=int(data.get("volume") or 0),
            avg_volume=float(data.get("avg_volume") or 0.0),
            relative_volume=float(data.get("relative_volume") or 0.0),
            avg_volume_basis=str(data.get("avg_volume_basis") or "manual"),
            float_shares=data.get("float_shares"),
            news=None,
            session_label=str(data.get("session_label") or "manual"),
            entry_signals=data.get("entry_signals"),
            db_id=data.get("db_id"),
            pillars=pillars,
        )
        profile = get_profile(self._profiles, self._active_profile_name)
        quantity = int((self.get_current_balance() * (profile.position_size_pct / 100.0)) / max(price, 0.01))
        if self._use_alpaca_orders and quantity >= 1:
            blocked_reason = self.preview_broker_market_order(
                symbol=symbol,
                qty=quantity,
                side="buy",
                source="manual_entry",
                estimated_price=price,
            )
            if blocked_reason:
                return {"ok": False, "error": blocked_reason}

        trade = await self._enter_trade(candidate, source="manual_entry")
        if trade is None:
            return {"ok": False, "error": "trade_not_entered"}
        return {"ok": True, "trade": trade.to_dict()}

    async def generate_eod_summary(self) -> DailySummary:
        now_date = datetime.now(self._tz).date().isoformat()
        trades = await self.db.get_trades(date_from=f"{now_date}T00:00:00", date_to=f"{now_date}T23:59:59")
        closed = [t for t in trades if t.status != "open" and t.pnl is not None]

        wins = [t for t in closed if (t.pnl or 0) > 0]
        losses = [t for t in closed if (t.pnl or 0) <= 0]

        total_pnl = sum(float(t.pnl or 0) for t in closed)
        largest_win = max((float(t.pnl or 0) for t in wins), default=None)
        largest_loss = min((float(t.pnl or 0) for t in losses), default=None)

        hits_today = await self.db.get_hits_today()
        alert_count = await self.db.count_alerts_on_date(now_date)

        summary = DailySummary(
            date=now_date,
            total_trades=len(closed),
            winning_trades=len(wins),
            losing_trades=len(losses),
            total_pnl=total_pnl,
            win_rate=(len(wins) / len(closed) * 100.0) if closed else 0.0,
            largest_win=largest_win,
            largest_loss=largest_loss,
            scanner_hits_count=len(hits_today),
            alerts_count=alert_count,
        )
        await self.db.upsert_daily_summary(summary)
        return summary

    def get_current_balance(self) -> float:
        unrealized = sum(
            ((self._latest_price_by_symbol.get(trade.ticker, trade.entry_price)) - trade.entry_price) * trade.quantity
            for trade in self._open_trades.values()
        )
        return self._starting_balance + self._all_time_realized_pnl + unrealized

    async def get_positions_with_prices(self) -> Dict[str, Any]:
        items = []
        for trade in self._open_trades.values():
            items.append(trade.to_dict_with_current_price(self._latest_price_by_symbol.get(trade.ticker, trade.entry_price)))

        daily_pnl_pct = (self._daily_pnl / self._starting_balance * 100.0) if self._starting_balance > 0 else 0.0
        return {
            "items": items,
            "account_size": self._starting_balance,
            "starting_balance": self._starting_balance,
            "current_balance": self.get_current_balance(),
            "daily_pnl": self._daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
        }

    async def get_history_with_stats(self) -> Dict[str, Any]:
        now_date = datetime.now(self._tz).date().isoformat()
        trades = await self.db.get_trades(date_from=f"{now_date}T00:00:00", date_to=f"{now_date}T23:59:59", limit=500)
        closed = [t for t in trades if t.status != "open" and t.pnl is not None]

        wins = [t for t in closed if (t.pnl or 0) > 0]
        losses = [t for t in closed if (t.pnl or 0) <= 0]
        losses_sum = sum(float(t.pnl or 0) for t in losses)

        stats = {
            "total_trades": len(closed),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": (len(wins) / len(closed) * 100.0) if closed else 0.0,
            "avg_winner": (sum(float(t.pnl or 0) for t in wins) / len(wins)) if wins else 0.0,
            "avg_loser": (sum(float(t.pnl or 0) for t in losses) / len(losses)) if losses else 0.0,
            "total_pnl": sum(float(t.pnl or 0) for t in closed),
            "largest_win": max((float(t.pnl or 0) for t in wins), default=0.0),
            "largest_loss": min((float(t.pnl or 0) for t in losses), default=0.0),
            "profit_factor": (
                abs(sum(float(t.pnl or 0) for t in wins) / losses_sum)
                if losses and losses_sum != 0
                else float("inf")
            ),
        }

        return {"items": [t.to_dict() for t in closed], "stats": stats}

    def get_status(self) -> Dict[str, Any]:
        """Extended status including all profile fields and run controls."""
        profile = self._profiles.get(self._active_profile_name)
        profile_fields: Dict[str, Any] = {}
        if profile:
            profile_fields = {
                "position_size_pct": profile.position_size_pct,
                "stop_loss_pct": profile.stop_loss_pct,
                "take_profit_pct": profile.take_profit_pct,
                "trailing_stop": profile.trailing_stop,
                "trailing_stop_pct": profile.trailing_stop_pct,
                "max_hold_minutes": profile.max_hold_minutes,
            }
        trading_status = self._trading_policy.get_guard_status().to_dict()
        return {
            "enabled": self._enabled,
            "active_profile": self._active_profile_name,
            "profile_fields": profile_fields,
            "available_profiles": list(self._profiles.keys()),
            "run_controls": {
                "account_size": self._account_size,
                "max_positions": self._max_positions,
                "max_daily_loss": self._max_daily_loss,
                "entry_delay_seconds": self._entry_delay_seconds,
                "use_alpaca_orders": self._use_alpaca_orders,
                "eod_summary_telegram": self._eod_summary_telegram,
                "enabled": self._enabled,
                "simulated_slippage_bps": self._simulated_slippage_bps,
                "reconcile_interval_seconds": self._reconcile_interval_seconds,
                "pending_order_stale_seconds": self._pending_order_stale_seconds,
                "reconciliation_position_mismatch_seconds": self._reconciliation_position_mismatch_seconds,
            },
            "stats": {
                "account_equity": 0.0,  # populated by route from Alpaca
                "daily_pnl": self._daily_pnl,
                "open_positions": len(self._open_trades),
                "max_positions": self._max_positions,
                "daily_loss_used": abs(min(self._daily_pnl, 0.0)),
                "daily_loss_limit": self._max_daily_loss,
                "starting_balance": self._starting_balance,
                "current_balance": self.get_current_balance(),
            },
            "reconciliation": {
                "last_reconciled_at": self._last_reconciled_at.isoformat() if self._last_reconciled_at else None,
                "issues": list(self._reconciliation_issues[-20:]),
                "broker_position_symbols": list(self._broker_position_symbols),
                "account": self._last_account_snapshot,
            },
            # Kept for backward compat
            "daily_pnl": self._daily_pnl,
            "open_positions": len(self._open_trades),
            "max_positions": self._max_positions,
            "max_daily_loss": self._max_daily_loss,
            "running": self._running,
            "trading": trading_status,
        }

    async def change_profile(self, profile_name: str) -> Dict[str, Any]:
        """Switch to a named profile (or just fetch its fields if already active)."""
        profile = get_profile(self._profiles, profile_name)
        self._active_profile_name = profile.name
        fields = {
            "position_size_pct": profile.position_size_pct,
            "stop_loss_pct": profile.stop_loss_pct,
            "take_profit_pct": profile.take_profit_pct,
            "trailing_stop": profile.trailing_stop,
            "trailing_stop_pct": profile.trailing_stop_pct,
            "max_hold_minutes": profile.max_hold_minutes,
        }
        return {"active_profile": self._active_profile_name, "fields": fields}

    async def save_profile_fields(self, profile_name: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing profile's fields in runtime."""
        existing = self._profiles.get(profile_name)
        if existing is None:
            return {"ok": False, "error": "profile_not_found"}

        updated = RiskProfile(
            name=profile_name,
            position_size_pct=float(fields.get("position_size_pct", existing.position_size_pct)),
            stop_loss_pct=float(fields.get("stop_loss_pct", existing.stop_loss_pct)),
            take_profit_pct=float(fields.get("take_profit_pct", existing.take_profit_pct)),
            trailing_stop=bool(fields.get("trailing_stop", existing.trailing_stop)),
            trailing_stop_pct=float(fields.get("trailing_stop_pct", existing.trailing_stop_pct)),
            max_hold_minutes=int(fields.get("max_hold_minutes", existing.max_hold_minutes)),
        )
        self._profiles[profile_name] = updated
        return {
            "ok": True,
            "profile": profile_name,
            "fields": {
                "position_size_pct": updated.position_size_pct,
                "stop_loss_pct": updated.stop_loss_pct,
                "take_profit_pct": updated.take_profit_pct,
                "trailing_stop": updated.trailing_stop,
                "trailing_stop_pct": updated.trailing_stop_pct,
                "max_hold_minutes": updated.max_hold_minutes,
            },
        }

    async def create_profile(self, name: str, fields: Dict[str, Any]) -> None:
        """Create a new custom risk profile in runtime."""
        self._profiles[name] = RiskProfile(
            name=name,
            position_size_pct=float(fields.get("position_size_pct", 5.0)),
            stop_loss_pct=float(fields.get("stop_loss_pct", 5.0)),
            take_profit_pct=float(fields.get("take_profit_pct", 10.0)),
            trailing_stop=bool(fields.get("trailing_stop", False)),
            trailing_stop_pct=float(fields.get("trailing_stop_pct", 0.0)),
            max_hold_minutes=int(fields.get("max_hold_minutes", 60)),
        )

    async def update_run_settings(self, settings: Dict[str, Any]) -> None:
        """Update run-level simulator settings at runtime."""
        if "account_size" in settings:
            self._account_size = float(settings["account_size"])
            self._starting_balance = float(settings["account_size"])
            self._all_time_realized_pnl = 0.0
            self._realized_pnl_today = 0.0
            self._daily_pnl = 0.0
            # Reset persisted balance to match new account size
            await self.db.set_simulator_state("current_balance", self._starting_balance)
        if "max_positions" in settings:
            self._max_positions = int(settings["max_positions"])
        if "max_daily_loss" in settings:
            self._max_daily_loss = float(settings["max_daily_loss"])
        if "entry_delay_seconds" in settings:
            self._entry_delay_seconds = int(settings["entry_delay_seconds"])
        if "use_alpaca_orders" in settings:
            self._use_alpaca_orders = bool(settings["use_alpaca_orders"])
        if "eod_summary_telegram" in settings:
            self._eod_summary_telegram = bool(settings["eod_summary_telegram"])
        if "simulated_slippage_bps" in settings:
            self._simulated_slippage_bps = float(settings["simulated_slippage_bps"])
        if "reconcile_interval_seconds" in settings:
            self._reconcile_interval_seconds = int(settings["reconcile_interval_seconds"])
        if "enabled" in settings:
            self._enabled = bool(settings["enabled"])

    async def emergency_stop(self) -> int:
        """Close all open positions immediately and pause the simulator."""
        closed = 0
        for trade in list(self._open_trades.values()):
            price = await self._resolve_exit_market_price(trade)
            await self._close_trade(trade, price, "emergency_stop")
            closed += 1
        self._enabled = False
        return closed

    async def get_open_trades(self) -> list[Trade]:
        return list(self._open_trades.values())

    def _is_active_hours(self) -> bool:
        now_et = datetime.now(timezone.utc).astimezone(self._tz)
        hour_decimal = now_et.hour + (now_et.minute / 60.0)
        start = self.settings.scanner.active_hours.start_hour_et
        end = self.settings.scanner.active_hours.end_hour_et
        return start <= hour_decimal < end

    def _is_near_market_close(self) -> bool:
        now_et = datetime.now(timezone.utc).astimezone(self._tz)
        close_time = now_et.replace(hour=15, minute=55, second=0, microsecond=0)
        return now_et >= close_time
