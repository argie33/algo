#!/usr/bin/env python3
"""Monitor data freshness across critical tables for orchestrator execution."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from utils.database_context import DatabaseContext
import json

CRITICAL_TABLES = {
    'price_daily': 'Daily stock prices',
    'technical_data_daily': 'Technical indicators',
    'buy_sell_daily': 'Buy/sell signals',
    'signal_quality_scores': 'Signal quality rankings',
    'swing_trader_scores': 'Swing trader rankings',
    'market_health_daily': 'Market health metrics',
    'trend_template_data': 'Trend template data',
    'sector_ranking': 'Sector performance'
}

def get_table_freshness():
    """Check data freshness for all critical tables."""
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)
    today_et = now_et.date()
    yesterday_et = today_et - timedelta(days=1)

    results = {}

    try:
        with DatabaseContext('read') as cur:
            for table, description in CRITICAL_TABLES.items():
                try:
                    # Check if table exists and has data
                    if table == 'market_health_daily':
                        cur.execute(f"SELECT MAX(date), COUNT(*) FROM {table}")
                    elif table == 'sector_ranking':
                        cur.execute(f"SELECT MAX(date), COUNT(*) FROM {table}")
                    else:
                        cur.execute(f"SELECT MAX(date), COUNT(DISTINCT symbol) as symbols FROM {table}")

                    row = cur.fetchone()
                    if not row or row[0] is None:
                        results[table] = {
                            'description': description,
                            'status': 'EMPTY',
                            'last_date': None,
                            'freshness': 'NO DATA',
                            'symbol_count': 0
                        }
                    else:
                        last_date = row[0]
                        symbol_count = row[1]

                        # Check if data is fresh (< 1 trading day old)
                        if isinstance(last_date, str):
                            last_date = datetime.strptime(last_date, '%Y-%m-%d').date()

                        # Trading day check (not weekend)
                        today_is_trading = today_et.weekday() < 5  # Mon-Fri
                        yesterday_is_trading = yesterday_et.weekday() < 5

                        if today_is_trading and last_date >= today_et:
                            freshness = 'FRESH (TODAY)'
                            status = 'OK'
                        elif last_date >= yesterday_et and yesterday_is_trading:
                            freshness = 'FRESH (YESTERDAY)'
                            status = 'OK'
                        else:
                            days_old = (today_et - last_date).days
                            freshness = f'STALE ({days_old} days old)'
                            status = 'STALE'

                        coverage_pct = (symbol_count / 5000) * 100 if symbol_count > 0 else 0

                        results[table] = {
                            'description': description,
                            'status': status,
                            'last_date': str(last_date),
                            'freshness': freshness,
                            'symbol_count': symbol_count,
                            'coverage_pct': f'{coverage_pct:.1f}%'
                        }

                except Exception as e:
                    results[table] = {
                        'description': description,
                        'status': 'ERROR',
                        'error': str(e)
                    }
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return {'error': str(e)}

    return results

def main():
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)

    print(f"\n{'='*80}")
    print(f"Data Freshness Check - {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"{'='*80}")

    results = get_table_freshness()

    if 'error' in results:
        print(f"[ERROR] {results['error']}")
        return 1

    all_fresh = True
    all_covered = True

    for table, data in results.items():
        status_symbol = '[OK]' if data['status'] == 'OK' else '[ERR]' if data['status'] == 'ERROR' else '[WARN]'
        print(f"\n{status_symbol} {table}")
        print(f"  Description: {data['description']}")
        print(f"  Status: {data['status']}")
        print(f"  Last update: {data.get('last_date', 'N/A')}")

        if 'freshness' in data:
            print(f"  Freshness: {data['freshness']}")

        if 'symbol_count' in data:
            print(f"  Symbols: {data['symbol_count']} ({data.get('coverage_pct', 'N/A')})")
            if data.get('symbol_count', 0) < 4500:  # 90% of 5000
                all_covered = False

        if data['status'] != 'OK':
            all_fresh = False

        if 'error' in data:
            print(f"  Error: {data['error']}")

    print(f"\n{'='*80}")
    if all_fresh and all_covered:
        print("[OK] All tables FRESH and COMPLETE - Ready for orchestrator execution")
        return 0
    elif all_fresh:
        print("[WARN] All tables FRESH but some have low symbol coverage (<90%)")
        return 1
    else:
        print("[ERR] Some tables STALE - Pipeline may not have completed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
