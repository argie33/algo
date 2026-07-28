#!/usr/bin/env python3
"""Comprehensive system health audit - data, loaders, and schema completeness.

Checks:
1. Data freshness for critical trading tables
2. Loader execution status
3. Orphaned/abandoned tables (design debt)
4. Deprecated features
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger

logger = get_logger(__name__)

# Tables with active loaders (critical for trading)
ACTIVE_TABLES = {
    "price_daily": "Alpaca SIP prices",
    "technical_data_daily": "Technical indicators (RSI, BB, etc.)",
    "stock_scores": "Composite quality/growth/value scores",
    "market_exposure_daily": "Market sector/industry exposures",
    "algo_signals": "Trading signals (buy/sell flags)",
    "growth_metrics": "SEC-based revenue/EPS growth",
    "quality_metrics": "Profitability/margin quality metrics",
    "value_metrics": "Valuation multiples (P/E, P/B, etc.)",
    "algo_trades": "Executed trades and fills",
    "algo_positions": "Current open positions",
    "algo_reconciliation_log": "End-of-day reconciliation",
    "industry_ranking": "Momentum ranking by sector",
    "sector_rotation_signal": "Rotation signals (strong/weak)",
    "trend_template_data": "Trend classification per symbol",
}

# Orphaned tables (no writers - design debt)
ORPHANED_TABLES = {
    "algo_daily_return_histogram": "Daily return distribution (designed but not implemented)",
    "algo_data_patrol": "Data integrity patrol results (no writer)",
    "algo_holding_period_histogram": "Holding period distribution (designed but not implemented)",
    "earnings_history": "Earnings event history (never populated)",
    "equity_curve_daily": "Daily equity curve snapshots (never populated)",
    "portfolio_holdings": "Portfolio position history (never populated)",
}

# Deprecated tables (loader was deleted, table references remain in config)
DEPRECATED_TABLES = {
    "price_extremes_52week": "52-week high/low (load_price_extremes.py deleted)",
    "market_cap_computed": "Market cap computation (load_market_cap_computed.py deleted)",
}


def check_table_health(table_name: str, description: str) -> dict:
    """Check a table for row count, last update, and data freshness."""
    try:
        with DatabaseContext("read") as cur:
            # Get row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]

            # Get most recent timestamp
            cur.execute(f"""
                SELECT
                    MAX(CASE
                        WHEN column_name IN ('updated_at', 'created_at') THEN column_name
                        ELSE NULL
                    END) as ts_col
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
            """)

            ts_col_row = cur.fetchone()
            ts_col = ts_col_row[0] if ts_col_row and ts_col_row[0] else None

            last_update = None
            if ts_col:
                try:
                    cur.execute(f"SELECT MAX({ts_col}) FROM {table_name}")
                    row = cur.fetchone()
                    if row and row[0]:
                        last_update = row[0]
                except Exception:
                    pass

            hours_ago = None
            if last_update:
                now = datetime.now(timezone.utc)
                # Handle both offset-aware and offset-naive timestamps
                if hasattr(last_update, 'tzinfo') and last_update.tzinfo:
                    delta = now - last_update
                else:
                    # Assume naive timestamps are UTC
                    from datetime import timezone as tz_module
                    delta = now - last_update.replace(tzinfo=tz_module.utc)
                hours_ago = delta.total_seconds() / 3600

            return {
                "table": table_name,
                "description": description,
                "row_count": count,
                "last_update": last_update,
                "hours_ago": hours_ago,
                "status": "OK" if count > 0 else "EMPTY",
            }
    except Exception as e:
        return {
            "table": table_name,
            "description": description,
            "row_count": None,
            "last_update": None,
            "hours_ago": None,
            "status": f"ERROR: {str(e)[:50]}",
        }


def print_section(title: str, tables: dict) -> None:
    """Print a formatted section of table statuses."""
    print(f"\n{title}")
    print("=" * 100)

    for table, desc in tables.items():
        info = check_table_health(table, desc)

        if info["row_count"] is None:
            status_str = f"  ERROR: {info['status']}"
        elif info["row_count"] == 0:
            status_str = "  EMPTY (0 rows)"
        elif info["hours_ago"] is not None:
            hours = info["hours_ago"]
            age_str = f"{hours:.1f}h" if hours < 24 else f"{hours/24:.1f}d"
            status_str = f"  OK: {info['row_count']:>6} rows | {age_str} old"
        else:
            status_str = f"  OK: {info['row_count']:>6} rows | (no timestamp)"

        print(f"  {table:<40} | {status_str}")
        print(f"    {desc}")


def check_loaders() -> None:
    """Check loader execution status from watermarks."""
    print("\nLOADER EXECUTION STATUS (Most Recent Runs)")
    print("=" * 100)

    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    loader,
                    COUNT(*) as symbol_count,
                    MAX(last_run_at) as last_run,
                    COUNT(*) FILTER (WHERE error_count > 0) as with_errors
                FROM loader_watermarks
                GROUP BY loader
                ORDER BY MAX(last_run_at) DESC NULLS LAST
                LIMIT 20
            """)

            now = datetime.now(timezone.utc)
            for loader, sym_count, last_run, errors in cur.fetchall():
                if last_run:
                    hours_ago = (now - last_run).total_seconds() / 3600
                    status = "FRESH" if hours_ago < 6 else "OK" if hours_ago < 24 else "OLD"
                    print(f"  {loader:<40} | {status:5} | {hours_ago:>6.1f}h | {sym_count:>5} syms | {errors:>3} err")
                else:
                    print(f"  {loader:<40} | NO RUN | (never)")
    except Exception as e:
        print(f"  ERROR: {e}")


def main() -> None:
    """Run complete system health audit."""
    print("\n" + "=" * 100)
    print("SYSTEM HEALTH AUDIT")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 100)

    # Active tables
    print_section("ACTIVE TABLES (Critical for Trading)", ACTIVE_TABLES)

    # Orphaned tables
    print_section("ORPHANED TABLES (No Writers - Design Debt)", ORPHANED_TABLES)

    # Deprecated tables
    print_section("DEPRECATED TABLES (Loaders Deleted)", DEPRECATED_TABLES)

    # Loader status
    check_loaders()

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print("""
INTERPRETATION:
  - ACTIVE TABLES (Fresh): OK - System is working correctly
  - ACTIVE TABLES (Old): WARN - Investigate loader execution
  - ORPHANED TABLES (Empty): Expected - these are design debt waiting for implementation
  - DEPRECATED TABLES (Empty): Expected - these loaders were removed

NOTE: Orphaned and deprecated tables will NOT trigger staleness alerts in the production
monitor (scripts/monitor_data_staleness.py). They are safe to ignore for trading purposes.
    """)


if __name__ == "__main__":
    main()
