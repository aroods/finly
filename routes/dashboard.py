from flask import Blueprint, render_template, redirect, url_for, flash

from db import get_db
from helpers import (
    summarize_positions,
    get_current_prices,
    build_profit_timeseries,
    get_fx_rates_for_assets,
)
from cache_store import CACHE


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route('/')
def dashboard():
    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        SELECT id, date, asset, category, type, quantity, price, currency
        FROM transactions
        ORDER BY date ASC, id ASC
        """
    )
    rows = cur.fetchall()
    transactions = [
        {
            "id": row[0],
            "date": row[1],
            "asset": row[2],
            "category": row[3],
            "type": row[4],
            "quantity": row[5],
            "price": row[6],
            "currency": row[7],
        }
        for row in rows
    ]

    asset_currency_map = {}
    for tx in transactions:
        asset = tx.get("asset")
        if not asset:
            continue
        asset_currency_map.setdefault(asset, tx.get("currency") or "PLN")

    positions = summarize_positions(transactions)
    open_positions = {
        key: data for key, data in positions.items() if data["net_quantity"] > 0
    }

    asset_symbols = [asset for (asset, _, _), _ in open_positions.items()]
    current_prices, current_currencies, current_fx_rates = get_current_prices(asset_symbols)

    dashboard_rows = []
    total_value_pln = 0.0
    adjusted_current_prices = {}

    for (asset, category, currency), data in sorted(
        open_positions.items(), key=lambda item: item[0][0]
    ):
        net_qty = data["net_quantity"]
        if net_qty <= 0:
            continue

        investment_cost_local = data["cost_basis"]
        weighted_avg_price_local = investment_cost_local / net_qty if net_qty else 0.0
        current_price_local = current_prices.get(asset, 0.0)
        fx_rate = current_fx_rates.get(asset, 1.0)

        if weighted_avg_price_local > 0 and current_price_local > weighted_avg_price_local * 20:
            current_price_local = current_price_local / 100.0

        weighted_avg_price_pln = weighted_avg_price_local * fx_rate
        investment_cost_pln = investment_cost_local * fx_rate
        current_price_pln = current_price_local * fx_rate
        current_value_pln = current_price_pln * net_qty
        profit_loss_pln = current_value_pln - investment_cost_pln
        profit_loss_perc = (profit_loss_pln / investment_cost_pln * 100) if investment_cost_pln else 0.0
        display_currency = currency or current_currencies.get(asset) or 'PLN'

        dashboard_rows.append(
            {
                "asset": asset,
                "category": category,
                "currency": display_currency,
                "quantity": net_qty,
                "weighted_avg_price_local": weighted_avg_price_local,
                "weighted_avg_price_pln": weighted_avg_price_pln,
                "investment_cost_pln": investment_cost_pln,
                "current_price_local": current_price_local,
                "current_price_pln": current_price_pln,
                "current_value_pln": current_value_pln,
                "profit_loss_pln": profit_loss_pln,
                "profit_loss_perc": profit_loss_perc,
            }
        )

        adjusted_current_prices[asset] = current_price_local
        total_value_pln += current_value_pln

    cur.execute("SELECT amount FROM cash_deposits ORDER BY created_at DESC LIMIT 1")
    cash_row = cur.fetchone()
    current_cash = cash_row[0] if cash_row else 0.0
    total_value_pln += current_cash

    pie_labels = [row["asset"] for row in dashboard_rows]
    pie_values = [row["current_value_pln"] for row in dashboard_rows]
    if current_cash:
        pie_labels.append("Cash")
        pie_values.append(current_cash)

    fx_rates_all = get_fx_rates_for_assets(asset_currency_map)
    profit_series = build_profit_timeseries(transactions, fx_rates_all, adjusted_current_prices)

    total_profit_pln = round(sum(row["profit_loss_pln"] for row in dashboard_rows), 2)
    if profit_series:
        profit_series[-1]["value"] = total_profit_pln

    try:
        stats = CACHE.stats()
    except Exception:
        stats = None

    return render_template(
        'index.html',
        dashboard_rows=dashboard_rows,
        current_cash=current_cash,
        total_value_pln=total_value_pln,
        pie_labels=pie_labels,
        pie_values=pie_values,
        cache_stats=stats,
        profit_series=profit_series,
        total_profit_pln=total_profit_pln,
    )


@dashboard_bp.route('/refresh')
def refresh_prices():
    flash("Prices refreshed!", "success")
    return redirect(url_for('dashboard.dashboard'))


@dashboard_bp.route('/clear-cache', methods=['POST'])
def clear_cache():
    prefix = request.form.get('prefix')
    if prefix:
        CACHE.clear_prefix(prefix)
    else:
        CACHE.clear_all()
    flash('Cache cleared!', 'success')
    return redirect(url_for('dashboard.dashboard'))
