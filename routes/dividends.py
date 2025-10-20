import time
from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db
from cache_store import CACHE
from helpers import get_current_prices
from services.twelvedata import fetch_dividends as td_fetch_dividends
from services.eod import fetch_dividends as eod_fetch_dividends

dividends_bp = Blueprint("dividends", __name__, url_prefix="/dividends")
DIVIDEND_TTL = 12 * 60 * 60  # 12 hours
TAX_RATE = 0.19

SYMBOL_EOD_MAP = {
    "INTC": "US.INTC",
    "AAPL": "US.AAPL",
    "MSFT": "US.MSFT",
    "NWG.L": "LSE.NWG",
    "PKN.WA": "WSE.PKN",
    "PZU.WA": "WSE.PZU",
}


def get_portfolio_assets():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT asset FROM transactions WHERE asset IS NOT NULL AND asset != ''")
    return [row[0] for row in cur.fetchall()]


def normalize_eod_symbol(asset: str) -> str:
    return SYMBOL_EOD_MAP.get(asset, f"US.{asset}" if "." not in asset else asset)


def parse_twelve_dividends(asset: str, data: dict):
    results = []
    if not data:
        return results
    items = data.get("dividends") or data.get("data")
    if not items:
        return results
    for item in items:
        amount = item.get("amount") or item.get("value")
        if amount is None:
            continue
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            continue
        ex_date = item.get("ex_dividend_date") or item.get("date")
        pay_date = item.get("payment_date") or item.get("pay_date")
        currency = item.get("currency") or data.get("currency") or "USD"
        results.append({
            "asset": asset,
            "ex_date": ex_date,
            "pay_date": pay_date,
            "amount": amount,
            "currency": currency,
            "source": "twelvedata",
        })
    return results


def parse_eod_dividends(asset: str, data):
    results = []
    if not data:
        return results
    items = data if isinstance(data, list) else data.get("dividends") or []
    for item in items:
        amount = item.get("value") or item.get("amount")
        if amount is None:
            continue
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            continue
        ex_date = item.get("date") or item.get("exDate")
        pay_date = item.get("paymentDate") or item.get("payDate")
        currency = item.get("currency") or "USD"
        results.append({
            "asset": asset,
            "ex_date": ex_date,
            "pay_date": pay_date,
            "amount": amount,
            "currency": currency,
            "source": "eod",
        })
    return results


def fetch_dividends_for_asset(asset: str):
    records = []
    try:
        td_data = td_fetch_dividends(asset)
        records.extend(parse_twelve_dividends(asset, td_data))
    except Exception as exc:
        print(f"Twelve Data dividend fetch failed for {asset}: {exc}")

    try:
        eod_symbol = normalize_eod_symbol(asset)
        eod_data = eod_fetch_dividends(eod_symbol)
        records.extend(parse_eod_dividends(asset, eod_data))
    except Exception as exc:
        print(f"EOD dividend fetch failed for {asset}: {exc}")

    return records


def upsert_dividend(record):
    if not record.get("ex_date"):
        return
    db = get_db()
    cur = db.cursor()
    net_per_share = record["amount"] * (1 - TAX_RATE)
    cur.execute(
        """
        INSERT INTO dividends (asset, ex_date, pay_date, amount, currency, gross_value, net_value, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset, ex_date, source) DO UPDATE SET
            pay_date=excluded.pay_date,
            amount=excluded.amount,
            currency=excluded.currency,
            gross_value=excluded.gross_value,
            net_value=excluded.net_value
        """,
        (
            record["asset"],
            record["ex_date"],
            record.get("pay_date"),
            record["amount"],
            record.get("currency", "USD"),
            record["amount"],
            net_per_share,
            record.get("source", "api"),
        ),
    )
    db.commit()


def refresh_dividends(force=False):
    last_sync = CACHE.get("dividends:last_sync", DIVIDEND_TTL)
    if last_sync and not force:
        return 0
    assets = get_portfolio_assets()
    new_entries = 0
    for asset in assets:
        for record in fetch_dividends_for_asset(asset):
            upsert_dividend(record)
            new_entries += 1
    CACHE.set("dividends:last_sync", time.time())
    return new_entries


def load_dividends():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, asset, ex_date, pay_date, amount, currency, shares, gross_value, net_value, source, notes
        FROM dividends
        ORDER BY COALESCE(pay_date, ex_date) DESC
        """
    )
    rows = cur.fetchall()
    return rows


def enrich_with_market_data(dividends):
    assets = {row["asset"] for row in dividends}
    price_map = {}
    if assets:
        try:
            price_map, _, _ = get_current_prices(list(assets))
        except Exception as exc:
            print(f"Price lookup failed for dividends view: {exc}")
    today = date.today()
    enriched = []
    for row in dividends:
        ex_date = row["ex_date"]
        pay_date = row["pay_date"]
        try:
            ex_date_obj = datetime.fromisoformat(ex_date).date() if ex_date else None
        except ValueError:
            ex_date_obj = None
        try:
            pay_date_obj = datetime.fromisoformat(pay_date).date() if pay_date else None
        except ValueError:
            pay_date_obj = None

        net_per_share = row["net_value"] if row["net_value"] else row["amount"] * (1 - TAX_RATE)
        shares = row["shares"] or 0
        total_net = net_per_share * shares if shares else None
        price = price_map.get(row["asset"]) if price_map else None
        yield_pct = (row["amount"] / price * 100) if price else None
        enriched.append({
            "id": row["id"],
            "asset": row["asset"],
            "ex_date": ex_date_obj,
            "pay_date": pay_date_obj,
            "amount": row["amount"],
            "currency": row["currency"],
            "shares": shares,
            "gross_value": row["gross_value"],
            "net_per_share": net_per_share,
            "total_net": total_net,
            "source": row["source"],
            "notes": row["notes"],
            "price": price,
            "yield_pct": yield_pct,
            "upcoming": pay_date_obj and pay_date_obj >= today,
        })
    return enriched


@dividends_bp.route("/", methods=["GET", "POST"])
def list_dividends():
    if request.method == "POST":
        added = refresh_dividends(force=True)
        flash(f"Dividend data refreshed ({added} entries processed)", "success")
        return redirect(url_for("dividends.list_dividends"))

    refresh_dividends(force=False)
    dividends = enrich_with_market_data(load_dividends())
    today = date.today()
    upcoming = [d for d in dividends if d["upcoming"]]
    history = [d for d in dividends if not d["upcoming"]]

    total_net_upcoming = sum((d["total_net"] or 0) for d in upcoming)
    total_net_12m = sum((d["total_net"] or 0) for d in history if d["pay_date"] and (today - d["pay_date"]).days <= 365)

    return render_template(
        "dividends/list.html",
        upcoming=upcoming,
        history=history,
        total_net_upcoming=total_net_upcoming,
        total_net_12m=total_net_12m,
        tax_rate=TAX_RATE,
    )
