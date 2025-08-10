from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import get_db
from helpers import calculate_weighted_avg, calculate_investment_cost, calculate_profit_loss, get_current_prices
from cache_store import CACHE

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route('/')
def dashboard():
    db = get_db()
    cur = db.cursor()

    # 1. Get all transactions
    cur.execute("SELECT asset, category, type, quantity, price, currency FROM transactions")
    transactions = cur.fetchall()
    
    # 2. Group transactions by asset & category
    # Key: (asset, category, currency)
    assets = {}
    for tx in transactions:
        asset, category, tx_type, quantity, price, currency = tx
        key = (asset, category, currency)
        if key not in assets:
            assets[key] = {"buys": [], "sells": []}
        if tx_type == "buy":
            assets[key]["buys"].append((quantity, price))
        elif tx_type == "sell":
            assets[key]["sells"].append((quantity, price))
    
    # 3. Get latest prices for all assets (you may already cache this)
    asset_symbols = list({asset for asset, _, _ in assets.keys()})
    # You must implement get_current_prices
    current_prices, current_currencies = get_current_prices(asset_symbols)
    # Example: current_prices = {'AAPL': 200.5, 'PKO.WA': 100.2, ...}

    dashboard_rows = []
    total_value_pln = 0.0

    # 4. Compute summaries
    for (asset, category, currency), txs in assets.items():
        total_bought = sum(q for q, _ in txs["buys"])
        total_sold = sum(q for q, _ in txs["sells"])
        net_qty = total_bought - total_sold

        wavg_price = calculate_weighted_avg(txs["buys"]) if txs["buys"] else 0
        investment_cost = calculate_investment_cost(txs["buys"])
        current_price = current_prices.get(asset, 0)
        current_currency = current_currencies.get(asset, None)
        current_value = current_price * net_qty
        profit_loss_pln, profit_loss_perc = calculate_profit_loss(current_value, investment_cost)

        dashboard_rows.append({
            "asset": asset,
            "category": category,
            "quantity": net_qty,
            "weighted_avg_price": wavg_price,
            "investment_cost": investment_cost,
            "current_price": current_price,
            "current_value": current_value,
            "profit_loss_pln": profit_loss_pln,
            "profit_loss_perc": profit_loss_perc
        })

        total_value_pln += current_value

    # 5. Get current cash
    cur.execute("SELECT amount FROM cash_deposits ORDER BY created_at DESC LIMIT 1")
    current_cash = cur.fetchone()[0] or 0.0
    total_value_pln += current_cash

    # 6. Asset allocation for pie chart (includes cash)
    pie_labels = [row["asset"] for row in dashboard_rows] + ["Cash"]
    pie_values = [row["current_value"] for row in dashboard_rows] + [current_cash]

    stats = CACHE.stats()
    return render_template('index.html',
        dashboard_rows=dashboard_rows,
        current_cash=current_cash,
        total_value_pln=total_value_pln,
        pie_labels=pie_labels,
        pie_values=pie_values,
        cache_stats=stats
    )

@dashboard_bp.route('/refresh')
def refresh_prices():
    # You may want to force-update cache, or just redirect (dashboard will always fetch fresh on load)
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