#!/usr/bin/env python3
"""
Clear cached Yahoo Finance price history entries that were stored in GBX (pence)
so they are repopulated in GBP using the updated logic.
"""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parent.parent / "portfolio.db"


def collect_gbp_assets(conn: sqlite3.Connection) -> list[str]:
    query = """
        SELECT DISTINCT asset
        FROM transactions
        WHERE asset IS NOT NULL
          AND TRIM(asset) != ''
          AND UPPER(currency) IN ('GBP', 'GBX', 'GBp')
    """
    assets = sorted({row[0].strip() for row in conn.execute(query) if row[0]})
    return assets


def purge_cache_for_asset(conn: sqlite3.Connection, asset: str) -> tuple[int, int]:
    price_key = f"price:{asset}"
    history_pattern = f"history:{asset}:%"

    cur = conn.cursor()
    cur.execute("DELETE FROM api_cache WHERE key = ?", (price_key,))
    price_deleted = cur.rowcount

    cur.execute("DELETE FROM api_cache WHERE key LIKE ?", (history_pattern,))
    history_deleted = cur.rowcount

    return price_deleted or 0, history_deleted or 0


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        assets = collect_gbp_assets(conn)
        if not assets:
            print("No GBP/GBX assets found in transactions table.")
            return

        total_price = 0
        total_history = 0

        for asset in assets:
            price_deleted, history_deleted = purge_cache_for_asset(conn, asset)
            total_price += price_deleted
            total_history += history_deleted
            if price_deleted or history_deleted:
                print(
                    f"{asset}: removed {history_deleted} history entries "
                    f"and {price_deleted} price entries"
                )

        conn.commit()
        print(
            f"Done. Removed {total_history} history rows and "
            f"{total_price} price rows across {len(assets)} assets."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
