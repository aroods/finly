import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "portfolio.db"


class CacheStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self._ensure_table()

    def _ensure_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    timestamp REAL
                )
                """
            )

    def get(self, key, max_age_seconds):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT value, timestamp FROM api_cache WHERE key = ?", (key,))
            row = cur.fetchone()
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO api_cache (key, value, timestamp)
                VALUES (?, ?, ?)
                """,
                (key, json.dumps(value), time.time()),
            )

    def stats(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM api_cache")
            total, oldest, newest = cur.fetchone()
        return {
            "total_items": total or 0,
            "oldest": datetime.fromtimestamp(oldest).strftime("%Y-%m-%d %H:%M:%S") if oldest else None,
            "newest": datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M:%S") if newest else None,
        }

    def clear_all(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM api_cache")

    def clear_prefix(self, prefix):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM api_cache WHERE key LIKE ?", (f"{prefix}%",))


# Create the global cache instance
CACHE = CacheStore()
