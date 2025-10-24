from __future__ import annotations
import time
import logging
from collections import defaultdict
from datetime import date, datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db
from cache_store import CACHE
from helpers import get_current_prices
from services.twelvedata import fetch_dividends as td_fetch_dividends
from symbol_utils import build_twelvedata_candidates

dividends_bp = Blueprint("dividends", __name__, url_prefix="/dividends")
DIVIDEND_TTL = 12 * 60 * 60  # 12 hours
TAX_RATE = 0.19

LOGGER = logging.getLogger(__name__)

def get_portfolio_assets():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT asset FROM transactions WHERE asset IS NOT NULL AND asset != ''")
    return [row[0] for row in cur.fetchall()]

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
            "shares": None,
        })
    return results



def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return None

def _holdings_on_date(transactions, target_date, inclusive=True):
    if target_date is None:
        return None
    net = 0.0
    for tx_date, tx_type, qty in transactions:
        if tx_date > target_date or (tx_date == target_date and not inclusive):
            break
        if tx_type == 'buy':
            net += qty
        elif tx_type == 'sell':
            net -= qty
    if net < 0:
        net = 0.0
    return round(net, 6)

def _sync_dividend_shares(dividends):
    if not dividends:
        return {}

    assets = {row['asset'] for row in dividends if row['asset']}
    if not assets:
        return {}

    placeholders = ','.join('?' for _ in assets)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"""
        SELECT asset, date, type, quantity
        FROM transactions
        WHERE asset IN ({placeholders})
        ORDER BY date ASC, id ASC
        """,
        list(assets),
    )
    tx_map = defaultdict(list)
    for tx in cur.fetchall():
        tx_date = _parse_date(tx['date'])
        if not tx_date:
            continue
        tx_type = (tx['type'] or '').lower()
        qty_raw = tx['quantity']
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            qty = 0.0
        tx_map[tx['asset']].append((tx_date, tx_type, qty))

    share_map = {}
    updates = []
    for row in dividends:
        asset = row['asset']
        if not asset:
            continue
        status = (row['status'] or 'synced') if 'status' in row.keys() else 'synced'
        if status not in ('synced', 'manual'):
            continue
        ex_date_obj = _parse_date(row['ex_date'])
        pay_date_obj = _parse_date(row['pay_date'])
        snapshot_date = ex_date_obj or pay_date_obj
        if not snapshot_date:
            continue
        inclusive = ex_date_obj is None
        shares = _holdings_on_date(tx_map.get(asset, []), snapshot_date, inclusive=inclusive)
        if shares is None:
            continue
        existing = row['shares'] or 0.0
        if shares <= 1e-9 and existing > 0:
            # keep manually entered value if the auto calculation returns zero
            continue
        share_map[row['id']] = shares
        if abs(existing - shares) > 1e-6:
            updates.append((shares, row['id']))

    if updates:
        cur.executemany('UPDATE dividends SET shares=? WHERE id=?', updates)
        db.commit()

    return share_map

def fetch_dividends_for_asset(asset: str):
    records: list[dict] = []

    td_candidates = build_twelvedata_candidates(asset)
    LOGGER.debug("Twelve Data candidates for %s: %s", asset, td_candidates)
    td_errors = []
    for symbol in td_candidates:
        try:
            td_data = td_fetch_dividends(symbol)
        except Exception as exc:
            LOGGER.warning("Twelve Data fetch error for %s (%s): %s", asset, symbol, exc)
            td_errors.append((symbol, str(exc)))
            continue
        parsed = parse_twelve_dividends(asset, td_data)
        if parsed:
            for entry in parsed:
                entry.setdefault('status', 'synced')
            LOGGER.info("Twelve Data dividends matched via %s -> %s (%d entries)", asset, symbol, len(parsed))
            records.extend(parsed)
            break
        LOGGER.debug("Twelve Data response for %s via %s returned no records", asset, symbol)
    if not records and td_errors:
        LOGGER.warning("Twelve Data dividend fetch fell back for %s: %s", asset, td_errors)

    LOGGER.info("Total dividend records fetched for %s: %d", asset, len(records))
    return records

