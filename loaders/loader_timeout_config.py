#!/usr/bin/env python3
"""Centralized loader timeout configuration.

CRITICAL: Single source of truth for all loader timeouts. Both
local_loader_scheduler.py and phase1_failsafe_retry.py MUST import from here
to prevent the timeout-mismatch brittleness that caused Monday cascades
(Session 93 root cause: local_loader_scheduler had 75min for earnings_calendar
while phase1 retry had 45min, causing Friday timeouts to never recover).

Timeouts calibrated per Session 92-93 real-world measurements + Session 99 production observations:
- Includes safety margins (50-200% above observed max runtime)
- Accounts for SEC API rate limiting (2 req/sec = 40-60min base for full universe)
- Accounts for yfinance circuit-breaker backoff (429/503 responses need retry overhead)
- Accounts for database lock contention (local dev concurrent sessions slow load/retry)
- SESSION 99 FIX: Added 30-100% additional margins after discovering yfinance rate limiting causes
  exponential slowdown mid-run (price_daily: 19+h actual vs 15h configured)

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
    # SESSION 99 FIX: Increased all rate-limited loaders by 30-100% after discovering
    #   yfinance/SEC rate limiting causes exponential slowdown mid-run, not just linear slowdown
    # Each timeout = measured_max + safety_margin_for_variance_and_retries
    # Session 92/93 measured runtimes (PRE-RATE-LIMITING-SLOWDOWN observations):
    # - prices (full universe): 761m measured (Session 92 comment), was 600m (NEGATIVE margin)
    #   SESSION 99: Actual 19+h observed due to yfinance rate limiting → 24h config
    # - earnings_calendar: 54.84m measured (Session 93 audit), was 45m (9.8m shortfall)
    #   SESSION 99: Increased to 120m for rate limiting margin
    # - company_info: 40+ min base, +retry overhead → 120m insufficient
    #   SESSION 99: Increased to 540m (9h) for SEC rate limiting
    # - financial_statements: ~120-150m actual (per-symbol rate-limited)
    #   SESSION 99: Increased to 540m (9h) for SEC rate limiting
    # - enhanced_quality_growth: yfinance hangs 40+ min, variance high
    # - valuations: 41m base @ 2req/sec SEC API, +overhead
    #   SESSION 99: Increased to 90m for SEC rate limiting
    # - earnings_sec: 41m base @ 2req/sec SEC API, +overhead
    #   SESSION 99: Increased to 150m for SEC rate limiting
    # - analyst_sentiment: max observed 20.3m (Session 93), was 45m with only 32% margin
    #   SESSION 99: Increased to 120m for yfinance rate limiting
    return {
        # Core pricing & market data (heaviest workloads)
        # SESSION 99 FIX: prices increased from 900m to 1440m (24h)
        # Reason: Actual measured runtime is 19+h due to yfinance rate limiting slowdown.
        # Circuit breaker halts at 92.2% completion because ETA exceeds budget. Now set budget
        # high enough to accommodate the exponential slowdown observed mid-run.
        "prices": 1440 * 60,  # 1440 min (24h) - accommodate yfinance rate limiting slowdown
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
        # SESSION 99 FIX: All increased by 30-50% for SEC rate limiting
        "valuations": 90 * 60,  # 90 min - Session 99: increased from 60m (50% margin for SEC 2req/sec)
        "financial_statements": 540 * 60,  # 540 min (9h) - Session 99: increased from 360m for SEC XBRL parsing
        # FIX 2026-08-18: terraform's ECS task-def key for this loader is "financials_all", not
        # "financial_statements" - same name-mismatch blind spot as stock_prices_daily, which
        # let terraform's timeout drift to 14400s (44% of this budget) undetected by the
        # regression test.
        "financials_all": 540 * 60,  # Alias for financial_statements (terraform ECS task-def key)
        # Individual financial statement tables (SESSION 94 FIX: prevent registry mismatch)
        # These are output tables from financial_statements loader, MUST use parent timeout
        # SESSION 100 FIX: All statement tables share the same 540m loader execution budget
        "annual_income_statement": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "annual_balance_sheet": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "annual_cash_flow": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "quarterly_income_statement": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "quarterly_balance_sheet": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "quarterly_cash_flow": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "ttm_income_statement": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "ttm_cash_flow": 540 * 60,  # 540 min - Part of consolidated financial_statements load
        "value_quality_growth": 40 * 60,  # 40 min - multi-source aggregation
        "enhanced_quality_growth": 300 * 60,  # 300 min (5h) - Session 92: yfinance variance high
        # Analyst data (yfinance rate-limited)
        # SESSION 99 FIX: All increased by 50-100% for yfinance rate limiting
        "analyst_earnings_estimates": 90 * 60,  # 90 min - Session 99: increased from 45m (100% margin)
        "analyst_sentiment": 120 * 60,  # 120 min - Session 99: increased from 60m (100% margin)
        "analyst_upgrades": 90 * 60,  # 90 min - Session 99: increased from 45m (100% margin)
        # Sector/industry
        "sector_industry": 15 * 60,  # 15 min - daily aggregation (3 output tables)
        # Company information (SEC API calls)
        # SESSION 99 FIX: increased from 300m (5h) to 540m (9h) for SEC rate limiting at 2req/sec
        "company_info": 540 * 60,  # 540 min (9h) - Session 99: SEC API @ 2req/sec for 4900 symbols
        "company_info_sec": 540 * 60,  # 540 min - Alias for company_info (table name in database)
        # SESSION 99 FIX: increased from 120m to 180m for yfinance rate limiting
        "profile": 180 * 60,  # 180 min - SESSION 99: increased from 120m; yfinance rate-limiting requires more margin
        "company_profile": 180 * 60,  # 180 min - Alias for profile
        # Holdings & positioning
        "positioning": 30 * 60,  # 30 min - multi-source aggregation
        "positioning_metrics": 30 * 60,  # 30 min - Alias for positioning (table name in database)
        # FIX 2026-08-18: was 15*60 (900s), 3x below the real budget. "institutional" and
        # "institutional_holdings_13f" (below) are the SAME script (loader_registry.py maps
        # "institutional" -> load_institutional_holdings_13f.py) and the ECS task-def timeout
        # for it is 2700s/45min (terraform/modules/loaders/main.tf), matching
        # institutional_holdings_13f's value here - but this shorthand name (the one actually
        # used by local_loader_scheduler.py's "reference" pipeline loader list) was never
        # synced to it, so every run through the shorthand enforced only a 900s Python-level
        # timeout regardless of the real 2700s budget.
        "institutional": 45 * 60,  # 45 min - SEC Form 13F institutional holdings parsing
        "insider_holdings": 45 * 60,  # 45 min - Session 92+ fix: SEC Form 4/5 bulk downloads + backoff
        "insider_holdings_sec": 45 * 60,  # 45 min - Alias for insider_holdings
        "short_interest": 10 * 60,  # 10 min - FINRA data
        "insider_velocity": 45 * 60,  # 45 min - Session 92+ fix: depends on insider_holdings
        "insider_transaction_velocity": 45 * 60,  # 45 min - Alias for insider_velocity
        # Earnings calendar & SEC data
        # SESSION 99 FIX: All increased by 25-100% for SEC rate limiting
        # FIX 2026-08-18: was 120m (Session 99, based on 54.84m measured + 100% margin).
        # Live-confirmed via logs/load_earnings_calendar_*.log: two real recent full-universe
        # runs took 63.9m and 75.3m - the loader's OWN internal SLA monitor already flagged
        # the 75.3m run as CRITICAL ("75.3 min elapsed (10 expected, warn at 30 min)"). Margin
        # over the 120m timeout has eroded from Session 99's 2.19x down to 1.59x as real-world
        # yfinance rate limiting has gotten worse over time - same trend that already forced
        # increases on current_reports_8k (120m->300m) and dividend_data (60m->150m). Raised
        # to 180m (2.4x margin over the worst observed run) before this one times out too.
        "earnings_calendar": 180 * 60,  # 180 min
        "earnings_calendar_sec": 150 * 60,  # 150 min - Session 99: increased from 90m for SEC rate limiting
        "earnings_sec": 150 * 60,  # 150 min - Session 99: increased from 90m (SEC heavy, 41m base + margin)
        # FIX 2026-08-17: was 120m (Session 99), never revisited after that pass. Live run
        # 2026-08-17 hard-timeout-killed at exactly 120m having reached only 2100/4930 symbols
        # (42.6%) at a measured ~17.5 symbols/min average (rate visibly degraded through the
        # run: ~130/min for the first 1500 symbols, dropping to ~6/min by the back half under
        # sustained SEC EDGAR load) - extrapolates to ~282m for the full universe, so the back
        # half of the alphabet silently lost 8-K data every run. 300m covers the extrapolated
        # full-universe runtime with margin, matching segment_info/sec_segment_info's existing
        # 540m for similarly SEC-XBRL-heavy work.
        "sec_reports": 400
        * 60,  # 400 min - 8-K report scanning, SEC rate-limited (2026-08-18: increased from 300m for phase2 timeout recovery)
        "segment_info": 540 * 60,  # 540 min (9h) - SESSION 99: increased from 360m; SEC XBRL parsing very slow
        "sec_segment_info": 540 * 60,  # 540 min - Alias for segment_info (XBRL parsing is heavyweight)
        "segment_metrics": 15 * 60,  # 15 min - segment aggregation
        # FIX 2026-08-17: was 60m (SESSION 94+), never got the SESSION 99 SEC-rate-limiting
        # pass the sibling SEC loaders (earnings_calendar/valuations/etc.) all received. Live
        # run 2026-08-17 hard-timeout-killed at exactly 60m having reached only 2900/4930
        # symbols (58.8%) at a measured ~39 symbols/min - extrapolates to ~126m for the full
        # universe, so the entire back half of the alphabet silently lost dividend data every
        # run. 150m matches the 100%+ margin convention used elsewhere in this file (e.g.
        # earnings_calendar_sec/earnings_sec) and covers the extrapolated full-universe runtime.
        "dividends": 150 * 60,  # 150 min - SEC XBRL per-symbol, 4900 symbols @ SEC rate limit
        "dividend_data": 150 * 60,  # 150 min - Alias for dividends
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
        # SESSION 99: Updated to match new timeout values
        "price_daily": 1440 * 60,  # Alias for prices (Session 99: 24h)
        "price_weekly": 1440 * 60,  # Alias for prices (Session 99: 24h)
        "price_monthly": 1440 * 60,  # Alias for prices (Session 99: 24h)
        "etf_price_daily": 1440 * 60,  # Alias for prices (Session 99: 24h)
        "etf_price_weekly": 1440 * 60,  # Alias for prices (Session 99: 24h)
        "etf_price_monthly": 1440 * 60,  # Alias for prices (Session 99: 24h)
        "technical_data_daily": 30 * 60,  # Alias for technical
        # FIX 2026-08-18 (loader-health review): was 90*60, diverging from trend_analysis
        # 15*60 despite the Alias-for comment (Session 98 copy-paste slip). No live-timeout
        # risk either way (real measured runtime ~5s), fixed for config-consistency.
        "trend_template_data": 15 * 60,  # Alias for trend_analysis
        # FIX 2026-08-18: terraform/modules/loaders/main.tf's ECS task-def key for the prices
        # loader is "stock_prices_daily", not "prices" - test_terraform_loader_timeouts_not_
        # less_than_python.py matches by name intersection, so without this alias it silently
        # never checked the most critical (CRITICAL LOADER, FAIL-CLOSED) loader in the pipeline.
        # Confirmed live: terraform had 54000s (15h) vs this loader's real 86400s (24h) budget.
        "stock_prices_daily": 1440 * 60,  # Alias for prices (terraform ECS task-def key)
        # FIX 2026-08-18: remaining terraform ECS task-def keys with no Python config match
        # (audited individually - each terraform value is already >= the real budget below,
        # so none of these were live drift risks, but registering them closes the same
        # name-mismatch blind spot for future changes).
        "market_constituents": 10 * 60,  # Alias for constituents (terraform ECS task-def key)
        "market_status_daily": 15 * 60,  # Alias for market_status (terraform ECS task-def key)
        "sector_industry_daily": 15 * 60,  # Alias for sector_industry (terraform ECS task-def key)
        "value_quality_growth_metrics": 40 * 60,  # Alias for value_quality_growth (terraform ECS task-def key)
        "enhanced_quality_growth_metrics": 300 * 60,  # Alias for enhanced_quality_growth (terraform ECS task-def key)
        "stock_symbols": 10 * 60,  # Alias for constituents
        "etf_symbols": 10 * 60,  # Alias for constituents
        "economic_data": 10 * 60,  # Alias for economic
        "aaii_sentiment": 10 * 60,  # Alias for aaii
        "analyst_upgrade_downgrade": 90 * 60,  # Alias for analyst_upgrades (Session 99: 90m)
        "analyst_sentiment_analysis": 120 * 60,  # Alias for analyst_sentiment (Session 99: 120m)
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
        "current_reports_8k": 400
        * 60,  # Alias for sec_reports (2026-08-18: increased from 300m for 3,183-row 8K timeout recovery)
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
