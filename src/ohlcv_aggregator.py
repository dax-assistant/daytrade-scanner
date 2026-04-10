from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.indicators import compute_overlays


@dataclass
class CandleBuilder:
    """Aggregate incoming OHLCV updates into candles for a fixed interval."""

    interval_sec: int
    max_candles: int = 500
    candles: Dict[str, List[Dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    active: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def ingest_bar(
        self,
        symbol: str,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: int,
        timestamp: int | float | str,
    ) -> Dict[str, Any]:
        symbol = symbol.upper()
        bucket = int(self._to_epoch_seconds(timestamp) // self.interval_sec) * self.interval_sec

        current = self.active.get(symbol)
        if not current or int(current.get("time", 0)) != bucket:
            if current:
                completed = dict(current)
                self.candles[symbol].append(completed)
                if len(self.candles[symbol]) > self.max_candles:
                    self.candles[symbol] = self.candles[symbol][-self.max_candles :]

            self.active[symbol] = {
                "time": bucket,
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": int(volume),
            }
            return dict(self.active[symbol])

        current["high"] = max(float(current.get("high", high_price)), float(high_price), float(close_price))
        current["low"] = min(float(current.get("low", low_price)), float(low_price), float(close_price))
        current["close"] = float(close_price)
        current["volume"] = int(current.get("volume", 0)) + int(volume)
        return dict(current)

    def get_snapshot(self, symbol: str) -> List[Dict[str, Any]]:
        symbol = symbol.upper()
        completed = list(self.candles.get(symbol, []))
        active = self.active.get(symbol)
        if active:
            completed.append(dict(active))
        return completed[-self.max_candles :]

    def get_snapshot_with_overlays(self, symbol: str) -> Dict[str, Any]:
        candles = self.get_snapshot(symbol)
        overlays = compute_overlays(candles)
        return {"candles": candles, "overlays": overlays}

    @staticmethod
    def _to_epoch_seconds(ts: int | float | str) -> int:
        if isinstance(ts, (int, float)):
            return int(ts)

        text = str(ts).strip()
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        try:
            return int(datetime.fromisoformat(text).timestamp())
        except ValueError:
            return int(datetime.now(timezone.utc).timestamp())
