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
"""


def to_yfinance_symbol(symbol: str) -> str:
    """Return the yfinance-compatible form of an internal ticker symbol.

    Only the dot-to-hyphen substitution is needed - yfinance accepts every other character
    our own tickers use unchanged.
    """
    return symbol.replace(".", "-")
