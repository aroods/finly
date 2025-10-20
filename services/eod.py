import os
import requests
from typing import Optional

from cache_store import CACHE

EOD_API_KEY = os.getenv("EOD_API_KEY")
BASE_URL = "https://eodhistoricaldata.com/api"


def _request(endpoint: str, params: Optional[dict] = None, cache_ttl: int = 6 * 60 * 60):
    if not EOD_API_KEY:
        raise RuntimeError("EOD_API_KEY not set")

    params = params or {}
    params["api_token"] = EOD_API_KEY

    cache_key = f"eod:{endpoint}:{sorted(params.items())}"
    cached = CACHE.get(cache_key, cache_ttl)
    if cached:
        return cached

    response = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    CACHE.set(cache_key, data)
    return data


def fetch_dividends(symbol: str):
    # Endpoint expects format EXCHANGE.TICKER e.g., US.AAPL
    return _request(f"dividends/{symbol}", cache_ttl=12 * 60 * 60)


def fetch_fundamentals(symbol: str):
    return _request(f"fundamentals/{symbol}", cache_ttl=24 * 60 * 60)
