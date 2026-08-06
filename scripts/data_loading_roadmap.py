#!/usr/bin/env python3
"""Comprehensive data loading roadmap.

Shows:
1. What data is loaded by which loaders
2. Which fields have high NULL rates (missing data)
3. Which formulas depend on those fields
4. What needs to be fixed to get complete data coverage
"""

import sys
sys.path.insert(0, '.')

from utils.db.connection import get_db_connection
from loaders.loader_registry import LOADER_TABLES

def get_table_row_count(table_name: str) -> int:
    """Get row count for a table."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT COUNT(*) FROM {table_name}')
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except:
        cur.close()
        conn.close()
        return 0

def get_column_null_rate(table_name: str, column_name: str) -> float | None:
    """Get NULL rate for a specific column."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(f'''
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN {column_name} IS NULL THEN 1 END) as nulls
            FROM {table_name}
        ''')
        total, nulls = cur.fetchone()
        cur.close()
        conn.close()
        if total == 0:
            return None
        return (nulls / total * 100)
    except:
        cur.close()
        conn.close()
        return None

def main():
    print("\n" + "="*80)
    print("DATA LOADING ROADMAP - Complete Coverage Analysis")
    print("="*80)

    print("\n" + "="*80)
    print("PART 1: LOADER STATUS - What's Being Loaded")
    print("="*80)

    for loader, tables in sorted(LOADER_TABLES.items()):
        print(f"\n{loader}")
        print(f"  Writes to: {tables[0]} (primary)" + (f" + {len(tables)-1} others" if len(tables) > 1 else ""))
        for table in tables:
            count = get_table_row_count(table)
            status = "LOADED" if count > 0 else "EMPTY"
            print(f"    - {table}: {count:,} rows [{status}]")

    print("\n\n" + "="*80)
    print("PART 2: DATA COMPLETENESS - Fields with HIGH NULL Rates (>25%)")
    print("="*80)
    print("\nThese fields are missing data that should be filled in:\n")

    # Check specific critical fields
    high_null_fields = [
        ("price_daily", "adj_close", "Adjusted close prices (needed for returns calc)"),
        ("price_daily", "data_source", "Price data source identification"),
        ("buy_sell_daily", "reason", "Buy/sell signal reasoning"),
        ("stock_scores", "components", "Component score breakdown"),
        ("stock_scores", "data_sources", "Data source attribution"),
        ("stock_scores", "unavailable_metrics", "List of unavailable metrics"),
        ("earnings_calendar", "announce_time", "Announcement time precision"),
        ("earnings_calendar", "eps_estimate", "EPS estimates"),
        ("earnings_calendar", "actual_eps", "Actual EPS results"),
        ("earnings_calendar", "revenue_estimate", "Revenue estimates"),
        ("earnings_calendar", "actual_revenue", "Actual revenue"),
        ("technical_data_daily", "roc_252d", "252-day rate of change"),
        ("technical_data_daily", "sma_200", "200-day simple moving average"),
    ]

    for table, col, description in high_null_fields:
        try:
            null_rate = get_column_null_rate(table, col)
            if null_rate is not None and null_rate > 25:
                print(f"[{null_rate:5.1f}% NULL] {table}.{col:<30} - {description}")
        except:
            pass

    print("\n\n" + "="*80)
    print("PART 3: MISSING DATA - Tables with No Rows")
    print("="*80)
    print("\nThese tables are expected but have no data:\n")

    expected_tables = [
        "analyst_earnings_estimates",
        "analyst_sentiment_analysis",
        "analyst_upgrade_downgrade",
        "company_profile",
        "dividend_data",
        "economic_data",
        "insider_holdings_sec",
        "insider_transaction_velocity",
        "institutional_holdings_13f",
        "positioning_metrics",
        "quality_metrics",
        "value_metrics",
        "growth_metrics",
        "momentum_metrics",
        "stability_metrics",
        "sector_ranking",
        "industry_ranking",
        "sector_performance",
        "trend_template_data",
    ]

    for table in expected_tables:
        try:
            count = get_table_row_count(table)
            if count == 0:
                print(f"[NO DATA] {table}")
            elif count < 1000:
                print(f"[SPARSE]  {table}: only {count} rows")
        except:
            print(f"[ERROR]   {table}: table may not exist")

    print("\n\n" + "="*80)
    print("PART 4: WHAT FORMULAS NEED")
    print("="*80)
    print("""
Key formulas and what data they need:

VALUE SCORE:
  - Forward P/E (analyst_earnings_estimates.eps_forward)
  - Book value, debt levels (financial_statements)
  - Dividend yield (dividend_data)

GROWTH SCORE:
  - EPS growth rate (analyst_earnings_estimates, financial_statements)
  - Revenue growth (financial_statements)
  - Analyst estimate revisions (analyst_earnings_estimates)

QUALITY SCORE:
  - ROE, ROA (financial_statements)
  - Debt/equity (financial_statements)
  - Earnings quality (financial_statements)

MOMENTUM SCORE:
  - Technical indicators (technical_data_daily)
  - Market sentiment (market_status_daily)
  - Insider buying (insider_transaction_velocity)

STABILITY SCORE:
  - Beta, volatility (risk_metrics_daily)
  - Debt ratios (financial_statements)
  - Cash flow stability (financial_statements)

POSITIONING SCORE:
  - Institutional ownership (institutional_holdings_13f)
  - Insider ownership (insider_holdings_sec)
  - Short interest (short_interest_finra)
""")

    print("\n" + "="*80)
    print("PART 5: NEXT STEPS TO COMPLETE DATA COVERAGE")
    print("="*80)
    print("""
PRIORITY 1 (Critical for all scores):
  1. Fix analyst_earnings_estimates loader - need forward EPS
  2. Fix financial_statements loader - need income/balance sheet data
  3. Populate missing growth_metrics, quality_metrics, value_metrics

PRIORITY 2 (Important for quality scores):
  1. Load insider_transaction_velocity properly
  2. Load institutional_holdings_13f data
  3. Load dividend_data

PRIORITY 3 (Enhancement):
  1. Fix earnings_calendar precision (announce_time, eps actual/estimate)
  2. Complete technical indicator coverage (sma_200, roc_252d)
  3. Add analyst sentiment and upgrade/downgrade signals

ACTION ITEMS:
  - Check which loaders are running in start_dashboard_dev.py
  - Verify API keys and credentials for external data sources
  - Fix any loader errors in logs
  - Add missing fields to score calculation formulas
  - Test end-to-end from loader → formula → dashboard
""")

if __name__ == "__main__":
    main()
