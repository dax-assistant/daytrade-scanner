from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class ExecutionGuardStatus:
    mode: str
    broker: str
    allowed: bool
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    qty: int
    estimated_price: float
    estimated_notional: float
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TradingPolicyError(RuntimeError):
    pass
