#!/usr/bin/env python3
"""Comprehensive audit of data display issues across loaders, API, and database."""

import os
import sys
import psycopg2
from datetime import datetime, timedelta
from collections import defaultdict

# Database connection
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
except Exception as e:
    print(f"[FAIL] DATABASE CONNECTION FAILED: {e}")
    sys.exit(1)

cursor = conn.cursor()

print("=" * 80)
print("DATA DISPLAY AUDIT - COMPREHENSIVE SYSTEM CHECK")
print("=" * 80)

# ============================================================================
# SECTION 1: TABLE EXISTENCE AND ROW COUNTS
# ============================================================================
print("\n[1] TABLE ROW COUNTS (What data is in the database?)")
print("-" * 80)

tables_to_check = [
    # Core data
    ('stock_symbols', 'symbol', 'count(*)'),
    ('price_daily', 'symbol', 'max(date)'),
    ('price_weekly', 'symbol', 'max(date)'),
    ('price_monthly', 'symbol', 'max(date)'),
    ('technical_data_daily', 'symbol', 'max(date)'),

    # Market data
    ('market_health_daily', 'date', 'max(date)'),
    ('sector_performance_daily', 'sector', 'max(date)'),
    ('industry_ranking', 'industry', 'max(date)'),
    ('sector_ranking', 'sector', 'max(date)'),

    # Signals and scores
    ('buy_sell_daily', 'symbol', 'max(date)'),
    ('signal_quality_scores', 'symbol', 'max(date)'),
    ('swing_trader_scores', 'symbol', 'max(date)'),
    ('stock_scores', 'symbol', 'max(date)'),

    # Company data
    ('company_profile', 'symbol', 'count(*)'),
    ('key_metrics', 'symbol', 'count(*)'),

    # Additional loaders
    ('analyst_sentiment_analysis', 'symbol', 'max(date)'),
    ('analyst_upgrade_downgrade', 'symbol', 'max(date)'),
    ('aaii_sentiment', 'date', 'max(date)'),
    ('fear_greed_index', 'date', 'max(date)'),
    ('naaim', 'date', 'max(date)'),
    ('sentiment', 'date', 'max(date)'),
    ('sentiment_social', 'date', 'max(date)'),
    ('earnings_calendar', 'symbol', 'max(date)'),
    ('signal_themes', 'symbol', 'max(date)'),
]

table_data = {}
for table, group_col, agg_func in tables_to_check:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]

        # Get date info
        if 'max(date)' in agg_func:
            cursor.execute(f"SELECT MAX(date) FROM {table}")
            date_result = cursor.fetchone()
            max_date = date_result[0] if date_result and date_result[0] else None

            if max_date:
                age = (datetime.now().date() - max_date).days
                status = "[OK]" if age <= 1 else "[WARN]" if age <= 7 else "[FAIL]"
                print(f"{status} {table:40} {count:>8} rows  Last: {max_date} ({age}d ago)")
            else:
                print(f"[FAIL] {table:40} {count:>8} rows  NO DATA")
        else:
            print(f"[OK] {table:40} {count:>8} rows")

        table_data[table] = {'count': count, 'max_date': max_date if 'max(date)' in agg_func else None}
    except psycopg2.Error as e:
        print(f"[FAIL] {table:40} ERROR: {str(e)[:50]}")

# ============================================================================
# SECTION 2: DATA FRESHNESS ANALYSIS
# ============================================================================
print("\n[2] DATA FRESHNESS (Are loaders running?)")
print("-" * 80)

critical_tables = ['stock_symbols', 'price_daily', 'market_health_daily', 'technical_data_daily']
for table in critical_tables:
    try:
        cursor.execute(f"""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN date = CURRENT_DATE THEN 1 END) as today,
                   COUNT(CASE WHEN date >= CURRENT_DATE - INTERVAL '1 day' THEN 1 END) as last_24h,
                   MAX(date) as max_date
            FROM {table}
        """)
        total, today, last_24h, max_date = cursor.fetchone()

        status = "[OK]" if today > 0 else "[FAIL]"
        print(f"{status} {table:35} Total: {total:6d}  Today: {today:6d}  Max date: {max_date}")
    except Exception as e:
        print(f"[FAIL] {table:35} ERROR: {str(e)[:50]}")

