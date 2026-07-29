"""Configured taxonomies for Data Engineering (no watchlist in this layer).

- MARKET_THEME_TAXONOMY: the fixed list of general market themes the Theme skill may
  assign (Req 11). The LLM must choose only from this list.
- SECTORS: the industry labels the Label skill may assign (Req 10).
- COMPANY_ALIASES / MACRO_ALIASES: a small built-in alias map that resolves common
  slang cheaply before falling back to the LLM (Req 9).
"""
from __future__ import annotations

# General market themes (Req 11). Extend freely — this is the whole allowed set.
MARKET_THEME_TAXONOMY: list[str] = [
    "Technology",
    "Artificial Intelligence",
    "Semiconductors",
    "Healthcare",
    "Financials",
    "Energy",
    "Oil & Gas",
    "Solar",
    "Clean Energy",
    "Industrials",
    "Consumer",
    "Real Estate",
    "Utilities",
    "Materials",
]

# Industry / sector labels (Req 10).
SECTORS: list[str] = [
    "Technology",
    "Consumer Discretionary",
    "Healthcare",
    "Industrials",
    "Financials",
    "Communication Services",
    "Consumer Staples",
    "Energy",
    "Real Estate",
    "Utilities",
    "Basic Materials",
]

UNCLASSIFIED = "Unclassified"

# The fixed bear-market signpost checklist the Macro Analyst scores every run
# (app/council/macro.py). Deliberately closed: a *fixed* list is what makes the tracker
# comparable run-over-run — the model grades these and only these, it never invents a
# signpost. (key, display name, what would trigger it).
BEAR_SIGNPOSTS: tuple[tuple[str, str, str], ...] = (
    ("yield_curve", "Yield Curve",
     "2s10s inverted, or re-steepening out of a deep inversion"),
    ("credit_spreads", "Credit Spreads",
     "High-yield / investment-grade spreads widening off the lows"),
    ("unemployment", "Labour Market",
     "Unemployment rising off cycle lows; layoffs broadening beyond one sector"),
    ("valuation", "Valuation",
     "Index multiples stretched versus history; thin or negative equity risk premium"),
    ("growth", "Growth Momentum",
     "ISM / PMI rolling over — below 50 and still falling"),
    ("breadth", "Market Breadth",
     "Leadership narrowing into a handful of mega-caps; equal-weight lagging"),
    ("policy", "Policy & Liquidity",
     "Tightening, QT, or restrictive real rates draining system liquidity"),
    ("inflation", "Inflation Re-acceleration",
     "Inflation turning back up and forcing a more hawkish policy path"),
    ("consumer", "Consumer Stress",
     "Delinquencies rising, savings drawn down, visible trade-down behaviour"),
    ("sentiment", "Positioning & Euphoria",
     "Speculative froth, rising leverage, retail chasing the tape"),
)

SIGNPOST_STATUSES: tuple[str, ...] = ("Triggered", "Watch", "Clear")

# Built-in alias → canonical ticker (Req 9.1). Lowercased keys.
COMPANY_ALIASES: dict[str, str] = {
    "zuck": "$META",
    "meta": "$META",
    "facebook": "$META",
    "fb": "$META",
    "nvidia": "$NVDA",
    "nvda": "$NVDA",
    "jensen": "$NVDA",
    "micron": "$MU",
    "mu": "$MU",
    "apple": "$AAPL",
    "tim cook": "$AAPL",
    "tesla": "$TSLA",
    "musk": "$TSLA",
}

# Built-in alias → canonical macro entity (Req 9.2). Lowercased keys.
MACRO_ALIASES: dict[str, str] = {
    "powell": "Federal_Reserve",
    "j-pow": "Federal_Reserve",
    "jpow": "Federal_Reserve",
    "the fed": "Federal_Reserve",
    "fed": "Federal_Reserve",
    "fomc": "Federal_Reserve",
    "federal reserve": "Federal_Reserve",
}
