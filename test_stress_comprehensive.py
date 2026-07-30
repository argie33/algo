#!/usr/bin/env python3
"""Comprehensive stress testing to find ALL remaining issues."""

import sys
import logging
from pathlib import Path
from datetime import datetime, date
import time

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# Setup
from utils.dotenv_loader import load_env_local
load_env_local()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception as e:
    logging.getLogger(__name__).warning(f"[CREDS] Could not load credentials: {e}")

from algo.infrastructure.config.main import AlgoConfig
from algo.orchestration.orchestrator import Orchestrator
from utils.db.context import DatabaseContext

print("\n" + "="*80)
print("COMPREHENSIVE STRESS TEST SUITE")
print("="*80)

issues_found = []

def log_issue(category, severity, title, details):
    """Log a found issue for final report."""
    issue = {
        'category': category,
        'severity': severity,
        'title': title,
        'details': details,
        'timestamp': datetime.now()
    }
    issues_found.append(issue)
    print(f"\n[{severity}] {category}: {title}")
    print(f"    Details: {details}")

try:
    config = AlgoConfig()
    print(f"\n[1] Testing Basic Orchestrator Startup (Dry-Run)")
    print("-" * 80)

    # Test 1: Run orchestrator multiple times
    print("\n[1.1] Running orchestrator 3x in succession (stress test)...")
    for run_num in range(1, 4):
        try:
            print(f"  Run {run_num}/3...", end=" ", flush=True)
            orch = Orchestrator(config=config, dry_run=True, verbose=False)
            result = orch.run()

            if not result.get('success'):
                log_issue('Orchestrator', 'ERROR', f'Run {run_num} failed', result.get('reason', 'Unknown'))

            # Check for halts
            if result.get('halted'):
                log_issue('Orchestrator', 'WARNING', f'Run {run_num} halted', result.get('halt_reason', 'Unknown'))

            print("OK")
            time.sleep(1)  # Small delay between runs
        except Exception as e:
            log_issue('Orchestrator', 'CRITICAL', f'Run {run_num} crashed', str(e)[:200])

    # Test 2: Check database consistency
    print("\n[1.2] Checking database consistency after runs...")
    with DatabaseContext('read') as cur:
        # Check for orphaned positions
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions ap
        WHERE NOT EXISTS (SELECT 1 FROM algo_trades t WHERE t.trade_id = ANY(ap.trade_ids_arr))
        AND trade_ids_arr IS NOT NULL AND array_length(trade_ids_arr, 1) > 0
        """)
        orphaned = cur.fetchone()[0]
        if orphaned > 0:
            log_issue('Database', 'ERROR', 'Orphaned positions found', f'{orphaned} positions reference non-existent trades')

        # Check for positions with NULL required fields
        cur.execute("""
        SELECT COUNT(*), string_agg(DISTINCT symbol, ', ')
        FROM algo_positions
        WHERE status = 'open'
        AND (current_price IS NULL OR quantity IS NULL OR entry_price IS NULL OR stop_loss_price IS NULL)
        """)
        result = cur.fetchone()
        if result and result[0] > 0:
            log_issue('Database', 'ERROR', 'Positions with NULL required fields', f'{result[0]} positions have NULL fields')

        # Check for trades with invalid status
        cur.execute("""
        SELECT COUNT(*), status
        FROM algo_trades
        GROUP BY status
        """)
        print("\n  Trade status distribution:")
        for count, status in cur.fetchall():
            print(f"    {status}: {count}")

    # Test 3: Edge case - what if portfolio value is zero?
    print("\n[1.3] Testing edge case handling...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT COUNT(*) FROM algo_portfolio_snapshots
        WHERE total_portfolio_value <= 0
        """)
        invalid_portfolio = cur.fetchone()[0]
        if invalid_portfolio > 0:
            log_issue('Edge Case', 'CRITICAL', 'Invalid portfolio values', f'{invalid_portfolio} snapshots with value <= 0')

    # Test 4: Check configuration validity
    print("\n[1.4] Validating all critical configuration parameters...")
    critical_params = [
        'execution_mode',
        'alpaca_paper_trading',
        'halt_drawdown_pct',
        'max_daily_loss_pct',
        'max_position_size_pct',
        'min_signal_quality_score'
    ]

    missing_params = []
    invalid_params = []

    for param in critical_params:
        value = config.get(param)
        if value is None:
            missing_params.append(param)
        # Check ranges
        if param == 'halt_drawdown_pct' and (value > 0 or value < -100):
            invalid_params.append(f"{param}={value} (should be -100 to 0)")
        if param == 'max_daily_loss_pct' and (value < 0 or value > 50):
            invalid_params.append(f"{param}={value} (should be 0 to 50)")

    if missing_params:
        log_issue('Config', 'CRITICAL', 'Missing critical parameters', ', '.join(missing_params))
    if invalid_params:
        log_issue('Config', 'ERROR', 'Invalid parameter values', ', '.join(invalid_params))

    # Test 5: Check exit engine can find positions
    print("\n[1.5] Testing exit engine can locate positions...")
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        open_count = cur.fetchone()[0]
        print(f"  Open positions in database: {open_count}")

        if open_count == 0:
            log_issue('Exit Engine', 'WARNING', 'No open positions to exit', 'Cannot fully test exit execution without open positions')

        # Check if positions have valid trade_ids
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status = 'open'
        AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) IS NULL OR array_length(trade_ids_arr, 1) = 0)
        """)
        no_trades = cur.fetchone()[0]
        if no_trades > 0:
            log_issue('Exit Engine', 'CRITICAL', 'Positions without trade_ids', f'{no_trades} open positions have no associated trades')

    # Test 6: Check for data freshness issues
    print("\n[1.6] Checking data freshness for critical tables...")
    with DatabaseContext('read') as cur:
        critical_tables = {
            'price_daily': 'Prices',
            'technical_data_daily': 'Technical indicators',
            'algo_positions': 'Position data'
        }

        for table, desc in critical_tables.items():
            cur.execute(f"""
            SELECT MAX(CASE WHEN date IS NOT NULL THEN date
                           WHEN signal_date IS NOT NULL THEN signal_date
                           WHEN created_at IS NOT NULL THEN created_at::date
                           ELSE NULL END)
            FROM {table}
            """)
            row = cur.fetchone()
            if row and row[0]:
                last_update = row[0]
                age_days = (date.today() - last_update).days
                if age_days > 2:
                    log_issue('Data Freshness', 'WARNING', f'{desc} stale', f'{desc} not updated for {age_days} days')

    # Test 7: Check for silent failures in position monitoring
    print("\n[1.7] Checking for position monitoring blind spots...")
    with DatabaseContext('read') as cur:
        # Check for positions below stop loss
        cur.execute("""
        SELECT symbol, current_price, stop_loss_price
        FROM algo_positions
        WHERE status = 'open'
        AND current_price <= stop_loss_price
        """)
        below_stops = cur.fetchall()
        if below_stops:
            symbols = ', '.join([row[0] for row in below_stops])
            log_issue('Position Monitor', 'CRITICAL', 'Positions below stop loss', f'{len(below_stops)} positions: {symbols}')

        # Check for extreme losses
        cur.execute("""
        SELECT symbol, unrealized_pnl_pct
        FROM algo_positions
        WHERE status = 'open'
        AND unrealized_pnl_pct < -50
        """)
        extreme_losses = cur.fetchall()
        if extreme_losses:
            symbols = ', '.join([f"{row[0]} ({row[1]:.1f}%)" for row in extreme_losses])
            log_issue('Position Monitor', 'WARNING', 'Extreme unrealized losses', f'{len(extreme_losses)} positions: {symbols}')

    # Test 8: Check orchestrator execution log for patterns
    print("\n[1.8] Analyzing orchestrator execution patterns...")
    with DatabaseContext('read') as cur:
        # Check success rate
        cur.execute("""
        SELECT overall_status, COUNT(*)
        FROM orchestrator_execution_log
        WHERE started_at > NOW() - INTERVAL '7 days'
        GROUP BY overall_status
        """)
        statuses = cur.fetchall()
        print(f"  Last 7 days execution status:")
        for status, count in statuses:
            print(f"    {status}: {count}")
            if status == 'error':
                log_issue('Orchestrator', 'WARNING', 'Error runs detected', f'{count} runs failed in last 7 days')

        # Check for repeated errors
        cur.execute("""
        SELECT halt_reason, COUNT(*) as cnt
        FROM orchestrator_execution_log
        WHERE overall_status = 'error'
        AND started_at > NOW() - INTERVAL '24 hours'
        GROUP BY halt_reason
        ORDER BY cnt DESC
        LIMIT 5
        """)
        repeated_errors = cur.fetchall()
        if repeated_errors:
            print(f"  Recent repeated errors:")
            for reason, count in repeated_errors:
                print(f"    {reason[:80]}: {count}x")
                if count > 2:
                    log_issue('Orchestrator', 'ERROR', 'Repeated error pattern', f'{reason[:100]}: {count} occurrences')

    # Test 9: Check signal quality
    print("\n[1.9] Checking signal generation quality...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN composite_sqs >= 85 THEN 1 ELSE 0 END) as high_quality
        FROM signal_quality_scores
        WHERE date = CURRENT_DATE
        """)
        result = cur.fetchone()
        if result and result[0] > 0:
            total, high_qual = result[0], result[1]
            quality_pct = (high_qual / total * 100) if total > 0 else 0
            print(f"  Today's signals: {total} total, {high_qual} high-quality ({quality_pct:.1f}%)")
            if quality_pct < 20:
                log_issue('Signal Quality', 'WARNING', 'Low quality signal rate', f'Only {quality_pct:.1f}% meet quality threshold')

    # Test 10: Memory and performance
    print("\n[1.10] Testing orchestrator runtime performance...")
    print("  Running orchestrator with timing...", end=" ", flush=True)
    start = time.time()
    orch = Orchestrator(config=config, dry_run=True, verbose=False)
    result = orch.run()
    elapsed = time.time() - start
    print(f"OK ({elapsed:.2f}s)")

    if elapsed > 30:
        log_issue('Performance', 'WARNING', 'Slow orchestrator execution', f'Orchestrator took {elapsed:.2f}s (>30s threshold)')

    print("\n" + "="*80)
    print(f"STRESS TEST COMPLETE - Found {len(issues_found)} issues")
    print("="*80)

    if issues_found:
        print(f"\n[SUMMARY] Issues by severity:")
        critical = len([i for i in issues_found if i['severity'] == 'CRITICAL'])
        error = len([i for i in issues_found if i['severity'] == 'ERROR'])
        warning = len([i for i in issues_found if i['severity'] == 'WARNING'])

        print(f"  CRITICAL: {critical}")
        print(f"  ERROR: {error}")
        print(f"  WARNING: {warning}")

        if critical > 0:
            print(f"\n[ACTION REQUIRED] {critical} CRITICAL issues found - must fix before production use")

        print("\nDetailed issues:")
        for i, issue in enumerate(issues_found, 1):
            print(f"\n{i}. [{issue['severity']}] {issue['category']}: {issue['title']}")
            print(f"   {issue['details']}")
    else:
        print("\nNo issues found!")

except Exception as e:
    print(f"\n[CRITICAL] Test suite failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
