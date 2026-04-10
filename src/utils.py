"""Shared utility functions for the Day Trade Scanner."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict

import pytz

# Eastern market session time boundaries
_PREMARKET_START = time(4, 0)
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)
_AFTERHOURS_END = time(20, 0)


def get_market_session(tz_name: str = "America/New_York") -> str:
    """Return current market session label: premarket, regular, afterhours, or closed."""
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    t = now.time()
    if t < _PREMARKET_START:
        return "closed"
    elif t < _MARKET_OPEN:
        return "premarket"
    elif t < _MARKET_CLOSE:
        return "regular"
    elif t < _AFTERHOURS_END:
        return "afterhours"
    else:
        return "closed"


def get_primary_window_info(
    tz_name: str = "America/New_York",
    start_hour: int = 7,
    end_hour: int = 10,
) -> Dict[str, Any]:
    tz = pytz.timezone(tz_name)
    now_et = datetime.now(tz)
    start_dt = now_et.replace(hour=int(start_hour), minute=0, second=0, microsecond=0)
    end_dt = now_et.replace(hour=int(end_hour), minute=0, second=0, microsecond=0)

    if now_et < start_dt:
        countdown = int((start_dt - now_et).total_seconds())
        is_active = False
    elif now_et < end_dt:
        countdown = int((end_dt - now_et).total_seconds())
        is_active = True
    else:
        next_start = start_dt + timedelta(days=1)
        countdown = int((next_start - now_et).total_seconds())
        is_active = False

    return {
        "start_hour_et": int(start_hour),
        "end_hour_et": int(end_hour),
        "is_active": is_active,
        "countdown_seconds": max(0, countdown),
    }


def get_session_info(tz_name: str = "America/New_York") -> Dict[str, Any]:
    """Return full session state dict for the /api/market/session endpoint."""
    tz = pytz.timezone(tz_name)
    now_et = datetime.now(tz)
    t = now_et.time()

    if t < _PREMARKET_START:
        session = "closed"
        label = "CLOSED"
        next_label = "Pre-Market"
        next_target = _PREMARKET_START
    elif t < _MARKET_OPEN:
        session = "premarket"
        label = "PRE-MARKET"
        next_label = "Market Open"
        next_target = _MARKET_OPEN
    elif t < _MARKET_CLOSE:
        session = "open"
        label = "MARKET OPEN"
        next_label = "Market Close"
        next_target = _MARKET_CLOSE
    elif t < _AFTERHOURS_END:
        session = "afterhours"
        label = "AFTER-HOURS"
        next_label = "After-Hours End"
        next_target = _AFTERHOURS_END
    else:
        session = "closed"
        label = "CLOSED"
        next_label = "Pre-Market"
        next_target = _PREMARKET_START

    # Calculate countdown seconds to next event
    target_dt = now_et.replace(
        hour=next_target.hour, minute=next_target.minute, second=0, microsecond=0
    )
    if target_dt <= now_et:
        target_dt += timedelta(days=1)
    countdown = int((target_dt - now_et).total_seconds())

    return {
        "session": session,
        "label": label,
        "is_open": session == "open",
        "times": {
            "premarket_start": _PREMARKET_START.strftime("%H:%M"),
            "market_open": _MARKET_OPEN.strftime("%H:%M"),
            "market_close": _MARKET_CLOSE.strftime("%H:%M"),
            "afterhours_end": _AFTERHOURS_END.strftime("%H:%M"),
        },
        "next_event": {
            "label": next_label,
            "time": next_target.strftime("%H:%M"),
            "countdown_seconds": countdown,
        },
        "primary_window": get_primary_window_info(tz_name),
        "current_time_et": now_et.isoformat(),
    }
