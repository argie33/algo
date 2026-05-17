#!/usr/bin/env python3
"""
System Verification Script - Check all critical components
"""
import sys
import os
os.environ['PYTHONPATH'] = '/c/Users/arger/code/algo'
sys.path.insert(0, '/c/Users/arger/code/algo')

import psycopg2
from config.credential_helper import get_db_config
from datetime import date, timedelta

def check_data_volume():
    """Check database data volume and freshness"""
    print("\n" + "="*70)
    print("PART 1: DATA COMPLETENESS CHECK")
    print("="*70)

    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()

        tables = [
            ('stock_symbols', 'COUNT(*)', 'Total symbols'),
            ('price_daily', 'COUNT(*)', 'Price records'),
            ('buy_sell_signals', 'COUNT(*)', 'Buy/Sell signals'),
            ('stock_scores', 'COUNT(*)', 'Stock scores'),
            ('quality_metrics', 'COUNT(*)', 'Quality metrics'),
            ('market_health_daily', 'COUNT(*)', 'Market health'),
            ('fear_greed_index', 'COUNT(*)', 'Fear/Greed'),
            ('analyst_sentiment_analysis', 'COUNT(*)', 'Analyst sentiment'),
            ('algo_trades', 'COUNT(*)', 'Algo trades'),
            ('algo_positions', 'COUNT(*)', 'Algo positions'),
        ]

        for table, query, label in tables:
            try:
                cur.execute(f"SELECT {query} FROM {table}")
                count = cur.fetchone()[0]
                status = "✓" if count > 0 else "✗"
                print(f"  {status} {label:25} {count:>10}")
            except Exception as e:
                print(f"  ✗ {label:25} ERROR: {str(e)[:30]}")

        # Check freshness
        print("\n  Data Freshness:")
        cur.execute("SELECT MAX(date) FROM price_daily")
        latest_price = cur.fetchone()[0]
        print(f"    - Latest price date: {latest_price}")

        cur.execute("SELECT MAX(date) FROM stock_scores")
        latest_scores = cur.fetchone()[0]
        print(f"    - Latest scores date: {latest_scores}")

        cur.execute("SELECT MAX(snapshot_date) FROM algo_portfolio_snapshots")
        latest_snapshot = cur.fetchone()[0]
        print(f"    - Latest portfolio snapshot: {latest_snapshot}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        return False

    return True


def check_orchestrator():
    """Test orchestrator dry-run"""
    print("\n" + "="*70)
    print("PART 2: ORCHESTRATOR TEST (DRY-RUN)")
    print("="*70)

    try:
        from algo.algo_orchestrator import Orchestrator

        # Test with last Friday (2026-05-15)
        test_date = date(2026, 5, 15)
        print(f"\n  Testing orchestrator for {test_date} (Friday)...")

        orch = Orchestrator(run_date=test_date, dry_run=True, verbose=False)
        result = orch.run()

        print(f"\n  Orchestrator Result: {result.get('success')}")
        print(f"  Phases completed: {list(result.get('phases', {}).keys())}")

        for phase_id, phase_data in result.get('phases', {}).items():
            status = "✓" if phase_data.get('status') == 'success' else "✗"
            name = phase_data.get('name', f'Phase {phase_id}')
            summary = phase_data.get('summary', '')
            print(f"    {status} Phase {phase_id} ({name}): {summary}")

        return result.get('success', False)

    except Exception as e:
        print(f"ERROR: Orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_calculations():
    """Verify key calculations"""
    print("\n" + "="*70)
    print("PART 3: CALCULATION VERIFICATION")
    print("="*70)

    try:
        from algo.algo_swing_score import SwingTraderScore

        print("\n  SwingTraderScore component weights:")
        scorer = SwingTraderScore()
        print(f"    - Setup quality (W): {scorer.W_SETUP}%")
        print(f"    - Trend quality (W): {scorer.W_TREND}%")
        print(f"    - Momentum/RS (W): {scorer.W_MOMENTUM}%")
        print(f"    - Volume (W): {scorer.W_VOLUME}%")
        print(f"    - Fundamentals (W): {scorer.W_FUNDAMENTALS}%")
        print(f"    - Sector (W): {scorer.W_SECTOR}%")
        print(f"    - Multi-TF (W): {scorer.W_MULTI_TF}%")
        total = (scorer.W_SETUP + scorer.W_TREND + scorer.W_MOMENTUM +
                 scorer.W_VOLUME + scorer.W_FUNDAMENTALS + scorer.W_SECTOR + scorer.W_MULTI_TF)
        print(f"    - TOTAL: {total}% (should be 100)")

        if total == 100:
            print("\n  ✓ Score weights are correctly balanced")
        else:
            print(f"\n  ✗ WARNING: Score weights sum to {total}% (should be 100)")

        return total == 100

    except Exception as e:
        print(f"ERROR: Could not verify calculations: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n╔═══════════════════════════════════════════════════════════════════╗")
    print("║            SYSTEM VERIFICATION & HEALTH CHECK (2026-05-17)        ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")

    results = {
        'data': check_data_volume(),
        'orchestrator': check_orchestrator(),
        'calculations': check_calculations(),
    }

    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    print(f"  {'Data Completeness':30} {'✓' if results['data'] else '✗'}")
    print(f"  {'Orchestrator Logic':30} {'✓' if results['orchestrator'] else '✗'}")
    print(f"  {'Calculation Correctness':30} {'✓' if results['calculations'] else '✗'}")

    all_pass = all(results.values())
    print(f"\n  Overall Status: {'✓ PASS' if all_pass else '✗ NEEDS ATTENTION'}")

    return 0 if all_pass else 1


if __name__ == '__main__':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.exit(main())
