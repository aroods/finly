import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "portfolio.db"
print("ApiCache using DB:", DB_PATH)

class CacheStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                timestamp REAL
            )
        """)
        conn.commit()
        conn.close()

    def get(self, key, max_age_seconds):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value, timestamp FROM api_cache WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        value, ts = row
        if time.time() - ts > max_age_seconds:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None

    def set(self, key, value):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO api_cache (key, value, timestamp)
            VALUES (?, ?, ?)
        """, (key, json.dumps(value), time.time()))
        conn.commit()
        conn.close()

    def stats(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM api_cache")
        total, oldest, newest = c.fetchone()
        print(c)
        conn.close()
        return {
            "total_items": total or 0,
            "oldest": datetime.fromtimestamp(oldest).strftime("%Y-%m-%d %H:%M:%S"),
            "newest": datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def clear_all(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM api_cache")
        conn.commit()
        conn.close()

    def clear_prefix(self, prefix):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM api_cache WHERE key LIKE ?", (f"{prefix}%",))
        conn.commit()
        conn.close()


# Create the global cache instance
CACHE = CacheStore()