# ============================================================================
# SECTION 3: API ENDPOINT FIELD VERIFICATION
# ============================================================================
print("\n[3] API QUERY SYNTAX & FIELD ISSUES")
print("-" * 80)

api_checks = [
    ("buy_sell_daily", ["symbol", "date", "ema_21", "adx", "signal"]),
    ("stock_scores", ["symbol", "momentum_score", "composite_score"]),
    ("market_health_daily", ["date", "vix_level", "advance_decline_ratio"]),
    ("price_daily", ["symbol", "date", "open", "high", "low", "close", "adj_close"]),
    ("price_weekly", ["symbol", "date", "open", "high", "low", "close", "adj_close"]),
    ("price_monthly", ["symbol", "date", "open", "high", "low", "close", "adj_close"]),
    ("sector_performance_daily", ["sector", "date", "price_change", "relative_strength"]),
]

for table, required_fields in api_checks:
    try:
        # Get columns
        cursor.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}'
        """)
        actual_cols = {row[0] for row in cursor.fetchall()}

        missing = [f for f in required_fields if f not in actual_cols]
        extra = actual_cols - set(required_fields)

        if missing:
            print(f"[FAIL] {table:35} MISSING: {', '.join(missing)}")
        else:
            print(f"[OK] {table:35} All fields present")

    except Exception as e:
        print(f"[FAIL] {table:35} ERROR: {str(e)[:40]}")

# ============================================================================
# SECTION 4: NULL VALUE ANALYSIS
# ============================================================================
print("\n[4] NULL VALUE ISSUES (Data quality problems)")
print("-" * 80)

null_checks = [
    ("buy_sell_daily", ["symbol", "ema_21", "adx", "signal"]),
    ("stock_scores", ["symbol", "momentum_score", "composite_score"]),
    ("technical_data_daily", ["symbol", "rsi", "sma_50", "ema_21"]),
    ("market_health_daily", ["vix_level", "advance_decline_ratio"]),
    ("swing_trader_scores", ["symbol", "components"]),
]

for table, fields in null_checks:
    try:
        # Get latest date's data
        cursor.execute(f"""
            SELECT COUNT(*) as total
            FROM {table}
            WHERE date >= CURRENT_DATE - INTERVAL '1 day'
        """)
        total_recent = cursor.fetchone()[0]

        if total_recent == 0:
            print(f"[WARN] {table:35} NO RECENT DATA")
            continue

        # Check each field for NULLs
        for field in fields:
            cursor.execute(f"""
                SELECT COUNT(CASE WHEN {field} IS NULL THEN 1 END)::float / COUNT(*)::float * 100
                FROM {table}
                WHERE date >= CURRENT_DATE - INTERVAL '1 day'
            """)
            null_pct = cursor.fetchone()[0]

            if null_pct is None:
                continue

            if null_pct > 50:
                print(f"[FAIL] {table:35} {field:20} {null_pct:.1f}% NULL")
            elif null_pct > 10:
                print(f"[WARN] {table:35} {field:20} {null_pct:.1f}% NULL")
    except Exception as e:
        print(f"[FAIL] {table:35} ERROR: {str(e)[:40]}")

# ============================================================================
# SECTION 5: LOADER EXECUTION STATUS
# ============================================================================
print("\n[5] LOADER EXECUTION STATUS (Did loaders actually run?)")
print("-" * 80)

try:
    cursor.execute("""
        SELECT loader_name,
               MAX(executed_at) as last_run,
               COUNT(*) as executions,
               SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
               SUM(CASE WHEN success THEN 0 ELSE 1 END) as failures
        FROM data_loader_status
        GROUP BY loader_name
        ORDER BY MAX(executed_at) DESC
        LIMIT 30
    """)

    results = cursor.fetchall()
    if not results:
        print("[FAIL] NO LOADER EXECUTION RECORDS FOUND")
    else:
        for loader, last_run, total_runs, successes, failures in results:
            if not last_run:
                print(f"[FAIL] {loader:40} NEVER RUN")
                continue

            age_hours = (datetime.now() - last_run.replace(tzinfo=None)).total_seconds() / 3600
            status = "[OK]" if age_hours < 24 and failures == 0 else "[WARN]" if age_hours < 72 else "[FAIL]"
            print(f"{status} {loader:40} Last: {last_run.strftime('%Y-%m-%d %H:%M')} ({age_hours:.1f}h ago) [{successes}OK {failures}FAIL]")
except Exception as e:
    print(f"[FAIL] ERROR QUERYING data_loader_status: {e}")

# ============================================================================
# SECTION 6: API RESPONSE STRUCTURE CHECK
# ============================================================================
print("\n[6] API RESPONSE STRUCTURE (Are endpoints returning right format?)")
print("-" * 80)

# Sample queries that API would use
api_query_checks = [
    ("Signals (buy_sell_daily)", """
        SELECT symbol, date, ema_21, adx, signal, signal_quality_score
        FROM buy_sell_daily
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
        ORDER BY date DESC, symbol
        LIMIT 3
    """),
    ("Scores (stock_scores)", """
        SELECT symbol, momentum_score, composite_score, updated_at
        FROM stock_scores
        WHERE updated_at >= CURRENT_DATE - INTERVAL '7 days'
        LIMIT 3
    """),
    ("Market Health", """
        SELECT date, vix_level, advance_decline_ratio, breadth_data
        FROM market_health_daily
        ORDER BY date DESC
        LIMIT 1
    """),
    ("Sector Performance", """
        SELECT sector, date, price_change, relative_strength
        FROM sector_performance_daily
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
        LIMIT 3
    """),
]

for check_name, query in api_query_checks:
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]

        if not rows:
            print(f"[FAIL] {check_name:40} NO DATA")
        else:
            has_nulls = False
            for row in rows:
                for val in row:
                    if val is None:
                        has_nulls = True
                        break

            status = "[WARN]" if has_nulls else "[OK]"
            print(f"{status} {check_name:40} {len(rows)} rows  {'(has NULLs)' if has_nulls else ''}")
    except Exception as e:
        print(f"[FAIL] {check_name:40} ERROR: {str(e)[:40]}")

# ============================================================================
# SECTION 7: CRITICAL WARNINGS
# ============================================================================
print("\n[7] CRITICAL ISSUES SUMMARY")
print("-" * 80)

issues = []

# Check 1: No price data
cursor.execute("SELECT COUNT(*) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '1 day'")
if cursor.fetchone()[0] == 0:
    issues.append("[CRIT] NO PRICE DATA FOR TODAY - loaders not running or database empty")

# Check 2: No recent loaders
cursor.execute("""
    SELECT COUNT(*) FROM data_loader_status
    WHERE executed_at >= NOW() - INTERVAL '24 hours'
""")
if cursor.fetchone()[0] == 0:
    issues.append("[CRIT] NO LOADER EXECUTIONS IN LAST 24H - Check EventBridge scheduler")

# Check 3: No signals
cursor.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE date >= CURRENT_DATE - INTERVAL '1 day'")
if cursor.fetchone()[0] == 0:
    issues.append("[WARN] NO BUY/SELL SIGNALS TODAY - Orchestrator may not be running")

# Check 4: Stale technical data
cursor.execute("SELECT MAX(date) FROM technical_data_daily")
tech_date = cursor.fetchone()[0]
if tech_date and (datetime.now().date() - tech_date).days > 1:
    issues.append(f"[WARN] TECHNICAL DATA STALE ({tech_date}) - Loaders behind schedule")

if not issues:
    print("[OK] No critical issues detected")
else:
    for issue in issues:
        print(issue)

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("END OF AUDIT")
print("=" * 80)
