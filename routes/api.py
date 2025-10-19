import requests
from flask import Blueprint, jsonify, request, current_app

from helpers import get_event_dates, get_current_prices

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
    except requests.RequestException as exc:
        current_app.logger.warning("Yahoo search failed for '%s': %s", query, exc)
        return jsonify([])


@api_bp.route('/event-dates')
def event_dates():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400
    events = get_event_dates(symbol)
    if isinstance(events, dict) and events.get("error"):
        current_app.logger.warning("Event lookup failed for %s: %s", symbol, events["error"])
        return jsonify(events), 502
    return jsonify(events)


@api_bp.route('/get-currency')
def get_currency():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "No symbol provided"}), 400

    try:
        _, currencies, _ = get_current_prices([symbol])
    except Exception as exc:
        current_app.logger.exception("Currency lookup failed for %s", symbol)
        return jsonify({"error": str(exc)}), 500

    currency = currencies.get(symbol)
    if not currency:
        current_app.logger.info("No currency detected for %s", symbol)
        return jsonify({"error": "Currency not available"}), 404
    return jsonify({"currency": currency})
