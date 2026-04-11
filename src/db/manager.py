from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

from src.data.models import DailySummary, StockCandidate, Trade
from src.db.migrations import run_migrations


class DatabaseManager:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await run_migrations(conn)

    async def insert_scanner_hit(self, candidate: StockCandidate) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO scanner_hits (
                    ticker, price, gap_percent, volume, avg_volume_20d, relative_volume,
                    float_shares, news_headline, news_source, news_url, news_published_at,
                    pillar_price, pillar_gap, pillar_relvol, pillar_float, pillar_news,
                    pillar_score, session_label, scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.ticker,
                    candidate.price,
                    candidate.gap_percent,
                    candidate.volume,
                    candidate.avg_volume,
                    candidate.relative_volume,
                    candidate.float_shares,
                    candidate.news.headline if candidate.news else None,
                    candidate.news.source if candidate.news else None,
                    candidate.news.url if candidate.news else None,
                    candidate.news.published_at.isoformat() if candidate.news else None,
                    bool(candidate.pillars.price) if candidate.pillars else False,
                    bool(candidate.pillars.gap_percent) if candidate.pillars else False,
                    bool(candidate.pillars.relative_volume) if candidate.pillars else False,
                    bool(candidate.pillars.float_shares) if candidate.pillars else False,
                    bool(candidate.pillars.news_catalyst) if candidate.pillars else False,
                    candidate.pillars.score if candidate.pillars else 0,
                    candidate.session_label,
                    candidate.scanned_at.isoformat(),
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    async def get_hits_today(self) -> List[Dict]:
        date_prefix = datetime.now(timezone.utc).date().isoformat()
        query = """
            SELECT *
            FROM scanner_hits
            WHERE scanned_at LIKE ? || '%'
            ORDER BY scanned_at DESC
        """
        return await self._fetch_all_dict(query, (date_prefix,))

    async def search_hits(
        self,
        ticker: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
        min_score: int = 0,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        conditions = ["pillar_score >= ?"]
        params: List[object] = [min_score]

        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker.upper())
        if date_from:
            conditions.append("scanned_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("scanned_at <= ?")
            params.append(date_to)

        params.extend([limit, offset])
        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT *
            FROM scanner_hits
            WHERE {where_clause}
            ORDER BY scanned_at DESC
            LIMIT ? OFFSET ?
        """
        return await self._fetch_all_dict(query, tuple(params))

    async def insert_alert(
        self,
        scanner_hit_id: Optional[int],
        ticker: str,
        status: str,
        message_id: str,
        sent_at: Optional[str] = None,
    ) -> int:
        sent_at_value = sent_at or datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO alerts (scanner_hit_id, ticker, status, telegram_message_id, sent_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scanner_hit_id, ticker.upper(), status, message_id, sent_at_value),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    async def insert_trade(self, trade: Trade) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO trades (
                    scanner_hit_id, ticker, side, risk_profile, entry_price, entry_time,
                    exit_price, exit_time, stop_loss, take_profit, trailing_stop_pct,
                    quantity, status, pnl, pnl_percent, alpaca_order_id, broker_order_state,
                    broker_client_order_id, broker_filled_qty, broker_filled_avg_price, broker_updated_at,
                    close_reason, max_price_seen, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.scanner_hit_id,
                    trade.ticker.upper(),
                    trade.side,
                    trade.risk_profile,
                    trade.entry_price,
                    trade.entry_time.isoformat(),
                    trade.exit_price,
                    trade.exit_time.isoformat() if trade.exit_time else None,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.trailing_stop_pct,
                    trade.quantity,
                    trade.status,
                    trade.pnl,
                    trade.pnl_percent,
                    trade.alpaca_order_id,
                    trade.broker_order_state,
                    trade.broker_client_order_id,
                    trade.broker_filled_qty,
                    trade.broker_filled_avg_price,
                    trade.broker_updated_at.isoformat() if trade.broker_updated_at else None,
                    trade.close_reason,
                    trade.max_price_seen,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid)

    async def update_trade(self, trade: Trade) -> None:
        if trade.id is None:
            raise ValueError("Trade ID is required to update trade")

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                UPDATE trades
                SET entry_price = ?, exit_price = ?, exit_time = ?, stop_loss = ?, take_profit = ?,
                    trailing_stop_pct = ?, quantity = ?, status = ?, pnl = ?, pnl_percent = ?,
                    alpaca_order_id = ?, broker_order_state = ?, broker_client_order_id = ?,
                    broker_filled_qty = ?, broker_filled_avg_price = ?, broker_updated_at = ?,
                    close_reason = ?, max_price_seen = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    trade.entry_price,
                    trade.exit_price,
                    trade.exit_time.isoformat() if trade.exit_time else None,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.trailing_stop_pct,
                    trade.quantity,
                    trade.status,
                    trade.pnl,
                    trade.pnl_percent,
                    trade.alpaca_order_id,
                    trade.broker_order_state,
                    trade.broker_client_order_id,
                    trade.broker_filled_qty,
                    trade.broker_filled_avg_price,
                    trade.broker_updated_at.isoformat() if trade.broker_updated_at else None,
                    trade.close_reason,
                    trade.max_price_seen,
                    datetime.now(timezone.utc).isoformat(),
                    trade.id,
                ),
            )
            await conn.commit()

    async def get_open_trades(self) -> List[Trade]:
        return await self._fetch_trades("SELECT * FROM trades WHERE status = 'open' ORDER BY entry_time ASC")

    async def get_active_trades(self) -> List[Trade]:
        return await self._fetch_trades(
            "SELECT * FROM trades WHERE status IN ('open', 'pending_entry', 'pending_exit', 'reconciliation_hold') ORDER BY entry_time ASC"
        )

    async def get_trades_today(self) -> List[Trade]:
        date_prefix = datetime.now(timezone.utc).date().isoformat()
        return await self._fetch_trades(
            "SELECT * FROM trades WHERE entry_time LIKE ? || '%' ORDER BY entry_time DESC",
            (date_prefix,),
        )

    async def get_trade_by_id(self, trade_id: int) -> Optional[Trade]:
        rows = await self._fetch_trades("SELECT * FROM trades WHERE id = ? LIMIT 1", (trade_id,))
        return rows[0] if rows else None

    async def get_closed_trades_by_exit_time(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Trade]:
        conditions: List[str] = ["status != 'open'", "exit_time IS NOT NULL"]
        params: List[object] = []

        if date_from:
            conditions.append("exit_time >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("exit_time <= ?")
            params.append(date_to)

        where_clause = " AND ".join(conditions)
        params.extend([limit, offset])
        query = f"""
            SELECT * FROM trades
            WHERE {where_clause}
            ORDER BY exit_time DESC
            LIMIT ? OFFSET ?
        """
        return await self._fetch_trades(query, tuple(params))

    async def get_trades(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Trade]:
        conditions: List[str] = []
        params: List[object] = []

        if date_from:
            conditions.append("entry_time >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("entry_time <= ?")
            params.append(date_to)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        query = f"""
            SELECT * FROM trades
            {where_clause}
            ORDER BY entry_time DESC
            LIMIT ? OFFSET ?
        """
        return await self._fetch_trades(query, tuple(params))

    async def count_alerts_on_date(self, date_prefix: str) -> int:
        rows = await self._fetch_all_dict(
            "SELECT COUNT(*) AS count FROM alerts WHERE sent_at LIKE ? || '%'",
            (date_prefix,),
        )
        return int((rows[0] or {}).get("count", 0)) if rows else 0

    async def upsert_daily_summary(self, summary: DailySummary) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO daily_summaries (
                    date, total_trades, winning_trades, losing_trades, total_pnl,
                    win_rate, largest_win, largest_loss, scanner_hits_count, alerts_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_trades = excluded.total_trades,
                    winning_trades = excluded.winning_trades,
                    losing_trades = excluded.losing_trades,
                    total_pnl = excluded.total_pnl,
                    win_rate = excluded.win_rate,
                    largest_win = excluded.largest_win,
                    largest_loss = excluded.largest_loss,
                    scanner_hits_count = excluded.scanner_hits_count,
                    alerts_count = excluded.alerts_count
                """,
                (
                    summary.date,
                    summary.total_trades,
                    summary.winning_trades,
                    summary.losing_trades,
                    summary.total_pnl,
                    summary.win_rate,
                    summary.largest_win,
                    summary.largest_loss,
                    summary.scanner_hits_count,
                    summary.alerts_count,
                ),
            )
            await conn.commit()

    async def get_daily_summary(self, date: str) -> Optional[DailySummary]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM daily_summaries WHERE date = ? LIMIT 1", (date,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return DailySummary(
                    date=row["date"],
                    total_trades=int(row["total_trades"]),
                    winning_trades=int(row["winning_trades"]),
                    losing_trades=int(row["losing_trades"]),
                    total_pnl=float(row["total_pnl"]),
                    win_rate=float(row["win_rate"]),
                    largest_win=float(row["largest_win"]) if row["largest_win"] is not None else None,
                    largest_loss=float(row["largest_loss"]) if row["largest_loss"] is not None else None,
                    scanner_hits_count=int(row["scanner_hits_count"]),
                    alerts_count=int(row["alerts_count"]),
                )

    async def get_summaries_range(self, date_from: str, date_to: str) -> List[DailySummary]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT * FROM daily_summaries
                WHERE date >= ? AND date <= ?
                ORDER BY date ASC
                """,
                (date_from, date_to),
            ) as cursor:
                rows = await cursor.fetchall()

        summaries: List[DailySummary] = []
        for row in rows:
            summaries.append(
                DailySummary(
                    date=row["date"],
                    total_trades=int(row["total_trades"]),
                    winning_trades=int(row["winning_trades"]),
                    losing_trades=int(row["losing_trades"]),
                    total_pnl=float(row["total_pnl"]),
                    win_rate=float(row["win_rate"]),
                    largest_win=float(row["largest_win"]) if row["largest_win"] is not None else None,
                    largest_loss=float(row["largest_loss"]) if row["largest_loss"] is not None else None,
                    scanner_hits_count=int(row["scanner_hits_count"]),
                    alerts_count=int(row["alerts_count"]),
                )
            )
        return summaries

    # ------------------------------------------------------------------ #
    # Watchlist items                                                      #
    # ------------------------------------------------------------------ #

    async def get_watchlist_items(self) -> List[Dict]:
        return await self._fetch_all_dict(
            "SELECT * FROM watchlist_items ORDER BY added_at DESC"
        )

    async def add_watchlist_item(
        self, ticker: str, notes: str = "", alert_threshold_pct: float = 5.0
    ) -> Dict:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO watchlist_items (ticker, notes, alert_threshold_pct) VALUES (?, ?, ?)",
                (ticker.upper(), notes, alert_threshold_pct),
            )
            await conn.commit()
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM watchlist_items WHERE ticker = ?", (ticker.upper(),)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else {}

    async def remove_watchlist_item(self, ticker: str) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM watchlist_items WHERE ticker = ?", (ticker.upper(),)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_watchlist_item(self, ticker: str, updates: Dict) -> bool:
        sets = []
        vals = []
        for key in ("notes", "alert_threshold_pct"):
            if key in updates:
                sets.append(f"{key} = ?")
                vals.append(updates[key])
        if not sets:
            return False
        sets.append("updated_at = datetime('now')")
        vals.append(ticker.upper())
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                f"UPDATE watchlist_items SET {', '.join(sets)} WHERE ticker = ?",
                vals,
            )
            await conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # Trade Journal                                                        #
    # ------------------------------------------------------------------ #

    async def upsert_journal_entry(self, trade_id: int, data: dict) -> dict:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT id FROM trade_journal WHERE trade_id = ?", (trade_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                await conn.execute(
                    """
                    UPDATE trade_journal
                    SET setup_type = ?, emotional_state = ?, grade = ?,
                        notes = ?, mistakes = ?, updated_at = datetime('now')
                    WHERE trade_id = ?
                    """,
                    (
                        data.get("setup_type"),
                        data.get("emotional_state"),
                        data.get("grade"),
                        data.get("notes"),
                        data.get("mistakes"),
                        trade_id,
                    ),
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO trade_journal (trade_id, setup_type, emotional_state, grade, notes, mistakes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade_id,
                        data.get("setup_type"),
                        data.get("emotional_state"),
                        data.get("grade"),
                        data.get("notes"),
                        data.get("mistakes"),
                    ),
                )
            await conn.commit()

            async with conn.execute(
                "SELECT * FROM trade_journal WHERE trade_id = ?", (trade_id,)
            ) as cursor:
                result = await cursor.fetchone()
                return dict(result) if result else {}

    async def get_journal_entry(self, trade_id: int) -> Optional[dict]:
        rows = await self._fetch_all_dict(
            "SELECT * FROM trade_journal WHERE trade_id = ? LIMIT 1", (trade_id,)
        )
        return rows[0] if rows else None

    async def get_all_journal_entries(self) -> List[dict]:
        return await self._fetch_all_dict(
            """
            SELECT j.*, t.ticker, t.pnl, t.entry_time, t.close_reason
            FROM trade_journal j
            JOIN trades t ON t.id = j.trade_id
            ORDER BY j.created_at DESC
            """
        )

    # ------------------------------------------------------------------ #
    # Analytics                                                            #
    # ------------------------------------------------------------------ #

    async def get_grade_analytics(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[dict]:
        conditions = ["t.status != 'open'", "t.pnl IS NOT NULL"]
        params: List[object] = []
        if date_from:
            conditions.append("t.entry_time >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("t.entry_time <= ?")
            params.append(date_to)
        where_clause = " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                f"""
                SELECT COALESCE(NULLIF(j.grade, ''), 'ungraded') AS grade,
                       COUNT(*) AS count,
                       AVG(t.pnl) AS avg_pnl,
                       SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) AS wins
                FROM trades t
                LEFT JOIN trade_journal j ON j.trade_id = t.id
                WHERE {where_clause}
                GROUP BY COALESCE(NULLIF(j.grade, ''), 'ungraded')
                """,
                tuple(params),
            ) as cursor:
                rows = await cursor.fetchall()

        order = {"A": 0, "B": 1, "C": 2, "D": 3, "ungraded": 4}
        analytics_map: dict[str, dict] = {
            "A": {"grade": "A", "count": 0, "avg_pnl": 0.0, "win_rate": 0.0},
            "B": {"grade": "B", "count": 0, "avg_pnl": 0.0, "win_rate": 0.0},
            "C": {"grade": "C", "count": 0, "avg_pnl": 0.0, "win_rate": 0.0},
            "D": {"grade": "D", "count": 0, "avg_pnl": 0.0, "win_rate": 0.0},
            "ungraded": {"grade": "ungraded", "count": 0, "avg_pnl": 0.0, "win_rate": 0.0},
        }
        for row in rows:
            count = int(row["count"] or 0)
            wins = int(row["wins"] or 0)
            grade = row["grade"]
            analytics_map[grade] = {
                "grade": grade,
                "count": count,
                "avg_pnl": round(float(row["avg_pnl"] or 0.0), 2),
                "win_rate": round((wins / count) * 100, 1) if count else 0.0,
            }

        items = sorted(analytics_map.values(), key=lambda item: order.get(item["grade"], 99))
        return items

    async def get_analytics_summary(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        conditions = ["status != 'open'", "pnl IS NOT NULL"]
        params: List[object] = []
        if date_from:
            conditions.append("entry_time >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("entry_time <= ?")
            params.append(date_to)
        where_clause = " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row

            async with conn.execute(
                f"""
                SELECT pnl, entry_time, exit_time, close_reason
                FROM trades
                WHERE {where_clause}
                ORDER BY entry_time ASC
                """,
                tuple(params),
            ) as cursor:
                rows = await cursor.fetchall()

        trades = [dict(r) for r in rows]

        if not trades:
            return {
                "total_trades": 0,
                "breakeven_count": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_winner": 0.0,
                "avg_loser": 0.0,
                "expectancy": 0.0,
                "avg_hold_minutes": 0.0,
                "max_win": 0.0,
                "max_loss": 0.0,
                "by_close_reason": {},
                "by_day_of_week": {},
                "by_hour": {},
                "streak": {"current": 0, "type": None, "best_win_streak": 0, "best_loss_streak": 0},
            }

        winners = [t for t in trades if float(t["pnl"]) > 0]
        losers = [t for t in trades if float(t["pnl"]) < 0]
        breakevens = [t for t in trades if float(t["pnl"]) == 0]

        total = len(trades)
        decisive_trades = len(winners) + len(losers)
        win_rate = (len(winners) / decisive_trades * 100) if decisive_trades > 0 else 0.0
        avg_winner = (sum(float(t["pnl"]) for t in winners) / len(winners)) if winners else 0.0
        avg_loser = (sum(float(t["pnl"]) for t in losers) / len(losers)) if losers else 0.0
        max_win = max((float(t["pnl"]) for t in winners), default=0.0)
        max_loss = min((float(t["pnl"]) for t in losers), default=0.0)

        gross_profit = sum(float(t["pnl"]) for t in winners)
        gross_loss = abs(sum(float(t["pnl"]) for t in losers))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        expectancy = (win_rate / 100 * avg_winner) + ((1 - win_rate / 100) * avg_loser)

        # Hold time
        hold_minutes_list = []
        for t in trades:
            try:
                if t["entry_time"] and t["exit_time"]:
                    entry = datetime.fromisoformat(str(t["entry_time"]))
                    exit_ = datetime.fromisoformat(str(t["exit_time"]))
                    diff = (exit_ - entry).total_seconds() / 60.0
                    if diff >= 0:
                        hold_minutes_list.append(diff)
            except Exception:
                pass
        avg_hold_minutes = (sum(hold_minutes_list) / len(hold_minutes_list)) if hold_minutes_list else 0.0

        # By close reason
        reason_map: dict = {}
        for t in trades:
            reason = t.get("close_reason") or "unknown"
            pnl = float(t["pnl"])
            if reason not in reason_map:
                reason_map[reason] = {"count": 0, "total_pnl": 0.0, "wins": 0}
            reason_map[reason]["count"] += 1
            reason_map[reason]["total_pnl"] += pnl
            if pnl > 0:
                reason_map[reason]["wins"] += 1
        by_close_reason = {}
        for reason, v in reason_map.items():
            by_close_reason[reason] = {
                "count": v["count"],
                "total_pnl": round(v["total_pnl"], 2),
                "avg_pnl": round(v["total_pnl"] / v["count"], 2) if v["count"] else 0.0,
                "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0.0,
            }

        # By day of week
        day_map: dict = {}
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for t in trades:
            try:
                dt = datetime.fromisoformat(str(t["entry_time"]))
                day = day_names[dt.weekday()]
            except Exception:
                day = "Unknown"
            pnl = float(t["pnl"])
            if day not in day_map:
                day_map[day] = {"count": 0, "total_pnl": 0.0, "wins": 0}
            day_map[day]["count"] += 1
            day_map[day]["total_pnl"] += pnl
            if pnl > 0:
                day_map[day]["wins"] += 1
        by_day_of_week = {}
        for day in day_names:
            if day in day_map:
                v = day_map[day]
                by_day_of_week[day] = {
                    "count": v["count"],
                    "total_pnl": round(v["total_pnl"], 2),
                    "avg_pnl": round(v["total_pnl"] / v["count"], 2) if v["count"] else 0.0,
                    "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0.0,
                }

        # By hour
        hour_map: dict = {}
        for t in trades:
            try:
                dt = datetime.fromisoformat(str(t["entry_time"]))
                # Convert UTC to ET (approximate: UTC-5)
                hour = str(dt.hour)
            except Exception:
                hour = "unknown"
            pnl = float(t["pnl"])
            if hour not in hour_map:
                hour_map[hour] = {"count": 0, "total_pnl": 0.0, "wins": 0}
            hour_map[hour]["count"] += 1
            hour_map[hour]["total_pnl"] += pnl
            if pnl > 0:
                hour_map[hour]["wins"] += 1
        by_hour = {}
        for hour in sorted(hour_map.keys(), key=lambda x: int(x) if x.isdigit() else 99):
            v = hour_map[hour]
            by_hour[hour] = {
                "count": v["count"],
                "total_pnl": round(v["total_pnl"], 2),
                "avg_pnl": round(v["total_pnl"] / v["count"], 2) if v["count"] else 0.0,
                "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0.0,
            }

        # Streak calculation
        current_streak = 0
        streak_type = None
        best_win = 0
        best_loss = 0
        cur_win = 0
        cur_loss = 0
        for t in trades:
            pnl = float(t["pnl"])
            if pnl > 0:
                cur_win += 1
                cur_loss = 0
                best_win = max(best_win, cur_win)
            else:
                cur_loss += 1
                cur_win = 0
                best_loss = max(best_loss, cur_loss)

        # Final streak
        last_pnl = float(trades[-1]["pnl"]) if trades else 0
        if last_pnl > 0:
            current_streak = cur_win
            streak_type = "win"
        else:
            current_streak = cur_loss
            streak_type = "loss"

        return {
            "total_trades": total,
            "breakeven_count": len(breakevens),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "avg_winner": round(avg_winner, 2),
            "avg_loser": round(avg_loser, 2),
            "expectancy": round(expectancy, 2),
            "avg_hold_minutes": round(avg_hold_minutes, 1),
            "max_win": round(max_win, 2),
            "max_loss": round(max_loss, 2),
            "by_close_reason": by_close_reason,
            "by_day_of_week": by_day_of_week,
            "by_hour": by_hour,
            "streak": {
                "current": current_streak,
                "type": streak_type,
                "best_win_streak": best_win,
                "best_loss_streak": best_loss,
            },
        }

    # ------------------------------------------------------------------ #
    # Simulator State Persistence                                          #
    # ------------------------------------------------------------------ #

    async def get_simulator_state(self, key: str) -> Optional[float]:
        """Read a persisted simulator state value by key."""
        rows = await self._fetch_all_dict(
            "SELECT value FROM simulator_state WHERE key = ? LIMIT 1", (key,)
        )
        if rows:
            return float(rows[0]["value"])
        return None

    async def set_simulator_state(self, key: str, value: float) -> None:
        """Upsert a simulator state value."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO simulator_state (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value),
            )
            await conn.commit()

    async def _fetch_trades(self, query: str, params: tuple = ()) -> List[Trade]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        return [self._row_to_trade(row) for row in rows]

    async def _fetch_all_dict(self, query: str, params: tuple = ()) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _row_to_trade(row: aiosqlite.Row) -> Trade:
        return Trade(
            id=int(row["id"]),
            scanner_hit_id=int(row["scanner_hit_id"]) if row["scanner_hit_id"] is not None else None,
            ticker=str(row["ticker"]),
            side=str(row["side"]),
            risk_profile=str(row["risk_profile"]),
            entry_price=float(row["entry_price"]),
            entry_time=datetime.fromisoformat(str(row["entry_time"])),
            exit_price=float(row["exit_price"]) if row["exit_price"] is not None else None,
            exit_time=datetime.fromisoformat(str(row["exit_time"])) if row["exit_time"] else None,
            stop_loss=float(row["stop_loss"]),
            take_profit=float(row["take_profit"]) if row["take_profit"] is not None else None,
            trailing_stop_pct=float(row["trailing_stop_pct"]) if row["trailing_stop_pct"] is not None else None,
            quantity=int(row["quantity"]),
            status=str(row["status"]),
            pnl=float(row["pnl"]) if row["pnl"] is not None else None,
            pnl_percent=float(row["pnl_percent"]) if row["pnl_percent"] is not None else None,
            alpaca_order_id=str(row["alpaca_order_id"]) if row["alpaca_order_id"] else None,
            broker_order_state=str(row["broker_order_state"]) if row["broker_order_state"] else None,
            broker_client_order_id=str(row["broker_client_order_id"]) if row["broker_client_order_id"] else None,
            broker_filled_qty=int(row["broker_filled_qty"]) if row["broker_filled_qty"] is not None else None,
            broker_filled_avg_price=float(row["broker_filled_avg_price"]) if row["broker_filled_avg_price"] is not None else None,
            broker_updated_at=datetime.fromisoformat(str(row["broker_updated_at"])) if row["broker_updated_at"] else None,
            close_reason=str(row["close_reason"]) if row["close_reason"] else None,
            max_price_seen=float(row["max_price_seen"] if row["max_price_seen"] is not None else row["entry_price"]),
        )
