from __future__ import annotations

from typing import List

from db import get_db

SYMBOL_TWELVE_OVERRIDES = {
    "NWG.L": ["NWG", "NWG:LSE", "LON:NWG"],
    "PKN.WA": ["PKN", "PKN:WSE", "WSE:PKN"],
    "PZU.WA": ["PZU", "PZU:WSE", "WSE:PZU"],
}


def get_symbol_mappings(asset: str, provider: str) -> List[str]:
    """Return active provider symbols mapped to the internal asset symbol."""
    if not asset:
        return []

    normalized_asset = asset.strip().upper()
    provider = (provider or "").strip().lower()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT provider_symbol
        FROM symbol_mappings
        WHERE internal_symbol = ? AND provider = ? AND active = 1
        ORDER BY priority ASC, id ASC
        """,
        (normalized_asset, provider),
    )
    return [row[0] for row in cur.fetchall()]


def _base_twelvedata_candidates(asset: str) -> List[str]:
    candidates: List[str] = []
    if not asset:
        return candidates

    asset_norm = asset.strip().upper()
    seen = set()

    def add(symbol: str) -> None:
        sym = (symbol or "").strip()
        if not sym or sym in seen:
            return
        seen.add(sym)
        candidates.append(sym)

    add(asset_norm)
    for override in SYMBOL_TWELVE_OVERRIDES.get(asset_norm, []):
        add(override)

    if "." in asset_norm:
        root = asset_norm.split(".", 1)[0]
        add(root)
    else:
        root = asset_norm

    if asset_norm.endswith(".L"):
        add(f"{root}:LSE")
        add(f"LON:{root}")
    if asset_norm.endswith(".WA"):
        add(f"{root}:WSE")
        add(f"WSE:{root}")
    if asset_norm.endswith(".F"):
        add(f"{root}:FRA")
    if asset_norm.endswith(".DE"):
        add(f"{root}:ETR")
    if asset_norm.endswith(".MI"):
        add(f"{root}:MIL")
    if asset_norm.endswith(".PA"):
        add(f"{root}:PAR")

    return candidates


def build_twelvedata_candidates(asset: str) -> List[str]:
    """Combine DB-defined mappings with heuristic fallbacks for Twelve Data."""
    seen = set()
    ordered: List[str] = []

    for symbol in get_symbol_mappings(asset, "twelvedata"):
        sym = (symbol or "").strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ordered.append(sym)

    for symbol in _base_twelvedata_candidates(asset):
        if symbol in seen:
            continue
        seen.add(symbol)
        ordered.append(symbol)

    if not ordered and asset:
        ordered.append(asset.strip().upper())

    return ordered
