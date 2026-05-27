#!/usr/bin/env python3
"""
Comprehensive Data Coverage Diagnostic

This script identifies specific data coverage gaps and issues:
1. Missing prices for any symbols
2. Incomplete technical indicators
3. Data freshness across all tables
4. Loader execution history
5. Failed loaders and error patterns
6. Symbol universe completeness

Run via Lambda: python diagnostic_data_coverage.py > /tmp/report.txt
Or locally through API endpoint
"""

import json
import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger
from datetime import date as _date, datetime, timedelta

logger = get_logger(__name__)


def run_diagnostic():
    """Run comprehensive data coverage diagnostic."""

    conn = get_db_connection()
    cur = conn.cursor()

    results = {
        'run_at': datetime.utcnow().isoformat(),
        'checks': {}
    }

    print("=" * 100)
    print("DATA COVERAGE DIAGNOSTIC REPORT")
    print("=" * 100)

    # 1. Check symbol universe
    try:
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
        sp500_count = cur.fetchone()[0]

        print(f"\n[1] SYMBOL UNIVERSE")
        print(f"    S&P 500 symbols in database: {sp500_count}")

        if sp500_count < 500:
            print(f"    WARNING: Only {sp500_count}/500 symbols loaded")

        results['checks']['symbol_universe'] = {'sp500_count': sp500_count}
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['symbol_universe'] = {'error': str(e)}

    # 2. Check price_daily coverage
    try:
        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols_with_prices,
                MAX(date) as latest_price_date,
                MIN(date) as oldest_price_date,
                COUNT(*) as total_rows
            FROM price_daily
        """)
        row = cur.fetchone()
        symbols_with_prices, latest_date, oldest_date, total_rows = row

        print(f"\n[2] PRICE_DAILY TABLE")
        print(f"    Symbols with price data: {symbols_with_prices}")
        print(f"    Latest date: {latest_date}")
        print(f"    Oldest date: {oldest_date}")
        print(f"    Total rows: {total_rows}")

        # Check for stale prices
        if latest_date:
            days_stale = (_date.today() - latest_date).days
            print(f"    Data staleness: {days_stale} days old")
            if days_stale > 1:
                print(f"    WARNING: Price data is {days_stale} days old")

        results['checks']['price_daily'] = {
            'symbols': symbols_with_prices,
            'latest_date': str(latest_date),
            'days_stale': days_stale
        }
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['price_daily'] = {'error': str(e)}

    # 3. Check technical_data_daily
    try:
        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN rsi IS NULL THEN 1 END) as null_rsi,
                COUNT(CASE WHEN ema_50 IS NULL THEN 1 END) as null_ema_50,
                COUNT(CASE WHEN atr IS NULL THEN 1 END) as null_atr
            FROM technical_data_daily
        """)
        row = cur.fetchone()
        symbols, latest_date, total_rows, null_rsi, null_ema, null_atr = row

        print(f"\n[3] TECHNICAL_DATA_DAILY TABLE")
        print(f"    Symbols with technical data: {symbols}")
        print(f"    Latest date: {latest_date}")
        print(f"    Total rows: {total_rows}")
        print(f"    NULL RSI count: {null_rsi} ({100*null_rsi//max(total_rows,1)}%)")
        print(f"    NULL EMA50 count: {null_ema} ({100*null_ema//max(total_rows,1)}%)")
        print(f"    NULL ATR count: {null_atr} ({100*null_atr//max(total_rows,1)}%)")

        if null_rsi > total_rows * 0.1:
            print(f"    WARNING: >10% NULL RSI values detected")

        results['checks']['technical_data'] = {
            'symbols': symbols,
            'latest_date': str(latest_date),
            'null_rates': {
                'rsi': 100*null_rsi//max(total_rows,1),
                'ema50': 100*null_ema//max(total_rows,1),
                'atr': 100*null_atr//max(total_rows,1)
            }
        }
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['technical_data'] = {'error': str(e)}

    # 4. Check market_health_daily
    try:
        cur.execute("""
            SELECT
                MAX(date) as latest_date,
                COUNT(*) as total_rows
            FROM market_health_daily
        """)
        row = cur.fetchone()
        latest_date, total_rows = row

        print(f"\n[4] MARKET_HEALTH_DAILY TABLE")
        print(f"    Latest date: {latest_date}")
        print(f"    Total rows: {total_rows}")

        if latest_date:
            days_stale = (_date.today() - latest_date).days
            print(f"    Data staleness: {days_stale} days old")

        results['checks']['market_health'] = {
            'latest_date': str(latest_date),
            'rows': total_rows
        }
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['market_health'] = {'error': str(e)}

    # 5. Check loader execution status
    try:
        cur.execute("""
            SELECT loader_name, MAX(executed_at) as last_run, status, COUNT(*) as runs
            FROM data_loader_status
            WHERE executed_at > NOW() - INTERVAL '7 days'
            GROUP BY loader_name, status
            ORDER BY loader_name, last_run DESC
        """)

        print(f"\n[5] LOADER EXECUTION STATUS (Last 7 days)")
        rows = cur.fetchall()

        if rows:
            failed_loaders = set()
            for loader, last_run, status, runs in rows:
                if status == 'FAILED':
                    failed_loaders.add(loader)
                    print(f"    FAILED: {loader} (last: {last_run}, {runs} attempts)")

            if not failed_loaders:
                print(f"    All loaders successful in last 7 days")
            else:
                print(f"    {len(failed_loaders)} loaders with failures")

            results['checks']['loader_status'] = {
                'failed_loaders': list(failed_loaders),
                'total_checked': len(rows)
            }
        else:
            print(f"    No loader status data found")
            results['checks']['loader_status'] = {'error': 'No data'}
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['loader_status'] = {'error': str(e)}

    # 6. Check for missing prices by symbol
    try:
        cur.execute("""
            SELECT s.symbol, MAX(p.date) as latest_price
            FROM stock_symbols s
            LEFT JOIN price_daily p ON s.symbol = p.symbol
            WHERE s.is_sp500 = TRUE
            GROUP BY s.symbol
            HAVING MAX(p.date) < NOW() - INTERVAL '1 day'
            OR MAX(p.date) IS NULL
            ORDER BY latest_price
            LIMIT 20
        """)

        print(f"\n[6] SYMBOLS WITH STALE/MISSING PRICES (Sample)")
        rows = cur.fetchall()

        if rows:
            for symbol, latest_price in rows:
                days_stale = (datetime.now() - (latest_price or datetime.now() - timedelta(days=999))).days
                print(f"    {symbol:<10} latest: {latest_price} ({days_stale} days old)")

            results['checks']['stale_symbols'] = {
                'count': len(rows),
                'sample': [{'symbol': s, 'latest': str(d)} for s, d in rows]
            }
        else:
            print(f"    All S&P 500 symbols have recent prices")
            results['checks']['stale_symbols'] = {'count': 0}
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['stale_symbols'] = {'error': str(e)}

    # 7. Check fundamental metrics coverage
    try:
        metrics_tables = [
            'quality_metrics', 'growth_metrics', 'value_metrics',
            'stability_metrics', 'positioning_metrics'
        ]

        print(f"\n[7] FUNDAMENTAL METRICS COVERAGE")
        for table in metrics_tables:
            try:
                cur.execute(f"""
                    SELECT COUNT(DISTINCT symbol) as symbols, MAX(date) as latest_date
                    FROM {table}
                """)
                symbols, latest_date = cur.fetchone()
                print(f"    {table:<30} {symbols:>4} symbols, latest: {latest_date}")
            except:
                pass

        results['checks']['fundamental_metrics'] = 'See above'
    except Exception as e:
        print(f"    ERROR: {e}")

    # 8. Check earnings data
    try:
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) as symbols, MAX(fetched_at) as latest
            FROM earnings_estimates
        """)
        symbols, latest_date = cur.fetchone()

        print(f"\n[8] EARNINGS DATA")
        print(f"    Earnings estimates: {symbols} symbols")
        print(f"    Latest fetched: {latest_date}")

        results['checks']['earnings_data'] = {
            'symbols': symbols,
            'latest': str(latest_date)
        }
    except Exception as e:
        print(f"    ERROR: {e}")
        results['checks']['earnings_data'] = {'error': str(e)}

    # Summary
    print("\n" + "=" * 100)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 100)

    cur.close()
    conn.close()

    return results


if __name__ == "__main__":
    try:
        results = run_diagnostic()
        print("\nDiagnostic complete.")
        print("\nJSON Output for programmatic access:")
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
