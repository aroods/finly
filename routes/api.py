from flask import Blueprint, jsonify, request
from helpers import get_event_dates, get_current_prices
import requests

api_bp = Blueprint("api", __name__)

@api_bp.route('/yahoo-search')
def yahoo_search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": query, "quotesCount": 10, "newsCount": 0, "lang": "en"}
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        items = []
        for item in resp.json().get("quotes", []):
            if "symbol" in item and "shortname" in item:
                items.append({
                    "ticker": item["symbol"],
                    "name": item["shortname"],
                    "exchange": item.get("exchange", ""),
                    "type": item.get("quoteType", "")
                })
        return jsonify(items)
    except Exception as e:
        print(f"Yahoo search error: {e}")
        return jsonify([])
    

@api_bp.route('/event-dates')
def event_dates():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400
    events = get_event_dates(symbol)
    return jsonify(events)

@api_bp.route('/get-currency')
def get_currency():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    try:
        _, currencies = get_current_prices([symbol])
        print("Currencies:", currencies)  # <-- debug!
        currency = currencies.get(symbol, "")
        if not currency:
            print("No currency for", symbol)
        return jsonify({"currency": currency})
    except Exception as e:
        print("Currency fetch error:", e)  # <-- debug!
        return jsonify({"error": str(e)}), 500