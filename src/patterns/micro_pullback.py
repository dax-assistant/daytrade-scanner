from __future__ import annotations

from typing import Any, Dict, List


def detect_micro_pullback(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect a simple micro-pullback continuation setup.

    Pattern:
    - 3+ strong green candles (surge)
    - followed by 1-3 small red/doji candles on lighter volume (pullback)
    - latest close breaks above pullback high (trigger)
    """
    if len(bars) < 7:
        return {
            "detected": False,
            "entry_price": None,
            "stop_price": None,
            "target_price": None,
            "pattern_bars": 0,
            "reason": "not_enough_bars",
        }

    norm = []
    for b in bars:
        norm.append(
            {
                "open": float(b.get("open", 0) or 0),
                "high": float(b.get("high", 0) or 0),
                "low": float(b.get("low", 0) or 0),
                "close": float(b.get("close", 0) or 0),
                "volume": float(b.get("volume", 0) or 0),
            }
        )

    latest = norm[-1]

    # Find pullback window (1-3 candles before latest)
    for pullback_len in (3, 2, 1):
        if len(norm) < pullback_len + 4:
            continue

        pullback = norm[-(pullback_len + 1) : -1]
        surge = norm[-(pullback_len + 4) : -(pullback_len + 1)]

        if len(surge) < 3:
            continue

        # Surge: mostly green with expanding highs
        surge_green = sum(1 for c in surge if c["close"] > c["open"])
        if surge_green < 3:
            continue

        if not (surge[0]["high"] < surge[1]["high"] <= surge[2]["high"]):
            continue

        # Pullback: red/doji, smaller ranges, lighter volume than surge avg
        surge_avg_vol = sum(c["volume"] for c in surge) / max(1, len(surge))
        pullback_ok = True
        for c in pullback:
            body = abs(c["close"] - c["open"])
            rng = max(0.000001, c["high"] - c["low"])
            body_pct = body / rng
            red_or_doji = c["close"] <= c["open"] or body_pct < 0.35
            lighter_vol = c["volume"] <= surge_avg_vol
            if not (red_or_doji and lighter_vol):
                pullback_ok = False
                break

        if not pullback_ok:
            continue

        pullback_high = max(c["high"] for c in pullback)
        pullback_low = min(c["low"] for c in pullback)

        # Trigger: latest breaks above pullback high
        if latest["close"] <= pullback_high:
            continue

        entry_price = latest["close"]
        stop_price = pullback_low
        risk = max(0.000001, entry_price - stop_price)
        target_price = entry_price + (2.0 * risk)

        return {
            "detected": True,
            "entry_price": round(entry_price, 4),
            "stop_price": round(stop_price, 4),
            "target_price": round(target_price, 4),
            "pattern_bars": len(surge) + len(pullback) + 1,
            "reason": "micro_pullback_breakout",
        }

    return {
        "detected": False,
        "entry_price": None,
        "stop_price": None,
        "target_price": None,
        "pattern_bars": 0,
        "reason": "pattern_not_found",
    }
