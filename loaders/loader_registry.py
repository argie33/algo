#!/usr/bin/env python3
"""Canonical loader-script -> output-table(s) mapping.

Single source of truth, extracted after hand-maintained copies of this
mapping silently fell out of sync with loader renames/consolidations since
Session 275. Multiple independent audit scripts had entries for deleted/renamed
loaders (e.g. load_yfinance_snapshot.py, load_growth_metrics.py), and some
(load_earnings_calendar_sec.py) were mapped to wrong tables entirely -
'earnings_history' (permanently-empty legacy table) instead of the actual
'earnings_calendar_sec' (353k+ rows updated daily). This registry centralizes
the truth to prevent such drift.

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
    # Restored 2026-08-04: this table (real earnings announcement dates + EPS estimates/
    # actuals, used by algo/risk/earnings_blackout.py's blackout-window gating) had no
    # active loader since load_yfinance_derived_metrics.py was deleted 2026-07-19,
    # "believed superseded" by earnings_calendar_sec - which is actually a different
    # concept (SEC 10-K/10-Q *filing* dates, not earnings *announcement* dates). See
    # loaders/load_earnings_calendar.py's module docstring for the full incident.
    "load_earnings_calendar.py": ["earnings_calendar"],
    "load_market_constituents.py": ["stock_symbols", "etf_symbols"],
    # ttm_income_statement/ttm_cash_flow are deliberately excluded: the loader's
    # statement-type config still lists them as write targets, but
    # data_loader_status marks both DEPRECATED (confirmed live: 60-63 days
    # stale, everything else this loader writes is <1 day old) - listing them
    # here would make every audit script relying on this registry falsely
    # flag a healthy loader as CRITICAL/stale on a table nothing expects fresh
    # anymore. Worth a separate look at why the loader's config wasn't cleaned
    # up to match, but that's a distinct question from this mapping's accuracy.
    # DISABLED 2026-08-06: SEC financial statement loaders hang for 5+ hours and get force-killed.
    # Not used by trading logic (only referenced in data_patrol monitoring).
    # Can be re-enabled after fixing the hang issue with per-request timeouts.
    # "load_financial_statements.py": [
    #     "annual_income_statement",
    #     "annual_balance_sheet",
    #     "annual_cash_flow",
    #     "quarterly_income_statement",
    #     "quarterly_balance_sheet",
    #     "quarterly_cash_flow",
    # ],
    "load_sec_valuations.py": ["sec_valuations"],
    # load_sec_cash_flow_metrics.py REMOVED 2026-07-27: duplicated quality_metrics formulas
    # exactly, zero incremental signal for real SEC API cost - see steering/DATA_LOADERS.md.
    "load_institutional_holdings_13f.py": ["institutional_holdings_13f"],
    "load_insider_holdings_sec.py": ["insider_holdings_sec"],
    "load_positioning_metrics.py": ["positioning_metrics"],
    # Consolidated Session 275: replaces load_quality_growth_metrics.py and the
    # yfinance-derived-metrics portion of the old yfinance_derived_metrics loader.
    "load_value_quality_growth_metrics.py": ["growth_metrics", "quality_metrics", "value_metrics"],
    "load_enhanced_quality_growth_metrics.py": ["quality_metrics", "growth_metrics"],  # Adds analyst estimates, earnings surprises, trend metrics
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
    # Added 2026-08-03: real forward-EPS source for value_metrics.forward_pe, previously
    # hardcoded None every run - see load_analyst_earnings_estimates.py's module docstring.
    "load_analyst_earnings_estimates.py": ["analyst_earnings_estimates"],
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


# NAMING SCHEMES REFERENCE
# ========================
# Three different naming conventions are used across the codebase:
#
# 1. FILENAME: What run_loader.py expects (used in registry keys)
#    Examples: "load_prices.py", "load_technical_indicators.py"
#
# 2. SHORTHAND: What local_loader_scheduler.py uses (friendly names)
#    Examples: "prices", "technical", "market_status"
#    Used in PIPELINES dict (morning, metrics, signals)
#
# 3. TASK_DEFINITION: What terraform/lambda use (ECS task definitions + table names)
#    Examples: "stock_prices_daily", "technical_data_daily"
#    Used in terraform loader_file_map keys and Lambda VALID_LOADER_NAMES
#
# The mappings below normalize these to avoid drift.

SHORTHAND_TO_FILENAME: dict[str, str] = {
    "prices": "load_prices.py",
    "technical": "load_technical_indicators.py",
    "market_status": "load_market_status_daily.py",
    "earnings_calendar": "load_earnings_calendar.py",
    "trend_analysis": "load_trend_analysis.py",
    "sector_industry": "load_sector_industry_daily.py",
    "analyst_earnings_estimates": "load_analyst_earnings_estimates.py",
    "value_quality_growth": "load_value_quality_growth_metrics.py",
    "enhanced_quality_growth": "load_enhanced_quality_growth_metrics.py",
    "positioning_metrics": "load_positioning_metrics.py",
    "stability_metrics": "load_risk_metrics_daily.py",  # Stability is part of risk_metrics loader
    "scores": "load_stock_scores.py",
    "buy_sell": "load_buy_sell_daily.py",
}


def normalize_loader_name(name: str) -> str:
    """Convert a shorthand or filename to the canonical filename format.

    Handles multiple input formats:
    - Shorthand: "prices" → "load_prices.py"
    - Shorthand without .py: "prices" → "load_prices.py"
    - Filename: "load_prices.py" → "load_prices.py"
    - Filename without .py: "load_prices" → "load_prices.py"

    Args:
        name: Loader name in any format

    Returns:
        Canonical filename (e.g., "load_prices.py")

    Raises:
        ValueError: If the loader is not recognized
    """
    # If it's already a filename, normalize it
    if name.startswith("load_"):
        return name if name.endswith(".py") else name + ".py"

    # Try shorthand mapping
    if name in SHORTHAND_TO_FILENAME:
        return SHORTHAND_TO_FILENAME[name]

    # Try shorthand without .py suffix
    if name.endswith(".py"):
        shorthand = name[:-3]
        if shorthand in SHORTHAND_TO_FILENAME:
            return SHORTHAND_TO_FILENAME[shorthand]

    # Not found
    raise ValueError(
        f"[LOADER_REGISTRY] Unknown loader name: {name!r}. "
        f"Valid shorthand names: {sorted(SHORTHAND_TO_FILENAME.keys())}. "
        f"Or use full filenames like 'load_prices.py'."
    )
