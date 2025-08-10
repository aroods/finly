from datetime import datetime
import yfinance as yf
from cache_store import CacheStore

def euro_datetime(value):
    if value:
        # Try to parse ISO format with microseconds, fallback to shorter
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    return ''

# tweak the path if you keep everything in repo root
CACHE = CacheStore(db_path="portfolio.db")

PRICE_TTL = 10 * 60      # 10 minutes
EVENT_TTL = 24 * 60 * 60 # 24 hours

def get_current_prices(symbols):
    prices = {}
    currencies = {}
    for symbol in symbols:
        # 1) try cache
        cached = CACHE.get(f"price:{symbol}", PRICE_TTL)
        if cached:
            price, currency = cached  # we store (price, currency)
            prices[symbol] = float(price) if price else 0
            currencies[symbol] = currency
            continue

        # 2) fallback to live fetch
        try:
            ticker = yf.Ticker(symbol)
            info = getattr(ticker, "fast_info", None)
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
                currency = getattr(ticker, "info", {}).get("currency", None)

            # GBX/GBp fix
            if currency in ("GBX", "GBp"):
                price = float(price) / 100 if price else 0
                currency = "GBP"

            prices[symbol] = float(price) if price else 0
            currencies[symbol] = currency

            # 3) save to cache
            CACHE.set(f"price:{symbol}", (prices[symbol], currencies[symbol]))

        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            prices[symbol] = 0
            currencies[symbol] = None

    return prices, currencies


def get_event_dates(symbol):
    # 1) try cache
    cached = CACHE.get(f"events:{symbol}", EVENT_TTL)
    if cached:
        return cached

    # 2) live fetch
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.get_info()
        events = {}

        # Dividend date (ex-dividend)
        if info.get('dividendDate'):
            dt = datetime.fromtimestamp(info['dividendDate'])
            events['dividend_date'] = dt.strftime('%Y-%m-%d')

        # Earnings date
        if info.get('earningsTimestamp'):
            dt = datetime.fromtimestamp(info['earningsTimestamp'])
            events['earnings_date'] = dt.strftime('%Y-%m-%d')

        # Future earnings dates (list)
        if info.get('earningsDates'):
            edates = [
                datetime.fromtimestamp(d['raw']).strftime('%Y-%m-%d')
                for d in info['earningsDates'] if d.get('raw')
            ]
            if edates:
                events['future_earnings_dates'] = edates

        # 3) save to cache and return
        CACHE.set(f"events:{symbol}", events)
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