#!/usr/bin/env python3
"""Centralized loader timeout configuration.

CRITICAL: Single source of truth for all loader timeouts. Both
local_loader_scheduler.py and phase1_failsafe_retry.py MUST import from here
to prevent the timeout-mismatch brittleness that caused Monday cascades
(Session 93 root cause: local_loader_scheduler had 75min for earnings_calendar
while phase1 retry had 45min, causing Friday timeouts to never recover).

Timeouts calibrated per Session 92-93 real-world measurements:
- Includes safety margins (50-150% above observed max runtime)
- Accounts for SEC API rate limiting (2 req/sec = 40-60min base for full universe)
- Accounts for yfinance circuit-breaker backoff (429/503 responses need retry overhead)
- Accounts for database lock contention (local dev concurrent sessions slow load/retry)

All values are SECONDS (multiply by 60 for minutes in comments).
"""


def get_loader_timeouts() -> dict[str, int]:
    """Return authoritative loader timeout configuration.

    Returns:
        Dict mapping loader shorthand names to timeout seconds
        Also includes individual financial statement table names for failsafe retry lookup
    """
    # SESSION 93 FIX: Unified timeout configuration with proper safety margins
    # SESSION 94 FIX: Added individual financial statement table mappings
    # to prevent registry mismatch when status_manager checks table names
    # Each timeout = measured_max + safety_margin_for_variance_and_retries
    # Session 92/93 measured runtimes:
    # - prices (full universe): 761m measured (Session 92 comment), was 600m (NEGATIVE margin)
    # - earnings_calendar: 54.84m measured (Session 93 audit), was 45m (9.8m shortfall)
    # - company_info: 40+ min base, +retry overhead → 120m insufficient
    # - financial_statements: ~120-150m actual (per-symbol rate-limited)
    # - enhanced_quality_growth: yfinance hangs 40+ min, variance high
    # - valuations: 41m base @ 2req/sec SEC API, +overhead
    # - earnings_sec: 41m base @ 2req/sec SEC API, +overhead
    # - analyst_sentiment: max observed 20.3m (Session 93), was 45m with only 32% margin
    return {
        # Core pricing & market data (heaviest workloads)
        "prices": 900 * 60,  # 900 min - Session 93: 761m measured + 140m safety buffer
        "technical": 30 * 60,  # 30 min - vectorized in-database
        "constituents": 10 * 60,  # 10 min - static symbol list
        "economic": 10 * 60,  # 10 min - FRED + DXY index
        # Market status & sentiment
        "market_status": 15 * 60,  # 15 min - 3 tables (health/exposure/sentiment)
        # Individual market status output tables (Session 275+ consolidation)
        # load_market_status_daily.py writes to these three, may look up timeout by table_name
        "market_health_daily": 15 * 60,  # 15 min - Part of consolidated market_status
        "market_exposure_daily": 15 * 60,  # 15 min - Part of consolidated market_status
        "market_sentiment": 15 * 60,  # 15 min - Part of consolidated market_status
        "naaim": 10 * 60,  # 10 min - published weekly
        "aaii": 10 * 60,  # 10 min - published weekly
        # Technical analysis
        "trend_analysis": 15 * 60,  # 15 min - template pattern matching
        "momentum": 30 * 60,  # 30 min - risk metrics (momentum + stability)
        "stability_metrics": 30 * 60,  # 30 min - alias for momentum
        # SEC/Financial data (batch API calls with rate limiting)
        "valuations": 60 * 60,  # 60 min - Session 92+ fix: SEC API @ 2 req/sec (41m base + overhead)
        "financial_statements": 360 * 60,  # 360 min (6h) - Session 96+: Increased from 240m; SEC rate limiting requires additional safety margin
        # Individual financial statement tables (SESSION 94 FIX: prevent registry mismatch)
        # These are output tables from financial_statements loader, need same timeout as parent
        "annual_income_statement": 120 * 60,  # 120 min - One of 6 statement types from financial_statements
        "annual_balance_sheet": 120 * 60,  # 120 min - One of 6 statement types from financial_statements
        "annual_cash_flow": 120 * 60,  # 120 min - One of 6 statement types from financial_statements
        "quarterly_income_statement": 120 * 60,  # 120 min - One of 6 statement types from financial_statements
        "quarterly_balance_sheet": 120 * 60,  # 120 min - One of 6 statement types from financial_statements
        "quarterly_cash_flow": 120 * 60,  # 120 min - One of 6 statement types from financial_statements
        "value_quality_growth": 40 * 60,  # 40 min - multi-source aggregation
        "enhanced_quality_growth": 300 * 60,  # 300 min (5h) - Session 92: yfinance variance high
        # Analyst data (yfinance rate-limited)
        "analyst_earnings_estimates": 45 * 60,  # 45 min - Session 92+ fix: yfinance backoff overhead
        "analyst_sentiment": 60 * 60,  # 60 min - Session 93: audit found max 20.3m, increased from 45m
        "analyst_upgrades": 45 * 60,  # 45 min - Session 92+ fix: match sentiment/earnings
        # Sector/industry
        "sector_industry": 15 * 60,  # 15 min - daily aggregation (3 output tables)
        # Company information (SEC API calls)
        "company_info": 300 * 60,  # 300 min (5h) - Session 96+: Increased from 180m to account for rate-limiting variance and retry overhead; observed failures at 60m indicate undersized margin
        "company_info_sec": 300 * 60,  # 300 min - Alias for company_info (table name in database)
        "profile": 120
        * 60,  # 120 min - SESSION 96+: Increased from 45m; yfinance rate-limiting requires more robust timeout to prevent Monday cascades
        "company_profile": 120 * 60,  # 120 min - Alias for profile
        # Holdings & positioning
        "positioning": 30 * 60,  # 30 min - multi-source aggregation
        "positioning_metrics": 30 * 60,  # 30 min - Alias for positioning (table name in database)
        "institutional": 15 * 60,  # 15 min - SEC Schedule 13G parsing
        "insider_holdings": 45 * 60,  # 45 min - Session 92+ fix: SEC Form 4/5 bulk downloads + backoff
        "insider_holdings_sec": 45 * 60,  # 45 min - Alias for insider_holdings
        "short_interest": 10 * 60,  # 10 min - FINRA data
        "insider_velocity": 45 * 60,  # 45 min - Session 92+ fix: depends on insider_holdings
        "insider_transaction_velocity": 45 * 60,  # 45 min - Alias for insider_velocity
        # Earnings calendar & SEC data
        "earnings_calendar": 75 * 60,  # 75 min - Session 93: audit found 54.84m measured (9.8m shortfall at 45m)
        "earnings_calendar_sec": 90 * 60,  # 90 min - SEC-specific version needs more time
        "earnings_sec": 90 * 60,  # 90 min - Session 92: still failing at 60m (41m base + overhead)
        "sec_reports": 60 * 60,  # 60 min - 8-K report scanning (SEC API rate-limited)
        "segment_info": 360
        * 60,  # 360 min (6h) - SESSION 96+: Increased from 240m; SEC API rate limiting very tight; observed failures suggest need for additional buffer
        "sec_segment_info": 360 * 60,  # 360 min - Alias for segment_info (XBRL parsing is heavyweight)
        "segment_metrics": 15 * 60,  # 15 min - segment aggregation
        "dividends": 60
        * 60,  # 60 min - SESSION 94+ FIX: yfinance-based, 4900 symbols. Was 40m, increased due to rate-limit backoff overhead
        "dividend_data": 60 * 60,  # 60 min - Alias for dividends
        "sec_valuations": 60 * 60,  # 60 min - SEC-specific valuations
        # Trading signals
        "scores": 25 * 60,  # 25 min - scoring algorithm
        "stock_scores": 25 * 60,  # 25 min - Alias for scores
        "signal_quality": 15 * 60,  # 15 min - signal quality metrics
        "signal_quality_scores": 15 * 60,  # 15 min - Alias (actual table name)
        "algo": 20 * 60,  # 20 min - algo-specific metrics
        "algo_metrics_daily": 20 * 60,  # 20 min - Alias (actual table name)
        "buy_sell": 15 * 60,  # 15 min - buy/sell signal generation
        "buy_sell_daily": 15 * 60,  # 15 min - Alias for buy_sell
        # SESSION 98 FIX: Add all missing table-name aliases
        # These are actual output table names from loaders that may look up by table_name
        "price_daily": 900 * 60,  # Alias for prices
        "price_weekly": 900 * 60,  # Alias for prices
        "price_monthly": 900 * 60,  # Alias for prices
        "etf_price_daily": 900 * 60,  # Alias for prices
        "etf_price_weekly": 900 * 60,  # Alias for prices
        "etf_price_monthly": 900 * 60,  # Alias for prices
        "technical_data_daily": 30 * 60,  # Alias for technical
        "trend_template_data": 90 * 60,  # Alias for trend_analysis
        "stock_symbols": 10 * 60,  # Alias for constituents
        "etf_symbols": 10 * 60,  # Alias for constituents
        "economic_data": 10 * 60,  # Alias for economic
        "aaii_sentiment": 10 * 60,  # Alias for aaii
        "analyst_upgrade_downgrade": 45 * 60,  # Alias for analyst_upgrades
        "analyst_sentiment_analysis": 60 * 60,  # Alias for analyst_sentiment
        "quality_metrics": 40 * 60,  # Output of value_quality_growth loader
        "growth_metrics": 40 * 60,  # Output of value_quality_growth loader
        "value_metrics": 40 * 60,  # Output of value_quality_growth loader
        "momentum_metrics": 30 * 60,  # Alias for stability_metrics
        "institutional_holdings_13f": 45 * 60,  # Alias for institutional
        "short_interest_finra": 10 * 60,  # Alias for short_interest
        "sec_segment_metrics": 15 * 60,  # Alias for segment_metrics
        "sector_ranking": 15 * 60,  # Output of sector_industry loader
        "industry_ranking": 15 * 60,  # Output of sector_industry loader
        "sector_performance": 15 * 60,  # Output of sector_industry loader
        "current_reports_8k": 20 * 60,  # Alias for sec_reports
    }


