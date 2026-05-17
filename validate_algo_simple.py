#!/usr/bin/env python3
"""
Simple Algo Validation - Check critical production readiness items.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import date

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

try:
    from config.credential_helper import get_db_password
except ImportError:
    def get_db_password():
        return os.getenv("DB_PASSWORD", "")


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )


print("=" * 70)
print("CRITICAL PRODUCTION READINESS CHECKS")
print("=" * 70)

issues = []
passed = 0

# ===== 1. DATA FRESHNESS =====
print("\n1. DATA FRESHNESS")
conn = get_db_conn()
cur = conn.cursor()

cur.execute("SELECT MAX(date) FROM price_daily")
latest_price = cur.fetchone()[0]
days_stale = (date.today() - latest_price).days if latest_price else 999

if days_stale <= 2:
    print(f"   [OK] Price data fresh ({days_stale} days old)")
    passed += 1
else:
    print(f"   [FAIL] Price data STALE ({days_stale} days old)")
    issues.append(f"Price data {days_stale} days stale (>2 day threshold)")

cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '2 days'")
fresh_symbols = cur.fetchone()[0]
print(f"   [OK] {fresh_symbols} symbols with fresh data")
passed += 1

conn.close()

# ===== 2. STOCK SCORES =====
print("\n2. STOCK SCORES & SIGNAL GENERATION")
conn = get_db_conn()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL")
scored_symbols = cur.fetchone()[0]
print(f"   [OK] {scored_symbols} symbols with composite scores")
passed += 1

cur.execute("""
    SELECT
        MIN(composite_score) as min_score,
        MAX(composite_score) as max_score,
        AVG(composite_score) as avg_score
    FROM stock_scores
    WHERE composite_score IS NOT NULL
""")
min_s, max_s, avg_s = cur.fetchone()

if min_s == max_s:
    print(f"   [FAIL] All scores are identical ({min_s}) - CALCULATION BROKEN")
    issues.append("Stock score calculation is broken (all values identical)")
elif max_s - min_s < 10:
    print(f"   [WARN] Score distribution too narrow: {min_s:.1f}-{max_s:.1f}")
    issues.append("Stock scores have insufficient variation")
else:
    print(f"   [OK] Scores vary: min={min_s:.1f}, avg={avg_s:.1f}, max={max_s:.1f}")
    passed += 1

conn.close()

# ===== 3. BUY/SELL SIGNALS =====
print("\n3. BUY/SELL SIGNALS")
conn = get_db_conn()
cur = conn.cursor()

cur.execute("""
    SELECT
        date,
        COUNT(*) as total,
        SUM(CASE WHEN signal = 'BUY' THEN 1 ELSE 0 END) as buys,
        SUM(CASE WHEN signal = 'SELL' THEN 1 ELSE 0 END) as sells
    FROM buy_sell_daily
    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY date
    ORDER BY date DESC
    LIMIT 3
""")

signal_rows = cur.fetchall()
if signal_rows:
    for signal_date, total, buys, sells in signal_rows:
        print(f"   [OK] {signal_date}: {total} signals (BUY={buys}, SELL={sells})")
    passed += 1
else:
    print(f"   [FAIL] No signals generated in last 7 days")
    issues.append("No buy/sell signals generated recently")

conn.close()

# ===== 4. PE RATIOS =====
print("\n4. VALUE METRICS (PE RATIOS)")
conn = get_db_conn()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM value_metrics WHERE pe_ratio IS NOT NULL AND pe_ratio > 0")
pe_symbols = cur.fetchone()[0]
total_symbols = 10167

coverage = pe_symbols / total_symbols * 100 if total_symbols > 0 else 0

if coverage < 5:
    print(f"   [WARN] PE ratio coverage: {pe_symbols}/{total_symbols} ({coverage:.1f}%)")
    issues.append(f"PE ratio coverage very low ({coverage:.1f}%)")
elif coverage < 50:
    print(f"   [WARN] PE ratio coverage: {pe_symbols}/{total_symbols} ({coverage:.1f}%)")
else:
    print(f"   [OK] PE ratio coverage: {pe_symbols}/{total_symbols} ({coverage:.1f}%)")
    passed += 1

# Check range
cur.execute("""
    SELECT
        MIN(pe_ratio) as min_pe,
        MAX(pe_ratio) as max_pe,
        AVG(pe_ratio) as avg_pe
    FROM value_metrics
    WHERE pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 1000
""")
min_pe, max_pe, avg_pe = cur.fetchone()
if min_pe and max_pe:
    print(f"   [OK] PE ratio range: {min_pe:.1f} - {max_pe:.1f} (avg {avg_pe:.1f})")

conn.close()

# ===== 5. ALGO TRADES =====
print("\n5. ALGO TRADING")
conn = get_db_conn()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM algo_trades")
total_trades = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status IN ('OPEN', 'PARTIAL')")
open_trades = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'CLOSED'")
closed_trades = cur.fetchone()[0]

print(f"   [OK] Total trades: {total_trades} (Open: {open_trades}, Closed: {closed_trades})")
passed += 1

if total_trades < 5:
    print(f"   [WARN] Very few trade history ({total_trades} trades)")
    issues.append("Limited trade history (algo barely tested)")

conn.close()

# ===== 6. BACKTEST RESULTS =====
print("\n6. BACKTEST VALIDATION")
conn = get_db_conn()
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM backtest_results")
backtest_count = cur.fetchone()[0]

if backtest_count > 0:
    cur.execute("""
        SELECT
            COUNT(*) as run_count,
            AVG(total_return) as avg_return,
            AVG(sharpe_ratio) as avg_sharpe
        FROM backtest_results
    """)
    runs, avg_ret, avg_sharpe = cur.fetchone()
    print(f"   [OK] {runs} backtest runs, avg return={avg_ret:.1f}%, avg sharpe={avg_sharpe:.2f}")
    passed += 1
else:
    print(f"   [FAIL] No backtest results")
    issues.append("Algo has not been backtested")

conn.close()

# ===== SUMMARY =====
print("\n" + "=" * 70)
print(f"PASSED: {passed} checks")
print(f"ISSUES: {len(issues)} found")

if issues:
    print("\nCRITICAL ISSUES:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")

print("=" * 70)

sys.exit(0 if len(issues) == 0 else 1)
