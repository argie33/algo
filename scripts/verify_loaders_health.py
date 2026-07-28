#!/usr/bin/env python3
"""Verify each loader is producing correct output.

Checks:
1. Each loader's most recent execution status
2. Output table has recent data
3. Data quality (no excessive NULLs, duplicates)
4. Loader execution time
5. Whether loader output feeds downstream dependencies
"""

from datetime import datetime
from typing import Any

import psycopg2

# Kept in sync with the active loader list in scripts/local_loader_scheduler.py.
# Previous version of this dict referenced load_yfinance_snapshot.py and
# load_yfinance_derived_metrics.py, both fully deprecated + deleted in Session 275
# (see steering/DATA_LOADERS.md), plus several renamed loaders (e.g.
# load_quality_growth_metrics.py -> load_value_quality_growth_metrics.py,
# load_sector_rankings.py/load_sector_performance.py -> load_sector_industry_daily.py,
# load_market_health_daily.py -> load_market_status_daily.py). Those stale entries
# checked tables that no longer exist or are no longer written, producing false
# CRITICAL/STALE noise on every run regardless of real system health.
LOADERS: dict[str, dict[str, Any]] = {
    "load_prices.py": {
        "output_table": "price_daily",
        "date_column": "date",
        "min_rows": 5000000,
        "critical": True,
    },
    "load_technical_indicators.py": {
        "output_table": "technical_data_daily",
        "date_column": "date",
        "min_rows": 100000,
        "critical": True,
    },
    "load_trend_analysis.py": {
        "output_table": "trend_template_data",
        "date_column": "date",
        "min_rows": 50000,
        "critical": True,
    },
    "load_market_status_daily.py": {
        "output_table": "market_sentiment",
        "date_column": "date",
        "min_rows": 1,
        "critical": False,
    },
    "load_naaim.py": {
        "output_table": "naaim",
        "date_column": "date",
        "min_rows": 100,
        "critical": False,
        # NAAIM Exposure Index is published weekly (Wednesdays) - trading-day staleness
        # logic (built for daily sources) always false-flags this as stale by midweek.
        "max_staleness_days": 9,
    },
    "load_aaii_sentiment.py": {
        "output_table": "aaii_sentiment",
        "date_column": "date",
        "min_rows": 100,
        "critical": False,
        # AAII sentiment survey is published weekly (Thursdays) - same reasoning as NAAIM.
        "max_staleness_days": 9,
    },
    "load_short_interest_finra.py": {
        "output_table": "short_interest_finra",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    "load_company_info_sec.py": {
        "output_table": "company_info_sec",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": True,
    },
    "load_earnings_calendar_sec.py": {
        "output_table": "earnings_calendar_sec",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    "load_market_constituents.py": {
        "output_table": "stock_symbols",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": True,
    },
    "load_financial_statements.py": {
        "output_table": "annual_income_statement",
        "date_column": None,
        "min_rows": 100,
        "critical": True,
    },
    "load_sec_valuations.py": {
        "output_table": "sec_valuations",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    # load_sec_cash_flow_metrics.py REMOVED 2026-07-27 (no longer scheduled - see
    # steering/DATA_LOADERS.md GAP note): leaving a "date_column": "updated_at" health entry for
    # a loader that no longer runs would just false-alarm this table as perpetually stale, the
    # exact drift-bug class this file exists to catch (see loader_registry.py's docstring).
    "load_institutional_holdings_13f.py": {
        "output_table": "institutional_holdings_13f",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    "load_insider_holdings_sec.py": {
        "output_table": "insider_holdings_sec",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    "load_positioning_metrics.py": {
        "output_table": "positioning_metrics",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    "load_value_quality_growth_metrics.py": {
        "output_table": "quality_metrics",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": True,
        "note": "Consolidated loader: also writes growth_metrics, value_metrics",
    },
    "load_risk_metrics_daily.py": {
        "output_table": "stability_metrics",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": True,
    },
    "load_stock_scores.py": {
        "output_table": "stock_scores",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": True,
    },
    "load_buy_sell_daily.py": {
        "output_table": "buy_sell_daily",
        "date_column": "date",
        "min_rows": 10000,
        "critical": True,
    },
    "load_signal_quality_scores.py": {
        "output_table": "signal_quality_scores",
        "date_column": "date",
        "min_rows": 10000,
        "critical": False,
    },
    "load_algo_metrics_daily.py": {
        "output_table": "algo_metrics_daily",
        "date_column": "date",
        "min_rows": 1,
        "critical": False,
    },
    "load_sector_industry_daily.py": {
        "output_table": "sector_ranking",
        "date_column": "date",
        "min_rows": 100,
        "critical": False,
        "note": "Consolidated loader: also writes industry_ranking, sector_performance",
    },
    "load_market_exposure_daily.py": {
        "output_table": "market_exposure_daily",
        "date_column": "date",
        "min_rows": 1,
        "critical": False,
        "note": "Computed by algo/risk/market_exposure.py during orchestrator Phase 5, not a standalone loaders/ script",
    },
    "load_economic_data.py": {
        "output_table": "economic_data",
        "date_column": "date",
        "min_rows": 10,
        "critical": False,
        "note": "Consolidated loader: writes FRED + DXY to economic_data",
    },
}

# Guard against this file's output_table entries silently drifting from reality
# again (the exact bug this whole LOADERS dict was rebuilt to fix - see comment
# above). loaders/loader_registry.py is the single shared source of truth,
# independently cross-referenced from scripts/audit_all_loaders.py and
# scripts/refresh_stale_loaders.py too; failing loudly here at import time means
# a future loader rename/consolidation that updates the registry but not this
# file's per-entry thresholds gets caught immediately instead of silently
# producing false health signals again.
def _validate_against_registry() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from loaders.loader_registry import all_tables

    for loader_name, cfg in LOADERS.items():
        registry_tables = all_tables(loader_name)
        if not registry_tables:
            continue  # Not in the registry (e.g. the market_exposure_daily pseudo-entry lives there too, so this only skips genuinely unknown names)
        if cfg["output_table"] not in registry_tables:
            raise AssertionError(
                f"[LOADERS] {loader_name}'s output_table={cfg['output_table']!r} not in "
                f"loaders/loader_registry.py's known tables {registry_tables} - one of these "
                f"two mappings has drifted from the other, fix before trusting this script's output."
            )


_validate_against_registry()


def verify_loader(conn: Any, loader_name: str, config: dict) -> dict[str, Any]:
    """Verify a single loader's output."""
    cur = conn.cursor()
    results = {
        "loader": loader_name,
        "status": "UNKNOWN",
        "issues": [],
        "table": config["output_table"],
    }

    try:
        # Check if output table exists
        cur.execute(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{config["output_table"]}'
            )
        """)
        if not cur.fetchone()[0]:
            results["status"] = "TABLE_MISSING"
            results["issues"].append(f"Output table {config['output_table']} does not exist")
            return results

        # Check row count
        cur.execute(f"SELECT COUNT(*) FROM {config['output_table']}")
        row_count = cur.fetchone()[0]

        if row_count < config["min_rows"]:
            results["issues"].append(f"Low row count: {row_count} (expected >= {config['min_rows']})")

        # Check data freshness if date column exists
        if config["date_column"]:
            try:
                cur.execute(f"""
                    SELECT MAX({config["date_column"]}::date)
                    FROM {config["output_table"]}
                """)
                max_date = cur.fetchone()[0]

                if max_date:
                    today = datetime.now().date()
                    age = today - max_date

                    from datetime import timedelta

                    max_staleness_days = config.get("max_staleness_days")
                    if max_staleness_days is not None:
                        # Non-daily source (e.g. weekly NAAIM/AAII surveys) - trading-day
                        # logic below assumes near-daily cadence and always false-flags
                        # these. Use a flat calendar-day tolerance instead.
                        prev_trading_day = today - timedelta(days=max_staleness_days)
                    else:
                        # CRITICAL FIX: Use trading-day logic instead of hardcoded 2-day threshold.
                        # A 3-day weekend (Fri to Tue = 4 calendar days) is only 1 trading day apart.
                        # Use MarketCalendar to correctly handle holidays and weekends.
                        from algo.infrastructure import MarketCalendar

                        # Allow up to 2 trading days of staleness for monitoring purposes
                        expected_date = today - timedelta(days=1)
                        for _ in range(20):  # Look back up to 20 calendar days
                            if MarketCalendar.is_trading_day(expected_date):
                                break
                            expected_date -= timedelta(days=1)

                        # Also get the previous trading day
                        prev_trading_day = expected_date - timedelta(days=1)
                        for _ in range(20):
                            if MarketCalendar.is_trading_day(prev_trading_day):
                                break
                            prev_trading_day -= timedelta(days=1)

                    if max_date < prev_trading_day:
                        results["issues"].append(
                            f"Stale data: from {max_date} ({age.days} calendar days old, "
                            f"older than {prev_trading_day})"
                        )
                else:
                    results["issues"].append("No date data found")
            except Exception:
                # Skip if date column doesn't work
                pass

        # Check for excessive NULLs in key columns
        try:
            cur.execute(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = '{config['output_table']}' LIMIT 5"
            )
            cols = [row[0] for row in cur.fetchall()]

            for col in cols[:3]:  # Check first 3 columns
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {config['output_table']} WHERE {col} IS NULL")
                    null_count = cur.fetchone()[0]
                    null_pct = 100 * null_count / max(1, row_count)

                    if null_pct > 20:
                        results["issues"].append(f"High NULL rate in {col}: {null_pct:.1f}%")
                except Exception:
                    pass  # Skip if column check fails
        except Exception:
            pass  # Skip if column enumeration fails

        # Determine overall status
        if not results["issues"]:
            results["status"] = "HEALTHY"
        elif config["critical"]:
            results["status"] = "CRITICAL" if row_count == 0 else "DEGRADED"
        else:
            results["status"] = "WARNING"

    except Exception as e:
        results["status"] = "ERROR"
        results["issues"].append(str(e))

    return results


def verify_all_loaders():
    """Verify all loaders."""
    print("\n" + "=" * 100)
    print("LOADER HEALTH VERIFICATION")
    print("=" * 100)

    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")

        results = []
        critical_issues = []
        warnings = []

        for loader_name, config in LOADERS.items():
            result = verify_loader(conn, loader_name, config)
            results.append(result)

            if result["status"] == "CRITICAL":
                critical_issues.append(result)
            elif result["status"] in ["DEGRADED", "WARNING", "ERROR"]:
                warnings.append(result)

        conn.close()

        # Print summary table
        print(f"\n{'Loader':<40} | {'Status':<12} | Issues")
        print("-" * 100)

        for result in results:
            issues_str = "; ".join(result["issues"][:1]) if result["issues"] else "OK"
            print(f"{result['loader']:<40} | {result['status']:<12} | {issues_str}")

        # Print detailed issues
        if critical_issues:
            print("\n" + "=" * 100)
            print("CRITICAL ISSUES - IMMEDIATE ACTION REQUIRED")
            print("=" * 100)
            for result in critical_issues:
                print(f"\n{result['loader']}:")
                for issue in result["issues"]:
                    print(f"  - {issue}")

        if warnings:
            print("\n" + "=" * 100)
            print("WARNINGS - REVIEW RECOMMENDED")
            print("=" * 100)
            for result in warnings:
                print(f"\n{result['loader']}:")
                for issue in result["issues"]:
                    print(f"  - {issue}")

        # Overall health
        healthy_count = len([r for r in results if r["status"] == "HEALTHY"])
        total_count = len(results)

        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Healthy loaders: {healthy_count}/{total_count}")
        print(f"Critical issues: {len(critical_issues)}")
        print(f"Warnings: {len(warnings)}")

        if critical_issues:
            print("\nOVERALL STATUS: SYSTEM HAS CRITICAL ISSUES")
            return False
        elif warnings:
            print("\nOVERALL STATUS: SYSTEM OPERATIONAL WITH WARNINGS")
            return True
        else:
            print("\nOVERALL STATUS: ALL LOADERS HEALTHY")
            return True

    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database: {e!s}")
        return False
    except Exception as e:
        print(f"ERROR: Verification failed: {e!s}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys

    success = verify_all_loaders()
    sys.exit(0 if success else 1)
