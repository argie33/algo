"""Convert this codebase's own ticker convention to yfinance's expected symbol format.

FIXED 2026-08-19 (goal session continuation - "which factor inputs are missing the most"
audit): our own listings use the NYSE/NASDAQ dot convention for multi-class share tickers
(BRK.B, BF.B, HEI.A, ...) - the same convention load_institutional_holdings_13f.py's
crosswalk fix (2026-08-18) documents OpenFIGI/Bloomberg diverging from via a SLASH
("TICKER/A"). yfinance diverges the same way via a HYPHEN instead: live-verified
`yf.Ticker("BRK.B").earnings_estimate` returns an empty DataFrame (silently indistinguishable
from "no analyst coverage") while `yf.Ticker("BRK-B").earnings_estimate` returns the real,
current consensus data. Every yfinance-backed loader in this codebase (analyst_earnings_
estimates, analyst_upgrade_downgrade, analyst_sentiment_analysis, and the yfinance-fallback
paths in load_enhanced_quality_growth_metrics.py / yfinance_financials.py) passed the raw
dot-convention symbol straight to `yf.Ticker()`, silently losing real analyst/financials
coverage for all 23 active dot-suffixed symbols (BRK.A/BRK.B, HEI.A, LEN.B, MOG.A/MOG.B,
TAP.A, GEF.B, WSO.B, and more) - live-confirmed via BRK.B/BF.B (empty) vs BRK-B/BF-B (real,
4-row DataFrames).

FIXED 2026-08-21 (goal session - "is missing data really missing, or are we doing it wrong
again"): this function was a second, incomplete copy of normalization logic that already
existed in `utils/data/source_router.py::_normalize_yfinance_symbol` (fixed there 2026-08-03),
which also converts this codebase's '$'-suffix preferred-share convention (e.g. "MET$E",
"SCE$L") to yfinance's "-P" + series-letter form (e.g. "MET-PE"). This copy only had the
dot-to-hyphen half, so every '$'-suffix symbol passed through the 6 call sites above (all in
this file's importers) reached `yf.Ticker()` unconverted and 404'd/returned empty -
indistinguishable from genuine "no analyst coverage" or "no data", the exact same failure
mode the dot-suffix fix above already documents. Live-confirmed against the local DB:
SCE$L (SCE Trust VI) is currently `active=true` with no "Preferred"/"Depositary"/etc. token
in its security_name to exclude it via `get_active_symbols(exclude_etfs=True)`'s name filter,
so it reaches these loaders as a real, unresolved gap. Per the "same logic in more than one
place is a bug" rule (see MEMORY.md Signals section), `source_router.py` now delegates to
this function instead of keeping its own copy - this is the single source of truth.
"""

import re


def to_yfinance_symbol(symbol: str) -> str:
    """Return the yfinance-compatible form of an internal ticker symbol.

    Two independent notation mismatches vs. yfinance:
    - Multi-class shares use a '.'-suffix here (e.g. "BRK.B") but yfinance requires a
      hyphen ("BRK-B").
    - Preferred/depositary shares use a '$'-suffix here (e.g. "MET$E") but yfinance
      requires "-P" + the series letter ("MET-PE").
    Order matters: '.' must be replaced before '$' since no symbol in this dataset mixes
    both, but doing '.' first keeps behavior identical to the pre-existing single-purpose
    replacement this consolidates.
    """
    if "." in symbol:
        symbol = symbol.replace(".", "-")
    if "$" in symbol:
        symbol = re.sub(r"\$([A-Z]+)", r"-P\1", symbol)
    return symbol
