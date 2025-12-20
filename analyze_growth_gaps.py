#!/usr/bin/env python3
"""
Growth Metrics Gap Analyzer - Identify missing data without running all loaders.
Analyzes data availability across all tables to guide selective loading.

Usage:
  python analyze_growth_gaps.py [--summary|--detailed|--symbols|--fix]

  --summary     Show overall coverage gaps (default)
  --detailed    Show per-metric gaps with specific symbols missing
  --symbols     List symbols missing each metric
  --fix         Generate targeted fix plan (which loaders to run)
"""

import logging
import os
import sys
from datetime import date
from typing import Dict, List, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Database connection (from environment variables)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'stocks')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_PORT = int(os.getenv('DB_PORT', '5432'))


def get_db_connection():
    """Create database connection."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)


def analyze_growth_metrics_coverage() -> Dict:
    """Analyze coverage of growth_metrics table and upstream data sources."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    results = {
        "total_symbols": 0,
        "total_unique_dates": 0,
        "growth_metrics_coverage": {},
        "upstream_coverage": {},
        "data_gaps": {},
        "symbols_by_gap": {},
        "recommendations": [],
    }

    try:
        # 1. Get total symbols in stock_symbols table
        cur.execute("SELECT COUNT(DISTINCT symbol) as count FROM stock_symbols;")
        results["total_symbols"] = cur.fetchone()["count"]
        logger.info(f"Total symbols in database: {results['total_symbols']}")

        # 2. Get growth_metrics coverage by metric
        cur.execute("""
            SELECT
                'revenue_growth_3y_cagr' as metric,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) as non_null,
                COUNT(DISTINCT symbol) as unique_symbols
            FROM growth_metrics
            WHERE date = CURRENT_DATE
            UNION ALL
            SELECT
                'eps_growth_3y_cagr',
                COUNT(*),
                COUNT(CASE WHEN eps_growth_3y_cagr IS NOT NULL THEN 1 END),
                COUNT(DISTINCT symbol)
            FROM growth_metrics
            WHERE date = CURRENT_DATE
            UNION ALL
            SELECT
                'operating_income_growth_yoy',
                COUNT(*),
                COUNT(CASE WHEN operating_income_growth_yoy IS NOT NULL THEN 1 END),
                COUNT(DISTINCT symbol)
            FROM growth_metrics
            WHERE date = CURRENT_DATE
            UNION ALL
            SELECT
                'fcf_growth_yoy',
                COUNT(*),
                COUNT(CASE WHEN fcf_growth_yoy IS NOT NULL THEN 1 END),
                COUNT(DISTINCT symbol)
            FROM growth_metrics
            WHERE date = CURRENT_DATE
            UNION ALL
            SELECT
                'net_income_growth_yoy',
                COUNT(*),
                COUNT(CASE WHEN net_income_growth_yoy IS NOT NULL THEN 1 END),
                COUNT(DISTINCT symbol)
            FROM growth_metrics
            WHERE date = CURRENT_DATE
            UNION ALL
            SELECT
                'quarterly_growth_momentum',
                COUNT(*),
                COUNT(CASE WHEN quarterly_growth_momentum IS NOT NULL THEN 1 END),
                COUNT(DISTINCT symbol)
            FROM growth_metrics
            WHERE date = CURRENT_DATE;
        """)

        for row in cur.fetchall():
            metric = row["metric"]
            coverage = (
                (row["non_null"] / row["total_rows"] * 100)
                if row["total_rows"] > 0
                else 0
            )
            results["growth_metrics_coverage"][metric] = {
                "total_rows": row["total_rows"],
                "non_null": row["non_null"],
                "unique_symbols": row["unique_symbols"],
                "coverage_pct": round(coverage, 2),
            }

        # 3. Upstream data availability
        upstream_queries = {
            "annual_income_statement": "SELECT COUNT(DISTINCT symbol) as count FROM annual_income_statement;",
            "quarterly_income_statement": "SELECT COUNT(DISTINCT symbol) as count FROM quarterly_income_statement;",
            "annual_cash_flow": "SELECT COUNT(DISTINCT symbol) as count FROM annual_cash_flow;",
            "annual_balance_sheet": "SELECT COUNT(DISTINCT symbol) as count FROM annual_balance_sheet;",
            "earnings_history": "SELECT COUNT(DISTINCT symbol) as count FROM earnings_history;",
            "key_metrics": "SELECT COUNT(DISTINCT symbol) as count FROM key_metrics WHERE date = CURRENT_DATE;",
        }

        for table_name, query in upstream_queries.items():
            cur.execute(query)
            count = cur.fetchone()["count"]
            coverage_pct = (count / results["total_symbols"] * 100) if results["total_symbols"] > 0 else 0
            results["upstream_coverage"][table_name] = {
                "symbols_with_data": count,
                "coverage_pct": round(coverage_pct, 2),
            }

        # 4. Identify gap categories
        cur.execute("""
            SELECT
                CASE
                    WHEN (SELECT COUNT(*) FROM annual_income_statement WHERE annual_income_statement.symbol = ss.symbol) > 0
                        THEN 'has_annual_statements'
                    WHEN (SELECT COUNT(*) FROM quarterly_income_statement WHERE quarterly_income_statement.symbol = ss.symbol) > 0
                        THEN 'has_quarterly_statements'
                    WHEN (SELECT COUNT(*) FROM key_metrics WHERE key_metrics.symbol = ss.symbol AND date = CURRENT_DATE) > 0
                        THEN 'has_key_metrics_only'
                    ELSE 'no_data'
                END as gap_category,
                COUNT(*) as symbol_count
            FROM stock_symbols ss
            LEFT JOIN growth_metrics gm ON ss.symbol = gm.symbol AND gm.date = CURRENT_DATE
            GROUP BY gap_category;
        """)

        for row in cur.fetchall():
            results["data_gaps"][row["gap_category"]] = row["symbol_count"]

        # 5. Generate recommendations
        logger.info("\n" + "="*80)
        logger.info("DATA AVAILABILITY SUMMARY")
        logger.info("="*80)

        print("\n📊 GROWTH METRICS COVERAGE (Today's Data)")
        print("-" * 80)
        for metric, coverage in results["growth_metrics_coverage"].items():
            pct = coverage["coverage_pct"]
            status = "✅" if pct > 80 else "⚠️" if pct > 50 else "❌"
            print(
                f"{status} {metric:40} {coverage['non_null']:6}/{coverage['total_rows']:6} ({pct:5.1f}%)"
            )

        print("\n📦 UPSTREAM DATA SOURCES")
        print("-" * 80)
        for source, coverage in results["upstream_coverage"].items():
            pct = coverage["coverage_pct"]
            status = "✅" if pct > 80 else "⚠️" if pct > 50 else "❌"
            print(
                f"{status} {source:40} {coverage['symbols_with_data']:6} symbols ({pct:5.1f}%)"
            )

        print("\n🔍 DATA GAP CATEGORIES")
        print("-" * 80)
        total_gaps = sum(results["data_gaps"].values())
        for category, count in sorted(results["data_gaps"].items()):
            pct = (count / total_gaps * 100) if total_gaps > 0 else 0
            print(f"  {category:40} {count:6} symbols ({pct:5.1f}%)")

        # 6. Generate fix recommendations
        print("\n💡 REMEDIATION RECOMMENDATIONS")
        print("-" * 80)

        annual_stmt_coverage = results["upstream_coverage"].get(
            "annual_income_statement", {}
        ).get("coverage_pct", 0)
        quarterly_stmt_coverage = results["upstream_coverage"].get(
            "quarterly_income_statement", {}
        ).get("coverage_pct", 0)
        key_metrics_coverage = results["upstream_coverage"].get("key_metrics", {}).get(
            "coverage_pct", 0
        )

        recommendations = []

        if annual_stmt_coverage < 100:
            missing_annual = results["total_symbols"] - (
                results["upstream_coverage"].get("annual_income_statement", {}).get(
                    "symbols_with_data", 0
                )
            )
            recommendations.append(
                f"  1. Run loadannualincomestatement.py for ~{missing_annual} symbols "
                f"(to reach 100% vs current {annual_stmt_coverage:.1f}%)"
            )

        if quarterly_stmt_coverage < 100:
            missing_quarterly = results["total_symbols"] - (
                results["upstream_coverage"]
                .get("quarterly_income_statement", {})
                .get("symbols_with_data", 0)
            )
            recommendations.append(
                f"  2. Run loadquarterlyincomestatement.py for ~{missing_quarterly} symbols "
                f"(to reach 100% vs current {quarterly_stmt_coverage:.1f}%)"
            )

        if key_metrics_coverage < 100:
            missing_key = results["total_symbols"] - (
                results["upstream_coverage"].get("key_metrics", {}).get(
                    "symbols_with_data", 0
                )
            )
            recommendations.append(
                f"  3. Run loaddailycompanydata.py for ~{missing_key} symbols "
                f"(to reach 100% vs current {key_metrics_coverage:.1f}%)"
            )

        recommendations.append(
            f"  4. After upstream loaders complete, run: "
            f"python selective_growth_loader.py --batch-size 500"
        )

        for rec in recommendations:
            print(rec)
            results["recommendations"].append(rec)

        print("\n📝 STRATEGY")
        print("-" * 80)
        print("  AVOID: Running loadfactormetrics.py on all symbols (causes context window errors)")
        print("  INSTEAD:")
        print("    1. Run upstream loaders SEQUENTIALLY for specific missing symbols")
        print("    2. Use selective_growth_loader.py to update only missing growth metrics")
        print("    3. Process in batches of 500 symbols at a time")
        print("    4. This prevents context window explosion and memory issues")
        print("="*80 + "\n")

    except Exception as e:
        logger.error(f"Error during analysis: {e}")
        raise
    finally:
        cur.close()
        conn.close()

    return results


if __name__ == "__main__":
    analyze_growth_metrics_coverage()
