"""API endpoint URLs for external data sources.

Centralizes endpoint configuration to support:
- Swapping between different API versions
- Environment-specific endpoints (test vs production)
- Rate limit and feature parity considerations
"""

import os


def get_yahoo_finance_url() -> str:
    """Return Yahoo Finance API base URL.

    Used by: algo_data_patrol (cross-validation), intraday pricing
    Pattern: https://query1.finance.yahoo.com
    """
    return "https://query1.finance.yahoo.com"


def get_alpaca_base_url() -> str:
    """Return Alpaca API base URL.

    Used by: market_events, position_monitor, execution-monitor Lambda, reconciliation.

    CRITICAL: this used to unconditionally return the paper-trading URL regardless of
    APCA_API_BASE_URL/execution_mode - every caller above hits this directly (not through
    algo/trading/executor_strategies.py's mode-aware resolve_base_url(), which is only wired
    into the actual order-submission path in executor.py). Once real live trading is enabled
    (execution_mode=auto + ALGO_LIVE_TRADING + APCA_API_BASE_URL=https://api.alpaca.markets),
    Alpaca credentials are a single shared key/secret pair (see credential_manager.py - there
    is no separate "live" vs "paper" credential concept in this codebase, only the base URL
    differs) - so these callers would silently query/mutate the PAPER account's halt status,
    stale-order cancellation, and position quantities using live-account credentials, while
    believing they were operating on the real account. Now honors APCA_API_BASE_URL (the same
    env var executor.py's strategy reads) so these calls track whatever endpoint the system is
    actually configured for, falling back to paper only when that env var is unset (matches
    the safe default every non-live environment already relies on).
    """
    return os.getenv("APCA_API_BASE_URL") or "https://paper-api.alpaca.markets"


def get_alpaca_data_url() -> str:
    """Return Alpaca Market Data API base URL.

    Used by: exit_engine, market data retrieval
    Pattern: https://data.alpaca.markets
    Requires: ALPACA_API_KEY environment variable
    """
    return "https://data.alpaca.markets"


def get_fred_url() -> str:
    """Return FRED API base URL.

    Used by: economic_data (consolidated FRED + DXY) loader
    Pattern: https://api.stlouisfed.org/fred
    Requires: FRED_API_KEY environment variable
    """
    return "https://api.stlouisfed.org/fred"


def get_aaii_sentiment_url() -> str:
    """Return AAII (American Association of Individual Investors) sentiment Excel download URL.

    Used by: load_aaii_sentiment loader
    Pattern: https://www.aaii.com/files/surveys/sentiment.xls
    Note: Direct Excel download (no API key required). Returns XLS or XLSX depending on AAII.
    """
    return "https://www.aaii.com/files/surveys/sentiment.xls"
