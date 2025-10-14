#!/usr/bin/env python3
"""Quick script to check if quarterly financial data exists for stock A"""

import os
import psycopg2

# Database config
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "password")
host = os.environ.get("DB_HOST", "localhost")
port = int(os.environ.get("DB_PORT", "5432"))
dbname = os.environ.get("DB_NAME", "stocks")

conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=dbname)
cursor = conn.cursor()

symbol = 'A'

print("=" * 80)
print(f"Checking quarterly financial data for symbol: {symbol}")
print("=" * 80)

# Check quarterly_income_statement
print("\n1. QUARTERLY INCOME STATEMENT")
cursor.execute("""
    SELECT date, item_name, value
    FROM quarterly_income_statement
    WHERE symbol = %s AND item_name IN ('Net Income', 'Total Revenue')
    ORDER BY date DESC
    LIMIT 10;
""", (symbol,))
rows = cursor.fetchall()
if rows:
    for date, item, value in rows:
        print(f"  {date} | {item}: {value}")
else:
    print("  ❌ NO DATA FOUND")

# Check quarterly_balance_sheet
print("\n2. QUARTERLY BALANCE SHEET")
cursor.execute("""
    SELECT date, item_name, value
    FROM quarterly_balance_sheet
    WHERE symbol = %s AND item_name IN ('Total Assets', 'Total Liabilities', 'Total Equity', 'Current Assets', 'Current Liabilities')
    ORDER BY date DESC
    LIMIT 15;
""", (symbol,))
rows = cursor.fetchall()
if rows:
    for date, item, value in rows:
        print(f"  {date} | {item}: {value}")
else:
    print("  ❌ NO DATA FOUND")

# Check quarterly_cash_flow
print("\n3. QUARTERLY CASH FLOW")
cursor.execute("""
    SELECT date, item_name, value
    FROM quarterly_cash_flow
    WHERE symbol = %s AND item_name IN ('Operating Cash Flow', 'Free Cash Flow')
    ORDER BY date DESC
    LIMIT 10;
""", (symbol,))
rows = cursor.fetchall()
if rows:
    for date, item, value in rows:
        print(f"  {date} | {item}: {value}")
else:
    print("  ❌ NO DATA FOUND")

# Check what's in quality_metrics for this symbol
print("\n4. CURRENT QUALITY METRICS")
cursor.execute("""
    SELECT symbol, date, accruals_ratio, fcf_to_net_income, debt_to_equity, current_ratio, asset_turnover
    FROM quality_metrics
    WHERE symbol = %s
    ORDER BY date DESC
    LIMIT 3;
""", (symbol,))
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"  {row[0]} | {row[1]}")
        print(f"    accruals_ratio: {row[2]}")
        print(f"    fcf_to_net_income: {row[3]}")
        print(f"    debt_to_equity: {row[4]}")
        print(f"    current_ratio: {row[5]}")
        print(f"    asset_turnover: {row[6]}")
else:
    print("  ❌ NO QUALITY METRICS FOUND")

cursor.close()
conn.close()

print("\n" + "=" * 80)
