#!/usr/bin/env python3
"""Centralized Data Freshness Configuration

Single source of truth for ALL table staleness thresholds.
Instead of scattered hardcoded constants across 6 files, define them once here.

Any code that checks "is this data stale?" must use functions in this module.
This ensures dashboard, API, orchestrator, and all other systems agree on
what "stale" means.

Usage:
    from utils.data_freshness_config import is_table_fresh, get_freshness_rule

    is_fresh, age_minutes, message = is_table_fresh("price_daily", latest_date)
    if not is_fresh:
        logger.warning(f"Price data stale: {message}")
"""

import logging
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger(__name__)
ET_ZONE = "America/New_York"


# ============================================================================
# FRESHNESS RULES: Define all table freshness thresholds here
# ============================================================================

FRESHNESS_RULES = {
    # === CRITICAL TABLES (Halt if stale) ===
    "price_daily": {
        "critical": True,
        "max_age_days": 1,
        "description": "Daily stock prices (SPY, holdings, universe)",
        "purpose": "Used for portfolio valuation, signal generation, position sizing",
        "applies_to": ["orchestrator_phase1", "dashboard", "api"],
    },
    "algo_portfolio_snapshots": {
        "critical": True,
        "max_age_days": 1,
        "description": "Daily portfolio value, returns, P&L tracking",
        "purpose": "Equity curve, Sharpe/Sortino, max drawdown, portfolio monitoring",
        "applies_to": ["orchestrator_phase1", "dashboard", "api"],
    },
    "algo_performance_daily": {
        "critical": True,
        "max_age_days": 1,
        "description": "Pre-computed performance metrics (win_rate, sharpe, drawdown)",
        "purpose": "Dashboard display, circuit breaker thresholds, performance reporting",
        "applies_to": ["orchestrator_phase2", "dashboard", "api"],
    },
    "algo_risk_daily": {
        "critical": True,
        "max_age_days": 1,
        "description": "Risk metrics (VaR, CVaR, portfolio beta, concentration)",
        "purpose": "Risk dashboard, position risk calculations",
        "applies_to": ["dashboard", "api"],
    },
    "buy_sell_daily": {
        "critical": True,
        "max_age_days": 1,
        "description": "Buy/sell signal flags for universe",
        "purpose": "Signal generation, entry/exit logic",
        "applies_to": ["orchestrator_phase5"],
    },
    "swing_trader_scores": {
        "critical": True,
        "max_age_days": 1,
        "description": "Pre-computed swing scores for all symbols",
        "purpose": "Signal ranking, portfolio construction",
        "applies_to": ["orchestrator_phase5", "dashboard"],
    },
    "market_health_daily": {
        "critical": True,
        "max_age_days": 1,
        "description": "Market regime (VIX, yield curve, market stage, breadth)",
        "purpose": "Circuit breakers, exposure limits, trading regime",
        "applies_to": ["orchestrator_phase2", "dashboard", "api"],
    },
    "market_exposure_daily": {
        "critical": True,
        "max_age_days": 1,
        "description": "Market exposure (long/short %, sector allocation)",
        "purpose": "Position monitoring, exposure policy enforcement",
        "applies_to": ["orchestrator_phase3b", "dashboard"],
    },

    # === IMPORTANT TABLES (Warning if stale, may still use) ===
    "technical_data_daily": {
        "critical": False,
        "max_age_days": 7,
        "description": "Technical indicators (RSI, MACD, Bollinger Bands)",
        "purpose": "Signal quality scoring, trade setup validation",
        "applies_to": ["orchestrator_phase5"],
    },
    "trend_template_data": {
        "critical": False,
        "max_age_days": 7,
        "description": "Trend template stage (1-4) for each symbol",
        "purpose": "Position metadata, trend validation",
        "applies_to": ["orchestrator_phase5", "dashboard"],
    },
    "grade_distribution_daily": {
        "critical": False,
        "max_age_days": 7,
        "description": "Grade distribution (A/B/C/D) counts",
        "purpose": "Dashboard quality metrics, distribution analysis",
        "applies_to": ["dashboard"],
    },
    "algo_config": {
        "critical": False,
        "max_age_days": 30,
        "description": "Circuit breaker thresholds, trading parameters",
        "purpose": "Runtime configuration, circuit breaker setup",
        "applies_to": ["orchestrator_all"],
    },

    # === SUPPORTING TABLES (Optional, soft warnings only) ===
    "sector_ranking": {
        "critical": False,
        "max_age_days": 14,
        "description": "Relative sector strength rankings",
        "purpose": "Sector rotation analysis, sector selection",
        "applies_to": ["dashboard"],
    },
    "economic_data": {
        "critical": False,
        "max_age_days": 14,
        "description": "Economic indicators (CPI, unemployment, Treasury yields)",
        "purpose": "Economic context, regime classification",
        "applies_to": ["dashboard", "api"],
    },
    "algo_trades": {
        "critical": False,
        "max_age_days": 1,
        "description": "Trade execution records (entries, exits, fills)",
        "purpose": "Performance calculation, position tracking, reconciliation",
        "applies_to": ["all"],
    },
}


