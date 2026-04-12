from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BrokerAccount:
    account_id: str
    status: str
    account_mode: str
    buying_power: float = 0.0
    cash: float = 0.0
    settled_cash: float = 0.0
    equity: float = 0.0
    portfolio_value: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: int
    side: str
    market_value: float = 0.0
    avg_entry_price: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerOrder:
    order_id: str
    symbol: str
    side: str
    qty: int
    filled_qty: int
    status: str
    order_type: str
    order_class: str = ""
    client_order_id: str = ""
    filled_avg_price: Optional[float] = None
    submitted_at: Optional[str] = None
    updated_at: Optional[str] = None
    filled_at: Optional[str] = None
    stop_loss: Dict[str, Any] = field(default_factory=dict)
    take_profit: Dict[str, Any] = field(default_factory=dict)
    legs: list[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerOrderSubmission:
    accepted: bool
    order: Optional[BrokerOrder]
    raw: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerCancelResult:
    ok: bool
    order_id: str
    status_code: Optional[int] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerHealth:
    ok: bool
    broker: str
    mode: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EntryOrderRequest:
    symbol: str
    qty: int
    side: str = "buy"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass(frozen=True)
class ExitOrderRequest:
    symbol: str
    qty: int
    side: str = "sell"
    broker_order_id: str = ""
