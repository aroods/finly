import sqlite3
import datetime
from flask import Flask, request, render_template, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf

app = Flask(__name__)

# Initialize SQLite database (create tables if they don't exist)
conn = sqlite3.connect('portfolio.db', check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    asset TEXT,
    type TEXT,
    quantity REAL,
    price REAL,
    currency TEXT,
    category TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    total_value_pln REAL
)
""")
conn.commit()

import os
print(os.getcwd())

def fetch_current_prices():
    """Fetch current prices for all assets and compute total portfolio value in PLN."""
    # Aggregate current holdings by asset (sum of quantities, buys minus sells)
    cur = conn.cursor()
    cur.execute("""
        SELECT asset, currency, category,
               SUM(CASE WHEN type='buy' THEN quantity ELSE -quantity END) as total_qty
        FROM transactions
        GROUP BY asset, currency, category
    """)
    rows = cur.fetchall()
    holdings = []
    total_value_pln = 0.0
    # Cache for currency conversion rates (to minimize external calls)
    currency_rates = {'PLN': 1.0}
    for asset, currency, category, total_qty in rows:
        if total_qty is None:
            continue
        total_qty = float(total_qty)
        # Skip assets that have zero or negative quantity (fully sold)
        if total_qty <= 0:
            continue
        # Fetch current asset price (in its local currency) using Yahoo Finance via yfinance
        try:
            ticker = yf.Ticker(asset)
            price = ticker.info.get('regularMarketPrice')
            if price is None:
                # Fallback: use last closing price if real-time price is not available
                hist = ticker.history(period="1d")
                price = hist['Close'][0] if not hist.empty else 0
        except Exception as e:
            print(f"Error fetching price for {asset}: {e}")
            continue  # Skip this asset if price fetch failed
        price = float(price) if price is not None else 0.0
        # Get currency conversion rate to PLN if asset is not priced in PLN
        currency = currency.upper()
        if currency not in currency_rates:
            if currency != 'PLN':
                try:
                    fx_ticker = yf.Ticker(f"{currency}PLN=X")
                    fx_rate = fx_ticker.info.get('regularMarketPrice')
                    if fx_rate is None:
                        fx_hist = fx_ticker.history(period="1d")
                        fx_rate = fx_hist['Close'][0] if not fx_hist.empty else 0
                except Exception as e:
                    print(f"Error fetching FX rate for {currency}: {e}")
                    fx_rate = 0
                fx_rate = float(fx_rate) if fx_rate is not None else 0.0
                currency_rates[currency] = fx_rate
            else:
                currency_rates[currency] = 1.0
        # Calculate current value in original currency and in PLN
        value_orig = price * total_qty
        value_pln = value_orig * currency_rates.get(currency, 0.0)
        total_value_pln += value_pln
        holdings.append({
            'asset': asset,
            'category': category,
            'quantity': total_qty,
            'price': price,
            'currency': currency,
            'value_orig': value_orig,
            'value_pln': value_pln
        })
    return holdings, total_value_pln

def take_snapshot():
    """Save a snapshot of total portfolio value in PLN to the database."""
    holdings, total_value_pln = fetch_current_prices()
    today = datetime.date.today().strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("INSERT INTO snapshots(date, total_value_pln) VALUES (?, ?)",
                (today, total_value_pln))
    conn.commit()
    print(f"Snapshot taken on {today}: Total PLN {total_value_pln:.2f}")

# Set up a background scheduler to take a snapshot on the 1st of each month at 00:00
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(take_snapshot, 'cron', day=1, hour=0, minute=0)

# @app.before_serving
# async def start_scheduler():
#     scheduler.start()  # Start scheduler when the first request is handled:contentReference[oaicite:0]{index=0}

@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    # Shut down scheduler when the app context is torn down (e.g., on app exit)
    try:
        scheduler.shutdown()
    except Exception:
        pass

@app.route('/')
def dashboard():
    """Dashboard page – shows current portfolio summary and charts."""
    holdings, total_value_pln = fetch_current_prices()
    # Prepare data for charts
    labels = [h['asset'] for h in holdings]
    values = [round(h['value_pln'], 2) for h in holdings]
    # Get historical snapshots for the portfolio value line chart
    cur = conn.cursor()
    cur.execute("SELECT date, total_value_pln FROM snapshots ORDER BY date")
    snapshot_data = cur.fetchall()
    line_labels = [row[0][:7] for row in snapshot_data]  # e.g., "2025-07"
    line_values = [row[1] for row in snapshot_data]
    return render_template('index.html',
                           holdings=holdings,
                           total_value_pln=total_value_pln,
                           pie_labels=labels,
                           pie_values=values,
                           line_labels=line_labels,
                           line_values=line_values)

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    """Page to add a new transaction (buy/sell an asset)."""
    if request.method == 'POST':
        # Read form fields
        date = request.form.get('date')
        asset = request.form.get('asset', '').strip().upper()       # ticker symbol
        ttype = request.form.get('type', '').lower()                # 'buy' or 'sell'
        quantity = request.form.get('quantity', '0')
        price = request.form.get('price', '0')
        currency = request.form.get('currency', '').strip().upper() # e.g. 'USD', 'PLN'
        category = request.form.get('category', '').strip()
        # Insert the transaction into the database
        cur = conn.cursor()
        cur.execute("""INSERT INTO transactions
                       (date, asset, type, quantity, price, currency, category)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (date, asset, ttype, float(quantity), float(price), currency, category))
        conn.commit()
        return redirect(url_for('dashboard'))  # Redirect to dashboard after adding
    else:
        # GET request: render the transaction input form
        return render_template('add.html')

if __name__ == '__main__':
    scheduler.start()
    # Run the Flask development server (listen on 0.0.0.0 so it's accessible externally)
    app.run(host='0.0.0.0', port=5000)
