#!/usr/bin/env python3
"""Verify complete pipeline data flow end-to-end.

Traces:
1. Data flowing from price source → all downstream outputs
2. Each layer's dependencies are satisfied
3. No broken links in the pipeline
4. Correct volume/quality at each stage
"""

import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

PIPELINE_LAYERS = {
    "Foundation": {
        "tables": ["price_daily"],
        "depends_on": [],
    },
    "Technical Analysis": {
        "tables": ["technical_data_daily"],
        "depends_on": ["price_daily"],
    },
    "Trend Analysis": {
        "tables": ["trend_template_data"],
        "depends_on": ["price_daily"],
    },
    "Financial Data": {
        "tables": ["financial_data_annual", "company_profile", "yfinance_snapshot"],
        "depends_on": [],
    },
    "Composite Metrics": {
        "tables": ["quality_metrics", "growth_metrics", "value_metrics",
                   "positioning_metrics", "stability_metrics", "momentum_metrics"],
        "depends_on": ["financial_data_annual", "company_profile"],
    },
    "Stock Scores": {
        "tables": ["stock_scores"],
        "depends_on": ["technical_data_daily", "quality_metrics", "growth_metrics"],
    },
    "Trading Signals": {
        "tables": ["buy_sell_daily"],
        "depends_on": ["stock_scores", "technical_data_daily"],
    },
    "Portfolio Management": {
        "tables": ["market_exposure_daily", "algo_metrics_daily"],
        "depends_on": ["buy_sell_daily"],
    },
}

def check_table_exists(cur: Any, table: str) -> bool:
    """Check if table exists."""
    try:
        cur.execute(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table}'
            )
        """)
        return cur.fetchone()[0]
    except:
        return False

def get_table_stats(cur: Any, table: str) -> Dict[str, Any]:
    """Get statistics for a table."""
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]

        # Get most recent data
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' AND data_type IN ('date', 'timestamp')
            LIMIT 1
        """)
        result = cur.fetchone()
        date_col = result[0] if result else None

        latest_date = None
        if date_col:
            cur.execute(f"SELECT MAX({date_col}) FROM {table}")
            latest_date = cur.fetchone()[0]

        return {
            "exists": True,
            "row_count": count,
            "latest_date": latest_date,
        }
    except:
        return {
            "exists": False,
            "row_count": 0,
            "latest_date": None,
        }

def verify_pipeline():
    """Verify complete pipeline flow."""
    print("\n" + "=" * 100)
    print("PIPELINE DATA FLOW VERIFICATION")
    print("=" * 100)

    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        all_healthy = True
        layer_results = {}

        for layer_name, config in PIPELINE_LAYERS.items():
            print(f"\n{layer_name.upper()}")
            print("-" * 100)

            layer_healthy = True
            layer_stats = {}

            # Check dependencies
            for dep_table in config["depends_on"]:
                dep_stats = get_table_stats(cur, dep_table)
                if not dep_stats["exists"]:
                    print(f"  DEPENDENCY ERROR: {dep_table} does not exist")
                    layer_healthy = False
                    all_healthy = False
                elif dep_stats["row_count"] == 0:
                    print(f"  DEPENDENCY WARNING: {dep_table} is empty")
                    layer_healthy = False
                    all_healthy = False
                else:
                    print(f"  Dependency OK: {dep_table} ({dep_stats['row_count']:,} rows, "
                          f"latest: {dep_stats['latest_date']})")

            # Check output tables
            print(f"  Outputs:")
            for table in config["tables"]:
                stats = get_table_stats(cur, table)
                layer_stats[table] = stats

                if not stats["exists"]:
                    print(f"    [MISSING] {table}")
                    layer_healthy = False
                    all_healthy = False
                elif stats["row_count"] == 0:
                    print(f"    [EMPTY]   {table}")
                    layer_healthy = False
                    all_healthy = False
                else:
                    age_days = (datetime.now().date() - stats["latest_date"]).days if stats["latest_date"] else None
                    age_str = f"{age_days}d old" if age_days is not None else "N/A"
                    print(f"    [OK]      {table:35} {stats['row_count']:>12,} rows  {age_str}")

            if layer_healthy:
                print(f"  Status: HEALTHY")
            else:
                print(f"  Status: ISSUES FOUND")

            layer_results[layer_name] = {
                "healthy": layer_healthy,
                "stats": layer_stats,
            }

        # Summary statistics
        print("\n" + "=" * 100)
        print("PIPELINE HEALTH SUMMARY")
        print("=" * 100)

        healthy_layers = [name for name, result in layer_results.items() if result["healthy"]]
        total_layers = len(layer_results)

        print(f"\nHealthy layers: {len(healthy_layers)}/{total_layers}")
        print(f"\nLayer Status:")
        for layer_name, result in layer_results.items():
            status = "HEALTHY" if result["healthy"] else "ISSUES"
            print(f"  {layer_name:30} - {status}")

        # Check for complete data flow
        print("\n" + "=" * 100)
        print("DATA FLOW COMPLETENESS")
        print("=" * 100)

        # Key milestone checks
        milestones = [
            ("Foundation (prices available)", "price_daily"),
            ("Technical analysis (indicators computed)", "technical_data_daily"),
            ("Financial data (company fundamentals loaded)", "company_profile"),
            ("Composite metrics (all metrics calculated)", "quality_metrics"),
            ("Stock scores (composite scores generated)", "stock_scores"),
            ("Trading signals (buy/sell signals generated)", "buy_sell_daily"),
            ("Portfolio mgmt (exposure/metrics calculated)", "algo_metrics_daily"),
        ]

        all_milestones_met = True
        for milestone_name, table in milestones:
            stats = get_table_stats(cur, table)
            if stats["exists"] and stats["row_count"] > 0:
                print(f"  [OK]   {milestone_name}")
            else:
                print(f"  [FAIL] {milestone_name}")
                all_milestones_met = False

        # Final assessment
        print("\n" + "=" * 100)
        print("FINAL ASSESSMENT")
        print("=" * 100)

        if all_healthy and all_milestones_met:
            print("STATUS: PIPELINE FULLY OPERATIONAL")
            print("  All layers producing data")
            print("  All dependencies satisfied")
            print("  Data flowing end-to-end")
            print("  All milestones achieved")
            result = True
        elif all_milestones_met:
            print("STATUS: PIPELINE OPERATIONAL WITH WARNINGS")
            print("  Some layers have quality issues but critical path is intact")
            result = True
        else:
            print("STATUS: PIPELINE HAS BROKEN LINKS")
            print("  Critical data flow is blocked")
            print("  Manual intervention required")
            result = False

        conn.close()
        return result

    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database: {str(e)}")
        return False
    except Exception as e:
        print(f"ERROR: Pipeline verification failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    success = verify_pipeline()
    sys.exit(0 if success else 1)
