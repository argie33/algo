"""Name-based classification helper for load_market_constituents.py, split out
(2026-09-14) to keep that already-oversized file from growing further (file-size-ratchet)
rather than because this logic is reused elsewhere.
"""

import re


def is_fund_or_etf_by_name(name: str) -> bool:
    """Secondary name-based fund/ETF catch used by fetch_global's write path, independent of
    should_exclude()/EXCLUSION_PATTERNS in load_market_constituents.py (this one runs on rows
    that already passed _is_excluded and the upstream feed's own ETF=Y flag).

    LIVE-CONFIRMED BUG 2026-09-14: this used to be a plain substring check
    (`"etf" in name.lower() or "fund" in name.lower()`), which false-positived on NFLX
    ("Netflix, Inc. - Common Stock") - "etf" is a substring of "n-ETF-lix", nothing to do
    with being an ETF/fund. This silently dropped NFLX (a real, liquid mega-cap, present
    with clean Test Issue=N/Financial Status=N/ETF=N fields in the upstream NASDAQ feed)
    from stock_symbols entirely - not active=false, ZERO row, so every downstream
    pillar/score for NFLX was simply absent, not just unscored. Live-swept the full
    current nasdaqlisted.txt+otherlisted.txt universe (5,681 non-ETF-flagged names): NFLX
    was the ONLY "etf"-substring false positive, and zero "fund"-substring false positives
    exist (every other "fund" hit is a real closed-end fund/BDC name, correctly excluded on
    other grounds - see load_market_constituents.py's GOVERNANCE 2026-09-01 comment on
    ARCC/GBDC/etc.). EXCLUSION_PATTERNS in that file already made this exact fix for
    `\\bfund\\b` and deliberately dropped a bare `\\betf\\b` for the identical reason (see
    its own NOTE) - this separate inline check had silently regressed to the sloppier
    substring form. Word-boundary regex fixes the collision without changing any other
    symbol's classification.
    """
    return bool(re.search(r"\betf\b", name, re.IGNORECASE) or re.search(r"\bfund\b", name, re.IGNORECASE))
