import yfinance as yf
from datetime import datetime

def euro_datetime(value):
    if value:
        # Try to parse ISO format with microseconds, fallback to shorter
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    return ''

def get_currency():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info if hasattr(ticker, 'fast_info') else ticker.info
        currency = info.get('currency', '')
        # Special handling for GBX (see previous solutions)
        if currency == "GBX":
            currency = "GBP"
        return jsonify({"currency": currency})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_current_prices(symbols):
    prices = {}
    currencies = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = None
            currency = None
            if info:
                price = (
                    info.get("lastPrice")
                    or info.get("last price")
                    or info.get("regularMarketPrice")
                    or info.get("last_close")
                    or info.get("previousClose")
                )
                currency = info.get("currency") or info.get("lastCurrency") or None
            if not price:
                hist = ticker.history(period="1d")
                price = hist['Close'][-1] if not hist.empty else 0
            if not currency:
                # fallback: get currency from .info
                currency = getattr(ticker, "info", {}).get("currency", None)
            # GBX fix
            # print(symbol, currency, price)
        
            if currency == "GBp":
                price = float(price) / 100 if price else 0
                currency = "GBP"  # Treat as GBP after conversion
            prices[symbol] = float(price) if price else 0
            currencies[symbol] = currency
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            prices[symbol] = 0
            currencies[symbol] = None
        print(symbol, currency, price)
    return prices, currencies

def get_event_dates(symbol):
    """Returns dict with dividend_date, earnings_date, etc. for a given ticker."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.get_info()
        events = {}

        # Dividend date (ex-dividend)
        if 'dividendDate' in info and info['dividendDate']:
            dt = datetime.fromtimestamp(info['dividendDate'])
            events['dividend_date'] = dt.strftime('%Y-%m-%d')
        # Earnings (results) date
        cal = info.get('earningsTimestamp', None)
        if cal:
            dt = datetime.fromtimestamp(cal)
            events['earnings_date'] = dt.strftime('%Y-%m-%d')
        # Try earningsDates as well (sometimes available as list)
        if 'earningsDates' in info and info['earningsDates']:
            edates = [datetime.fromtimestamp(d['raw']).strftime('%Y-%m-%d') for d in info['earningsDates'] if d.get('raw')]
            events['future_earnings_dates'] = edates
        return events
    except Exception as e:
        print(f"Event date fetch error for {symbol}: {e}")
        return {"error": str(e)}

def calculate_weighted_avg(transactions):
    total_qty = sum(q for q, _ in transactions)
    if total_qty == 0:
        return 0
    return sum(q * p for q, p in transactions) / total_qty

def calculate_investment_cost(transactions):
    return sum(q * p for q, p in transactions)

def calculate_profit_loss(current_value, investment_cost):
    if investment_cost == 0:
        return 0, 0
    pln = current_value - investment_cost
    perc = (pln / investment_cost) * 100
    return pln, perc

