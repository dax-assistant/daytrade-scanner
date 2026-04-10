#!/usr/bin/env python3
"""
Backfill script: fix exit_price, pnl, pnl_percent for closed trades
where the bug left exit_price = entry_price.

The correct exit price is stored in max_price_seen.
Only touches trades where:
  - status != 'open'
  - exit_price = entry_price
  - max_price_seen IS NOT NULL
  - max_price_seen != entry_price
"""

import sqlite3
import shutil
from pathlib import Path

DB_PATH = Path("/Users/dax/.openclaw/workspace/daytrade-scanner/scanner.db")
BAK_PATH = DB_PATH.with_suffix(".db.bak")

# ── 1. Backup ──────────────────────────────────────────────────────────────
print(f"📦 Backing up database to {BAK_PATH} ...")
shutil.copy2(DB_PATH, BAK_PATH)
print(f"   ✅ Backup created ({BAK_PATH.stat().st_size:,} bytes)\n")

# ── 2. Connect & fetch affected rows ──────────────────────────────────────
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
cur = con.cursor()

cur.execute("""
    SELECT id, ticker, status, close_reason,
           entry_price, exit_price, max_price_seen, pnl, pnl_percent, quantity
    FROM trades
    WHERE status != 'open'
      AND exit_price = entry_price
      AND max_price_seen IS NOT NULL
      AND max_price_seen != entry_price
    ORDER BY id
""")
rows = cur.fetchall()

print(f"🔍 Found {len(rows)} trades to backfill:\n")
print(f"{'ID':>4}  {'Ticker':<6}  {'Close Reason':<14}  {'Entry':>8}  {'Old Exit':>8}  {'New Exit':>8}  {'Old PnL':>9}  {'New PnL':>9}  {'PnL%':>7}")
print("-" * 96)

updates = []
for r in rows:
    new_exit   = r["max_price_seen"]
    new_pnl    = (new_exit - r["entry_price"]) * r["quantity"]
    new_pnl_pct = ((new_exit - r["entry_price"]) / r["entry_price"]) * 100

    print(
        f"{r['id']:>4}  {r['ticker']:<6}  {r['close_reason'] or '':<14}  "
        f"{r['entry_price']:>8.4f}  {r['exit_price']:>8.4f}  {new_exit:>8.4f}  "
        f"{r['pnl']:>9.2f}  {new_pnl:>9.2f}  {new_pnl_pct:>7.2f}%"
    )
    updates.append((new_exit, new_pnl, new_pnl_pct, r["id"]))

# ── 3. Apply updates ───────────────────────────────────────────────────────
print(f"\n✍️  Applying {len(updates)} updates ...")
cur.executemany("""
    UPDATE trades
    SET exit_price  = ?,
        pnl         = ?,
        pnl_percent = ?,
        updated_at  = datetime('now')
    WHERE id = ?
""", updates)
con.commit()
con.close()
print(f"   ✅ Committed.\n")

# ── 4. Summary by close_reason ─────────────────────────────────────────────
con2 = sqlite3.connect(DB_PATH)
con2.row_factory = sqlite3.Row
cur2 = con2.cursor()

cur2.execute("""
    SELECT close_reason,
           COUNT(*)          AS trades,
           SUM(pnl)          AS total_pnl,
           AVG(pnl)          AS avg_pnl,
           AVG(pnl_percent)  AS avg_pnl_pct
    FROM trades
    WHERE status != 'open'
    GROUP BY close_reason
    ORDER BY total_pnl DESC
""")
summary = cur2.fetchall()
con2.close()

print("📊 Post-backfill P&L summary by close_reason:\n")
print(f"{'Close Reason':<16}  {'Trades':>6}  {'Total PnL':>11}  {'Avg PnL':>9}  {'Avg PnL%':>9}")
print("-" * 58)
grand_trades = grand_pnl = 0
for s in summary:
    reason      = s["close_reason"] or "(none)"
    total_pnl   = s["total_pnl"] or 0.0
    avg_pnl     = s["avg_pnl"] or 0.0
    avg_pnl_pct = s["avg_pnl_pct"] or 0.0
    print(
        f"{reason:<16}  {s['trades']:>6}  ${total_pnl:>10.2f}  ${avg_pnl:>8.2f}  {avg_pnl_pct:>8.2f}%"
    )
    grand_trades += s["trades"]
    grand_pnl    += total_pnl

print("-" * 58)
print(f"{'TOTAL':<16}  {grand_trades:>6}  ${grand_pnl:>10.2f}")
print("\n✅ Backfill complete.")
