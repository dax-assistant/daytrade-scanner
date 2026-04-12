from __future__ import annotations

from src.brokers.alpaca import AlpacaBrokerAdapter
from src.brokers.base import BrokerAdapter
from src.brokers.ibkr import IBKRBrokerAdapter
from src.brokers.tradier import TradierBrokerAdapter
from src.config import Settings
from src.data.alpaca_client import AlpacaClient


def build_broker_adapter(settings: Settings, *, alpaca_client: AlpacaClient) -> BrokerAdapter:
    broker = settings.trading.broker.strip().lower()
    if broker == "alpaca":
        return AlpacaBrokerAdapter(alpaca_client)
    if broker == "ibkr":
        return IBKRBrokerAdapter()  # type: ignore[return-value]
    if broker == "tradier":
        return TradierBrokerAdapter()  # type: ignore[return-value]
    raise ValueError(f"Unsupported broker adapter: {broker}")