def get_freshness_rule(table_name: str) -> Optional[Dict[str, Any]]:
    """Get freshness rule for a table.

    Args:
        table_name: Name of the table (e.g., 'price_daily')

    Returns:
        Rule dict with 'max_age_days', 'critical', 'description', or None if not found
    """
    return FRESHNESS_RULES.get(table_name)


def is_table_fresh(
    table_name: str,
    latest_date: Optional[Any],
    current_date: Optional[date] = None,
) -> Tuple[bool, Optional[float], str]:
    """Check if a table's latest data is fresh (within threshold).

    Args:
        table_name: Name of the table (e.g., 'price_daily')
        latest_date: Last date/timestamp from the table (datetime, date, or ISO string)
        current_date: Reference date for age calculation (defaults to today)

    Returns:
        Tuple of (is_fresh: bool, age_minutes: Optional[float], message: str)

    Examples:
        >>> is_fresh, age, msg = is_table_fresh('price_daily', datetime(2026, 6, 10))
        >>> if not is_fresh:
        ...     logger.warning(f"Stale data: {msg}")

        >>> is_fresh, _, msg = is_table_fresh('sector_ranking', date(2026, 5, 25))
        >>> # Returns (False, None, "sector_ranking is 17 days old (threshold 14d)")
    """
    if latest_date is None:
        return False, None, f"{table_name} has no data"

    rule = get_freshness_rule(table_name)
    if rule is None:
        return True, None, f"{table_name} (no rule defined, assuming fresh)"

    # Parse latest_date
    if isinstance(latest_date, str):
        try:
            from datetime import datetime as dt
            latest_dt = dt.fromisoformat(latest_date)
            latest_date_only = latest_dt.date()
        except (ValueError, AttributeError):
            return False, None, f"{table_name}: invalid date format {latest_date}"
    elif isinstance(latest_date, datetime):
        latest_date_only = latest_date.date()
    elif isinstance(latest_date, date):
        latest_date_only = latest_date
    else:
        return False, None, f"{table_name}: unsupported date type {type(latest_date)}"

    # Age calculation
    if current_date is None:
        current_date = date.today()
    elif isinstance(current_date, datetime):
        current_date = current_date.date()

    age_days = (current_date - latest_date_only).days
    age_minutes = age_days * 24 * 60  # For precision in warnings

    # Check against threshold
    max_age = rule["max_age_days"]
    is_fresh = age_days <= max_age

    if is_fresh:
        status = "OK"
        level = "✓"
    else:
        status = "STALE"
        level = "⚠️"

    message = (
        f"{level} {table_name}: {age_days}d old (threshold {max_age}d) — {status}"
    )

    return is_fresh, age_minutes, message


