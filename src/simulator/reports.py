from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz

from src.db.manager import DatabaseManager
from src.data.models import DailySummary


class ReportGenerator:
    def __init__(self, db: DatabaseManager, notifier: Any, timezone_name: str = "America/New_York") -> None:
        self.db = db
        self.notifier = notifier
        self._tz = pytz.timezone(timezone_name)

    async def send_eod_summary(self, summary: DailySummary) -> None:
        await self.notifier.send_eod_summary(summary)

    async def send_weekly_report(self) -> None:
        now = datetime.now(self._tz).date()
        start = now - timedelta(days=6)
        summaries = await self.db.get_summaries_range(start.isoformat(), now.isoformat())
        if not summaries:
            return

        agg = self._aggregate_summaries(summaries)
        text = (
            f"📈 Weekly Report ({start.isoformat()} → {now.isoformat()})\n"
            f"Trades: {agg['total_trades']} | Win Rate: {agg['win_rate']:.0f}%\n"
            f"P&L: ${agg['total_pnl']:+.2f}\n"
            f"Hits: {agg['scanner_hits_count']} | Alerts: {agg['alerts_count']}"
        )
        await self.notifier.send_weekly_report(text, data=agg)

    async def send_monthly_report(self) -> None:
        now = datetime.now(self._tz).date()
        start = now.replace(day=1)
        summaries = await self.db.get_summaries_range(start.isoformat(), now.isoformat())
        if not summaries:
            return

        by_month: Dict[str, List[DailySummary]] = defaultdict(list)
        for summary in summaries:
            key = summary.date[:7]
            by_month[key].append(summary)

        latest_month = sorted(by_month.keys())[-1]
        agg = self._aggregate_summaries(by_month[latest_month])
        text = (
            f"🗓️ Monthly Report ({latest_month})\n"
            f"Trades: {agg['total_trades']} | Win Rate: {agg['win_rate']:.0f}%\n"
            f"P&L: ${agg['total_pnl']:+.2f}\n"
            f"Hits: {agg['scanner_hits_count']} | Alerts: {agg['alerts_count']}"
        )
        await self.notifier.send_monthly_report(text, data=agg)

    def _aggregate_summaries(self, summaries: List[DailySummary]) -> Dict[str, float]:
        total_trades = sum(s.total_trades for s in summaries)
        wins = sum(s.winning_trades for s in summaries)
        pnl = sum(s.total_pnl for s in summaries)
        hits = sum(s.scanner_hits_count for s in summaries)
        alerts = sum(s.alerts_count for s in summaries)
        return {
            "total_trades": total_trades,
            "win_rate": (wins / total_trades * 100.0) if total_trades else 0.0,
            "total_pnl": pnl,
            "scanner_hits_count": hits,
            "alerts_count": alerts,
        }
