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


def get_alpaca_base_url(execution_mode: str | None = None) -> str:
    """Return Alpaca API base URL.

    Used by: market_events, position_monitor, execution-monitor Lambda, reconciliation.

    CRITICAL: this used to unconditionally return the paper-trading URL regardless of
    APCA_API_BASE_URL/execution_mode - every caller above hits this directly (not through
    algo/trading/executor_strategies.py's mode-aware resolve_base_url(), which is only wired
    into the actual order-submission path in executor.py). That was fixed to honor
    APCA_API_BASE_URL directly, but that first fix checked ONLY whether the env var was set -
    not the same three-condition live-intent gate AutoExecutionMode._check_live_intent() uses
    to decide whether the order-submission path itself goes live
    (ALGO_LIVE_TRADING == "I_UNDERSTAND_REAL_MONEY" AND ALPACA_PAPER_TRADING != "true" AND the
    URL doesn't say "paper" - AND execution_mode == "auto"; paper/review modes always stay on
    paper regardless of the URL env var). That gap is real: an operator can set
    APCA_API_BASE_URL=https://api.alpaca.markets ahead of a future live cutover (e.g. staging
    secrets) while ALGO_LIVE_TRADING is not yet acknowledged and execution_mode is still
    "paper" - executor.py correctly keeps submitting orders to paper, but this function would
    have started pointing halt detection (market_events), stale-order cancellation, and
    position-quantity reconciliation (position_monitor) at the LIVE account using the shared
    credentials, all while order submission stayed on paper. Same "wrong account" failure mode
    as the original bug, just inverted.

    Now, when execution_mode is provided, mirrors AutoExecutionMode's full gate: only trusts
    APCA_API_BASE_URL as live when execution_mode == "auto" AND the same live-intent
    conditions hold; every other mode (or a failed gate) returns paper, exactly matching what
    executor.py would actually do with order submission. When execution_mode is omitted (e.g.
    lambda/execution-monitor's get_alpaca_credentials(), which has no convenient config
    object at its call site), falls back to the env-var-presence check as before - callers
    that can pass execution_mode should.
    """
    configured_url = os.getenv("APCA_API_BASE_URL")

    if execution_mode is not None:
        if execution_mode.lower() != "auto":
            return "https://paper-api.alpaca.markets"
        live_ack = os.getenv("ALGO_LIVE_TRADING", "").strip()
        paper_flag = os.getenv("ALPACA_PAPER_TRADING", "true").strip().lower()
        url_says_paper = "paper" in (configured_url or "").lower()
        live_intent = live_ack == "I_UNDERSTAND_REAL_MONEY" and paper_flag != "true" and not url_says_paper
        if not live_intent:
            return "https://paper-api.alpaca.markets"
        return configured_url or "https://api.alpaca.markets"

    return configured_url or "https://paper-api.alpaca.markets"


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