def upsert_dividend(record):
    if not record.get("ex_date"):
        return
    db = get_db()
    cur = db.cursor()
    net_per_share = record["amount"] * (1 - TAX_RATE)
    status = record.get('status', 'synced')
    shares_value = record.get('shares')
    if shares_value is not None:
        try:
            shares_value = float(shares_value)
        except (TypeError, ValueError):
            shares_value = None
    notes = record.get('notes')
    cur.execute(
        """
        INSERT INTO dividends (asset, ex_date, pay_date, amount, currency, shares, gross_value, net_value, source, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset, ex_date, source) DO UPDATE SET
            pay_date=excluded.pay_date,
            amount=excluded.amount,
            currency=excluded.currency,
            shares=CASE WHEN excluded.shares IS NOT NULL THEN excluded.shares ELSE dividends.shares END,
            gross_value=excluded.gross_value,
            net_value=excluded.net_value,
            source=excluded.source,
            status=excluded.status,
            notes=CASE WHEN excluded.notes IS NOT NULL THEN excluded.notes ELSE dividends.notes END
        """,
        (
            record["asset"],
            record["ex_date"],
            record.get("pay_date"),
            record["amount"],
            record.get("currency", "USD"),
            shares_value,
            record["amount"],
            net_per_share,
            record.get("source", "api"),
            status,
            notes,
        ),
    )
    db.commit()

def refresh_dividends(force=False):
    last_sync = CACHE.get("dividends:last_sync", DIVIDEND_TTL)
    cached_result = CACHE.get("dividends:last_result", DIVIDEND_TTL) or {"processed": 0, "missing": []}
    if last_sync and not force:
        LOGGER.debug("Dividends refresh skipped (cached)")
        return cached_result

    assets = get_portfolio_assets()
    result = {"processed": 0, "missing": []}
    LOGGER.info("Refreshing dividends for %d assets (force=%s)", len(assets), force)

    for asset in assets:
        fetched = fetch_dividends_for_asset(asset)
        if not fetched:
            LOGGER.warning("No dividend data returned for %s", asset)
            result["missing"].append(asset)
            continue
        for record in fetched:
            upsert_dividend(record)
            result["processed"] += 1

    if result["missing"]:
        seen = []
        for symbol in result["missing"]:
            if symbol not in seen:
                seen.append(symbol)
        result["missing"] = seen

    CACHE.set("dividends:last_sync", time.time())
    CACHE.set("dividends:last_result", result)
    LOGGER.info("Dividend refresh completed: %s", result)
    return result

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
    share_map = _sync_dividend_shares(dividends)
    assets = {row['asset'] for row in dividends}
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

        net_per_share = row['net_value'] if row['net_value'] else row['amount'] * (1 - TAX_RATE)
        shares = share_map.get(row['id'])
        if shares is None:
            shares = row['shares'] or 0.0
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
            "status": row["status"] if "status" in row.keys() else "synced",
            "price": price,
            "yield_pct": yield_pct,
            "upcoming": pay_date_obj and pay_date_obj >= today,
        })
    return enriched

@dividends_bp.route("/", methods=["GET"])
def list_dividends():
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

@dividends_bp.route("/manual", methods=["GET", "POST"])
def add_manual_dividend():
    def _value(name: str, default: str = "") -> str:
        return (request.values.get(name) or default).strip()

    form = {
        "asset": _value("asset").upper(),
        "ex_date": _value("ex_date"),
        "pay_date": _value("pay_date"),
        "amount": _value("amount"),
        "currency": _value("currency", "USD").upper(),
        "shares": _value("shares"),
        "notes": request.values.get("notes") or "",
    }

    if request.method == "POST":
        errors = []
        asset = form["asset"]
        if not asset:
            errors.append("Asset is required.")

        ex_date = form["ex_date"]
        if not ex_date:
            errors.append("Ex-date is required.")

        amount = None
        try:
            amount = float(form["amount"])
        except (TypeError, ValueError):
            errors.append("Amount must be a numeric value.")
        else:
            if amount <= 0:
                errors.append("Amount must be greater than zero.")

        shares = None
        if form["shares"]:
            try:
                shares = float(form["shares"])
            except (TypeError, ValueError):
                errors.append("Shares must be numeric.")

        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            record = {
                "asset": asset,
                "ex_date": ex_date,
                "pay_date": form["pay_date"] or ex_date,
                "amount": amount,
                "currency": form["currency"] or "USD",
                "source": "manual",
                "status": "manual",
                "shares": shares,
                "notes": form["notes"] or None,
            }
            upsert_dividend(record)
            flash("Manual dividend saved.", "success")
            return redirect(url_for("dividends.list_dividends"))

    return render_template("dividends/manual_form.html", form=form, tax_rate=TAX_RATE)
