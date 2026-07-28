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

import logging

logger = logging.getLogger(__name__)

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
    # load_sec_cash_flow_metrics.py REMOVED 2026-07-27: duplicated quality_metrics formulas
    # exactly, zero incremental signal for real SEC API cost - see steering/DATA_LOADERS.md.
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
    # SEC data loaders (Phase 6: material events, insider velocity, segment disclosures)
    "load_current_reports_8k.py": ["current_reports_8k"],
    "load_insider_transaction_velocity.py": ["insider_transaction_velocity"],
    "load_dividend_data.py": ["dividend_data"],
    "load_sec_segment_info.py": ["sec_segment_info"],
    "load_sec_segment_metrics.py": ["sec_segment_metrics"],
    # Restored 2026-07-27 (see scripts/local_loader_scheduler.py) - was previously
    # missing from this registry, which made it silently invisible to every
    # health/audit script built on LOADER_TABLES despite being flagged
    # "critical_loaders" in terraform/modules/loaders/main.tf.
    "load_company_profile.py": ["company_profile"],
    # Restored 2026-07-27: same "missing from this registry" gap as load_company_profile.py
    # above, for the two yfinance-backed analyst loaders restored the same day (see
    # scripts/local_loader_scheduler.py and steering/DATA_LOADERS.md).
    "load_analyst_upgrade_downgrade.py": ["analyst_upgrade_downgrade"],
    "load_analyst_sentiment_analysis.py": ["analyst_sentiment_analysis"],
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
    tables = LOADER_TABLES.get(loader_name)
    if tables is None:
        tables = PSEUDO_LOADER_TABLES.get(loader_name)
    if tables is None:
        logger.warning(f"[LOADER_REGISTRY] Unknown loader: {loader_name}. Not found in LOADER_TABLES or PSEUDO_LOADER_TABLES.")
    return tables[0] if tables else None


def all_tables(loader_name: str) -> list[str]:
    """Return all output tables for a loader script (raises on unknown loader)."""
    tables = LOADER_TABLES.get(loader_name)
    if tables is None:
        tables = PSEUDO_LOADER_TABLES.get(loader_name)
    if tables is None:
        raise ValueError(
            f"[LOADER_REGISTRY] Unknown loader: {loader_name!r}. "
            f"Not found in LOADER_TABLES or PSEUDO_LOADER_TABLES. "
            f"This is a configuration error - the loader name may be misspelled, deprecated, "
            f"or the registry was not updated after a rename/consolidation. "
            f"Available loaders: {sorted(set(LOADER_TABLES.keys()) | set(PSEUDO_LOADER_TABLES.keys()))}"
        )
    return tables
