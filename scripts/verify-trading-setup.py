#!/usr/bin/env python3
"""
Verify trading setup - check if orchestrator can actually execute live trades.

This script checks:
1. Market data freshness (Phase 1 requirement)
2. Lambda environment configuration (execution mode, live trading flag)
3. Alpaca credentials availability
4. Recent trade execution status
"""

import os
import sys
import psycopg2
import boto3
import json
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path.cwd()))

def check_data_freshness():
    """Check if market data is fresh enough for trading."""
    try:
        from config.credential_manager import get_db_password, get_db_config, DEFAULT_DB_PORT, DEFAULT_DB_USER, DEFAULT_DB_NAME

        db_config = get_db_config()
        password = get_db_password()
        ssl_mode = 'prefer' if db_config.get('host') == 'localhost' else 'require'

        conn = psycopg2.connect(
            host=db_config.get('host'),
            port=db_config.get('port', DEFAULT_DB_PORT),
            user=db_config.get('user', DEFAULT_DB_USER),
            password=password,
            database=db_config.get('database', DEFAULT_DB_NAME),
            sslmode=ssl_mode
        )

        cur = conn.cursor()

        # Check critical table dates
        cur.execute("SELECT MAX(date) FROM price_daily")
        price_date = cur.fetchone()[0]

        cur.execute("SELECT MAX(date) FROM technical_data_daily")
        tech_date = cur.fetchone()[0]

        cur.execute("SELECT MAX(date) FROM market_health_daily")
        health_date = cur.fetchone()[0]

        cur.execute("SELECT CURRENT_DATE")
        today = cur.fetchone()[0]

        cur.close()
        conn.close()

        print("=" * 70)
        print("1. DATA FRESHNESS CHECK")
        print("=" * 70)

        print(f"  System date: {today}")
        print(f"  Latest price_daily: {price_date}")
        print(f"  Latest technical_data_daily: {tech_date}")
        print(f"  Latest market_health_daily: {health_date}")

        if price_date and tech_date and health_date:
            days_stale = (today - price_date).days
            if days_stale <= 1:
                print(f"  ✓ DATA FRESH: {days_stale} day(s) old (acceptable)")
                return True
            else:
                print(f"  ✗ DATA STALE: {days_stale} day(s) old (orchestrator will halt)")
                print(f"    → Run loaders for {price_date + timedelta(days=1)} to fix")
                return False
        else:
            print(f"  ✗ MISSING DATA: Cannot determine freshness")
            return False

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def check_lambda_environment():
    """Check Lambda environment variables for live trading."""
    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')

        response = lambda_client.get_function_configuration(
            FunctionName='algo-algo-dev'
        )

        env_vars = response.get('Environment', {}).get('Variables', {})

        print("\n" + "=" * 70)
        print("2. LAMBDA ENVIRONMENT CHECK")
        print("=" * 70)

        # Check each critical variable
        execution_mode = env_vars.get('ORCHESTRATOR_EXECUTION_MODE', '(not set)')
        live_trading_flag = env_vars.get('ALGO_LIVE_TRADING', '(not set)')
        paper_flag = env_vars.get('ALPACA_PAPER_TRADING', '(not set)')

        print(f"  ORCHESTRATOR_EXECUTION_MODE: {execution_mode}")
        print(f"  ALGO_LIVE_TRADING: {live_trading_flag}")
        print(f"  ALPACA_PAPER_TRADING: {paper_flag}")

        checks_passed = 0
        checks_total = 3

        if execution_mode == 'auto':
            print("    ✓ Execution mode is 'auto' (will attempt live trading)")
            checks_passed += 1
        else:
            print(f"    ✗ Execution mode is '{execution_mode}' (not 'auto')")

        if live_trading_flag == 'I_UNDERSTAND_REAL_MONEY':
            print("    ✓ Live trading flag is set (live Alpaca account)")
            checks_passed += 1
        else:
            print(f"    ✗ Live trading flag is '{live_trading_flag}' (not 'I_UNDERSTAND_REAL_MONEY')")

        if paper_flag == 'false':
            print("    ✓ Paper trading disabled (using live API)")
            checks_passed += 1
        else:
            print(f"    ✗ Paper trading flag is '{paper_flag}' (not 'false')")

        if checks_passed == checks_total:
            return True
        else:
            print(f"\n  ✗ Lambda environment incomplete ({checks_passed}/{checks_total} checks passed)")
            print(f"    → Redeploy via 'git push origin main' or manually update Lambda config")
            return False

    except Exception as e:
        print(f"  ✗ ERROR: Cannot access Lambda (credentials invalid?): {e}")
        return False


