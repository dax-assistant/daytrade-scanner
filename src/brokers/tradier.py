from __future__ import annotations

from src.brokers.models import BrokerHealth


class TradierBrokerAdapter:
    broker_name = "tradier"

    async def healthcheck(self) -> BrokerHealth:
        return BrokerHealth(ok=False, broker=self.broker_name, mode="unconfigured", detail="adapter_not_implemented")
