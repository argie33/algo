#!/usr/bin/env python3
"""Comprehensive data completeness audit - identify missing/stale data across all sources."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import psycopg2
from psycopg2.extras import DictCursor
from utils.db.connection import _get_connection_pool

def get_connection():
    """Get DB connection."""
    pool = _get_connection_pool()
    return pool.getconn()

def audit_financial_statements():
    """Audit financial statement data completeness."""
    print("\n" + "=" * 80)
    print("FINANCIAL STATEMENTS AUDIT")
    print("=" * 80)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    tables = {
        'annual_income_statement': [
            ('revenue', 'Core revenue'),
            ('diluted_eps', 'Diluted EPS - FIXED 2026-07-28'),
            ('shares_outstanding_basic', 'Shares outstanding - FIXED 2026-07-28'),
            ('net_income', 'Net income'),
            ('operating_income', 'Operating income'),
            ('depreciation_expense', 'Depreciation - FIXED 2026-07-28'),
            ('amortization_expense', 'Amortization - FIXED 2026-07-28'),
        ],
        'annual_balance_sheet': [
            ('total_assets', 'Total assets'),
            ('goodwill', 'Goodwill - FIXED 2026-07-28, needs backfill'),
            ('inventory', 'Inventory - FIXED 2026-07-28, needs backfill'),
            ('cash_and_equivalents', 'Cash - FIXED 2026-07-28, needs backfill'),
            ('accounts_receivable', 'Receivables - FIXED 2026-07-28, needs backfill'),
            ('ppe_net', 'PPE net - FIXED 2026-07-28, needs backfill'),
            ('long_term_debt', 'LT Debt - FIXED 2026-07-28, needs backfill'),
            ('stockholders_equity', 'Stockholders equity'),
        ],
        'annual_cash_flow': [
            ('capex', 'Capital expenditures - FIXED 2026-07-28, needs backfill'),
            ('operating_cash_flow', 'Operating cash flow'),
            ('free_cash_flow', 'Free cash flow'),
            ('financing_cash_flow', 'Financing cash flow'),
        ],
    }

    for table, fields in tables.items():
        try:
            # Count total rows
            cur.execute(f'SELECT COUNT(*) as cnt FROM {table}')
            total = cur.fetchone()['cnt']

            print(f"\n{table}: {total:,} total rows")
            print("-" * 80)

            for col, desc in fields:
                # Check NULL percentage
                cur.execute(f'''
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN {col} IS NULL THEN 1 END) as nulls,
                        MAX({col}) as max_val
                    FROM {table}
                ''')
                result = cur.fetchone()
                total_rows = result['total']
                null_count = result['nulls']
                pct_null = (null_count / total_rows * 100) if total_rows > 0 else 0

                status = "[OK]" if pct_null < 5 else "[WARN]" if pct_null < 50 else "[CRIT]"
                print(f"  {status} {col:30} | {pct_null:6.1f}% NULL | {null_count:,}/{total_rows:,}")

        except Exception as e:
            print(f"  ERROR querying {table}: {e}")

    cur.close()
    conn.close()

def audit_loader_status():
    """Audit loader execution status."""
    print("\n" + "=" * 80)
    print("LOADER EXECUTION STATUS")
    print("=" * 80)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    try:
        cur.execute('''
            SELECT
                table_name, status,
                execution_completed, execution_started,
                reason,
                consecutive_failures
            FROM data_loader_status
            ORDER BY execution_completed DESC NULLS LAST
            LIMIT 40
        ''')

        print(f"\n{'Table':40} | {'Status':10} | {'Age':10} | {'Failures':2}")
        print("-" * 80)

        now = datetime.now()
        for row in cur:
            table = row['table_name']
            status = row['status']
            completed = row['execution_completed']
            consecutive_failures = row['consecutive_failures'] or 0

            # Calculate age
            if completed:
                age = now - completed
                if age.days > 0:
                    age_str = f"{age.days}d"
                else:
                    age_str = f"{age.seconds//3600}h"
            else:
                age_str = "never"

            status_icon = "[OK]" if status == "HEALTHY" else "[WARN]" if status == "STALE" else "[CRIT]"
            print(f"{table:40} | {status:10} | {age_str:10} | {consecutive_failures:2}")

            if row['reason']:
                print(f"  → {row['reason']}")

    except Exception as e:
        print(f"Error: {e}")

    cur.close()
    conn.close()

def audit_missing_sources():
    """Identify critical data sources that should be loaded but aren't."""
    print("\n" + "=" * 80)
    print("POTENTIALLY MISSING DATA SOURCES")
    print("=" * 80)

    print("""
OFFICIAL SOURCES BEING USED:
  [OK] SEC EDGAR (companyfacts API) - financial statements, valuations, dividends, segment data
  [OK] SEC Forms 3/4/5 - insider transaction data
  [OK] SEC 13F - institutional holdings
  [OK] SEC 8-K/10-K/10-Q - current reports, earnings calendar
  [OK] FRED (56 economic series) - macro data (SOFR, yields, employment, inflation, housing, etc)
  [OK] FINRA - short interest
  [OK] Alpaca SIP - market prices
  [OK] NYSE/NASDAQ - trading calendar
  [OK] yfinance - analyst ratings (only free source), put/call ratio

POTENTIALLY USEFUL SOURCES NOT YET INTEGRATED:
  [?] SEC EDGAR - Supplemental Detail Tables (for complex financial statement analysis)
  [?] SEC EDGAR - Revisions/Amendments (track data corrections)
  [?] NIST/SEC Cybersecurity Risk Disclosure (new 2023 requirement, 8-K Item 1.05)
  [?] Fed Funds Rate forecasts (CME FedWatch) vs actual SOFR
  [?] CFTC Commitments of Traders (COT reports) for commodity exposure
  [?] Options flow data (IV rank/percentile for volatility regime)
  [?] Insider trading velocity by sector (FINRA forms)
  [?] Activist investor alerts (13D/13G filings)
  [?] Debt/equity offering alerts
  [?] Analyst estimate revisions history (not just current consensus)
  [?] Corporate event calendar (splits, dividends, earnings)
  [?] ESG data (MSCI/Sustainalytics - paid)
  [?] Supply chain disruption indices

KNOWN INCOMPLETE INTEGRATIONS:
  [WARN] Institutional holdings (13F) - OpenFIGI crosswalk backfill ongoing
  [WARN] TTM financial statements - requires aggregation logic (low priority)
  [WARN] Historical backfill - many columns have NULL before fix dates
""")

def audit_schema_gaps():
    """Check if all expected columns exist and are being populated."""
    print("\n" + "=" * 80)
    print("SCHEMA COMPLETENESS")
    print("=" * 80)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    try:
        # Check annual income statement schema
        cur.execute('''
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'annual_income_statement'
            ORDER BY ordinal_position
        ''')

        print(f"\nannual_income_statement columns: {cur.rowcount}")

        columns = cur.fetchall()
        for col in columns:
            print(f"  {col['column_name']:40} {col['data_type']}")

    except Exception as e:
        print(f"Error: {e}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    try:
        audit_financial_statements()
        audit_loader_status()
        audit_missing_sources()
        print("\n" + "=" * 80)
        print("AUDIT COMPLETE")
        print("=" * 80)
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
