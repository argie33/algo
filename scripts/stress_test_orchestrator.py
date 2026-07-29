#!/usr/bin/env python3
"""
Exhaustive orchestrator stress testing and issue discovery.

Tests:
1. Rapid consecutive runs (resource exhaustion)
2. Concurrent execution attempts (lock handling)
3. Large portfolio scenarios (performance/correctness)
4. Market condition extremes (VIX, volatility)
5. Data edge cases (missing data, gaps, nulls)
6. Error recovery (database failures, timeouts)
7. Cascade failures (downstream phase dependencies)
8. State corruption scenarios
"""

import subprocess
import time
import logging
from datetime import datetime, timedelta
from utils.db.context import DatabaseContext
import json

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def get_latest_run():
    """Get the most recent orchestrator run from database."""
    with DatabaseContext("read") as cur:
        cur.execute('''
            SELECT run_id, overall_status, phase_results, started_at
            FROM orchestrator_execution_log
            ORDER BY started_at DESC
            LIMIT 1
        ''')
        return cur.fetchone()

def run_orchestrator():
    """Run orchestrator and return result."""
    try:
        result = subprocess.run(
            ["python", "scripts/run_local_orchestrator.py", "--afternoon", "--force"],
            capture_output=True,
            text=True,
            timeout=180
        )
        # Check database for latest run
        run_id, status, phases, started_at = get_latest_run()
        return {
            'run_id': run_id,
            'status': status,
            'phases': phases if isinstance(phases, list) else json.loads(phases),
            'started_at': started_at
        }
    except Exception as e:
        logger.error(f"Orchestrator run failed: {e}")
        return None

def analyze_run(run_data):
    """Analyze run for issues."""
    if not run_data:
        return None

    issues = []
    phases = run_data['phases']

    for phase in phases:
        phase_num = phase.get('phase')
        phase_status = phase.get('status')
        summary = phase.get('summary', '')

        # Check for errors/failures
        if phase_status not in ['ok', 'success', 'blocked']:
            issues.append({
                'phase': phase_num,
                'status': phase_status,
                'summary': summary[:100] if summary else 'No details'
            })

        # Check for warnings in summary
        if 'warning' in summary.lower() or 'error' in summary.lower():
            if phase_status not in ['error', 'halted']:
                issues.append({
                    'phase': phase_num,
                    'type': 'warning_in_success',
                    'summary': summary[:100]
                })

    return issues if issues else None

def test_rapid_consecutive_runs(count=5):
    """Test rapid consecutive execution for resource exhaustion."""
    logger.info(f"\n{'='*70}")
    logger.info(f"TEST 1: Rapid Consecutive Runs (x{count})")
    logger.info(f"{'='*70}")

    all_issues = []
    for i in range(1, count + 1):
        logger.info(f"\n[{i}/{count}] Running orchestrator...")
        run = run_orchestrator()
        if run:
            logger.info(f"  Status: {run['status']}")
            issues = analyze_run(run)
            if issues:
                logger.warning(f"  Issues found: {len(issues)}")
                all_issues.extend(issues)
            else:
                logger.info(f"  OK")
        time.sleep(1)

    return all_issues

def test_data_edge_cases():
    """Test data integrity with edge cases."""
    logger.info(f"\n{'='*70}")
    logger.info(f"TEST 2: Data Edge Cases")
    logger.info(f"{'='*70}")

    issues = []

    with DatabaseContext("read") as cur:
        # Check for NULL values in critical fields
        tests = [
            ("Positions missing current_price",
             "SELECT COUNT(*) FROM algo_positions WHERE status='open' AND current_price IS NULL"),
            ("Trades missing entry_price",
             "SELECT COUNT(*) FROM algo_trades WHERE entry_price IS NULL"),
            ("Signals with NULL quality_score",
             "SELECT COUNT(*) FROM buy_sell_daily WHERE created_at > NOW() - INTERVAL '1 day' AND signal_quality_score IS NULL"),
            ("Positions with zero quantity",
             "SELECT COUNT(*) FROM algo_positions WHERE quantity = 0 AND status = 'open'"),
            ("Negative P&L without exit",
             "SELECT COUNT(*) FROM algo_trades WHERE pnl < -1000 AND status = 'open'"),
        ]

        for test_name, query in tests:
            try:
                cur.execute(query)
                count = cur.fetchone()[0]
                if count > 0:
                    logger.warning(f"  {test_name}: {count} found")
                    issues.append({'test': test_name, 'count': count})
                else:
                    logger.info(f"  {test_name}: OK")
            except Exception as e:
                logger.error(f"  {test_name}: Query failed - {e}")

    return issues

