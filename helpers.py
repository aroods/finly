from datetime import datetime, timedelta, date as date_cls
import math
import yfinance as yf

from cache_store import CacheStore


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_currency(code):
    return (code or "PLN").upper()


def euro_datetime(value):
    if value:
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    return ''


CACHE = CacheStore(db_path="portfolio.db")

PENCE_TICKERS = {
    "NWG.L",
    "NWG",
    "LON: NWG",
}

PRICE_TTL = 10 * 60      # 10 minutes
EVENT_TTL = 24 * 60 * 60 # 24 hours
FX_TTL = 60 * 60         # 1 hour
HISTORY_TTL = 12 * 60 * 60  # 12 hours


def _get_price_history(symbol, start_date, end_date):
    cache_key = f"history:{symbol}:{start_date}:{end_date}"
    cached = CACHE.get(cache_key, HISTORY_TTL)
    if cached:
        series = []
        for day_str, price in cached:
            try:
                day = datetime.fromisoformat(day_str).date()
                series.append((day, float(price)))
            except Exception:
                continue
        if series:
            return series
    try:
        hist = yf.Ticker(symbol).history(
            start=start_date.isoformat(), end=(end_date + timedelta(days=1)).isoformat()
        )
    except Exception:
        hist = None
    series = []
    if hist is not None and not hist.empty:
        close_series = hist.get("Close")
        if close_series is not None:
            for index, price in close_series.items():
                if price is None:
                    continue
                price = float(price)
                if math.isnan(price):
                    continue
                if hasattr(index, "to_pydatetime"):
                    day = index.to_pydatetime().date()
                else:
                    day = index.date()
                series.append((day, price))
    series.sort()
    if series:
        CACHE.set(cache_key, [(day.isoformat(), price) for day, price in series])
    return series


