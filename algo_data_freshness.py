#!/usr/bin/env python3
"""
Data Freshness Monitor & Loader Schedule

Audits every data source the algo depends on and reports:
  - Latest data date
  - Age (vs today)
  - Expected refresh frequency
  - Status: OK / STALE / EMPTY / ERROR

Each table has a documented refresh frequency:

  REAL-TIME (intraday):    None — we don't trade intraday
  DAILY (every weekday):   price_daily, technical_data_daily, buy_sell_daily,
                           market_health_daily, trend_template_data,
                           signal_quality_scores, sector_ranking, industry_ranking,
                           insider_transactions, analyst_upgrade_downgrade
  WEEKLY:                  price_weekly, buy_sell_weekly, stock_scores,
                           value_trap_scores, aaii_sentiment
  MONTHLY:                 price_monthly, buy_sell_monthly, growth_metrics,
                           key_metrics
  QUARTERLY:               earnings_history, earnings_metrics, earnings_estimates
  STATIC:                  company_profile, stock_symbols (refresh as needed)

The orchestrator's Phase 1 reads from this module. It fails-closed when
any DAILY-frequency table is more than 7 days stale.

Persists status to data_loader_status table for dashboard display.

USAGE:
  python3 algo_data_freshness.py           # print status report
  python3 algo_data_freshness.py --json    # JSON output for piping
"""

import os
import json
import psycopg2
import argparse
from pathlib import Path
from dotenv import load_dotenv
from datetime import date as _date, datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


# (table_name, date_column, frequency, role, stale_days_threshold)
DATA_SOURCES = [
    # -- DAILY (must be fresh for algo to run) --
    ('price_daily',                'date',              'daily',     'CRITICAL: OHLCV',                     7),
    ('technical_data_daily',       'date',              'daily',     'CRITICAL: SMA/RSI/ATR',               7),
    ('buy_sell_daily',             'date',              'daily',     'CRITICAL: Pine BUY/SELL signals',     7),
    ('trend_template_data',        'date',              'daily',     'CRITICAL: Minervini/Weinstein',       7),
    ('signal_quality_scores',      'date',              'daily',     'CRITICAL: Composite SQS',             7),
    ('market_health_daily',        'date',              'daily',     'CRITICAL: Market regime',             7),
    ('data_completeness_scores',   'updated_at',        'daily',     'CRITICAL: Per-symbol data quality',   7),
    ('sector_ranking',             'date_recorded',     'daily',     'IMPORTANT: Sector momentum',         10),
    ('industry_ranking',           'date_recorded',     'daily',     'IMPORTANT: Industry rank',           10),
    ('insider_transactions',       'transaction_date',  'daily',     'OPTIONAL: Insider buys/sells',       14),
    ('analyst_upgrade_downgrade',  'action_date',       'daily',     'OPTIONAL: Analyst rating changes',   14),
    # -- WEEKLY --
    ('price_weekly',               'date',              'weekly',    'CRITICAL: Weekly OHLCV',             14),
    ('buy_sell_weekly',            'date',              'weekly',    'IMPORTANT: Weekly Pine signals',     14),
    ('stock_scores',               'score_date',        'weekly',    'IMPORTANT: IBD composite',           14),
    ('value_trap_scores',          'updated_at',        'weekly',    'IMPORTANT: Value trap risk',         14),
    ('aaii_sentiment',             'date',              'weekly',    'OPTIONAL: Investor sentiment',       14),
    # -- MONTHLY --
    ('price_monthly',              'date',              'monthly',   'IMPORTANT: Monthly OHLCV',           45),
    ('buy_sell_monthly',           'date',              'monthly',   'OPTIONAL: Monthly Pine signals',     45),
    ('growth_metrics',             'date',              'monthly',   'IMPORTANT: 3y CAGR fundamentals',    45),
    # -- QUARTERLY (low cost — earnings dates) --
    ('earnings_history',           'quarter',           'quarterly', 'IMPORTANT: Past earnings dates',     120),
    ('earnings_metrics',           'report_date',       'quarterly', 'IMPORTANT: Earnings quality',        120),
    # -- STATIC --
    ('company_profile',            None,                'static',    'IMPORTANT: Sector/industry meta',    None),
    ('stock_symbols',              None,                'static',    'CRITICAL: Universe',                 None),
]


def audit():
    today = _date.today()
    results = []

    for tbl, date_col, freq, role, stale_days in DATA_SOURCES:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        try:
            if date_col:
                cur.execute(f"SELECT COUNT(*), MAX({date_col}::date) FROM {tbl}")
            else:
                cur.execute(f"SELECT COUNT(*), NULL FROM {tbl}")
            count, max_date = cur.fetchone()

            age_days = (today - max_date).days if max_date else None
            if count == 0:
                status = 'empty'
            elif stale_days is not None and age_days is not None and age_days > stale_days:
                status = 'stale'
            else:
                status = 'ok'

            results.append({
                'table': tbl,
                'frequency': freq,
                'role': role,
                'latest_date': max_date.isoformat() if max_date else None,
                'age_days': age_days,
                'row_count': count,
                'stale_threshold_days': stale_days,
                'status': status,
            })
        except Exception as e:
            results.append({
                'table': tbl,
                'frequency': freq,
                'role': role,
                'status': 'error',
                'error': str(e)[:80],
            })
        finally:
            cur.close()
            conn.close()
    return results


