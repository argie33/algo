#!/usr/bin/env python3
"""XBRL/SEC Data Quality Investigation - HONA & FDXF Spinoff Issue

FINDING: Recent spinoffs (HONA, FDXF) have NO financial data parsed from XBRL
STATUS: Scores showing 33% completeness with Quality/Value/Growth=NULL

ISSUE:
- Fiscal Year: 0 (FIXED: now 2025)
- Financial Data: ALL NULL (total_assets, total_liabilities, stockholders_equity, etc)
- SEC Valuations: Exist but incomplete
- XBRL Parser: Failing to extract values for these companies

ROOT CAUSE CANDIDATES:
1. XBRL namespace mapping issue for new companies
2. Spinoff financial statements use non-standard XBRL tags
3. SEC filing not yet properly indexed in data source
4. Company profile missing from SEC database

AFFECTED STOCKS (S&P 500):
- HONA: Honeywell Aerospace (spun from HON)
- FDXF: FedEx Freight (spun from FDX)
"""

from utils.db import DatabaseContext
from datetime import datetime

print("=" * 90)
print("XBRL/SEC DATA QUALITY AUDIT - HONA & FDXF INVESTIGATION")
print("=" * 90)

try:
    with DatabaseContext('read') as cur:
        # 1. Check if SEC annual income statement exists and has data
        print("\n1. ANNUAL INCOME STATEMENT DATA:")
        for symbol in ['HONA', 'FDXF']:
            cur.execute('''
                SELECT symbol, fiscal_year, revenue, net_income, operating_income,
                       earnings_per_share
                FROM annual_income_statement WHERE symbol = %s
            ''', [symbol])
            row = cur.fetchone()
            if row:
                sym, fy, rev, ni, oi, eps = row
                print(f"  {sym}: FY{fy} | Revenue={rev} | NI={ni} | OI={oi} | EPS={eps}")
                if all(v is None for v in [rev, ni, oi, eps]):
                    print(f"    ^^ WARNING: All income statement fields are NULL")

        # 2. Check sec_valuations to see what's available
        print("\n2. SEC VALUATIONS:")
        for symbol in ['HONA', 'FDXF']:
            cur.execute('''
                SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield
                FROM sec_valuations WHERE symbol = %s
            ''', [symbol])
            row = cur.fetchone()
            if row:
                sym, pe, pb, ps, peg, div = row
                has_data = sum(1 for v in [pe, pb, ps, peg, div] if v is not None)
                print(f"  {sym}: {has_data}/5 valuation metrics available")
                if has_data == 0:
                    print(f"    ^^ WARNING: All valuations are NULL")

        # 3. Check stock scores to see what's being computed
        print("\n3. STOCK SCORES STATUS:")
        for symbol in ['HONA', 'FDXF']:
            cur.execute('''
                SELECT symbol, composite_score, momentum_score, quality_score, value_score,
                       growth_score, stability_score, positioning_score,
                       data_completeness, data_unavailable
                FROM stock_scores WHERE symbol = %s
            ''', [symbol])
            row = cur.fetchone()
            if row:
                sym, comp, mom, qual, val, growth, stab, pos, complete, unavail = row
                print(f"  {sym}:")
                comp_str = f"{comp:.1f}" if comp else "NULL"
                complete_str = f"{complete:.0f}%" if complete else "NULL"
                print(f"    Composite: {comp_str} | Complete: {complete_str} | Unavailable: {unavail}")
                scores = [('Momentum', mom), ('Quality', qual), ('Value', val),
                         ('Growth', growth), ('Stability', stab), ('Positioning', pos)]
                for name, score in scores:
                    status = f"{score:.0f}" if score else "NULL"
                    print(f"      {name:12s}: {status}")

        # 4. Check what loaders have tried to process these symbols
        print("\n4. RECENT LOADER STATUS:")
        cur.execute('''
            SELECT table_name, status, COUNT(*) as count
            FROM data_loader_status
            GROUP BY table_name, status
            HAVING table_name IN ('quality_metrics', 'value_metrics', 'growth_metrics')
            ORDER BY table_name
        ''')
        rows = cur.fetchall()
        for table, status, count in rows:
            print(f"  {table}: {status} ({count} rows)")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 90)
print("RECOMMENDATIONS:")
print("=" * 90)
print("""
1. ROOT CAUSE: XBRL parser creates empty records for HONA/FDXF
   - Fiscal year missing (0) - FIXED to 2025
   - Financial values all NULL - REQUIRES XBRL PARSER FIX

2. NEXT STEPS:
   a) Check SEC Edgar for HONA/FDXF XBRL filing format
   b) Update load_financial_statements.py XBRL parser for spinoffs
   c) Re-run: python loaders/load_financial_statements.py --symbols HONA,FDXF
   d) Re-run: python loaders/load_value_quality_growth_metrics.py --symbols HONA,FDXF

3. VALIDATION:
   After fixes, verify:
   - annual_balance_sheet has non-NULL values
   - quality_metrics has non-NULL scores
   - stock_scores.data_completeness > 50%
""")
