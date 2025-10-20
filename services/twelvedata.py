import os
import requests
from typing import Optional

from cache_store import CACHE

TWELVE_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com"


def _request(endpoint: str, params: Optional[dict] = None, cache_ttl: int = 6 * 60 * 60):
    if not TWELVE_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY not set")

    params = params or {}
    params["apikey"] = TWELVE_API_KEY

    cache_key = f"twelvedata:{endpoint}:{sorted(params.items())}"
    cached = CACHE.get(cache_key, cache_ttl)
    if cached is not None:
        return cached

    response = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("status") == "error":
        message = data.get("message") or "Twelve Data error"
        raise RuntimeError(message)
    CACHE.set(cache_key, data)
    return data


def fetch_dividends(symbol: str):
    return _request("dividends", {"symbol": symbol}, cache_ttl=12 * 60 * 60)


def fetch_fundamentals(symbol: str):
    return _request("fundamentals", {"symbol": symbol}, cache_ttl=24 * 60 * 60)

def fetch_logo(symbol: str):
    return _request("logo", {"symbol": symbol}, cache_ttl=7 * 24 * 60 * 60)


def search_symbols(query: str, outputsize: int = 10):
    data = _request("symbol_search", {"symbol": query, "outputsize": outputsize}, cache_ttl=60 * 60)
    if isinstance(data, dict):
        return data.get("data", [])
    return data
