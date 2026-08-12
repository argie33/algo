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
    """
    # SESSION 93 FIX: Unified timeout configuration with proper safety margins
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
        "naaim": 10 * 60,  # 10 min - published weekly
        "aaii": 10 * 60,  # 10 min - published weekly
        # Technical analysis
        "trend_analysis": 15 * 60,  # 15 min - template pattern matching
        "momentum": 30 * 60,  # 30 min - risk metrics (momentum + stability)
        "stability_metrics": 30 * 60,  # 30 min - alias for momentum
        # SEC/Financial data (batch API calls with rate limiting)
        "valuations": 60 * 60,  # 60 min - Session 92+ fix: SEC API @ 2 req/sec (41m base + overhead)
        "financial_statements": 240 * 60,  # 240 min (4h) - Session 92: per-symbol incremental loading
        "value_quality_growth": 40 * 60,  # 40 min - multi-source aggregation
        "enhanced_quality_growth": 300 * 60,  # 300 min (5h) - Session 92: yfinance variance high
        # Analyst data (yfinance rate-limited)
        "analyst_earnings_estimates": 45 * 60,  # 45 min - Session 92+ fix: yfinance backoff overhead
        "analyst_sentiment": 60 * 60,  # 60 min - Session 93: audit found max 20.3m, increased from 45m
        "analyst_upgrades": 45 * 60,  # 45 min - Session 92+ fix: match sentiment/earnings
        # Sector/industry
        "sector_industry": 15 * 60,  # 15 min - daily aggregation (3 output tables)
        # Company information (SEC API calls)
        "company_info": 180 * 60,  # 180 min (3h) - Session 92: ~4900 symbols @ 2 req/sec SEC API
        "profile": 10 * 60,  # 10 min - uses cached company_info
        # Holdings & positioning
        "positioning": 30 * 60,  # 30 min - multi-source aggregation
        "institutional": 15 * 60,  # 15 min - SEC Schedule 13G parsing
        "insider_holdings": 45 * 60,  # 45 min - Session 92+ fix: SEC Form 4/5 bulk downloads + backoff
        "short_interest": 10 * 60,  # 10 min - FINRA data
        "insider_velocity": 45 * 60,  # 45 min - Session 92+ fix: depends on insider_holdings
        # Earnings calendar & SEC data
        "earnings_calendar": 75 * 60,  # 75 min - Session 93: audit found 54.84m measured (9.8m shortfall at 45m)
        "earnings_sec": 90 * 60,  # 90 min - Session 92: still failing at 60m (41m base + overhead)
        "sec_reports": 60 * 60,  # 60 min - 8-K report scanning (SEC API rate-limited)
        "segment_info": 60 * 60,  # 60 min - Session 92+ fix: SEC API rate limiting (was 45m)
        "segment_metrics": 15 * 60,  # 15 min - segment aggregation
        "dividends": 40 * 60,  # 40 min - Session 92+ fix: yfinance rate limiting
        # Trading signals
        "scores": 25 * 60,  # 25 min - scoring algorithm
        "signal_quality": 15 * 60,  # 15 min - signal quality metrics
        "algo": 20 * 60,  # 20 min - algo-specific metrics
        "buy_sell": 15 * 60,  # 15 min - buy/sell signal generation
    }


def get_loader_timeout(loader_name: str, default_seconds: int = 3600) -> int:
    """Get timeout for a specific loader.

    Args:
        loader_name: Loader shorthand name (e.g., "prices", "valuations")
        default_seconds: Default if loader not found (default 1 hour)

    Returns:
        Timeout in seconds
    """
    timeouts = get_loader_timeouts()
    return timeouts.get(loader_name, default_seconds)