def _get_fx_rate_to_pln(currency):
    currency = _normalize_currency(currency)
    if currency == "PLN":
        return 1.0
    cache_key = f"fx:{currency}"
    cached = CACHE.get(cache_key, FX_TTL)
    if cached:
        try:
            return float(cached)
        except Exception:
            pass
    symbol = f"{currency}PLN=X"
    rate = None
    try:
        ticker = yf.Ticker(symbol)
        info = getattr(ticker, "fast_info", None)
        if info:
            rate = (
                info.get("lastPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )
        if not rate:
            hist = ticker.history(period="1d")
            if not hist.empty:
                rate = hist["Close"][-1]
    except Exception:
        rate = None
    if not rate:
        rate = 1.0
    rate = float(rate)
    CACHE.set(cache_key, rate)
    return rate


def get_fx_rates_for_assets(asset_currency_map):
    rates = {}
    cache = {}
    for asset, currency in asset_currency_map.items():
        norm = _normalize_currency(currency)
        if norm in cache:
            rate = cache[norm]
        else:
            rate = _get_fx_rate_to_pln(norm)
            cache[norm] = rate
        rates[asset] = rate
    return rates


def summarize_positions(transactions):
    positions = {}
    for tx in transactions:
        asset = (tx.get("asset") or "").strip()
        if not asset:
            continue
        category = tx.get("category") or "Unknown"
        currency = _normalize_currency(tx.get("currency"))
        quantity = _safe_float(tx.get("quantity"))
        price = _safe_float(tx.get("price"))
        tx_type = (tx.get("type") or "").lower()

        key = (asset, category, currency)
        position = positions.setdefault(
            key,
            {
                "net_quantity": 0.0,
                "cost_basis": 0.0,
                "realized_pl": 0.0,
            },
        )

        if tx_type == "buy":
            position["net_quantity"] += quantity
            position["cost_basis"] += quantity * price
        elif tx_type == "sell":
            available_qty = position["net_quantity"]
            if available_qty <= 0:
                continue
            avg_cost = position["cost_basis"] / available_qty if available_qty else 0.0
            sell_qty = min(quantity, available_qty)
            position["net_quantity"] -= sell_qty
            position["cost_basis"] -= sell_qty * avg_cost
            position["realized_pl"] += sell_qty * (price - avg_cost)
        else:
            continue

        if abs(position["net_quantity"]) < 1e-9:
            position["net_quantity"] = 0.0
        if abs(position["cost_basis"]) < 1e-9:
            position["cost_basis"] = 0.0

    return positions


def get_current_prices(symbols):
    prices = {}
    currencies = {}
    fx_rates = {}
    currency_cache = {}
    for symbol in symbols:
        if not symbol:
            continue
        cached = CACHE.get(f"price:{symbol}", PRICE_TTL)
        price = None
        currency = None
        if cached:
            try:
                price, currency = cached
                price = float(price)
            except Exception:
                price = None
                currency = None
        if price is None:
            try:
                ticker = yf.Ticker(symbol)
                info = getattr(ticker, "fast_info", None)
                if info:
                    price = (
                        info.get("lastPrice")
                        or info.get("regularMarketPrice")
                        or info.get("previousClose")
                    )
                    currency = info.get("currency") or info.get("lastCurrency")
                if price is None:
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        price = hist['Close'][-1]
                if currency is None:
                    currency = getattr(ticker, "info", {}).get("currency")
            except Exception:
                price = None
                currency = None
        price = _safe_float(price)
        raw_currency = currency
        currency = _normalize_currency(currency)
        if raw_currency in ("GBX", "GBp") and price:
            price = float(price) / 100.0
            currency = "GBP"
        elif raw_currency == "GBP" and price and symbol in PENCE_TICKERS:
            price = float(price) / 100.0
        elif raw_currency == "GBP" and price:
            price = float(price)
        prices[symbol] = float(price)
        currencies[symbol] = currency
        if currency in currency_cache:
            fx_rates[symbol] = currency_cache[currency]
        else:
            fx_rate = _get_fx_rate_to_pln(currency)
            fx_rates[symbol] = fx_rate
            currency_cache[currency] = fx_rate
        CACHE.set(f"price:{symbol}", (prices[symbol], currency))
    return prices, currencies, fx_rates


def get_event_dates(symbol):
    cached = CACHE.get(f"events:{symbol}", EVENT_TTL)
    if cached:
        return cached
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.get_info()
    except Exception as exc:
        return {"error": str(exc)}
    events = {}
    if info.get('dividendDate'):
        dt = datetime.fromtimestamp(info['dividendDate'])
        events['dividend_date'] = dt.strftime('%Y-%m-%d')
    if info.get('earningsTimestamp'):
        dt = datetime.fromtimestamp(info['earningsTimestamp'])
        events['earnings_date'] = dt.strftime('%Y-%m-%d')
    if info.get('earningsDates'):
        edates = [
            datetime.fromtimestamp(d['raw']).strftime('%Y-%m-%d')
            for d in info['earningsDates'] if d.get('raw')
        ]
        if edates:
            events['future_earnings_dates'] = edates
    CACHE.set(f"events:{symbol}", events)
    return events


def calculate_weighted_avg(transactions):
    total_qty = sum(_safe_float(q) for q, _ in transactions)
    if total_qty == 0:
        return 0.0
    return sum(_safe_float(q) * _safe_float(p) for q, p in transactions) / total_qty


def calculate_investment_cost(transactions):
    return sum(_safe_float(q) * _safe_float(p) for q, p in transactions)


def calculate_profit_loss(current_value, investment_cost):
    current_value = _safe_float(current_value)
    investment_cost = _safe_float(investment_cost)
    if investment_cost == 0:
        return 0.0, 0.0
    pln = current_value - investment_cost
    perc = (pln / investment_cost) * 100
    return pln, perc


def build_profit_timeseries(transactions, asset_fx_rates=None, current_price_map=None):
    if not transactions:
        return []

    parsed = []
    assets = set()
    asset_currency = {}
    for tx in transactions:
        asset = (tx.get("asset") or "").strip()
        if not asset:
            continue
        tx_date = tx.get("date")
        if isinstance(tx_date, datetime):
            tx_day = tx_date.date()
        else:
            try:
                tx_day = datetime.fromisoformat(tx_date).date()
            except Exception:
                try:
                    tx_day = datetime.strptime(tx_date, "%Y-%m-%d").date()
                except Exception:
                    continue
        currency = _normalize_currency(tx.get("currency"))
        parsed.append(
            {
                "id": tx.get("id", 0),
                "date": tx_day,
                "asset": asset,
                "currency": currency,
                "type": (tx.get("type") or "").lower(),
                "quantity": _safe_float(tx.get("quantity")),
                "price": _safe_float(tx.get("price")),
            }
        )
        assets.add(asset)
        asset_currency.setdefault(asset, currency)

    if not parsed:
        return []

    parsed.sort(key=lambda item: (item["date"], item["id"]))
    start_date = parsed[0]["date"]
    end_date = max(parsed[-1]["date"], date_cls.today())

    if asset_fx_rates is None:
        asset_fx_rates = get_fx_rates_for_assets(asset_currency)

    price_histories = {}
    for asset in assets:
        series = _get_price_history(asset, start_date, end_date)
        if asset in PENCE_TICKERS:
            series = [(day, price / 100.0) for day, price in series]
        price_histories[asset] = series
    price_indexes = {asset: 0 for asset in assets}
    last_price = {asset: None for asset in assets}

    positions = {
        asset: {"qty": 0.0, "cost_local": 0.0, "cost_pln": 0.0} for asset in assets
    }
    realized_profit_pln = 0.0

    profit_series = []
    tx_index = 0
    total_transactions = len(parsed)
    day = start_date
    while day <= end_date:
        while tx_index < total_transactions and parsed[tx_index]["date"] <= day:
            tx = parsed[tx_index]
            asset = tx["asset"]
            fx_rate = asset_fx_rates.get(asset, 1.0)
            record = positions.setdefault(asset, {"qty": 0.0, "cost_local": 0.0, "cost_pln": 0.0})
            quantity = tx["quantity"]
            price = tx["price"]
            if tx["type"] == "buy":
                record["qty"] += quantity
                record["cost_local"] += quantity * price
                record["cost_pln"] += quantity * price * fx_rate
            elif tx["type"] == "sell":
                available_qty = record["qty"]
                if available_qty > 0:
                    sell_qty = min(quantity, available_qty)
                    avg_cost_local = record["cost_local"] / available_qty if available_qty else 0.0
                    avg_cost_pln = record["cost_pln"] / available_qty if available_qty else 0.0
                    record["qty"] -= sell_qty
                    record["cost_local"] -= sell_qty * avg_cost_local
                    record["cost_pln"] -= sell_qty * avg_cost_pln
                    proceeds_pln = sell_qty * price * fx_rate
                    realized_profit_pln += proceeds_pln - sell_qty * avg_cost_pln
                    if abs(record["cost_local"]) < 1e-8:
                        record["cost_local"] = 0.0
                    if abs(record["cost_pln"]) < 1e-8:
                        record["cost_pln"] = 0.0
            tx_index += 1

        unrealized_pln = 0.0
        for asset, record in positions.items():
            qty = record["qty"]
            if qty <= 0:
                continue
            series = price_histories.get(asset, [])
            idx = price_indexes.get(asset, 0)
            while idx < len(series) and series[idx][0] <= day:
                last_price[asset] = series[idx][1]
                idx += 1
            price_indexes[asset] = idx
            price_local = last_price.get(asset)
            if price_local is None and current_price_map:
                price_local = current_price_map.get(asset)
            if price_local is None:
                continue
            fx_rate = asset_fx_rates.get(asset, 1.0)
            price_pln = price_local * fx_rate
            unrealized_pln += qty * price_pln - record["cost_pln"]
        total_profit = realized_profit_pln + unrealized_pln
        profit_series.append({"date": day.isoformat(), "value": round(total_profit, 2)})
        day += timedelta(days=1)

    return profit_series
