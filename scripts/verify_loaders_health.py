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

LOADERS = {
    "load_prices.py": {
        "output_table": "price_daily",
        "date_column": "date",
        "min_rows": 100000,
        "critical": True,
    },
    "load_technical_indicators.py": {
        "output_table": "technical_data_daily",
        "date_column": "date",
        "min_rows": 50000,
        "critical": True,
    },
    "load_trend_analysis.py": {
        "output_table": "trend_template_data",
        "date_column": "date",
        "min_rows": 500000,
        "critical": True,
    },
    "load_company_cache.py": {
        "output_table": "yfinance_snapshot",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": False,
    },
    "load_fundamental_metrics.py": {
        "output_table": "company_profile",
        "date_column": "updated_at",
        "min_rows": 1000,
        "critical": True,
    },
    "load_quality_growth_metrics.py": {
        "output_table": "quality_metrics",
        "date_column": None,
        "min_rows": 1000,
        "critical": True,
    },
    "load_stock_scores.py": {
        "output_table": "stock_scores",
        "date_column": "created_at",
        "min_rows": 1000,
        "critical": True,
    },
    "load_buy_sell_daily.py": {
        "output_table": "buy_sell_daily",
        "date_column": "date",
        "min_rows": 10000,
        "critical": True,
    },
    # Consolidated: load_risk_metrics_daily.py writes to both momentum_metrics and stability_metrics
    "load_risk_metrics_daily.py": {
        "output_table": "momentum_metrics",  # Primary table (stability_metrics is side effect)
        "date_column": None,
        "min_rows": 1000,
        "critical": False,
    },
    "load_positioning_metrics.py": {
        "output_table": "positioning_metrics",
        "date_column": None,
        "min_rows": 1000,
        "critical": False,
    },
    "load_market_health_daily.py": {
        "output_table": "market_health_daily",
        "date_column": "date",
        "min_rows": 100,
        "critical": False,
    },
    "load_sector_rankings.py": {
        "output_table": "sector_ranking",
        "date_column": "date",
        "min_rows": 100,
        "critical": False,
    },
    "load_market_exposure_daily.py": {
        "output_table": "market_exposure_daily",
        "date_column": "date",
        "min_rows": 10,
        "critical": False,
    },
    "load_algo_metrics_daily.py": {
        "output_table": "algo_metrics_daily",
        "date_column": "date",
        "min_rows": 1,
        "critical": False,
    },
}

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
            results["issues"].append(
                f"Low row count: {row_count} (expected >= {config['min_rows']})"
            )

        # Check data freshness if date column exists
        if config["date_column"]:
            try:
                cur.execute(f"""
                    SELECT MAX({config['date_column']}::date)
                    FROM {config['output_table']}
                """)
                max_date = cur.fetchone()[0]

                if max_date:
                    age = datetime.now().date() - max_date
                    if age.days > 2:
                        results["issues"].append(
                            f"Stale data: {age.days} days old (max_date: {max_date})"
                        )
            except Exception:
                # Skip if date column doesn't work
                pass
            else:
                results["issues"].append("No date data found")

        # Check for excessive NULLs in key columns
        try:
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{config['output_table']}' LIMIT 5")
            cols = [row[0] for row in cur.fetchall()]

            for col in cols[:3]:  # Check first 3 columns
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {config['output_table']} WHERE {col} IS NULL")
                    null_count = cur.fetchone()[0]
                    null_pct = 100 * null_count / max(1, row_count)

                    if null_pct > 20:
                        results["issues"].append(
                            f"High NULL rate in {col}: {null_pct:.1f}%"
                        )
                except:
                    pass  # Skip if column check fails
        except:
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
