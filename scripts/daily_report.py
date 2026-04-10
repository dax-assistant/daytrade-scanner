#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from zoneinfo import ZoneInfo

BASE_URL = "http://10.1.1.158:8081"
TELEGRAM_TARGET = "8474445926"
TIMEZONE = ZoneInfo("America/New_York")
DB_PATH = Path(__file__).resolve().parent.parent / "scanner.db"


@dataclass
class FetchResult:
    ok: bool
    status: int | None
    data: dict[str, Any] | None
    error: str | None = None


def fetch_json(path: str, timeout: int = 8) -> FetchResult:
    url = f"{BASE_URL}{path}"
    req = request.Request(url, headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return FetchResult(ok=True, status=getattr(resp, "status", 200), data=payload)
    except error.HTTPError as exc:
        body = None
        try:
            raw = exc.read().decode("utf-8")
            body = json.loads(raw) if raw else None
        except Exception:
            body = None
        return FetchResult(ok=False, status=exc.code, data=body, error=str(exc))
    except Exception as exc:
        return FetchResult(ok=False, status=None, data=None, error=str(exc))


def send_telegram(message: str) -> None:
    subprocess.run(
        [
            "openclaw",
            "message",
            "send",
            "--channel",
            "telegram",
            "--target",
            TELEGRAM_TARGET,
            "-m",
            message,
        ],
        check=True,
    )


def fmt_money(value: float, signed: bool = False) -> str:
    if signed:
        return f"{value:+,.2f}"
    return f"{value:,.2f}"


def fmt_num(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        if text.endswith("Z"):
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TIMEZONE)
    return dt.astimezone(TIMEZONE)


def is_today_trade(item: dict[str, Any], report_date: datetime.date) -> bool:
    for key in ("exit_time", "entry_time", "created_at"):
        dt = parse_dt(item.get(key))
        if dt and dt.date() == report_date:
            return True
    return False


def build_today_stats(items: list[dict[str, Any]], report_date: datetime.date) -> dict[str, Any]:
    today_items = [item for item in items if is_today_trade(item, report_date)]
    winners = [item for item in today_items if fmt_num(item.get("pnl")) > 0]
    losers = [item for item in today_items if fmt_num(item.get("pnl")) < 0]
    breakevens = [item for item in today_items if fmt_num(item.get("pnl")) == 0]

    decisive = len(winners) + len(losers)
    best = max(today_items, key=lambda item: fmt_num(item.get("pnl")), default=None)
    worst = min(today_items, key=lambda item: fmt_num(item.get("pnl")), default=None)

    return {
        "items": today_items,
        "total_trades": len(today_items),
        "winners": len(winners),
        "losers": len(losers),
        "breakevens": len(breakevens),
        "total_pnl": round(sum(fmt_num(item.get("pnl")) for item in today_items), 2),
        "win_rate": round((len(winners) / decisive * 100.0), 1) if decisive else 0.0,
        "best": best,
        "worst": worst,
    }


def alltime_total_pnl(summary: dict[str, Any]) -> float:
    by_reason = summary.get("by_close_reason") or {}
    if by_reason:
        return round(sum(fmt_num(item.get("total_pnl")) for item in by_reason.values()), 2)
    return 0.0


def prettify_reason(reason: str | None) -> str:
    if not reason:
        return "N/A"
    return str(reason).replace("_", " ").strip().title()


def top_setup(summary: dict[str, Any]) -> str:
    by_reason = summary.get("by_close_reason") or {}
    if not by_reason:
        return "N/A"
    reason, data = max(by_reason.items(), key=lambda pair: fmt_num((pair[1] or {}).get("total_pnl")))
    return f"{prettify_reason(reason)} (${fmt_money(fmt_num((data or {}).get('total_pnl')))} )".replace(" )", ")")


def grades_from_api(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result = {
        "A": {"count": 0, "avg_pnl": 0.0},
        "B": {"count": 0, "avg_pnl": 0.0},
        "C": {"count": 0, "avg_pnl": 0.0},
        "D": {"count": 0, "avg_pnl": 0.0},
        "ungraded": {"count": 0, "avg_pnl": 0.0},
    }
    for item in (payload or {}).get("items", []):
        grade = str(item.get("grade") or "ungraded")
        if grade not in result:
            continue
        result[grade] = {
            "count": int(item.get("count") or 0),
            "avg_pnl": round(fmt_num(item.get("avg_pnl")), 2),
        }
    return result


def grades_from_db() -> dict[str, dict[str, Any]]:
    result = {
        "A": {"count": 0, "avg_pnl": 0.0},
        "B": {"count": 0, "avg_pnl": 0.0},
        "C": {"count": 0, "avg_pnl": 0.0},
        "D": {"count": 0, "avg_pnl": 0.0},
        "ungraded": {"count": 0, "avg_pnl": 0.0},
    }
    if not DB_PATH.exists():
        return result

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(j.grade, ''), 'ungraded') AS grade,
                   COUNT(*) AS count,
                   AVG(t.pnl) AS avg_pnl
            FROM trades t
            LEFT JOIN trade_journal j ON j.trade_id = t.id
            WHERE t.status != 'open' AND t.pnl IS NOT NULL
            GROUP BY COALESCE(NULLIF(j.grade, ''), 'ungraded')
            """
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        grade = row["grade"]
        if grade not in result:
            continue
        result[grade] = {
            "count": int(row["count"] or 0),
            "avg_pnl": round(fmt_num(row["avg_pnl"]), 2),
        }
    return result


def build_report(
    report_date: datetime.date,
    today_summary: dict[str, Any],
    alltime_summary: dict[str, Any],
    grade_data: dict[str, dict[str, Any]],
) -> str:
    best = today_summary.get("best") or {}
    worst = today_summary.get("worst") or {}
    return "\n".join(
        [
            f"📊 Daily Trading Report — {report_date.strftime('%a %b %-d')}",
            "",
            "TODAY",
            (
                f"• Trades: {today_summary['total_trades']} "
                f"({today_summary['winners']}W / {today_summary['losers']}L / {today_summary['breakevens']} BE)"
            ),
            f"• P&L: ${fmt_money(today_summary['total_pnl'], signed=True)}",
            f"• Win Rate: {today_summary['win_rate']:.1f}%",
            (
                f"• Best: ${fmt_money(fmt_num(best.get('pnl')), signed=True)} ({best.get('ticker') or 'N/A'}) "
                f"| Worst: ${fmt_money(fmt_num(worst.get('pnl')), signed=True)} ({worst.get('ticker') or 'N/A'})"
            ),
            "",
            "ALL-TIME",
            (
                f"• Total P&L: ${fmt_money(alltime_total_pnl(alltime_summary), signed=True)} "
                f"across {int(alltime_summary.get('total_trades') or 0)} trades"
            ),
            (
                f"• Win Rate: {fmt_num(alltime_summary.get('win_rate')):.1f}% "
                f"| Profit Factor: {fmt_num(alltime_summary.get('profit_factor')):.2f}"
            ),
            f"• Expectancy: ${fmt_money(fmt_num(alltime_summary.get('expectancy')), signed=True)}/trade",
            "",
            "GRADES (all-time)",
            f"• A: {grade_data['A']['count']} trades, avg ${fmt_money(grade_data['A']['avg_pnl'], signed=True)}",
            f"• B: {grade_data['B']['count']} trades, avg ${fmt_money(grade_data['B']['avg_pnl'], signed=True)}",
            f"• C: {grade_data['C']['count']} trades, avg ${fmt_money(grade_data['C']['avg_pnl'], signed=True)}",
            f"• D: {grade_data['D']['count']} trades, avg ${fmt_money(grade_data['D']['avg_pnl'], signed=True)}",
            f"• Ungraded: {grade_data['ungraded']['count']}",
            "",
            f"BEST SETUP: {top_setup(alltime_summary)}",
        ]
    )


def main() -> int:
    report_date = (datetime.now(TIMEZONE) - timedelta(days=1)).date()  # prior trading day

    today_summary_result = fetch_json("/api/analytics/summary?" + parse.urlencode({"range": "today"}))
    alltime_summary_result = fetch_json("/api/analytics/summary?" + parse.urlencode({"range": "alltime"}))
    grades_result = fetch_json("/api/analytics/grades?" + parse.urlencode({"range": "alltime"}))
    history_result = fetch_json("/api/simulator/history")

    core_failures = [
        result
        for result in (today_summary_result, alltime_summary_result, history_result)
        if not result.ok
    ]
    if core_failures:
        send_telegram("Scanner offline, no report available")
        return 0

    history_items = list((history_result.data or {}).get("items", []))
    today_stats = build_today_stats(history_items, report_date)

    today_total_from_api = int(((today_summary_result.data or {}).get("total_trades") or 0))
    if today_stats["total_trades"] == 0:
        send_telegram(f"No trades {report_date.strftime('%a %b %-d')} — scanner ran but no setups triggered.")
        return 0

    grade_data = grades_from_api(grades_result.data) if grades_result.ok else grades_from_db()
    report = build_report(report_date, today_stats, alltime_summary_result.data or {}, grade_data)
    send_telegram(report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Failed to send Telegram message: {exc}", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except Exception as exc:
        try:
            send_telegram("Scanner offline, no report available")
        except Exception:
            print(f"Unhandled error: {exc}", file=sys.stderr)
            raise
        raise SystemExit(0)