def check_recent_trades():
    """Check what trades have been executed and in what mode."""
    try:
        from config.credential_manager import get_db_password, get_db_config, DEFAULT_DB_PORT, DEFAULT_DB_USER, DEFAULT_DB_NAME

        db_config = get_db_config()
        password = get_db_password()
        ssl_mode = 'prefer' if db_config.get('host') == 'localhost' else 'require'

        conn = psycopg2.connect(
            host=db_config.get('host'),
            port=db_config.get('port', DEFAULT_DB_PORT),
            user=db_config.get('user', DEFAULT_DB_USER),
            password=password,
            database=db_config.get('database', DEFAULT_DB_NAME),
            sslmode=ssl_mode
        )

        cur = conn.cursor()

        # Check last 5 trades
        cur.execute("""
            SELECT trade_id, symbol, execution_mode, status, alpaca_order_id, created_at
            FROM algo_trades
            ORDER BY created_at DESC
            LIMIT 5
        """)

        trades = cur.fetchall()

        # Check trading by execution mode
        cur.execute("""
            SELECT execution_mode, COUNT(*) as count
            FROM algo_trades
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY execution_mode
        """)

        mode_counts = cur.fetchall()

        cur.close()
        conn.close()

        print("\n" + "=" * 70)
        print("3. TRADE EXECUTION STATUS")
        print("=" * 70)

        if mode_counts:
            print("  Recent trades by execution mode (last 30 days):")
            has_live = False
            for mode, count in mode_counts:
                print(f"    {mode}: {count} trades")
                if mode == 'auto':
                    has_live = True

            if has_live:
                print("    ✓ Live trades (auto mode) detected")
            else:
                print("    ✗ No live trades (auto mode) found - all in paper/dry mode")
        else:
            print("  ✗ No trades found in last 30 days")

        if trades:
            print("\n  Most recent trades:")
            for trade_id, symbol, mode, status, order_id, created_at in trades:
                is_live = order_id and not order_id.startswith('LOCAL-')
                status_icon = "✓" if is_live else "✗"
                print(f"    {status_icon} {trade_id}: {symbol} {mode:6} {order_id[:20]}")
        else:
            print("\n  No trades found")

        return True

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def check_alpaca_credentials():
    """Verify Alpaca credentials are available."""
    try:
        from config.credential_manager import get_alpaca_credentials

        creds = get_alpaca_credentials()

        print("\n" + "=" * 70)
        print("4. ALPACA CREDENTIALS CHECK")
        print("=" * 70)

        if creds and creds.get('key'):
            print(f"  ✓ Alpaca key loaded (starting with: {creds['key'][:4]}...)")
            print(f"  ✓ Alpaca secret loaded")
            return True
        else:
            print(f"  ✗ Alpaca credentials missing or incomplete")
            return False

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def main():
    print("\n" + "=" * 70)
    print("ORCHESTRATOR TRADING SETUP VERIFICATION")
    print("=" * 70)

    results = {
        'data_freshness': check_data_freshness(),
        'lambda_environment': check_lambda_environment(),
        'alpaca_credentials': check_alpaca_credentials(),
        'recent_trades': check_recent_trades(),
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_ok = all(results.values())

    if results['data_freshness']:
        print("✓ Market data is fresh")
    else:
        print("✗ Market data is stale - orchestrator will not trade")

    if results['lambda_environment']:
        print("✓ Lambda is configured for live trading")
    else:
        print("✗ Lambda environment incomplete - trades will be in paper mode")

    if results['alpaca_credentials']:
        print("✓ Alpaca credentials available")
    else:
        print("✗ Alpaca credentials not available")

    print("\n" + "=" * 70)
    if all_ok:
        print("✓✓✓ SYSTEM READY FOR LIVE TRADING ✓✓✓")
        print("=" * 70)
        return 0
    else:
        print("✗✗✗ ISSUES FOUND - See diagnostics above ✗✗✗")
        print("=" * 70)
        print("\nNext steps:")
        if not results['data_freshness']:
            print("  1. Run the EOD pipeline to load fresh market data")
            print("     aws stepfunctions start-execution \\")
            print('       --state-machine-arn "arn:aws:states:us-east-1:...eod-pipeline-dev" \\')
            print('       --input \'{"run_date": "2026-05-29"}\'')
        if not results['lambda_environment']:
            print("  2. Redeploy Lambda or update environment manually")
            print("     git push origin main  # Triggers GitHub Actions deployment")
        return 1


if __name__ == '__main__':
    from datetime import timedelta
    sys.exit(main())
