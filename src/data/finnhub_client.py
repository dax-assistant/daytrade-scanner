from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from src.config import Settings
from src.data.models import NewsCatalyst

LOGGER = logging.getLogger(__name__)


class AsyncRateLimiter:
    def __init__(self, calls_per_minute: int) -> None:
        self._min_interval = 60.0 / max(1, calls_per_minute)
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            wait_for = self._min_interval - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_call = time.monotonic()


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime


class FinnhubClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = AsyncRateLimiter(settings.runtime.rate_limits.finnhub_calls_per_minute)
        self._float_cache: Dict[str, CacheEntry] = {}
        self._news_cache: Dict[str, CacheEntry] = {}

    async def start(self) -> None:
        if self._session:
            return
        timeout = aiohttp.ClientTimeout(total=self.settings.finnhub.request_timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def get_float_shares(self, symbol: str) -> Optional[int]:
        symbol = symbol.upper()
        cached = self._float_cache.get(symbol)
        if cached and cached.expires_at > datetime.now(timezone.utc):
            return cached.value

        payload = await self._request_json("/stock/profile2", {"symbol": symbol})
        share_outstanding_m = payload.get("shareOutstanding") if isinstance(payload, dict) else None
        if share_outstanding_m is None:
            return None

        float_shares = int(float(share_outstanding_m) * 1_000_000)
        self._float_cache[symbol] = CacheEntry(
            value=float_shares,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        return float_shares

    async def get_recent_news(
        self,
        symbol: str,
        max_age_hours: int,
    ) -> Optional[NewsCatalyst]:
        symbol = symbol.upper()
        cached = self._news_cache.get(symbol)
        if cached and cached.expires_at > datetime.now(timezone.utc):
            return cached.value

        now_utc = datetime.now(timezone.utc)
        from_date = (now_utc - timedelta(days=1)).date().isoformat()
        to_date = now_utc.date().isoformat()

        payload = await self._request_json(
            "/company-news",
            {"symbol": symbol, "from": from_date, "to": to_date},
        )

        catalyst = self._extract_latest_catalyst(payload, max_age_hours=max_age_hours)
        self._news_cache[symbol] = CacheEntry(
            value=catalyst,
            expires_at=now_utc + timedelta(minutes=5),
        )
        return catalyst

    def _extract_latest_catalyst(self, payload: Any, max_age_hours: int) -> Optional[NewsCatalyst]:
        if not isinstance(payload, list) or not payload:
            return None

        now_ts = int(datetime.now(timezone.utc).timestamp())
        max_age_seconds = max_age_hours * 3600

        candidates: List[NewsCatalyst] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            ts = int(item.get("datetime") or 0)
            if ts <= 0:
                continue
            age_seconds = now_ts - ts
            if age_seconds < 0 or age_seconds > max_age_seconds:
                continue

            published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
            candidates.append(
                NewsCatalyst(
                    headline=str(item.get("headline") or "Unknown headline"),
                    source=str(item.get("source") or "Finnhub"),
                    url=str(item.get("url") or ""),
                    published_at=published_at,
                    age_minutes=max(0, int(age_seconds / 60)),
                )
            )

        if not candidates:
            return None

        candidates.sort(key=lambda x: x.published_at, reverse=True)
        return candidates[0]

    async def _request_json(self, path: str, params: Dict[str, Any], max_attempts: int = 4) -> Any:
        if not self._session:
            raise RuntimeError("FinnhubClient.start() must be called before requests")

        url = f"{self.settings.finnhub.base_url.rstrip('/')}{path}"
        all_params = {**params, "token": self.settings.finnhub.api_key}

        for attempt in range(1, max_attempts + 1):
            await self._rate_limiter.wait()
            try:
                async with self._session.get(url, params=all_params) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "2"))
                        LOGGER.warning("Finnhub rate limited. Retrying in %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as exc:
                if attempt == max_attempts:
                    raise
                LOGGER.warning("Finnhub request failed (%s). Attempt %s/%s", exc.status, attempt, max_attempts)
                await asyncio.sleep(attempt)
            except asyncio.TimeoutError:
                if attempt == max_attempts:
                    raise
                LOGGER.warning("Finnhub request timeout. Attempt %s/%s", attempt, max_attempts)
                await asyncio.sleep(attempt)

        raise RuntimeError(f"Failed Finnhub request after {max_attempts} attempts: {url}")
