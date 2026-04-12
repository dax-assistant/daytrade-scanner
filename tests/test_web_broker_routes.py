import unittest

from src.brokers.models import BrokerAccount, BrokerOrder, BrokerPosition
from src.web.routes import (
    _broker_payload,
    _cancel_broker_order,
    _get_broker_account_snapshot,
    _get_broker_open_orders_snapshot,
    _get_broker_order_snapshot,
    _get_broker_positions_snapshot,
)


class FakeCancelResult:
    def __init__(self, ok=True, order_id='ord-1', status_code=204, error=''):
        self.ok = ok
        self.order_id = order_id
        self.status_code = status_code
        self.error = error

    def to_dict(self):
        return {"ok": self.ok, "order_id": self.order_id, "status_code": self.status_code, "error": self.error}


class FakeBrokerAdapter:
    broker_name = "fake"

    async def get_account(self):
        return BrokerAccount(
            account_id="acct-123",
            status="ACTIVE",
            account_mode="cash",
            buying_power=1500.0,
            cash=1200.0,
            settled_cash=1100.0,
            equity=1550.0,
            portfolio_value=1550.0,
        )

    async def get_positions(self):
        return [
            BrokerPosition(symbol="AAPL", qty=10, side="long", market_value=1725.0, avg_entry_price=172.5),
        ]

    async def list_open_orders(self):
        return [
            BrokerOrder(
                order_id="ord-1",
                symbol="AAPL",
                side="buy",
                qty=10,
                filled_qty=0,
                status="new",
                order_type="market",
                client_order_id="cli-1",
                submitted_at="2026-04-11T21:00:00Z",
            )
        ]

    async def get_order(self, broker_order_id: str, *, nested: bool = False):
        return BrokerOrder(
            order_id=broker_order_id,
            symbol="AAPL",
            side="buy",
            qty=10,
            filled_qty=0,
            status="new",
            order_type="market",
            client_order_id="cli-1",
            submitted_at="2026-04-11T21:00:00Z",
            updated_at="2026-04-11T21:01:00Z",
        )

    async def cancel_order(self, broker_order_id: str):
        return FakeCancelResult(ok=True, order_id=broker_order_id, status_code=204)


class FakeRequest:
    def __init__(self):
        self.app = type("App", (), {})()
        self.app.state = type("State", (), {})()
        self.app.state.alpaca_client = None
        self.app.state.broker_adapter = FakeBrokerAdapter()


class BrokerRouteHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_broker_account_snapshot_prefers_adapter(self):
        request = FakeRequest()
        payload = await _get_broker_account_snapshot(request)
        self.assertEqual(payload["account_id"], "acct-123")
        self.assertEqual(payload["portfolio_value"], 1550.0)
        self.assertEqual(payload["settled_cash"], 1100.0)

    async def test_broker_positions_snapshot_returns_normalized_positions(self):
        request = FakeRequest()
        items = await _get_broker_positions_snapshot(request)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["symbol"], "AAPL")
        self.assertEqual(items[0]["qty"], 10)

    async def test_broker_open_orders_snapshot_returns_normalized_orders(self):
        request = FakeRequest()
        items = await _get_broker_open_orders_snapshot(request)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["order_id"], "ord-1")
        self.assertEqual(items[0]["client_order_id"], "cli-1")

    async def test_broker_order_snapshot_returns_order_detail(self):
        request = FakeRequest()
        order = await _get_broker_order_snapshot(request, 'ord-1')
        self.assertEqual(order['order_id'], 'ord-1')
        self.assertEqual(order['client_order_id'], 'cli-1')

    async def test_cancel_broker_order_uses_adapter(self):
        request = FakeRequest()
        result = await _cancel_broker_order(request, 'ord-1')
        self.assertTrue(result['ok'])
        self.assertEqual(result['order_id'], 'ord-1')
        self.assertEqual(result['status_code'], 204)

    def test_broker_payload_preserves_normalized_fields(self):
        payload = _broker_payload(
            BrokerOrder(
                order_id="ord-2",
                symbol="MSFT",
                side="buy",
                qty=5,
                filled_qty=0,
                status="new",
                order_type="market",
                client_order_id="cli-2",
                submitted_at="2026-04-11T21:05:00Z",
            )
        )
        self.assertEqual(payload["order_id"], "ord-2")
        self.assertEqual(payload["client_order_id"], "cli-2")
        self.assertEqual(payload["submitted_at"], "2026-04-11T21:05:00Z")


if __name__ == "__main__":
    unittest.main()
