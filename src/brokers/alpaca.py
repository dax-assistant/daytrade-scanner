from __future__ import annotations

from src.brokers.models import (
    BrokerAccount,
    BrokerCancelResult,
    BrokerHealth,
    BrokerOrder,
    BrokerOrderSubmission,
    BrokerPosition,
    EntryOrderRequest,
    ExitOrderRequest,
)
from src.data.alpaca_client import AlpacaClient


class AlpacaBrokerAdapter:
    broker_name = "alpaca"

    def __init__(self, client: AlpacaClient) -> None:
        self.client = client

    def _normalize_order(self, raw: dict) -> BrokerOrder:
        return BrokerOrder(
            order_id=str(raw.get("id") or ""),
            symbol=str(raw.get("symbol") or "").upper(),
            side=str(raw.get("side") or ""),
            qty=int(float(raw.get("qty") or 0) or 0),
            filled_qty=int(float(raw.get("filled_qty") or 0) or 0),
            status=str(raw.get("status") or "unknown").lower(),
            order_type=str(raw.get("type") or ""),
            order_class=str(raw.get("order_class") or ""),
            client_order_id=str(raw.get("client_order_id") or ""),
            filled_avg_price=(float(raw.get("filled_avg_price")) if raw.get("filled_avg_price") not in (None, "") else None),
            submitted_at=str(raw.get("submitted_at")) if raw.get("submitted_at") else None,
            updated_at=str(raw.get("updated_at")) if raw.get("updated_at") else None,
            filled_at=str(raw.get("filled_at")) if raw.get("filled_at") else None,
            stop_loss=raw.get("stop_loss") if isinstance(raw.get("stop_loss"), dict) else {},
            take_profit=raw.get("take_profit") if isinstance(raw.get("take_profit"), dict) else {},
            legs=[leg for leg in raw.get("legs", []) if isinstance(leg, dict)] if isinstance(raw.get("legs"), list) else [],
            raw=raw,
        )

    async def get_account(self) -> BrokerAccount:
        raw = await self.client.get_account()
        return BrokerAccount(
            account_id=str(raw.get("id") or ""),
            status=str(raw.get("status") or "unknown"),
            account_mode="margin" if str(raw.get("multiplier") or "1") not in {"", "1", "1.0"} else "cash",
            buying_power=float(raw.get("buying_power") or 0.0),
            cash=float(raw.get("cash") or 0.0),
            settled_cash=float(raw.get("cash") or 0.0),
            equity=float(raw.get("equity") or 0.0),
            portfolio_value=float(raw.get("portfolio_value") or raw.get("equity") or 0.0),
            raw=raw,
        )

    async def get_positions(self) -> list[BrokerPosition]:
        raw_positions = await self.client.get_positions()
        return [
            BrokerPosition(
                symbol=str(item.get("symbol") or "").upper(),
                qty=int(float(item.get("qty") or 0) or 0),
                side=str(item.get("side") or "long"),
                market_value=float(item.get("market_value") or 0.0),
                avg_entry_price=float(item.get("avg_entry_price") or 0.0),
                raw=item,
            )
            for item in raw_positions
        ]

    async def get_order(self, broker_order_id: str, *, nested: bool = False) -> BrokerOrder | None:
        raw = await self.client.get_order(broker_order_id, nested=nested)
        if not raw:
            return None
        return self._normalize_order(raw)

    async def list_open_orders(self) -> list[BrokerOrder]:
        raw_orders = await self.client.list_orders(status="open")
        return [self._normalize_order(item) for item in raw_orders if isinstance(item, dict)]

    async def submit_market_entry(self, request: EntryOrderRequest) -> BrokerOrderSubmission:
        if request.stop_loss and request.stop_loss > 0:
            raw = await self.client.submit_protected_order(
                symbol=request.symbol,
                qty=request.qty,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
            )
        else:
            raw = await self.client.submit_market_order(request.symbol, request.qty, side=request.side)
        order = self._normalize_order(raw) if raw else None
        return BrokerOrderSubmission(accepted=bool(order and order.order_id), order=order, raw=raw)

    async def submit_market_exit(self, request: ExitOrderRequest) -> BrokerOrderSubmission:
        raw = await self.client.submit_market_order(request.symbol, request.qty, side=request.side)
        order = self._normalize_order(raw) if raw else None
        return BrokerOrderSubmission(accepted=bool(order and order.order_id), order=order, raw=raw)

    async def cancel_order(self, broker_order_id: str) -> BrokerCancelResult:
        status_code = await self.client.cancel_order(broker_order_id)
        return BrokerCancelResult(ok=status_code in {200, 204}, order_id=broker_order_id, status_code=status_code)

    async def supports_bracket_orders(self) -> bool:
        return True

    async def healthcheck(self) -> BrokerHealth:
        try:
            account = await self.get_account()
            return BrokerHealth(ok=bool(account.account_id), broker=self.broker_name, mode=self.client.get_active_trading_env(), detail=account.status)
        except Exception as exc:
            return BrokerHealth(ok=False, broker=self.broker_name, mode=self.client.get_active_trading_env(), detail=str(exc))
