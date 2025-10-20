import sqlite3
from pathlib import Path

from flask import g

DB_PATH = Path(__file__).resolve().parent / "portfolio.db"


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    # Transactions table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        asset TEXT NOT NULL,
        type TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL NOT NULL,
        currency TEXT NOT NULL,
        category TEXT NOT NULL
    )
    ''')

    # Cash deposits table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS cash_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        amount REAL NOT NULL,
        delta REAL NOT NULL,
        note TEXT
    )
    ''')

    # Bonds table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bonds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series TEXT NOT NULL,
        bond_type TEXT NOT NULL,
        purchase_date TEXT NOT NULL,
        maturity_date TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        face_value REAL NOT NULL,
        annual_rate REAL NOT NULL,
        margin REAL DEFAULT 0,
        index_rate REAL DEFAULT 0,
        capitalization INTEGER NOT NULL DEFAULT 1,
        notes TEXT
    )
    ''')

    # Dividends table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS dividends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset TEXT NOT NULL,
        ex_date TEXT,
        pay_date TEXT,
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        shares REAL DEFAULT 0,
        gross_value REAL DEFAULT 0,
        net_value REAL DEFAULT 0,
        source TEXT,
        notes TEXT,
        status TEXT NOT NULL DEFAULT 'synced',
        UNIQUE(asset, ex_date, source)
    )
    ''')

    # Symbol mappings table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS symbol_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        internal_symbol TEXT NOT NULL,
        provider TEXT NOT NULL,
        provider_symbol TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT,
        UNIQUE(internal_symbol, provider, provider_symbol)
    )
    ''')

    # Ensure dividends.status column exists
    cur.execute("PRAGMA table_info(dividends)")
    dividend_columns = {row[1] for row in cur.fetchall()}
    if "status" not in dividend_columns:
        cur.execute("ALTER TABLE dividends ADD COLUMN status TEXT NOT NULL DEFAULT 'synced'")

    # Indexes for faster lookups
    cur.execute('''
    CREATE INDEX IF NOT EXISTS idx_symbol_mappings_lookup
    ON symbol_mappings (internal_symbol, provider, active, priority)
    ''')

    # Add any other tables (snapshots, etc.) here
    db.commit()
    db.close()
