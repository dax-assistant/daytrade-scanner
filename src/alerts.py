from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

import aiohttp

from src.config import Settings
from src.data.models import DailySummary, StockCandidate, Trade

LOGGER = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self._session:
            return
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def format_scanner_hit(self, candidate: StockCandidate) -> str:
        arrow = "↑" if candidate.gap_percent >= 0 else "↓"
        news_headline = candidate.news.headline if candidate.news else "No fresh headline found"
        float_m = (candidate.float_shares or 0) / 1_000_000 if candidate.float_shares else 0
        rel_vol = f"{candidate.relative_volume:.1f}x"
        stars = "⭐" * (candidate.pillars.score if candidate.pillars else 0)
        pillars_text = f"{candidate.pillars.score if candidate.pillars else 0}/5"

        return (
            f"🔥 SCANNER HIT: ${candidate.ticker}\n"
            f"Price: ${candidate.price:.2f} ({arrow}{abs(candidate.gap_percent):.1f}%)\n"
            f"Float: {float_m:.1f}M shares\n"
            f"Rel Volume: {rel_vol}\n"
            f"News: {news_headline}\n"
            f"Pillars: {pillars_text} {stars}"
        )

    def format_eod_summary(self, s: DailySummary) -> str:
        return (
            f"📊 EOD Summary — {s.date}\n"
            f"Trades: {s.total_trades} | Wins: {s.winning_trades} ({s.win_rate:.0f}%)\n"
            f"P&L: ${s.total_pnl:+.2f}\n"
            f"Best: ${s.largest_win or 0:.2f} | Worst: ${s.largest_loss or 0:.2f}\n"
            f"Scanner Hits: {s.scanner_hits_count} | Alerts: {s.alerts_count}"
        )

    def format_trade_alert(self, trade: Trade, action: str) -> str:
        if action == "opened":
            return (
                f"🟢 TRADE OPENED: ${trade.ticker}\n"
                f"Entry: ${trade.entry_price:.2f} | Qty: {trade.quantity}\n"
                f"Stop: ${trade.stop_loss:.2f} | Target: ${trade.take_profit or 'trailing'}\n"
                f"Profile: {trade.risk_profile}"
            )

        return (
            f"{'🟢' if (trade.pnl or 0) >= 0 else '🔴'} TRADE CLOSED: ${trade.ticker}\n"
            f"P&L: ${trade.pnl:+.2f} ({trade.pnl_percent:+.1f}%)\n"
            f"Entry: ${trade.entry_price:.2f} → Exit: ${trade.exit_price:.2f}\n"
            f"Reason: {trade.close_reason}"
        )

    async def send_scanner_hit(self, candidate: StockCandidate) -> Dict[str, str]:
        text = self.format_scanner_hit(candidate)
        return await self._send_message(text=text)

    async def send_system_message(self, text: str) -> Dict[str, str]:
        return await self._send_message(text=text)

    async def send_eod_summary(self, summary: DailySummary) -> Dict[str, str]:
        return await self._send_message(text=self.format_eod_summary(summary))

    async def send_trade_alert(self, trade: Trade, action: str) -> Dict[str, str]:
        return await self._send_message(text=self.format_trade_alert(trade, action))

    async def _send_message(self, text: str, max_attempts: int = 4) -> Dict[str, str]:
        if not self._session:
            raise RuntimeError("TelegramAlerter.start() must be called before requests")

        token = self.settings.telegram.bot_token
        url = f"{self.settings.telegram.base_url.rstrip('/')}/bot{token}/sendMessage"
        payload = {
            "chat_id": self.settings.telegram.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }

        for attempt in range(1, max_attempts + 1):
            try:
                async with self._session.post(url, json=payload) as resp:
                    if resp.status == 429:
                        body = await resp.json(content_type=None)
                        retry_after = int(((body or {}).get("parameters") or {}).get("retry_after", 2))
                        LOGGER.warning("Telegram rate limit hit. Retrying in %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()
                    body = await resp.json(content_type=None)
                    return {
                        "status": "sent",
                        "message_id": str(((body or {}).get("result") or {}).get("message_id", "")),
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception as exc:
                if attempt == max_attempts:
                    LOGGER.error("Failed to send Telegram alert after %s attempts: %s", max_attempts, exc)
                    return {
                        "status": "failed",
                        "message_id": "",
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    }
                await asyncio.sleep(attempt)

        return {
            "status": "failed",
            "message_id": "",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
