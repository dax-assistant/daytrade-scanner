from __future__ import annotations

import aiosqlite

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS scanner_hits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        price REAL NOT NULL,
        gap_percent REAL NOT NULL,
        volume INTEGER NOT NULL,
        avg_volume_20d REAL NOT NULL,
        relative_volume REAL NOT NULL,
        float_shares INTEGER,
        news_headline TEXT,
        news_source TEXT,
        news_url TEXT,
        news_published_at TEXT,
        pillar_price BOOLEAN NOT NULL,
        pillar_gap BOOLEAN NOT NULL,
        pillar_relvol BOOLEAN NOT NULL,
        pillar_float BOOLEAN NOT NULL,
        pillar_news BOOLEAN NOT NULL,
        pillar_score INTEGER NOT NULL,
        session_label TEXT NOT NULL,
        scanned_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hits_ticker ON scanner_hits(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_hits_scanned_at ON scanner_hits(scanned_at)",
    "CREATE INDEX IF NOT EXISTS idx_hits_score ON scanner_hits(pillar_score)",
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scanner_hit_id INTEGER REFERENCES scanner_hits(id),
        ticker TEXT NOT NULL,
        status TEXT NOT NULL,
        telegram_message_id TEXT,
        sent_at TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scanner_hit_id INTEGER REFERENCES scanner_hits(id),
        ticker TEXT NOT NULL,
        side TEXT NOT NULL DEFAULT 'buy',
        risk_profile TEXT NOT NULL,
        entry_price REAL NOT NULL,
        entry_time TEXT NOT NULL,
        exit_price REAL,
        exit_time TEXT,
        stop_loss REAL NOT NULL,
        take_profit REAL,
        trailing_stop_pct REAL,
        quantity INTEGER NOT NULL,
        status TEXT NOT NULL,
        pnl REAL,
        pnl_percent REAL,
        alpaca_order_id TEXT,
        broker_order_state TEXT,
        broker_client_order_id TEXT,
        broker_filled_qty INTEGER,
        broker_filled_avg_price REAL,
        broker_updated_at TEXT,
        close_reason TEXT,
        max_price_seen REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)",
    "CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)",
    """
    CREATE TABLE IF NOT EXISTS daily_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        total_trades INTEGER NOT NULL DEFAULT 0,
        winning_trades INTEGER NOT NULL DEFAULT 0,
        losing_trades INTEGER NOT NULL DEFAULT 0,
        total_pnl REAL NOT NULL DEFAULT 0.0,
        win_rate REAL NOT NULL DEFAULT 0.0,
        largest_win REAL,
        largest_loss REAL,
        scanner_hits_count INTEGER NOT NULL DEFAULT 0,
        alerts_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # Custom watchlist (persisted, separate from scanner candidates)
    """
    CREATE TABLE IF NOT EXISTS watchlist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL UNIQUE,
        notes TEXT NOT NULL DEFAULT '',
        alert_threshold_pct REAL NOT NULL DEFAULT 5.0,
        added_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON watchlist_items(ticker)",
    # Trade Journal
    """
    CREATE TABLE IF NOT EXISTS trade_journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER REFERENCES trades(id),
        setup_type TEXT,
        emotional_state TEXT,
        grade TEXT,
        notes TEXT,
        mistakes TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_trade_id ON trade_journal(trade_id)",
    # Simulator state persistence — stores running current_balance across restarts
    """
    CREATE TABLE IF NOT EXISTS simulator_state (
        key TEXT PRIMARY KEY,
        value REAL NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
]


TRADE_COLUMN_MIGRATIONS = [
    ("broker_order_state", "ALTER TABLE trades ADD COLUMN broker_order_state TEXT"),
    ("broker_client_order_id", "ALTER TABLE trades ADD COLUMN broker_client_order_id TEXT"),
    ("broker_filled_qty", "ALTER TABLE trades ADD COLUMN broker_filled_qty INTEGER"),
    ("broker_filled_avg_price", "ALTER TABLE trades ADD COLUMN broker_filled_avg_price REAL"),
    ("broker_updated_at", "ALTER TABLE trades ADD COLUMN broker_updated_at TEXT"),
]


async def run_migrations(conn: aiosqlite.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        await conn.execute(statement)

    async with conn.execute("PRAGMA table_info(trades)") as cursor:
        rows = await cursor.fetchall()
    existing_columns = {str(row[1]) for row in rows}
    for column_name, statement in TRADE_COLUMN_MIGRATIONS:
        if column_name not in existing_columns:
            await conn.execute(statement)

    await conn.commit()
