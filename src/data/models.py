from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class NewsCatalyst:
    headline: str
    source: str
    url: str
    published_at: datetime
    age_minutes: int


@dataclass
class PillarEvaluation:
    price: bool
    gap_percent: bool
    relative_volume: bool
    float_shares: bool
    news_catalyst: bool

    @property
    def score(self) -> int:
        return sum(1 for v in asdict(self).values() if bool(v))


@dataclass
class StockCandidate:
    ticker: str
    price: float
    gap_percent: float
    volume: int
    avg_volume: float
    relative_volume: float
    avg_volume_basis: str = "unknown"
    float_shares: Optional[int] = None
    news: Optional[NewsCatalyst] = None
    market_rank: Optional[int] = None
    session_label: str = "unknown"
    scanned_at: datetime = field(default_factory=datetime.utcnow)
    pillars: Optional[PillarEvaluation] = None
    float_tier: str = "unknown"
    entry_signals: Optional[Dict[str, Any]] = None
    db_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        news_dict: Optional[Dict[str, Any]] = None
        if self.news:
            news_dict = {
                "headline": self.news.headline,
                "source": self.news.source,
                "url": self.news.url,
                "published_at": self.news.published_at.isoformat(),
                "age_minutes": self.news.age_minutes,
            }

        pillars_dict = asdict(self.pillars) if self.pillars else None
        return {
            "ticker": self.ticker,
            "price": self.price,
            "gap_percent": self.gap_percent,
            "volume": self.volume,
            "avg_volume": self.avg_volume,
            "relative_volume": self.relative_volume,
            "avg_volume_basis": self.avg_volume_basis,
            "float_shares": self.float_shares,
            "float_tier": self.float_tier,
            "news": news_dict,
            "market_rank": self.market_rank,
            "session_label": self.session_label,
            "scanned_at": self.scanned_at.isoformat(),
            "pillars": pillars_dict,
            "pillar_details": pillars_dict,
            "score": self.pillars.score if self.pillars else 0,
            "entry_signals": self.entry_signals,
            "db_id": self.db_id,
        }


@dataclass
class RiskProfile:
    name: str
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop: bool
    trailing_stop_pct: float
    max_hold_minutes: int


@dataclass
class Trade:
    id: Optional[int]
    scanner_hit_id: Optional[int]
    ticker: str
    side: str
    risk_profile: str
    entry_price: float
    entry_time: datetime
    exit_price: Optional[float]
    exit_time: Optional[datetime]
    stop_loss: float
    take_profit: Optional[float]
    trailing_stop_pct: Optional[float]
    quantity: int
    status: str
    pnl: Optional[float]
    pnl_percent: Optional[float]
    alpaca_order_id: Optional[str]
    broker_order_state: Optional[str]
    broker_client_order_id: Optional[str]
    broker_filled_qty: Optional[int]
    broker_filled_avg_price: Optional[float]
    broker_updated_at: Optional[datetime]
    close_reason: Optional[str]
    max_price_seen: float

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["entry_time"] = self.entry_time.isoformat()
        payload["exit_time"] = self.exit_time.isoformat() if self.exit_time else None
        payload["broker_updated_at"] = self.broker_updated_at.isoformat() if self.broker_updated_at else None
        return payload

    def to_dict_with_current_price(self, current_price: Optional[float] = None) -> Dict[str, Any]:
        payload = self.to_dict()
        px = float(current_price if current_price is not None else self.entry_price)
        unrealized = (px - self.entry_price) * self.quantity if self.status == "open" else 0.0
        hold_minutes = int((datetime.now(timezone.utc) - self.entry_time).total_seconds() / 60)
        payload.update(
            {
                "current_price": px,
                "unrealized_pnl": unrealized,
                "unrealized_pnl_pct": ((px - self.entry_price) / self.entry_price * 100.0) if self.entry_price else 0.0,
                "hold_minutes": max(0, hold_minutes),
            }
        )
        return payload


@dataclass
class DailySummary:
    date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    win_rate: float
    largest_win: Optional[float]
    largest_loss: Optional[float]
    scanner_hits_count: int
    alerts_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
