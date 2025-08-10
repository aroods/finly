import sqlite3
from flask import g

DB_PATH = "portfolio.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
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
    # cur.execute('''
    # DROP TABLE api_cache;  ''')

    # cur.execute('''
    # ALTER TABLE cash_deposits RENAME COLUMN date TO created_at;  ''')

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

    # Add any other tables (snapshots, etc.) here
    db.commit()
    db.close()
