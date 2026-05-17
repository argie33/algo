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
import logging

logger = logging.getLogger(__name__)

def check_data_volume():
    """Check database data volume and freshness"""
    logger.info("\n" + "="*70)
    logger.info("PART 1: DATA COMPLETENESS CHECK")
    logger.info("="*70)

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
                logger.info(f"  {status} {label:25} {count:>10}")
            except Exception as e:
                logger.info(f"  ✗ {label:25} ERROR: {str(e)[:30]}")

        # Check freshness
        logger.info("\n  Data Freshness:")
        cur.execute("SELECT MAX(date) FROM price_daily")
        latest_price = cur.fetchone()[0]
        logger.info(f"    - Latest price date: {latest_price}")

        cur.execute("SELECT MAX(date) FROM stock_scores")
        latest_scores = cur.fetchone()[0]
        logger.info(f"    - Latest scores date: {latest_scores}")

        cur.execute("SELECT MAX(snapshot_date) FROM algo_portfolio_snapshots")
        latest_snapshot = cur.fetchone()[0]
        logger.info(f"    - Latest portfolio snapshot: {latest_snapshot}")

        cur.close()
        conn.close()

    except Exception as e:
        logger.info(f"ERROR: Could not connect to database: {e}")
        return False

    return True


def check_orchestrator():
    """Test orchestrator dry-run"""
    logger.info("\n" + "="*70)
    logger.info("PART 2: ORCHESTRATOR TEST (DRY-RUN)")
    logger.info("="*70)

    try:
        from algo.algo_orchestrator import Orchestrator

        # Test with last Friday (2026-05-15)
        test_date = date(2026, 5, 15)
        logger.info(f"\n  Testing orchestrator for {test_date} (Friday)...")

        orch = Orchestrator(run_date=test_date, dry_run=True, verbose=False)
        result = orch.run()

        logger.info(f"\n  Orchestrator Result: {result.get('success')}")
        logger.info(f"  Phases completed: {list(result.get('phases', {}).keys())}")

        for phase_id, phase_data in result.get('phases', {}).items():
            status = "✓" if phase_data.get('status') == 'success' else "✗"
            name = phase_data.get('name', f'Phase {phase_id}')
            summary = phase_data.get('summary', '')
            logger.info(f"    {status} Phase {phase_id} ({name}): {summary}")

        return result.get('success', False)

    except Exception as e:
        logger.info(f"ERROR: Orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_calculations():
    """Verify key calculations"""
    logger.info("\n" + "="*70)
    logger.info("PART 3: CALCULATION VERIFICATION")
    logger.info("="*70)

    try:
        from algo.algo_swing_score import SwingTraderScore

        logger.info("\n  SwingTraderScore component weights:")
        scorer = SwingTraderScore()
        logger.info(f"    - Setup quality (W): {scorer.W_SETUP}%")
        logger.info(f"    - Trend quality (W): {scorer.W_TREND}%")
        logger.info(f"    - Momentum/RS (W): {scorer.W_MOMENTUM}%")
        logger.info(f"    - Volume (W): {scorer.W_VOLUME}%")
        logger.info(f"    - Fundamentals (W): {scorer.W_FUNDAMENTALS}%")
        logger.info(f"    - Sector (W): {scorer.W_SECTOR}%")
        logger.info(f"    - Multi-TF (W): {scorer.W_MULTI_TF}%")
        total = (scorer.W_SETUP + scorer.W_TREND + scorer.W_MOMENTUM +
                 scorer.W_VOLUME + scorer.W_FUNDAMENTALS + scorer.W_SECTOR + scorer.W_MULTI_TF)
        logger.info(f"    - TOTAL: {total}% (should be 100)")

        if total == 100:
            logger.info("\n  ✓ Score weights are correctly balanced")
        else:
            logger.info(f"\n  ✗ WARNING: Score weights sum to {total}% (should be 100)")

        return total == 100

    except Exception as e:
        logger.info(f"ERROR: Could not verify calculations: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    logger.info("\n╔═══════════════════════════════════════════════════════════════════╗")
    logger.info("║            SYSTEM VERIFICATION & HEALTH CHECK (2026-05-17)        ║")
    logger.info("╚═══════════════════════════════════════════════════════════════════╝")

    results = {
        'data': check_data_volume(),
        'orchestrator': check_orchestrator(),
        'calculations': check_calculations(),
    }

    logger.info("\n" + "="*70)
    logger.info("VERIFICATION SUMMARY")
    logger.info("="*70)
    logger.info(f"  {'Data Completeness':30} {'✓' if results['data'] else '✗'}")
    logger.info(f"  {'Orchestrator Logic':30} {'✓' if results['orchestrator'] else '✗'}")
    logger.info(f"  {'Calculation Correctness':30} {'✓' if results['calculations'] else '✗'}")

    all_pass = all(results.values())
    logger.info(f"\n  Overall Status: {'✓ PASS' if all_pass else '✗ NEEDS ATTENTION'}")

    return 0 if all_pass else 1


if __name__ == '__main__':
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.exit(main())
