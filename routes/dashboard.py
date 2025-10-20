from flask import Blueprint, render_template, redirect, url_for, flash, request
from datetime import datetime

from db import get_db
from helpers import (
    summarize_positions,
    get_current_prices,
    build_profit_timeseries,
    get_fx_rates_for_assets,
    get_logo_url,
)
from bond_helpers import parse_bond_row, calculate_accrual
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
    adjusted_current_prices = {}
    equity_total_value = 0.0
    equity_profit_total = 0.0

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
        equity_total_value += current_value_pln
        equity_profit_total += profit_loss_pln

    for row in dashboard_rows:
        row["logo_url"] = get_logo_url(row["asset"])

    cur.execute("SELECT amount FROM cash_deposits ORDER BY created_at DESC LIMIT 1")
    cash_row = cur.fetchone()
    current_cash = cash_row[0] if cash_row else 0.0

    cur.execute("SELECT * FROM bonds ORDER BY purchase_date DESC, id DESC")
    bond_rows_raw = cur.fetchall()
    bond_positions = [parse_bond_row(row) for row in bond_rows_raw]
    bond_rows = []
    bond_total_value = 0.0
    bond_total_accrued = 0.0
    for bond in bond_positions:
        accrual = calculate_accrual(bond)
        bond_rows.append((bond, accrual))
        bond_total_value += accrual["current_value"]
        bond_total_accrued += accrual["accrued_interest"]

    total_value_pln = equity_total_value + current_cash + bond_total_value

    fx_rates_all = get_fx_rates_for_assets(asset_currency_map)
    profit_series = build_profit_timeseries(transactions, fx_rates_all, adjusted_current_prices)

    if profit_series:
        for point in profit_series:
            point_date = datetime.fromisoformat(point["date"]).date()
            bond_contribution = 0.0
            for bond in bond_positions:
                accrual = calculate_accrual(bond, reference=point_date)
                bond_contribution += accrual["accrued_interest"]
            point["value"] = round(point["value"] + bond_contribution, 2)
        total_profit_pln = profit_series[-1]["value"]
    else:
        total_profit_pln = round(equity_profit_total + bond_total_accrued, 2)

    overview_colors = {
        "Equities/ETFs": "#38bdf8",
        "Bonds": "#10b981",
        "Cash": "#facc15",
    }

    def cycle_colors(base_colors, count):
        if not base_colors:
            return []
        return [base_colors[i % len(base_colors)] for i in range(count)]

    equity_detail_data = [
        {"label": row["asset"], "value": round(row["current_value_pln"], 2)}
        for row in dashboard_rows
    ]
    bond_detail_data = [
        {"label": bond.series, "value": round(accrual["current_value"], 2)}
        for bond, accrual in bond_rows
    ]

    EQUITY_COLORS = [
        "#38bdf8", "#818cf8", "#f472b6", "#fb7185", "#f97316",
        "#facc15", "#4ade80", "#34d399", "#22d3ee", "#a855f7", "#64748b"
    ]
    BOND_COLORS = [
        "#10b981", "#34d399", "#22d3ee", "#0ea5e9", "#14b8a6", "#2dd4bf", "#5eead4", "#99f6e4"
    ]

    equity_total_value = round(equity_total_value, 2)
    equity_profit_total_rounded = round(equity_profit_total, 2)
    bond_total_value = round(bond_total_value, 2)
    current_cash = round(current_cash, 2)
    bond_total_accrued = round(bond_total_accrued, 2)
    total_value_pln = round(total_value_pln, 2)

    pie_overview = [
        {"label": "Equities/ETFs", "value": equity_total_value, "color": overview_colors["Equities/ETFs"]},
        {"label": "Bonds", "value": bond_total_value, "color": overview_colors["Bonds"]},
        {"label": "Cash", "value": current_cash, "color": overview_colors["Cash"]},
    ]

    pie_detail_map = {
        "Equities/ETFs": {
            "data": equity_detail_data,
            "colors": cycle_colors(EQUITY_COLORS, len(equity_detail_data)),
        },
        "Bonds": {
            "data": bond_detail_data,
            "colors": cycle_colors(BOND_COLORS, len(bond_detail_data)),
        },
        "Cash": {
            "data": [{"label": "Cash", "value": current_cash}],
            "colors": [overview_colors["Cash"]],
        },
    }

    try:
        stats = CACHE.stats()
    except Exception:
        stats = None

    return render_template(
        'index.html',
        dashboard_rows=dashboard_rows,
        current_cash=current_cash,
        total_value_pln=total_value_pln,
        cache_stats=stats,
        profit_series=profit_series,
        total_profit_pln=total_profit_pln,
        bond_rows=bond_rows,
        bond_total_value=bond_total_value,
        bond_total_accrued=bond_total_accrued,
        pie_overview=pie_overview,
        pie_detail_map=pie_detail_map,
        equity_total_value=equity_total_value,
        equity_profit_total=equity_profit_total_rounded,
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
