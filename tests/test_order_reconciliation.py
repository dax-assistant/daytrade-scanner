import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from src.brokers.models import BrokerAccount, BrokerOrder, BrokerOrderSubmission, BrokerPosition
from src.config import load_settings
from src.data.models import StockCandidate
from src.db.manager import DatabaseManager
from src.event_bus import EventBus
from src.simulator.engine import PaperTradingSimulator


class FakeAlpacaClient:
    def __init__(self, settings, submit_orders, fetched_orders, latest_price=10.0, positions=None, account=None):
        self.settings = settings
        self.submit_orders = list(submit_orders)
        self.fetched_orders = list(fetched_orders)
        self.latest_price = latest_price
        self.positions = list(positions or [])
        self.account = dict(account or {})
        self.market_submissions = []
        self.protected_submissions = []
        self.get_order_calls = []

    async def submit_market_order(self, symbol: str, qty: int, side: str = "buy"):
        self.market_submissions.append({"symbol": symbol, "qty": qty, "side": side})
        result = self.submit_orders.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def submit_protected_order(self, *, symbol: str, qty: int, stop_loss: float, take_profit=None):
        self.protected_submissions.append(
            {"symbol": symbol, "qty": qty, "stop_loss": stop_loss, "take_profit": take_profit}
        )
        return self.submit_orders.pop(0)

    async def get_order(self, order_id: str, *, nested: bool = False):
        self.get_order_calls.append({"order_id": order_id, "nested": nested})
        return self.fetched_orders.pop(0)

    async def get_latest_trade_price(self, symbol: str):
        return self.latest_price

    async def get_positions(self):
        if self.positions and isinstance(self.positions[0], list):
            return self.positions.pop(0)
        return list(self.positions)

    async def get_account(self):
        return dict(self.account)

    @staticmethod
    def normalize_order_state(order):
        return str(order.get("status") or "unknown").lower()

    @staticmethod
    def order_filled_qty(order):
        return int(float(order.get("filled_qty") or 0) or 0)

    @staticmethod
    def order_filled_avg_price(order):
        return float(order.get("filled_avg_price") or 0.0)


class FakeBrokerAdapter:
    broker_name = "fake"

    def __init__(self, *, submit_orders=None, fetched_orders=None, positions=None, account=None):
        self.submit_orders = list(submit_orders or [])
        self.fetched_orders = list(fetched_orders or [])
        self.positions = list(positions or [])
        self.account = account or BrokerAccount(account_id="acct-1", status="ACTIVE", account_mode="cash", cash=1000.0, settled_cash=1000.0, equity=1000.0, portfolio_value=1000.0)
        self.entry_requests = []
        self.exit_requests = []
        self.get_order_calls = []

    async def get_account(self):
        return self.account

    async def get_positions(self):
        if self.positions and isinstance(self.positions[0], list):
            return self.positions.pop(0)
        return list(self.positions)

    async def get_order(self, broker_order_id: str, *, nested: bool = False):
        self.get_order_calls.append({"order_id": broker_order_id, "nested": nested})
        return self.fetched_orders.pop(0)

    async def list_open_orders(self):
        return []

    async def submit_market_entry(self, request):
        self.entry_requests.append(request)
        order = self.submit_orders.pop(0)
        return BrokerOrderSubmission(accepted=True, order=order, raw={})

    async def submit_market_exit(self, request):
        self.exit_requests.append(request)
        order = self.submit_orders.pop(0)
        return BrokerOrderSubmission(accepted=True, order=order, raw={})

    async def cancel_order(self, broker_order_id: str):
        raise NotImplementedError

    async def supports_bracket_orders(self):
        return True

    async def healthcheck(self):
        raise NotImplementedError


class OrderReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ.setdefault("ALPACA_PAPER_KEY_ID", "test-paper-key")
        os.environ.setdefault("ALPACA_PAPER_SECRET_KEY", "test-paper-secret")
        os.environ.setdefault("FINNHUB_API_KEY", "test-finnhub")
        self.settings = load_settings("config.yaml")
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(str(Path(self.tempdir.name) / "test.db"))
        await self.db.initialize()
        self.event_bus = EventBus()
        self.events = []

        async def on_open(trade):
            self.events.append(("trade_opened", trade.ticker, trade.status))

        async def on_close(trade):
            self.events.append(("trade_closed", trade.ticker, trade.status))

        self.event_bus.on("trade_opened", on_open)
        self.event_bus.on("trade_closed", on_close)

    async def asyncTearDown(self):
        self.tempdir.cleanup()

    def make_sim(self, submit_orders, fetched_orders, latest_price=10.0, positions=None, account=None, broker_adapter=None):
        sim = PaperTradingSimulator(
            self.settings,
            self.event_bus,
            self.db,
            FakeAlpacaClient(
                self.settings,
                submit_orders,
                fetched_orders,
                latest_price=latest_price,
                positions=positions,
                account=account,
            ),
            broker_adapter=broker_adapter,
        )
        sim._use_alpaca_orders = True
        return sim

    @staticmethod
    def make_candidate(symbol: str, price: float = 10.0):
        return StockCandidate(
            ticker=symbol,
            price=price,
            gap_percent=10.0,
            volume=100_000,
            avg_volume=50_000,
            relative_volume=4.0,
        )

    async def test_pending_entry_reconciles_to_open(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-1",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-1",
                    "submitted_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-1",
                    "status": "filled",
                    "filled_qty": "100",
                    "filled_avg_price": "10.25",
                    "client_order_id": "entry-1",
                    "updated_at": "2026-04-10T23:00:05Z",
                }
            ],
        )

        trade = await sim._enter_trade(self.make_candidate("AAPL"), source="test")
        self.assertEqual(trade.status, "pending_entry")
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertEqual(stored.quantity, 100)
        self.assertEqual(stored.broker_order_state, "filled")
        self.assertAlmostEqual(stored.entry_price, 10.25)
        self.assertIn(("trade_opened", "AAPL", "open"), self.events)

    async def test_paper_premarket_entry_skips_broker_native_protection(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-paper-1",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-paper-1",
                    "submitted_at": "2026-04-10T13:08:00Z",
                }
            ],
            fetched_orders=[],
        )

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=False):
            trade = await sim._enter_trade(self.make_candidate("BIRD", price=15.5), source="test")

        self.assertEqual(trade.status, "pending_entry")
        self.assertEqual(trade.alpaca_order_id, "entry-paper-1")
        self.assertEqual(sim.alpaca_client.market_submissions[0]["symbol"], "BIRD")
        self.assertEqual(sim.alpaca_client.protected_submissions, [])

    async def test_paper_premarket_pending_entry_waits_past_stale_timeout(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-paper-2",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-paper-2",
                    "submitted_at": "2026-04-10T13:08:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-paper-2",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-paper-2",
                    "updated_at": "2026-04-10T13:20:00Z",
                }
            ],
        )

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=False):
            trade = await sim._enter_trade(self.make_candidate("RMSG", price=2.85), source="test")
            trade.broker_updated_at = trade.entry_time.replace(year=2025)
            await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "pending_entry")
        self.assertIsNone(stored.close_reason)

    async def test_adapter_normalized_order_reconciles_without_alpaca_raw_shape(self):
        broker_adapter = FakeBrokerAdapter(
            submit_orders=[
                BrokerOrder(
                    order_id="entry-adapter-1",
                    symbol="AAPL",
                    side="buy",
                    qty=100,
                    filled_qty=0,
                    status="new",
                    order_type="market",
                    client_order_id="adapter-client-1",
                    submitted_at="2026-04-10T23:00:00Z",
                )
            ],
            fetched_orders=[
                BrokerOrder(
                    order_id="entry-adapter-1",
                    symbol="AAPL",
                    side="buy",
                    qty=100,
                    filled_qty=100,
                    status="filled",
                    order_type="market",
                    client_order_id="adapter-client-1",
                    filled_avg_price=10.25,
                    updated_at="2026-04-10T23:00:05Z",
                )
            ],
            positions=[[BrokerPosition(symbol="AAPL", qty=100, side="long")]],
        )
        sim = self.make_sim(submit_orders=[], fetched_orders=[], broker_adapter=broker_adapter)

        trade = await sim._enter_trade(self.make_candidate("AAPL"), source="test")
        self.assertEqual(trade.status, "pending_entry")
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertEqual(stored.quantity, 100)
        self.assertEqual(stored.broker_order_state, "filled")
        self.assertEqual(stored.alpaca_order_id, "entry-adapter-1")
        self.assertEqual(stored.broker_client_order_id, "adapter-client-1")
        self.assertAlmostEqual(stored.entry_price, 10.25)

    async def test_inject_synthetic_trade_supports_stale_metadata(self):
        sim = self.make_sim(submit_orders=[], fetched_orders=[])
        result = await sim.inject_synthetic_trade(
            {
                "ticker": "PLTR",
                "status": "pending_entry",
                "entry_price": 25.0,
                "quantity": 10,
                "alpaca_order_id": "ord-stale-1",
                "broker_order_state": "partially_filled",
                "broker_filled_qty": 4,
                "broker_filled_avg_price": 25.1,
                "entry_age_seconds": 900,
                "broker_updated_age_seconds": 600,
            }
        )

        self.assertTrue(result["ok"])
        trade = sim._open_trades["PLTR"]
        self.assertEqual(trade.status, "pending_entry")
        self.assertEqual(trade.broker_filled_qty, 4)
        self.assertIsNotNone(trade.broker_updated_at)
        self.assertGreaterEqual((trade.broker_updated_at - trade.entry_time).total_seconds(), 299)

    async def test_protected_entry_uses_broker_native_bracket_submission(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-protected",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-protected",
                    "order_class": "bracket",
                    "stop_loss": {"stop_price": "9.51"},
                    "take_profit": {"limit_price": "11.01"},
                    "submitted_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[],
        )

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=True):
            trade = await sim._enter_trade(self.make_candidate("AAPL"), source="test")

        self.assertEqual(trade.status, "pending_entry")
        self.assertEqual(len(sim.alpaca_client.protected_submissions), 1)
        self.assertEqual(len(sim.alpaca_client.market_submissions), 0)
        submission = sim.alpaca_client.protected_submissions[0]
        self.assertEqual(submission["symbol"], "AAPL")
        self.assertAlmostEqual(submission["stop_loss"], trade.stop_loss)
        self.assertAlmostEqual(submission["take_profit"], trade.take_profit)
        self.assertEqual(trade.broker_protection_type, "bracket")
        self.assertEqual(trade.broker_protection_status, "expected")
        self.assertIn("waiting for child orders", trade.broker_protection_note.lower())

    async def test_open_trade_reconciliation_tracks_active_broker_protection_without_forcing_close(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-bracket-open",
                    "status": "filled",
                    "filled_qty": "100",
                    "filled_avg_price": "10.00",
                    "client_order_id": "entry-bracket-open",
                    "order_class": "bracket",
                    "stop_loss": {"stop_price": "9.70"},
                    "take_profit": {"limit_price": "10.50"},
                    "updated_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-bracket-open",
                    "status": "filled",
                    "filled_qty": "100",
                    "filled_avg_price": "10.00",
                    "client_order_id": "entry-bracket-open",
                    "order_class": "bracket",
                    "stop_loss": {"stop_price": "9.70"},
                    "take_profit": {"limit_price": "10.50"},
                    "legs": [
                        {"id": "tp-1", "type": "limit", "status": "new", "limit_price": "10.50"},
                        {"id": "sl-1", "type": "stop", "status": "accepted", "stop_price": "9.70"},
                    ],
                    "updated_at": "2026-04-10T23:00:05Z",
                }
            ],
        )

        trade = await sim._enter_trade(self.make_candidate("QQQ"), source="test")
        self.assertEqual(trade.status, "open")

        await sim._reconcile_trade_order(trade)
        stored = await self.db.get_trade_by_id(trade.id)

        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertEqual(stored.broker_protection_status, "active")
        self.assertIn("target:new", stored.broker_protection_note)
        self.assertIn("stop:accepted", stored.broker_protection_note)
        self.assertTrue(sim.alpaca_client.get_order_calls[0]["nested"])

    async def test_trailing_stop_profile_fails_closed_for_broker_native_entry(self):
        sim = self.make_sim(submit_orders=[], fetched_orders=[])
        sim._active_profile_name = "aggressive"

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=True):
            trade = await sim._enter_trade(self.make_candidate("AMD"), source="test")

        self.assertIsNone(trade)
        self.assertEqual(len(sim.alpaca_client.protected_submissions), 0)
        self.assertEqual(len(sim.alpaca_client.market_submissions), 0)
        self.assertTrue(any("broker_native_protection_does_not_support_trailing_stop" in issue for issue in sim._reconciliation_issues))

    async def test_rejected_entry_fails_closed(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-r",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-r",
                    "submitted_at": "2026-04-10T23:10:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-r",
                    "status": "rejected",
                    "filled_qty": "0",
                    "client_order_id": "entry-r",
                    "updated_at": "2026-04-10T23:10:05Z",
                }
            ],
            latest_price=12.0,
        )

        trade = await sim._enter_trade(self.make_candidate("MSFT", price=12.0), source="test")
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "entry_failed")
        self.assertEqual(stored.close_reason, "rejected")
        self.assertNotIn("MSFT", sim._open_trades)


    async def test_paper_exit_outside_regular_session_records_local_close_without_queued_broker_order(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-outside-1",
                    "status": "filled",
                    "filled_qty": "100",
                    "filled_avg_price": "10.00",
                    "client_order_id": "entry-outside-1",
                    "updated_at": "2026-04-10T15:00:00Z",
                }
            ],
            fetched_orders=[],
            latest_price=10.5,
        )

        trade = await sim._enter_trade(self.make_candidate("LATE", price=10.0), source="test")
        self.assertEqual(trade.status, "open")

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=False):
            await sim._close_trade(trade, 10.5, "closed_time")

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertEqual(stored.status, "closed_time")
        self.assertAlmostEqual(stored.exit_price, 10.5)
        self.assertAlmostEqual(stored.pnl, (stored.exit_price - stored.entry_price) * stored.quantity)
        self.assertEqual(len(sim.alpaca_client.market_submissions), 1)
        self.assertIn(("trade_closed", "LATE", "closed_time"), self.events)

    async def test_paper_exit_reject_with_no_broker_position_records_local_close_once(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-reject-1",
                    "status": "filled",
                    "filled_qty": "100",
                    "filled_avg_price": "10.00",
                    "client_order_id": "entry-reject-1",
                    "updated_at": "2026-04-10T15:00:00Z",
                },
                RuntimeError("403 forbidden"),
            ],
            fetched_orders=[],
            latest_price=9.5,
            positions=[],
        )

        trade = await sim._enter_trade(self.make_candidate("MISS", price=10.0), source="test")
        self.assertEqual(trade.status, "open")

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=True):
            await sim._close_trade(trade, 9.5, "closed_stop")

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertEqual(stored.status, "closed_stop")
        self.assertAlmostEqual(stored.exit_price, 9.5)
        self.assertAlmostEqual(stored.pnl, (stored.exit_price - stored.entry_price) * stored.quantity)
        self.assertEqual(len(sim.alpaca_client.market_submissions), 2)
        self.assertIn(("trade_closed", "MISS", "closed_stop"), self.events)

    async def test_pending_exit_cancel_returns_trade_to_open(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-2",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "10.10",
                    "client_order_id": "entry-2",
                    "updated_at": "2026-04-10T23:15:00Z",
                },
                {
                    "id": "exit-2",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "exit-2",
                    "submitted_at": "2026-04-10T23:20:00Z",
                },
            ],
            fetched_orders=[
                {
                    "id": "exit-2",
                    "status": "canceled",
                    "filled_qty": "0",
                    "client_order_id": "exit-2",
                    "updated_at": "2026-04-10T23:20:05Z",
                }
            ],
        )

        trade = await sim._enter_trade(self.make_candidate("TSLA"), source="test")
        self.assertEqual(trade.status, "open")
        await sim._close_trade(trade, 10.5, "closed_manual")
        self.assertEqual(trade.status, "pending_exit")
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertIsNone(stored.close_reason)
        self.assertIn("TSLA", sim._open_trades)

    async def test_pending_exit_fill_closes_trade(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-3",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "12.10",
                    "client_order_id": "entry-3",
                    "updated_at": "2026-04-10T23:15:00Z",
                },
                {
                    "id": "exit-3",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "exit-3",
                    "submitted_at": "2026-04-10T23:20:00Z",
                },
            ],
            fetched_orders=[
                {
                    "id": "exit-3",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "12.55",
                    "client_order_id": "exit-3",
                    "updated_at": "2026-04-10T23:20:05Z",
                }
            ],
            latest_price=12.0,
        )

        trade = await sim._enter_trade(self.make_candidate("NVDA", price=12.0), source="test")
        await sim._close_trade(trade, 12.5, "closed_manual")
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "closed_manual")
        self.assertEqual(stored.close_reason, "closed_manual")
        self.assertAlmostEqual(stored.exit_price, 12.55)
        self.assertNotIn("NVDA", sim._open_trades)
        self.assertIn(("trade_closed", "NVDA", "closed_manual"), self.events)

    async def test_pending_entry_partial_fill_stays_pending_with_broker_metadata(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-partial",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-partial",
                    "submitted_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-partial",
                    "status": "partially_filled",
                    "filled_qty": "25",
                    "filled_avg_price": "10.15",
                    "client_order_id": "entry-partial",
                    "updated_at": "2026-04-10T23:00:05Z",
                }
            ],
        )
        sim._pending_order_stale_seconds = 10_000_000

        trade = await sim._enter_trade(self.make_candidate("INTC"), source="test")
        expected_quantity = trade.quantity
        expected_entry_price = trade.entry_price
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "pending_entry")
        self.assertEqual(stored.quantity, expected_quantity)
        self.assertAlmostEqual(stored.entry_price, expected_entry_price)
        self.assertEqual(stored.broker_order_state, "partially_filled")
        self.assertEqual(stored.broker_filled_qty, 25)
        self.assertAlmostEqual(stored.broker_filled_avg_price, 10.15)
        self.assertIsNotNone(stored.broker_updated_at)
        self.assertIn("INTC", sim._open_trades)
        self.assertNotIn(("trade_opened", "INTC", "open"), self.events)

    async def test_stale_partial_pending_entry_quarantines_conservatively(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-partial-stale",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-partial-stale",
                    "submitted_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-partial-stale",
                    "status": "partially_filled",
                    "filled_qty": "10",
                    "filled_avg_price": "9.95",
                    "client_order_id": "entry-partial-stale",
                    "updated_at": "2026-04-10T23:00:00Z",
                }
            ],
        )
        sim._pending_order_stale_seconds = 1

        trade = await sim._enter_trade(self.make_candidate("AMD"), source="test")
        trade.broker_updated_at = trade.entry_time.replace(year=2025)
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "reconciliation_hold")
        self.assertEqual(stored.close_reason, "partial_entry_fill_stale")
        self.assertEqual(stored.broker_order_state, "partially_filled")
        self.assertEqual(stored.broker_filled_qty, 10)
        self.assertAlmostEqual(stored.broker_filled_avg_price, 9.95)
        self.assertIn("AMD", sim._open_trades)
        self.assertTrue(any(issue.startswith("stale_partial_pending_entry:AMD") for issue in sim._reconciliation_issues))

    async def test_stale_pending_entry_fails_closed(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-stale",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-stale",
                    "submitted_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-stale",
                    "status": "accepted",
                    "filled_qty": "0",
                    "client_order_id": "entry-stale",
                    "updated_at": "2026-04-10T23:00:00Z",
                }
            ],
        )
        sim._pending_order_stale_seconds = 1

        with patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=True):
            trade = await sim._enter_trade(self.make_candidate("AMD"), source="test")
            trade.broker_updated_at = trade.entry_time.replace(year=2025)
            await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "entry_failed")
        self.assertEqual(stored.close_reason, "stale_entry_order")
        self.assertNotIn("AMD", sim._open_trades)
        self.assertTrue(any(issue.startswith("stale_pending_entry:AMD") for issue in sim._reconciliation_issues))

    async def test_pending_exit_partial_fill_stays_pending_with_broker_metadata(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-partial-exit",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "12.10",
                    "client_order_id": "entry-partial-exit",
                    "updated_at": "2026-04-10T23:15:00Z",
                },
                {
                    "id": "exit-partial",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "exit-partial",
                    "submitted_at": "2026-04-10T23:20:00Z",
                },
            ],
            fetched_orders=[
                {
                    "id": "exit-partial",
                    "status": "partially_filled",
                    "filled_qty": "20",
                    "filled_avg_price": "12.55",
                    "client_order_id": "exit-partial",
                    "updated_at": "2026-04-10T23:20:05Z",
                }
            ],
        )
        sim._pending_order_stale_seconds = 10_000_000

        trade = await sim._enter_trade(self.make_candidate("META", price=12.0), source="test")
        await sim._close_trade(trade, 12.5, "closed_manual")
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "pending_exit")
        self.assertEqual(stored.close_reason, "closed_manual")
        self.assertEqual(stored.broker_order_state, "partially_filled")
        self.assertEqual(stored.broker_filled_qty, 20)
        self.assertAlmostEqual(stored.broker_filled_avg_price, 12.55)
        self.assertIsNotNone(stored.broker_updated_at)
        self.assertIn("META", sim._open_trades)
        self.assertNotIn(("trade_closed", "META", "closed_manual"), self.events)

    async def test_stale_partial_pending_exit_quarantines_conservatively(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-stale-exit",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "12.10",
                    "client_order_id": "entry-stale-exit",
                    "updated_at": "2026-04-10T23:15:00Z",
                },
                {
                    "id": "exit-stale-partial",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "exit-stale-partial",
                    "submitted_at": "2026-04-10T23:20:00Z",
                },
            ],
            fetched_orders=[
                {
                    "id": "exit-stale-partial",
                    "status": "partially_filled",
                    "filled_qty": "15",
                    "filled_avg_price": "12.40",
                    "client_order_id": "exit-stale-partial",
                    "updated_at": "2026-04-10T23:20:00Z",
                }
            ],
        )
        sim._pending_order_stale_seconds = 1

        trade = await sim._enter_trade(self.make_candidate("QQQM", price=12.0), source="test")
        await sim._close_trade(trade, 12.5, "closed_manual")
        trade.broker_updated_at = trade.entry_time.replace(year=2025)
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "reconciliation_hold")
        self.assertEqual(stored.close_reason, "partial_exit_fill_stale")
        self.assertIsNone(stored.exit_price)
        self.assertIsNone(stored.exit_time)
        self.assertEqual(stored.broker_order_state, "partially_filled")
        self.assertEqual(stored.broker_filled_qty, 15)
        self.assertAlmostEqual(stored.broker_filled_avg_price, 12.40)
        self.assertIn("QQQM", sim._open_trades)
        self.assertTrue(any(issue.startswith("stale_partial_pending_exit:QQQM") for issue in sim._reconciliation_issues))

    async def test_missing_broker_position_quarantines_then_recovers(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-hold",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "11.10",
                    "client_order_id": "entry-hold",
                    "updated_at": "2026-04-10T23:15:00Z",
                }
            ],
            fetched_orders=[],
            positions=[[], [{"symbol": "QQQ", "qty": "50"}]],
        )
        sim._reconciliation_position_mismatch_seconds = 1

        trade = await sim._enter_trade(self.make_candidate("QQQ", price=11.0), source="test")
        sim._symbol_missing_since["QQQ"] = trade.entry_time.replace(year=2025)
        await sim._reconcile_state()

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "reconciliation_hold")
        self.assertEqual(stored.close_reason, "missing_broker_position")

        await sim._reconcile_state()
        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertIsNone(stored.close_reason)

    async def test_manual_reconcile_resolves_partial_entry_hold_when_broker_fills(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-manual-reconcile",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-manual-reconcile",
                    "submitted_at": "2026-04-10T23:00:00Z",
                }
            ],
            fetched_orders=[
                {
                    "id": "entry-manual-reconcile",
                    "status": "partially_filled",
                    "filled_qty": "10",
                    "filled_avg_price": "10.05",
                    "client_order_id": "entry-manual-reconcile",
                    "updated_at": "2026-04-10T23:00:00Z",
                },
                {
                    "id": "entry-manual-reconcile",
                    "status": "filled",
                    "filled_qty": "100",
                    "filled_avg_price": "10.25",
                    "client_order_id": "entry-manual-reconcile",
                    "updated_at": "2026-04-10T23:01:00Z",
                },
            ],
        )
        sim._pending_order_stale_seconds = 1

        trade = await sim._enter_trade(self.make_candidate("AAL"), source="test")
        trade.broker_updated_at = trade.entry_time.replace(year=2025)
        await sim._reconcile_trade_order(trade)

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "reconciliation_hold")
        self.assertEqual(stored.close_reason, "partial_entry_fill_stale")

        result = await sim.reconcile_now(trade_id=trade.id)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("scope"), "trade")

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertIsNone(stored.close_reason)
        self.assertEqual(stored.broker_order_state, "filled")
        self.assertEqual(stored.quantity, 100)
        self.assertAlmostEqual(stored.entry_price, 10.25)

    async def test_manual_reconcile_resolves_missing_broker_position_hold(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-manual-position",
                    "status": "filled",
                    "filled_qty": "50",
                    "filled_avg_price": "11.10",
                    "client_order_id": "entry-manual-position",
                    "updated_at": "2026-04-10T23:15:00Z",
                }
            ],
            fetched_orders=[],
            positions=[[], [{"symbol": "SPY", "qty": "50"}]],
        )
        sim._reconciliation_position_mismatch_seconds = 1

        trade = await sim._enter_trade(self.make_candidate("SPY", price=11.0), source="test")
        sim._symbol_missing_since["SPY"] = trade.entry_time.replace(year=2025)
        await sim._reconcile_state()

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "reconciliation_hold")
        self.assertEqual(stored.close_reason, "missing_broker_position")

        result = await sim.reconcile_now(trade_id=trade.id)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("scope"), "trade")

        stored = await self.db.get_trade_by_id(trade.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, "open")
        self.assertIsNone(stored.close_reason)

    async def test_paper_entry_uses_simulator_entry_threshold_not_alert_threshold(self):
        sim = self.make_sim(
            submit_orders=[
                {
                    "id": "entry-low-pillar",
                    "status": "new",
                    "filled_qty": "0",
                    "client_order_id": "entry-low-pillar",
                    "submitted_at": "2026-04-24T13:00:00Z",
                }
            ],
            fetched_orders=[],
            latest_price=10.0,
        )
        sim._entry_delay_seconds = 0

        candidate = self.make_candidate("TRT", price=10.0)
        candidate.pillars = candidate.pillars or None
        from src.data.models import PillarEvaluation
        candidate.pillars = PillarEvaluation(
            price=True,
            gap_percent=False,
            relative_volume=False,
            float_shares=False,
            news_catalyst=False,
        )
        candidate.entry_signals = {
            "macd_positive": True,
            "above_vwap": True,
            "above_ema9": True,
            "volume_bullish": True,
            "all_clear": True,
        }

        with patch.object(PaperTradingSimulator, "_is_active_hours", return_value=True), patch.object(PaperTradingSimulator, "_is_regular_market_session", return_value=False):
            await sim.on_scanner_hit(candidate)

        self.assertIn("TRT", sim._open_trades)
        trade = sim._open_trades["TRT"]
        self.assertEqual(trade.status, "pending_entry")
        self.assertEqual(trade.alpaca_order_id, "entry-low-pillar")


if __name__ == "__main__":
    unittest.main()
