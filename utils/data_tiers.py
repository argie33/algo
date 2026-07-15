"""Data tier classification: Critical (MUST-HAVE) vs Auxiliary (nice-to-have) data.

This module defines which data is essential for trading vs enrichment-only.
Used by: Phase 1 (data freshness), Phase 1 Failsafe (retry strategy), dashboards.

Philosophy:
- CRITICAL data: If missing/stale, halt trading or use last-known-good fallback
- AUXILIARY data: If missing, trading proceeds with reduced signal quality
"""


# CRITICAL DATA TIER
# ==================
# Trading cannot proceed without these tables being fresh (≤1 trading day old, ≥75% symbols).
# If critical data is stale or missing:
# - Phase 1 detects staleness and potentially halts
# - Phase 1 Failsafe retries the loader
# - If retry fails, orchestrator halts trading

CRITICAL_DATA: set[str] = {
    # Prices: Required for position sizing, P&L, entry/exit signals
    "price_daily",
    "price_weekly",
    "price_monthly",
    "etf_price_daily",
    "etf_price_weekly",
    "etf_price_monthly",
    # Technical indicators: Required for Minervini/Weinstein signal generation (Phase 5, Phase 7)
    "technical_data_daily",
    # Market regime: Required for position sizing constraints (Phase 3b, Phase 5)
    "market_health_daily",
    "market_exposure_daily",
    # Earnings dates: Required for 7-day blackout window gating (Phase 5)
    "earnings_calendar",
}

# AUXILIARY DATA TIER
# ===================
# Trading proceeds even if missing, but signal quality degrades.
# If auxiliary data is stale/missing:
# - Phase 1 logs warning but does not halt
# - Phase 1 Failsafe skips retry (don't spend orchestrator time on it)
# - Dashboard shows graceful degradation (missing metrics, not errors)

AUXILIARY_DATA: set[str] = {
    # Sector rotation: Used for portfolio balance hints (Phase 3b is not strict)
    "sector_ranking",
    # Trend criteria: Optional filter for signal generation (Phase 5 can work without it)
    "trend_template_data",
    # Growth metrics: Enriches signal quality but not required for entry
    "growth_metrics",
    # Value metrics: Used for quality filters but not blocking
    "value_metrics",
    # Positioning: Institutional money flow enrichment (optional)
    "positioning_metrics",
    # Sentiment: Analyst sentiment (nice-to-have quality metric)
    "analyst_sentiment_analysis",
    # Quality/stability: Risk enrichment (not required for base logic)
    "stability_metrics",
    # Economic data: Macro context (optional for regime understanding)
    "economic_metrics_daily",
    # VIX/breadth: Market health enrichment (market_health_daily is critical, these are supplementary)
    "aaii_sentiment",
    "fear_greed_index",
    # Scores & signals: Orchestrator-generated outputs (Phase 5/7 will regenerate)
    "stock_scores",
    "buy_sell_daily",
}

# Generated data (computed by orchestrator itself, not loaded from external APIs)
# These should never be in "incomplete" status - they're outputs, not inputs
ORCHESTRATOR_GENERATED: set[str] = {
    "stock_scores",  # Phase 5 output
    "buy_sell_daily",  # Phase 5 output
}


# Analysis helpers
def is_critical(table_name: str) -> bool:
    return table_name in CRITICAL_DATA


def is_auxiliary(table_name: str) -> bool:
    return table_name in AUXILIARY_DATA


def is_orchestrator_generated(table_name: str) -> bool:
    return table_name in ORCHESTRATOR_GENERATED


def get_tier(table_name: str) -> str:
    if is_critical(table_name):
        return "critical"
    elif is_auxiliary(table_name):
        return "auxiliary"
    elif is_orchestrator_generated(table_name):
        return "generated"
    else:
        return "unknown"
