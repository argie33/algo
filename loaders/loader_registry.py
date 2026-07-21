#!/usr/bin/env python3
"""Canonical loader-script -> output-table(s) mapping.

Single source of truth, extracted after the exact same drift bug (hand-
maintained copies of this mapping silently falling out of sync with loader
renames/consolidations since Session 275) was found and independently fixed
in THREE different local health/audit scripts:
  - scripts/verify_loaders_health.py
  - scripts/audit_all_loaders.py
  - scripts/refresh_stale_loaders.py

All three had entries for loader scripts deleted or renamed since Session 275
(e.g. load_yfinance_snapshot.py, load_growth_metrics.py), and one
(load_earnings_calendar_sec.py) was mapped to the wrong table entirely -
'earnings_history' (a permanently-empty legacy table) instead of
'earnings_calendar_sec' (the table the loader actually writes to, confirmed
live: 353k+ rows updated daily). That misdirection made a healthy loader
report as broken while the table it actually populates was never checked.

Kept in sync with the active loader list in scripts/local_loader_scheduler.py
(the source used to reconcile all three fixes above) - update here first when
a loader is added, renamed, or consolidated, and the health/audit scripts
pick it up automatically instead of drifting independently again.
"""

# Loader script filename -> list of output tables it writes to. First table in
# the list is the loader's primary table.
LOADER_TABLES: dict[str, list[str]] = {
    "load_prices.py": [
        "price_daily",
        "price_weekly",
        "price_monthly",
        "etf_price_daily",
        "etf_price_weekly",
        "etf_price_monthly",
    ],
    "load_technical_indicators.py": ["technical_data_daily"],
    "load_trend_analysis.py": ["trend_template_data"],
    # Consolidated Session 275: replaces the old load_market_health_daily.py,
    # load_market_exposure_daily.py, load_market_sentiment.py.
    "load_market_status_daily.py": ["market_health_daily", "market_exposure_daily", "market_sentiment"],
    "load_naaim.py": ["naaim"],
    "load_aaii_sentiment.py": ["aaii_sentiment"],
    "load_short_interest_finra.py": ["short_interest_finra"],
    "load_company_info_sec.py": ["company_info_sec"],
    "load_earnings_calendar_sec.py": ["earnings_calendar_sec"],
    "load_market_constituents.py": ["stock_symbols", "etf_symbols"],
    # ttm_income_statement/ttm_cash_flow are deliberately excluded: the loader's
    # statement-type config still lists them as write targets, but
    # data_loader_status marks both DEPRECATED (confirmed live: 60-63 days
    # stale, everything else this loader writes is <1 day old) - listing them
    # here would make every audit script relying on this registry falsely
    # flag a healthy loader as CRITICAL/stale on a table nothing expects fresh
    # anymore. Worth a separate look at why the loader's config wasn't cleaned
    # up to match, but that's a distinct question from this mapping's accuracy.
    "load_financial_statements.py": [
        "annual_income_statement",
        "annual_balance_sheet",
        "annual_cash_flow",
        "quarterly_income_statement",
        "quarterly_balance_sheet",
        "quarterly_cash_flow",
    ],
    "load_sec_valuations.py": ["sec_valuations"],
    "load_sec_cash_flow_metrics.py": ["sec_cash_flow_metrics"],
    "load_institutional_holdings_13f.py": ["institutional_holdings_13f"],
    "load_insider_holdings_sec.py": ["insider_holdings_sec"],
    "load_positioning_metrics.py": ["positioning_metrics"],
    # Consolidated Session 275: replaces load_quality_growth_metrics.py and the
    # yfinance-derived-metrics portion of the old yfinance_derived_metrics loader.
    "load_value_quality_growth_metrics.py": ["growth_metrics", "quality_metrics", "value_metrics"],
    "load_risk_metrics_daily.py": ["momentum_metrics", "stability_metrics"],
    "load_stock_scores.py": ["stock_scores"],
    "load_buy_sell_daily.py": ["buy_sell_daily"],
    "load_signal_quality_scores.py": ["signal_quality_scores"],
    "load_algo_metrics_daily.py": ["algo_metrics_daily"],
    # Consolidated Session 275: replaces load_sector_rankings.py and
    # load_sector_performance.py.
    "load_sector_industry_daily.py": ["sector_ranking", "industry_ranking", "sector_performance"],
    "load_economic_data.py": ["economic_data"],
}

# market_exposure_daily is computed by algo/risk/market_exposure.py during
# orchestrator Phase 5, not by a standalone loaders/*.py script - kept as a
# pseudo-entry so scripts that report per-"loader" status have somewhere to
# attribute it, since load_market_status_daily.py also writes it as one of
# three tables in a single atomic run and callers may want to check it alone.
PSEUDO_LOADER_TABLES: dict[str, list[str]] = {
    "load_market_exposure_daily.py": ["market_exposure_daily"],
}


def primary_table(loader_name: str) -> str | None:
    """Return the first (primary) output table for a loader script, or None if unknown."""
    tables = LOADER_TABLES.get(loader_name) or PSEUDO_LOADER_TABLES.get(loader_name)
    return tables[0] if tables else None


def all_tables(loader_name: str) -> list[str]:
    """Return all output tables for a loader script, or [] if unknown."""
    return LOADER_TABLES.get(loader_name) or PSEUDO_LOADER_TABLES.get(loader_name) or []
