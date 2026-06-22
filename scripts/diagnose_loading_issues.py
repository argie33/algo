#!/usr/bin/env python3
"""Diagnose data loading issues - check what's missing for signal generation."""

import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from utils.db.context import DatabaseContext

EASTERN = ZoneInfo("America/New_York")


def check_table_data(table_name: str, description: str) -> dict:
    """Check if a table has recent data."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cur.fetchone()
            count = row[0] if row else 0

            if count == 0:
                return {
                    "table": table_name,
                    "status": "EMPTY",
                    "count": 0,
                    "desc": description,
                }

            cur.execute(f"SELECT MAX(date) FROM {table_name}")
            row = cur.fetchone()
            max_date = row[0] if row and row[0] else None

            if max_date is None:
                return {
                    "table": table_name,
                    "status": "NO_DATE",
                    "count": count,
                    "desc": description,
                }

            days_old = (date.today() - max_date).days
            if days_old == 0:
                status = "FRESH"
            elif days_old == 1:
                status = "1DAY_OLD"
            elif days_old <= 3:
                status = f"{days_old}DAYS_OLD"
            else:
                status = f"STALE_{days_old}DAYS"

            return {
                "table": table_name,
                "status": status,
                "count": count,
                "max_date": str(max_date),
                "desc": description,
            }
    except Exception as e:
        return {
            "table": table_name,
            "status": "ERROR",
            "error": str(e),
            "desc": description,
        }


def main():
    print("=" * 100)
    print("DATA LOADING DIAGNOSTIC REPORT")
    print(f"Generated: {datetime.now(EASTERN).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 100)

    # Critical tables for signal generation
    critical_tables = [
        ("price_daily", "Stock prices (REQUIRED)"),
        ("buy_sell_daily", "Buy/sell signals (REQUIRED)"),
        ("market_health_daily", "Market regime (REQUIRED for Phase 1)"),
        ("market_exposure_daily", "Position sizing exposure (REQUIRED for Phase 5)"),
        ("trend_template_data", "Trend scores (REQUIRED for swing scores)"),
    ]

    print("\n### CRITICAL TABLES FOR SIGNAL GENERATION ###")
    print("-" * 100)
    critical_results = []
    for table, desc in critical_tables:
        result = check_table_data(table, desc)
        critical_results.append(result)
        status = result["status"]
        marker = "✓" if status in ("FRESH", "1DAY_OLD") else "✗"
        info = (
            f" (max_date: {result.get('max_date', 'N/A')})"
            if "max_date" in result
            else f" ({result.get('error', 'N/A')})"
        )
        print(f"{marker} {table:30s} {status:20s} {desc:35s}{info}")

    # Score tables (depend on critical tables)
    print("\n### FACTOR SCORE TABLES (Dependent) ###")
    print("-" * 100)
    score_tables = [
        (
            "stock_scores",
            "Composite stock scores (Quality/Growth/Value/Momentum/Stability)",
        ),
        (
            "swing_trader_scores",
            "Legacy swing trader scores (depends on signal_quality_scores)",
        ),
        (
            "signal_quality_scores",
            "Signal quality validation (depends on buy_sell_daily)",
        ),
    ]

    score_results = []
    for table, desc in score_tables:
        result = check_table_data(table, desc)
        score_results.append(result)
        status = result["status"]
        marker = "✓" if status in ("FRESH", "1DAY_OLD") else "✗"
        info = (
            f" ({result.get('count', 0)} rows, max_date: {result.get('max_date', 'N/A')})"
            if "max_date" in result
            else f" ({result.get('error', 'N/A')})"
        )
        print(f"{marker} {table:30s} {status:20s} {desc:35s}{info}")

    # Factor input tables (for stock_scores)
    print("\n### FACTOR INPUT TABLES (Required for stock_scores) ###")
    print("-" * 100)
    factor_tables = [
        ("quality_metrics", "Quality factors (ROE, margins, debt ratios)"),
        ("growth_metrics", "Growth factors (revenue/EPS growth)"),
        ("value_metrics", "Value factors (P/E, P/B, dividend yield)"),
        ("positioning_metrics", "Positioning factors (institutional ownership)"),
        ("stability_metrics", "Stability factors (volatility, beta)"),
    ]

    factor_results = []
    for table, desc in factor_tables:
        result = check_table_data(table, desc)
        factor_results.append(result)
        status = result["status"]
        marker = "✓" if status != "EMPTY" else "✗"
        info = f" ({result.get('count', 0)} rows)" if "count" in result else f" ({result.get('error', 'N/A')})"
        print(f"{marker} {table:30s} {status:20s} {desc:35s}{info}")

    # Options data
    print("\n### OPTIONS DATA (Put/Call volumes) ###")
    print("-" * 100)
    options_tables = [
        ("options_chains", "Options chain data (Put/Call volumes)"),
        ("iv_history", "Implied Volatility history"),
    ]

    options_results = []
    for table, desc in options_tables:
        result = check_table_data(table, desc)
        options_results.append(result)
        status = result["status"]
        marker = "✓" if status != "EMPTY" else "✗"
        info = f" ({result.get('count', 0)} rows)" if "count" in result else f" ({result.get('error', 'N/A')})"
        print(f"{marker} {table:30s} {status:20s} {desc:35s}{info}")

    # Dependency analysis
    print("\n### DEPENDENCY ANALYSIS ###")
    print("-" * 100)

    # Check for stock_scores blockages
    stock_scores_status = next((r for r in score_results if r["table"] == "stock_scores"), {})
    factor_status = {r["table"]: r for r in factor_results}

    if stock_scores_status.get("status") == "EMPTY":
        missing_factors = [name for name, r in factor_status.items() if r["status"] == "EMPTY"]
        if missing_factors:
            print(f"✗ stock_scores is EMPTY. Missing factors: {', '.join(missing_factors)}")
            print(
                "  ACTION: Run quality_metrics, growth_metrics, value_metrics, positioning_metrics, stability_metrics loaders"
            )
        else:
            print("✗ stock_scores is EMPTY but all factor inputs are available")
            print("  ACTION: Run load_stock_scores.py manually to populate")
    else:
        print(f"✓ stock_scores available ({stock_scores_status.get('count', 0)} rows)")

    # Check for swing_trader_scores blockages
    swing_status = next((r for r in score_results if r["table"] == "swing_trader_scores"), {})
    signal_quality_status = next((r for r in score_results if r["table"] == "signal_quality_scores"), {})
    trend_status = next((r for r in critical_results if r["table"] == "trend_template_data"), {})

    if swing_status.get("status") == "EMPTY":
        blockers = []
        if signal_quality_status.get("status") == "EMPTY":
            blockers.append("signal_quality_scores")
        if trend_status.get("status") == "EMPTY":
            blockers.append("trend_template_data")

        if blockers:
            print(f"✗ swing_trader_scores is EMPTY. Blocked by: {', '.join(blockers)}")
            print("  ACTION: Run missing loaders first (signal_quality_scores, trend_template_data)")
        else:
            print("✗ swing_trader_scores is EMPTY but dependencies are available")
            print("  ACTION: Run load_swing_trader_scores_vectorized.py manually")
    else:
        print(f"✓ swing_trader_scores available ({swing_status.get('count', 0)} rows)")

    # Check for options data
    options_status = next((r for r in options_results if r["table"] == "options_chains"), {})
    if options_status.get("status") == "EMPTY":
        print("✗ options_chains is EMPTY - put/call data not loaded")
        print("  ACTION: Run load_options_chains.py (now fixed for AWS write context)")
    else:
        print(f"✓ options_chains available ({options_status.get('count', 0)} rows)")

    # Overall status
    print("\n### OVERALL STATUS ###")
    print("-" * 100)
    critical_pass = all(r["status"] in ("FRESH", "1DAY_OLD") for r in critical_results if r.get("status") != "ERROR")
    scores_pass = all(r["status"] != "EMPTY" for r in score_results if r.get("status") != "ERROR")

    if critical_pass and scores_pass:
        print("✓ READY FOR TRADING: All critical data loaded and fresh")
    else:
        print("✗ NOT READY FOR TRADING: Some critical data missing or stale")
        if not critical_pass:
            print("  - Critical tables need attention (price_daily, buy_sell_daily, market data)")
        if not scores_pass:
            print("  - Score tables need to be populated (stock_scores, swing_trader_scores)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