def persist(results):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_loader_status (
                table_name VARCHAR(80) PRIMARY KEY,
                frequency VARCHAR(20),
                role VARCHAR(80),
                latest_date DATE,
                age_days INTEGER,
                row_count BIGINT,
                stale_threshold_days INTEGER,
                status VARCHAR(20),
                last_audit_at TIMESTAMP,
                error_message TEXT
            )
        """)
        for r in results:
            cur.execute(
                """
                INSERT INTO data_loader_status
                    (table_name, frequency, role, latest_date, age_days, row_count,
                     stale_threshold_days, status, last_audit_at, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                ON CONFLICT (table_name) DO UPDATE SET
                    frequency = EXCLUDED.frequency,
                    role = EXCLUDED.role,
                    latest_date = EXCLUDED.latest_date,
                    age_days = EXCLUDED.age_days,
                    row_count = EXCLUDED.row_count,
                    stale_threshold_days = EXCLUDED.stale_threshold_days,
                    status = EXCLUDED.status,
                    last_audit_at = CURRENT_TIMESTAMP,
                    error_message = EXCLUDED.error_message
                """,
                (
                    r['table'], r['frequency'], r['role'],
                    r.get('latest_date'), r.get('age_days'), r.get('row_count'),
                    r.get('stale_threshold_days'), r['status'],
                    r.get('error'),
                ),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def report(results):
    today = _date.today()
    print(f"\n{'='*92}")
    print(f"DATA FRESHNESS AUDIT — {today}")
    print(f"{'='*92}\n")
    print(f"  {'Status':<10}{'Table':<28}{'Freq':<10}{'Latest':<13}{'Age':<10}{'Count':>10}  Role")
    print("-" * 92)

    counts = {'ok': 0, 'stale': 0, 'empty': 0, 'error': 0}
    critical_stale = []
    for r in results:
        status = r['status']
        counts[status] = counts.get(status, 0) + 1
        flag = {
            'ok': '[OK]   ',
            'stale': '[STALE]',
            'empty': '[EMPTY]',
            'error': '[ERROR]',
        }.get(status, '[?]')

        latest = r.get('latest_date') or 'N/A'
        age = f"{r['age_days']}d ago" if r.get('age_days') is not None else ''
        cnt = f"{r.get('row_count', 0):,}" if r.get('row_count') is not None else ''

        print(f"  {flag:<10}{r['table']:<28}{r['frequency']:<10}{latest:<13}{age:<10}{cnt:>10}  {r['role']}")

        if status in ('stale', 'empty', 'error') and 'CRITICAL' in r['role']:
            critical_stale.append(r['table'])

    print(f"\n{'='*92}")
    print(f"SUMMARY: {counts['ok']} OK, {counts['stale']} stale, {counts['empty']} empty, {counts['error']} error")
    if critical_stale:
        print(f"CRITICAL DATA STALE/MISSING: {', '.join(critical_stale)}")
        print("  -> Algo will FAIL-CLOSED in orchestrator phase 1 until these refresh.")
    else:
        print("All CRITICAL data fresh enough to trade.")

    return counts


def loader_schedule_summary():
    """Print recommended loader run schedule."""
    print(f"\n{'='*92}")
    print(f"RECOMMENDED LOADER SCHEDULE")
    print(f"{'='*92}")
    print("""
  AFTER MARKET CLOSE (5:00 PM ET):
    - load_pricing_loader.py        (price_daily, EOD prices)
    - load_technicals_loader.py     (RSI, MACD, SMA, ATR per symbol)
    - load_buysell_loader.py        (Pine Script signals from TradingView)
    - load_algo_metrics_daily.py    (trend_template, SQS, market_health)
    - load_sector_ranking_loader.py (sector & industry momentum)
    - load_insider_loader.py        (insider transactions, may run weekly)

  WEEKLY (Saturday morning):
    - load_pricing_loader.py --weekly
    - load_buysell_loader.py --weekly
    - load_stock_scores_loader.py   (IBD composite score)
    - load_value_trap_scores_loader.py
    - load_aaii_sentiment_loader.py

  MONTHLY (1st of month):
    - load_pricing_loader.py --monthly
    - load_buysell_loader.py --monthly
    - load_growth_metrics_loader.py
    - load_key_metrics_loader.py

  QUARTERLY (after earnings season — ~5 days post-quarter end):
    - load_earnings_history_loader.py
    - load_earnings_metrics_loader.py

  STATIC (run once + as needed when universe changes):
    - load_company_profile_loader.py
    - load_stock_symbols_loader.py

  ALGO RUN:
    - python3 algo_orchestrator.py            # Run once after data refresh
    - Phase 1 will fail-closed if any CRITICAL daily data is > 7 days old.
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Data freshness audit')
    parser.add_argument('--json', action='store_true', help='Output JSON only')
    parser.add_argument('--no-persist', action='store_true', help='Skip writing to data_loader_status')
    parser.add_argument('--schedule', action='store_true', help='Show recommended loader schedule')
    args = parser.parse_args()

    results = audit()
    if not args.no_persist:
        try:
            persist(results)
        except Exception as e:
            print(f"# warning: could not persist status: {e}")

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        counts = report(results)
        if args.schedule:
            loader_schedule_summary()
        # Exit code: 0 if all OK or only OPTIONAL stale, 1 if CRITICAL stale
        critical_problems = sum(
            1 for r in results
            if r['status'] in ('stale', 'empty', 'error') and 'CRITICAL' in r['role']
        )
        import sys
        sys.exit(1 if critical_problems > 0 else 0)