def check_multiple_tables(
    tables_and_dates: Dict[str, Optional[Any]],
    current_date: Optional[date] = None,
) -> Tuple[bool, List[str], List[str]]:
    """Check freshness of multiple tables at once.

    Args:
        tables_and_dates: Dict of {table_name: latest_date}
        current_date: Reference date

    Returns:
        Tuple of (all_fresh: bool, stale_tables: list, messages: list)
    """
    all_fresh = True
    stale_tables = []
    messages = []

    for table_name, latest_date in tables_and_dates.items():
        is_fresh, _, message = is_table_fresh(table_name, latest_date, current_date)
        messages.append(message)
        if not is_fresh:
            all_fresh = False
            rule = get_freshness_rule(table_name)
            if rule and rule.get("critical"):
                stale_tables.append(table_name)

    return all_fresh, stale_tables, messages


def get_max_age_minutes(table_name: str) -> Optional[int]:
    """Get max age in minutes for a table (convenience function).

    Args:
        table_name: Name of the table

    Returns:
        Max age in minutes, or None if rule not found
    """
    rule = get_freshness_rule(table_name)
    if rule:
        return rule["max_age_days"] * 24 * 60
    return None


def is_critical_table(table_name: str) -> bool:
    """Check if a table is critical (halt if stale).

    Args:
        table_name: Name of the table

    Returns:
        True if critical, False otherwise
    """
    rule = get_freshness_rule(table_name)
    return rule.get("critical", False) if rule else False


# ============================================================================
# TIMESTAMP HELPERS
# ============================================================================


def minutes_since(timestamp: Optional[Any]) -> Optional[float]:
    """Calculate minutes elapsed since a timestamp.

    Args:
        timestamp: datetime, date, or ISO string

    Returns:
        Minutes elapsed, or None if timestamp is None/invalid
    """
    if timestamp is None:
        return None

    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except (ValueError, AttributeError):
            return None

    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - timestamp
        return elapsed.total_seconds() / 60
    elif isinstance(timestamp, date):
        timestamp_dt = datetime.combine(timestamp, datetime.min.time())
        timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - timestamp_dt
        return elapsed.total_seconds() / 60

    return None


# ============================================================================
# COMMON QUERIES (SQL templates for checking table freshness)
# ============================================================================

SQL_FRESHNESS_CHECK = """
    SELECT tbl, role, latest, age,
           CASE WHEN age IS NULL OR age > stale_thresh THEN 'stale' ELSE 'ok' END AS st
    FROM (
      SELECT 'price_daily'    tbl,'CRIT' role, MAX(date)::date latest,
             (CURRENT_DATE - MAX(date)::date) age, 1 stale_thresh
             FROM price_daily
      UNION ALL
      SELECT 'algo_portfolio_snapshots','CRIT',
             MAX(snapshot_date)::date, (CURRENT_DATE - MAX(snapshot_date)::date), 1
             FROM algo_portfolio_snapshots
      UNION ALL
      SELECT 'algo_performance_daily','CRIT',
             MAX(report_date)::date, (CURRENT_DATE - MAX(report_date)::date), 1
             FROM algo_performance_daily
      UNION ALL
      SELECT 'algo_risk_daily','CRIT',
             MAX(report_date)::date, (CURRENT_DATE - MAX(report_date)::date), 1
             FROM algo_risk_daily
      UNION ALL
      SELECT 'buy_sell_daily','CRIT',
             MAX(date)::date, (CURRENT_DATE - MAX(date)::date), 1
             FROM buy_sell_daily
      UNION ALL
      SELECT 'swing_trader_scores','CRIT',
             MAX(date)::date, (CURRENT_DATE - MAX(date)::date), 1
             FROM swing_trader_scores
      UNION ALL
      SELECT 'market_health_daily','CRIT',
             MAX(date)::date, (CURRENT_DATE - MAX(date)::date), 1
             FROM market_health_daily
      UNION ALL
      SELECT 'technical_data_daily','IMP',
             MAX(date)::date, (CURRENT_DATE - MAX(date)::date), 7
             FROM technical_data_daily
    ) s
    ORDER BY CASE role WHEN 'CRIT' THEN 1 ELSE 2 END, tbl
"""
