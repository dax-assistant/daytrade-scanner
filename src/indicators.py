"""Technical indicator computations for chart overlays and entry signal evaluation."""

from __future__ import annotations

from typing import Any, Dict, List


def compute_ema(closes: List[float], period: int) -> List[float]:
    if not closes:
        return []
    if period <= 1:
        return [float(c) for c in closes]

    out: List[float] = []
    multiplier = 2.0 / (period + 1)
    ema_prev = float(closes[0])
    for close in closes:
        c = float(close)
        ema_prev = (c * multiplier) + (ema_prev * (1.0 - multiplier))
        out.append(ema_prev)
    return out


def compute_vwap(bars: List[Dict[str, Any]]) -> List[float]:
    if not bars:
        return []

    out: List[float] = []
    cumulative_pv = 0.0
    cumulative_v = 0.0
    for bar in bars:
        high = float(bar.get("high", 0) or 0)
        low = float(bar.get("low", 0) or 0)
        close = float(bar.get("close", 0) or 0)
        volume = float(bar.get("volume", 0) or 0)
        typical_price = (high + low + close) / 3.0
        cumulative_pv += typical_price * volume
        cumulative_v += volume
        out.append(cumulative_pv / cumulative_v if cumulative_v > 0 else close)
    return out


def compute_macd(
    closes: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> List[Dict[str, float]]:
    if not closes:
        return []

    ema_fast = compute_ema(closes, fast_period)
    ema_slow = compute_ema(closes, slow_period)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = compute_ema(macd_line, signal_period)

    out: List[Dict[str, float]] = []
    for m, s in zip(macd_line, signal_line):
        out.append({"macd": float(m), "signal": float(s), "histogram": float(m - s)})
    return out


def compute_overlays(bars: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    if not bars:
        return {"vwap": [], "ema9": [], "ema20": [], "macd": []}

    closes = [float(b.get("close", 0) or 0) for b in bars]
    vwap_vals = compute_vwap(bars)
    ema9_vals = compute_ema(closes, 9)
    ema20_vals = compute_ema(closes, 20)
    macd_vals = compute_macd(closes, 12, 26, 9)

    vwap = []
    ema9 = []
    ema20 = []
    macd = []

    for idx, bar in enumerate(bars):
        t = int(bar.get("time", 0) or 0)
        vwap.append({"time": t, "value": float(vwap_vals[idx])})
        ema9.append({"time": t, "value": float(ema9_vals[idx])})
        ema20.append({"time": t, "value": float(ema20_vals[idx])})
        m = macd_vals[idx]
        macd.append(
            {
                "time": t,
                "macd": float(m["macd"]),
                "signal": float(m["signal"]),
                "histogram": float(m["histogram"]),
            }
        )

    return {"vwap": vwap, "ema9": ema9, "ema20": ema20, "macd": macd}


def evaluate_entry_signals(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not bars:
        return {
            "macd_positive": False,
            "above_vwap": False,
            "above_ema9": False,
            "volume_bullish": False,
            "all_clear": False,
            "macd": {"value": 0.0, "signal": 0.0, "histogram": 0.0},
            "vwap": 0.0,
            "ema9": 0.0,
            "ema20": 0.0,
        }

    closes = [float(b.get("close", 0) or 0) for b in bars]
    vwap_vals = compute_vwap(bars)
    ema9_vals = compute_ema(closes, 9)
    ema20_vals = compute_ema(closes, 20)
    macd_vals = compute_macd(closes)

    latest_close = closes[-1]
    latest_vwap = vwap_vals[-1] if vwap_vals else latest_close
    latest_ema9 = ema9_vals[-1] if ema9_vals else latest_close
    latest_ema20 = ema20_vals[-1] if ema20_vals else latest_close
    latest_macd = macd_vals[-1] if macd_vals else {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    lookback = bars[-10:]
    buying_volume = 0.0
    selling_volume = 0.0
    for bar in lookback:
        o = float(bar.get("open", 0) or 0)
        c = float(bar.get("close", 0) or 0)
        v = float(bar.get("volume", 0) or 0)
        if c >= o:
            buying_volume += v
        else:
            selling_volume += v

    macd_positive = float(latest_macd["macd"]) > float(latest_macd["signal"])
    above_vwap = latest_close > latest_vwap
    above_ema9 = latest_close >= latest_ema9
    volume_bullish = buying_volume >= selling_volume

    all_clear = macd_positive and above_vwap and above_ema9 and volume_bullish

    return {
        "macd_positive": bool(macd_positive),
        "above_vwap": bool(above_vwap),
        "above_ema9": bool(above_ema9),
        "volume_bullish": bool(volume_bullish),
        "all_clear": bool(all_clear),
        "macd": {
            "value": float(latest_macd["macd"]),
            "signal": float(latest_macd["signal"]),
            "histogram": float(latest_macd["histogram"]),
            "is_positive": bool(macd_positive),
        },
        "vwap": float(latest_vwap),
        "ema9": float(latest_ema9),
        "ema20": float(latest_ema20),
        "volume_profile": {
            "buying_volume": int(buying_volume),
            "selling_volume": int(selling_volume),
            "is_bullish": bool(volume_bullish),
        },
    }
