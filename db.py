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
        UNIQUE(asset, ex_date, source)
    )
    ''')

    # Add any other tables (snapshots, etc.) here
    db.commit()
    db.close()