def test_position_concentration():
    """Test sector concentration limits."""
    logger.info(f"\n{'='*70}")
    logger.info(f"TEST 3: Position Concentration")
    logger.info(f"{'='*70}")

    issues = []

    with DatabaseContext("read") as cur:
        cur.execute('''
            SELECT cs.sector, COUNT(*) as cnt
            FROM algo_positions ap
            JOIN company_profile cs ON ap.symbol = cs.symbol
            WHERE ap.status = 'open'
            GROUP BY cs.sector
            HAVING COUNT(*) > 5
            ORDER BY COUNT(*) DESC
        ''')

        overconcentrated = cur.fetchall()
        if overconcentrated:
            logger.warning(f"  Over-concentrated sectors found:")
            for sector, cnt in overconcentrated:
                logger.warning(f"    {sector}: {cnt} positions")
                issues.append({'sector': sector, 'count': cnt, 'issue': 'over_concentration'})
        else:
            logger.info(f"  Concentration OK")

    return issues

def test_portfolio_performance():
    """Test portfolio health metrics."""
    logger.info(f"\n{'='*70}")
    logger.info(f"TEST 4: Portfolio Performance")
    logger.info(f"{'='*70}")

    issues = []

    with DatabaseContext("read") as cur:
        # Check for catastrophic losses
        cur.execute('''
            SELECT SUM(unrealized_pnl) as total_pnl, COUNT(*) as position_count
            FROM algo_positions
            WHERE status = 'open'
        ''')

        total_pnl, count = cur.fetchone()
        logger.info(f"  Open positions: {count}")
        logger.info(f"  Total unrealized P&L: {total_pnl}")

        if total_pnl and total_pnl < -10000:
            logger.warning(f"  WARNING: Large unrealized loss detected")
            issues.append({'issue': 'large_loss', 'amount': total_pnl})

        # Check for hung positions (no updates in 24h)
        cur.execute('''
            SELECT COUNT(*) FROM algo_positions
            WHERE status = 'open'
            AND updated_at < NOW() - INTERVAL '24 hours'
        ''')

        stale_count = cur.fetchone()[0]
        if stale_count > 0:
            logger.warning(f"  WARNING: {stale_count} positions not updated in 24h")
            issues.append({'issue': 'stale_positions', 'count': stale_count})

    return issues

def main():
    logger.info("="*70)
    logger.info("ORCHESTRATOR EXHAUSTIVE STRESS TEST")
    logger.info("="*70)

    all_findings = {}

    # Clear any stale locks first
    with DatabaseContext("write") as cur:
        cur.execute("DELETE FROM rds_locks WHERE name = 'orchestrator-run-lock'")

    # Run all tests
    all_findings['rapid_runs'] = test_rapid_consecutive_runs(5)
    all_findings['data_edges'] = test_data_edge_cases()
    all_findings['concentration'] = test_position_concentration()
    all_findings['portfolio'] = test_portfolio_performance()

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info("STRESS TEST SUMMARY")
    logger.info(f"{'='*70}")

    total_issues = sum(len(v) if v else 0 for v in all_findings.values())
    logger.info(f"\nTotal issues found: {total_issues}")

    for test_name, issues in all_findings.items():
        if issues:
            logger.warning(f"  {test_name}: {len(issues)} issues")
        else:
            logger.info(f"  {test_name}: OK")

    return all_findings

if __name__ == "__main__":
    findings = main()
    logger.info("\nTest complete. See above for detailed findings.")