def get_loader_timeout(loader_name: str, default_seconds: int | None = None) -> int:
    """Get timeout for a specific loader.

    CRITICAL (Session 96): Fail-fast instead of silently defaulting to 3600s.
    Silent 3600s default was truncating long loaders (company_info_sec: 180m config → 60m timeout),
    causing cascading Monday brittleness. All loaders must be explicitly registered.

    Args:
        loader_name: Loader shorthand name (e.g., "prices", "valuations")
        default_seconds: Default if loader not found. If None, raises error (fail-fast).

    Returns:
        Timeout in seconds

    Raises:
        RuntimeError: If loader not found and default_seconds is None
    """
    import logging
    import os

    logger = logging.getLogger(__name__)
    timeouts = get_loader_timeouts()

    if loader_name in timeouts:
        timeout_value = timeouts[loader_name]
        # Log the timeout for visibility
        if os.getenv("LOADER_TIMEOUT_DEBUG", "").lower() in ("1", "true", "yes"):
            logger.info(
                f"[LOADER_TIMEOUT] Using configured timeout for '{loader_name}': {timeout_value}s ({timeout_value // 60}m)"
            )
        return timeout_value

    if default_seconds is not None:
        logger.warning(
            f"[LOADER_TIMEOUT] Loader '{loader_name}' not in config, using provided default: {default_seconds}s ({default_seconds // 60}m). "
            f"Should register in loaders/loader_timeout_config.py."
        )
        return default_seconds

    raise RuntimeError(
        f"[LOADER_TIMEOUT] Loader '{loader_name}' not found in config. "
        f"Register in loaders/loader_timeout_config.py or pass explicit default_seconds. "
        f"Available loaders: {sorted(timeouts.keys())}"
    )
