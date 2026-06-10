#!/usr/bin/env python3
"""Comprehensive system audit to find all issues blocking the goal."""

import psycopg2
import os
import time
from datetime import datetime, timezone, date as date_type

print("\n" + "="*90)
print("COMPREHENSIVE SYSTEM AUDIT")
print("="*90)

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=int(os.environ.get('DB_PORT', 5432)),
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    dbname=os.environ['DB_NAME'],
    options='-c statement_timeout=10000',
)
cur = conn.cursor()

issues = []

# ============================================================================
# SECTION 1: DATA FRESHNESS
# ============================================================================
print("\n[1] DATA FRESHNESS CHECK")
print("-" * 90)

cur.execute("SELECT MAX(date), COUNT(DISTINCT symbol) FROM price_daily;")
max_price_date, price_symbols = cur.fetchone()
if max_price_date:
    if isinstance(max_price_date, str):
        max_price_date = datetime.fromisoformat(max_price_date).date()
    price_age = (datetime.now(timezone.utc).date() - max_price_date).days
    print(f"  Price Data:           {max_price_date} ({price_symbols} symbols, {price_age} days old)")
    if price_age > 1:
        issues.append(f"WARNING: Price data is {price_age} days old")
else:
    print(f"  Price Data:           NO DATA")
    issues.append(f"ERROR: No price data found")

cur.execute("SELECT MAX(date), COUNT(*) FROM trend_template_data;")
max_trend_date, trend_count = cur.fetchone()
if max_trend_date:
    if isinstance(max_trend_date, str):
        max_trend_date = datetime.fromisoformat(max_trend_date).date()
    trend_age = (datetime.now(timezone.utc).date() - max_trend_date).days
    print(f"  Trend Data:           {max_trend_date} ({trend_count} records, {trend_age} days old)")
    if trend_age > 2:
        issues.append(f"WARNING: Trend data is {trend_age} days old")
else:
    print(f"  Trend Data:           NO DATA")

cur.execute("SELECT MAX(date), COUNT(*) FROM swing_trader_scores;")
max_swing_date, swing_count = cur.fetchone()
if max_swing_date:
    if isinstance(max_swing_date, str):
        max_swing_date = datetime.fromisoformat(max_swing_date).date()
    swing_age = (datetime.now(timezone.utc).date() - max_swing_date).days
    print(f"  Swing Scores:         {max_swing_date} ({swing_count} records, {swing_age} days old)")
else:
    print(f"  Swing Scores:         NO DATA")

cur.execute("SELECT MAX(date), COUNT(*) FROM buy_sell_daily;")
max_signal_date, signal_count = cur.fetchone()
if max_signal_date:
    if isinstance(max_signal_date, str):
        max_signal_date = datetime.fromisoformat(max_signal_date).date()
    signal_age = (datetime.now(timezone.utc).date() - max_signal_date).days
    print(f"  Buy/Sell Signals:     {max_signal_date} ({signal_count} records, {signal_age} days old)")
    if signal_age > 2:
        issues.append(f"WARNING: Signals are {signal_age} days old")
else:
    print(f"  Buy/Sell Signals:     NO DATA")

cur.execute("SELECT MAX(date), COUNT(*) FROM market_health_daily;")
max_market_date, market_count = cur.fetchone()
if max_market_date:
    if isinstance(max_market_date, str):
        max_market_date = datetime.fromisoformat(max_market_date).date()
    market_age = (datetime.now(timezone.utc).date() - max_market_date).days
    print(f"  Market Health:        {max_market_date} ({market_count} records, {market_age} days old)")
else:
    print(f"  Market Health:        NO DATA")

# ============================================================================
# SECTION 2: ORCHESTRATOR
# ============================================================================
print("\n[2] ORCHESTRATOR EXECUTION")
print("-" * 90)

cur.execute("""
    SELECT run_id, created_at, overall_status
    FROM orchestrator_execution_log
    WHERE DATE(created_at) = CURRENT_DATE
    ORDER BY created_at DESC LIMIT 10;
""")
runs = cur.fetchall()
print(f"  Today's Runs: {len(runs)}")
for run_id, created_at, overall_status in runs:
    print(f"    {run_id}: {created_at.strftime('%H:%M:%S')} - {overall_status}")
    if overall_status != 'success':
        issues.append(f"ERROR: Run {run_id} failed")

# ============================================================================
# SECTION 3: POSITIONS
# ============================================================================
print("\n[3] POSITION DATA INTEGRITY")
print("-" * 90)

cur.execute("""
    SELECT COUNT(*) FROM algo_trades
    WHERE status IN ('open', 'filled', 'active', 'partially_filled')
      AND exit_date IS NULL;
""")
open_trades = cur.fetchone()[0]
print(f"  Open Trades (algo_trades): {open_trades}")

cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open';")
open_positions = cur.fetchone()[0]
print(f"  Open Positions (algo_positions): {open_positions}")

if open_trades > 0 and open_positions == 0:
    issues.append(f"ERROR: algo_positions empty but algo_trades has {open_trades} positions")

cur.execute("""
    SELECT snapshot_date, position_count, total_portfolio_value
    FROM algo_portfolio_snapshots
    ORDER BY snapshot_date DESC LIMIT 1;
""")
snap_row = cur.fetchone()
if snap_row:
    snapshot_date, position_count, total_value = snap_row
    print(f"  Portfolio Snapshot: {snapshot_date} - {position_count} positions - ${total_value:,.2f}")
    if position_count != open_trades:
        issues.append(f"ERROR: Snapshot shows {position_count} positions but algo_trades has {open_trades}")

# ============================================================================
# SECTION 4: DASHBOARD QUERIES
# ============================================================================
print("\n[4] DASHBOARD QUERIES")
print("-" * 90)

test_queries = [
    ('fetch_positions', '''
        SELECT COUNT(*) FROM (
            WITH open_trades AS (
                SELECT DISTINCT ON (symbol) symbol, entry_quantity, entry_price
                FROM algo_trades
                WHERE status IN ('open', 'filled', 'partially_filled', 'active')
                  AND exit_date IS NULL
                ORDER BY symbol, trade_date DESC
            ),
            latest_prices AS (
                SELECT DISTINCT ON (symbol) symbol, close as current_price
                FROM price_daily
                WHERE symbol IN (SELECT DISTINCT symbol FROM open_trades)
                ORDER BY symbol, date DESC
            )
            SELECT ot.symbol
            FROM open_trades ot
            LEFT JOIN latest_prices lp ON ot.symbol = lp.symbol
        ) t
    '''),
    ('fetch_market', 'SELECT COUNT(*) FROM market_exposure_daily'),
    ('fetch_portfolio', 'SELECT COUNT(*) FROM algo_portfolio_snapshots'),
]

for query_name, query_sql in test_queries:
    start = time.time()
    try:
        cur.execute(query_sql)
        result = cur.fetchone()[0]
        elapsed = time.time() - start
        status = "OK" if elapsed < 1.0 else "SLOW"
        print(f"  {query_name}: {elapsed:.3f}s [{status}]")
        if elapsed > 1.0:
            issues.append(f"PERF: {query_name} took {elapsed:.3f}s")
    except Exception as e:
        issues.append(f"ERROR: {query_name} query failed")
        print(f"  {query_name}: ERROR - {e}")

# ============================================================================
# SECTION 5: TABLES
# ============================================================================
print("\n[5] REQUIRED TABLES")
print("-" * 90)

tables = [
    'algo_trades', 'algo_positions', 'price_daily', 'trend_template_data',
    'algo_portfolio_snapshots', 'market_health_daily', 'market_exposure_daily',
    'swing_trader_scores', 'buy_sell_daily'
]

for table in tables:
    try:
        cur.execute(f"SELECT 1 FROM {table} LIMIT 1;")
        print(f"  {table}: OK")
    except Exception as e:
        issues.append(f"CRITICAL: Table {table} missing")
        print(f"  {table}: MISSING")

# ============================================================================
# SECTION 6: CONFIG
# ============================================================================
print("\n[6] ALGO CONFIGURATION")
print("-" * 90)

cur.execute("""
    SELECT key, value FROM algo_config
    WHERE key IN ('enable_algo', 'execution_mode', 'max_positions', 'alpaca_paper_trading')
    ORDER BY key;
""")
for key, value in cur.fetchall():
    print(f"  {key}: {value}")
    if key == 'enable_algo' and value.lower() != 'true':
        issues.append(f"WARNING: Algo disabled")
    if key == 'alpaca_paper_trading' and value.lower() == 'true':
        print(f"  -> PAPER TRADING MODE")

cur.close()
conn.close()

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*90)
print("AUDIT RESULTS")
print("="*90)

if not issues:
    print("\nNo issues found! System ready.")
else:
    critical = [i for i in issues if i.startswith("CRITICAL") or i.startswith("ERROR")]
    warnings = [i for i in issues if i.startswith("WARNING")]
    perf = [i for i in issues if i.startswith("PERF")]

    if critical:
        print(f"\nCRITICAL ISSUES ({len(critical)}):")
        for issue in critical:
            print(f"  !! {issue}")

    if perf:
        print(f"\nPERFORMANCE ISSUES ({len(perf)}):")
        for issue in perf:
            print(f"  ~ {issue}")

    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for issue in warnings:
            print(f"  ~ {issue}")

    print(f"\nTotal issues: {len(issues)}")

print("\n" + "="*90)
