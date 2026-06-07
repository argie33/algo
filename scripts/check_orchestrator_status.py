#!/usr/bin/env python3
"""
Quick status check for orchestrator readiness with full dataset.
Verifies RDS Proxy, loaders, and phase 1 freshness checks.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

def check_rds_connectivity():
    """Check if RDS is reachable."""
    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT 1")
        print("✓ RDS connectivity OK")
        return True
    except Exception as e:
        print(f"✗ RDS connectivity failed: {e}")
        return False

def check_database_state():
    """Check database has recent data."""
    try:
        with DatabaseContext('read') as cur:
            # Check stock_symbols
            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active=true")
            symbol_count = cur.fetchone()[0]
            print(f"✓ stock_symbols: {symbol_count} active symbols")

            # Check recent price data
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM price_daily
                WHERE date >= (CURRENT_DATE - INTERVAL '5 days')
            """)
            recent_prices = cur.fetchone()[0]
            print(f"✓ price_daily: {recent_prices} symbols with data in last 5 days")

            # Check buy_sell_daily (key for signal generation)
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily
                WHERE updated_at >= (CURRENT_DATE - INTERVAL '1 day')
            """)
            buy_sell_count = cur.fetchone()[0]
            coverage = (buy_sell_count / symbol_count * 100) if symbol_count > 0 else 0
            status = "✓" if coverage >= 90 else "⚠"
            print(f"{status} buy_sell_daily: {buy_sell_count}/{symbol_count} symbols ({coverage:.1f}%)")
            if coverage < 80:
                print("  CRITICAL: Symbol coverage below 80% minimum for trading")

            # Check signal_quality_scores
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM signal_quality_scores
                WHERE updated_at >= (CURRENT_DATE - INTERVAL '1 day')
            """)
            scores_count = cur.fetchone()[0]
            coverage = (scores_count / symbol_count * 100) if symbol_count > 0 else 0
            status = "✓" if coverage >= 90 else "⚠"
            print(f"{status} signal_quality_scores: {scores_count}/{symbol_count} symbols ({coverage:.1f}%)")

            # Check swing_trader_scores (required for phase 5)
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM swing_trader_scores
                WHERE updated_at >= (CURRENT_DATE - INTERVAL '1 day')
            """)
            swing_count = cur.fetchone()[0]
            coverage = (swing_count / symbol_count * 100) if symbol_count > 0 else 0
            status = "✓" if coverage >= 90 else "✗"
            print(f"{status} swing_trader_scores: {swing_count}/{symbol_count} symbols ({coverage:.1f}%)")
            if swing_count == 0:
                print("  CRITICAL: No swing_trader_scores found - morning prep pipeline may not have run")

            return symbol_count > 0 and coverage >= 80

    except Exception as e:
        print(f"✗ Database check failed: {e}")
        return False

def check_phase_1_readiness():
    """Check Phase 1 data freshness requirements."""
    try:
        with DatabaseContext('read') as cur:
            run_date = datetime.now(ZoneInfo("America/New_York")).date()

            # Check SPY price data (within 1 trading day)
            cur.execute("""
                SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY'
            """)
            spy_result = cur.fetchone()
            if spy_result and spy_result[0]:
                print(f"✓ SPY price data: {spy_result[0]}")
            else:
                print("✗ SPY price data: NOT FOUND")

            # Check market_health_daily
            cur.execute("""
                SELECT COUNT(*) FROM market_health_daily
                WHERE updated_at >= CURRENT_DATE - INTERVAL '1 day'
            """)
            market_health = cur.fetchone()[0]
            print(f"{'✓' if market_health > 0 else '✗'} market_health_daily: {market_health} records")

            # Check trend_template_data
            cur.execute("""
                SELECT COUNT(*) FROM trend_template_data
                WHERE updated_at >= CURRENT_DATE - INTERVAL '1 day'
            """)
            trend_template = cur.fetchone()[0]
            print(f"{'✓' if trend_template > 0 else '✗'} trend_template_data: {trend_template} records")

            return spy_result and spy_result[0] and market_health > 0 and trend_template > 0

    except Exception as e:
        print(f"✗ Phase 1 readiness check failed: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("ORCHESTRATOR FULL DATASET READINESS CHECK")
    print("="*60 + "\n")

    print("1. Connectivity Check")
    print("-" * 40)
    connectivity_ok = check_rds_connectivity()

    if not connectivity_ok:
        print("\n✗ Cannot proceed: RDS not reachable")
        return 1

    print("\n2. Database State Check")
    print("-" * 40)
    db_ok = check_database_state()

    print("\n3. Phase 1 Readiness Check")
    print("-" * 40)
    phase1_ok = check_phase_1_readiness()

    print("\n" + "="*60)
    if connectivity_ok and db_ok and phase1_ok:
        print("✓ READY: Orchestrator can run with full dataset")
        print("="*60 + "\n")
        return 0
    else:
        print("✗ NOT READY: Fix issues above before running orchestrator")
        if not db_ok:
            print("  Action: Run morning prep pipeline (2:00 AM ET) or manual loader trigger")
        if not phase1_ok:
            print("  Action: Check Phase 1 data freshness requirements")
        print("="*60 + "\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
