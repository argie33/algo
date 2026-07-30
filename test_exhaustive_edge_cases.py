#!/usr/bin/env python3
"""Exhaustive edge case testing to find REAL issues."""

import sys
import logging
from pathlib import Path
from datetime import date as _date, datetime, timedelta
import copy

logging.basicConfig(level=logging.ERROR, format='%(levelname)s:%(message)s')

from utils.dotenv_loader import load_env_local
load_env_local()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception:
    pass

from algo.infrastructure.config.main import AlgoConfig
from utils.db.context import DatabaseContext
import psycopg2

print("\n" + "="*80)
print("EXHAUSTIVE EDGE CASE TESTING - FINDING ALL ISSUES")
print("="*80)

issues = []

def report_issue(severity, category, title, details):
    """Report a found issue."""
    issue = {'severity': severity, 'category': category, 'title': title, 'details': details}
    issues.append(issue)
    print(f"\n[{severity}] {category}: {title}")
    print(f"  {details}")

try:
    config = AlgoConfig()

    # TEST 1: Database edge cases
    print("\n[TEST 1] DATABASE EDGE CASES")
    print("-" * 80)

    with DatabaseContext('write') as cur:
        # 1.1: Check for positions with invalid quantity
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status = 'open' AND (quantity IS NULL OR quantity <= 0)
        """)
        bad_qty = cur.fetchone()[0]
        if bad_qty > 0:
            report_issue('CRITICAL', 'Data', 'Positions with invalid quantity',
                        f'{bad_qty} positions have NULL or zero quantity - cannot calculate P&L')

        # 1.2: Check for negative portfolio values
        cur.execute("""
        SELECT COUNT(*) FROM algo_portfolio_snapshots
        WHERE total_portfolio_value < 0
        """)
        neg_portfolio = cur.fetchone()[0]
        if neg_portfolio > 0:
            report_issue('CRITICAL', 'Data', 'Negative portfolio values',
                        f'{neg_portfolio} snapshots show negative value - data corruption')

        # 1.3: Check for mismatched position/trade data
        cur.execute("""
        SELECT p.position_id FROM algo_positions p
        WHERE p.trade_ids_arr IS NOT NULL
        AND array_length(p.trade_ids_arr, 1) > 0
        AND NOT EXISTS (
            SELECT 1 FROM algo_trades t
            WHERE t.trade_id = ANY(p.trade_ids_arr)
        )
        LIMIT 5
        """)
        orphaned = cur.fetchall()
        if orphaned:
            report_issue('CRITICAL', 'Data', 'Orphaned position-trade links',
                        f'{len(orphaned)} positions reference non-existent trades')

        # 1.4: Check for trades with invalid status transitions
        cur.execute("""
        SELECT COUNT(*), status FROM algo_trades
        GROUP BY status
        """)
        statuses = cur.fetchall()
        print(f"  Trade status distribution: {dict(statuses)}")

        # Invalid statuses that shouldn't exist
        invalid_statuses = [row[1] for row in statuses if row[1] not in
                           ('pending', 'filled', 'partially_filled', 'rejected', 'cancelled', 'closed')]
        if invalid_statuses:
            report_issue('ERROR', 'Data', 'Invalid trade statuses',
                        f'Found invalid statuses: {invalid_statuses}')

        # 1.5: Check for duplicate positions for same symbol
        cur.execute("""
        SELECT symbol, COUNT(*) as cnt FROM algo_positions
        WHERE status = 'open'
        GROUP BY symbol HAVING COUNT(*) > 1
        """)
        dups = cur.fetchall()
        if dups:
            symbols = ', '.join([row[0] for row in dups])
            report_issue('ERROR', 'Data', 'Duplicate open positions',
                        f'Symbols with multiple open positions: {symbols}')

    # TEST 2: Configuration edge cases
    print("\n[TEST 2] CONFIGURATION EDGE CASES")
    print("-" * 80)

    # 2.1: Check if critical config values are sane
    critical_ranges = {
        'halt_drawdown_pct': (-100, 0),
        'max_daily_loss_pct': (0, 50),
        'max_position_size_pct': (0, 20),
        'base_risk_pct': (0.01, 5),
        'min_signal_quality_score': (1, 100),
    }

    for param, (min_val, max_val) in critical_ranges.items():
        try:
            val = float(config.get(param))
            if not (min_val <= val <= max_val):
                report_issue('ERROR', 'Config', f'Out-of-range value: {param}',
                            f'{param}={val} outside valid range [{min_val}, {max_val}]')
        except (ValueError, TypeError):
            report_issue('CRITICAL', 'Config', f'Invalid config value: {param}',
                        f'{param} cannot be converted to float')

    # 2.2: Check for contradictory configuration
    halt_dd = float(config.get('halt_drawdown_pct'))
    risk_red_5 = float(config.get('risk_reduction_at_minus_5'))
    if halt_dd > -5 and risk_red_5 > 0:
        report_issue('WARNING', 'Config', 'Halt and risk reduction mismatch',
                    'Halt triggers before risk reduction can activate - redundant config')

    # TEST 3: Position monitoring edge cases
    print("\n[TEST 3] POSITION MONITORING EDGE CASES")
    print("-" * 80)

    with DatabaseContext('read') as cur:
        # 3.1: Positions with current price == stop (exact at stop)
        cur.execute("""
        SELECT symbol FROM algo_positions
        WHERE status = 'open' AND current_price = stop_loss_price
        """)
        at_stops = [row[0] for row in cur.fetchall()]
        if at_stops:
            report_issue('WARNING', 'Monitoring', 'Positions exactly at stop loss',
                        f'Positions at exact stop: {", ".join(at_stops)}')

        # 3.2: Check for extreme price moves (>20% in one day)
        cur.execute("""
        SELECT symbol,
               ABS((current_price - entry_price) / entry_price * 100) as move_pct
        FROM algo_positions
        WHERE status = 'open'
        AND ABS((current_price - entry_price) / entry_price) > 0.2
        """)
        extreme = cur.fetchall()
        if extreme:
            for sym, move in extreme:
                report_issue('WARNING', 'Monitoring', 'Extreme price move',
                            f'{sym} moved {move:.1f}% from entry')

        # 3.3: Check for zero-quantity positions
        cur.execute("""
        SELECT symbol, quantity FROM algo_positions
        WHERE status = 'open' AND quantity = 0
        """)
        zero_qty = cur.fetchall()
        if zero_qty:
            report_issue('CRITICAL', 'Monitoring', 'Zero-quantity positions',
                        f'Positions with zero quantity: {[row[0] for row in zero_qty]}')

        # 3.4: Check for positions held longer than max_hold_days
        max_hold = int(config.get('max_hold_days'))
        cur.execute("""
        SELECT symbol, entry_date,
               (CURRENT_DATE - entry_date) as days_held
        FROM algo_positions
        WHERE status = 'open'
        AND (CURRENT_DATE - entry_date) > %s
        """, (max_hold,))
        over_hold = cur.fetchall()
        if over_hold:
            for sym, entry, days in over_hold:
                report_issue('WARNING', 'Monitoring', 'Position held past max_hold_days',
                            f'{sym}: held {days} days (max {max_hold})')

    # TEST 4: Exit execution edge cases
    print("\n[TEST 4] EXIT EXECUTION EDGE CASES")
    print("-" * 80)

    with DatabaseContext('read') as cur:
        # 4.1: Check if positions below stop loss will be caught
        cur.execute("""
        SELECT symbol, current_price, stop_loss_price
        FROM algo_positions
        WHERE status = 'open' AND current_price < stop_loss_price
        """)
        below_stops = cur.fetchall()
        if below_stops:
            for sym, price, stop in below_stops:
                report_issue('CRITICAL', 'Exit', 'Position below stop loss NOT DETECTED',
                            f'{sym}: price ${price:.2f} < stop ${stop:.2f} - SHOULD HAVE EXITED!')
        else:
            print("  [OK] No positions below stop loss (would be caught by exit engine)")

        # 4.2: Check for trades that are stuck in pending state
        cur.execute("""
        SELECT trade_id, symbol, status, created_at
        FROM algo_trades
        WHERE status IN ('pending', 'partial_filled')
        AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 hour'
        """)
        stuck_trades = cur.fetchall()
        if stuck_trades:
            for tid, sym, status, created in stuck_trades:
                age_hours = (datetime.now(created.tzinfo) - created).total_seconds() / 3600
                report_issue('ERROR', 'Exit', 'Stuck order (pending >1h)',
                            f'{sym} ({tid}): {status} for {age_hours:.1f}h')

    # TEST 5: Signal generation edge cases
    print("\n[TEST 5] SIGNAL GENERATION EDGE CASES")
    print("-" * 80)

    with DatabaseContext('read') as cur:
        # 5.1: Check signal quality
        cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN composite_sqs >= 85 THEN 1 ELSE 0 END) as high_quality
        FROM signal_quality_scores
        WHERE date = CURRENT_DATE
        """)
        result = cur.fetchone()
        if result and result[0] > 0:
            total, high_qual = result[0], result[1] or 0
            quality_pct = (high_qual / total * 100) if total > 0 else 0
            if quality_pct < 10:
                report_issue('WARNING', 'Signals', 'Very low quality signal rate',
                            f'Only {quality_pct:.1f}% of {total} signals are high-quality')
            print(f"  Signal quality: {quality_pct:.1f}% high-quality ({high_qual}/{total})")

        # 5.2: Check for missing critical signal columns
        try:
            cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM algo_signals
            WHERE date = CURRENT_DATE
            AND (signal_type IS NULL OR signal_date IS NULL OR close_price IS NULL)
            """)
            bad_signals = cur.fetchone()[0]
            if bad_signals > 0:
                report_issue('ERROR', 'Signals', 'Signals with NULL required fields',
                            f'{bad_signals} signals have NULL critical fields')
        except:
            pass  # Table might not have these columns

    # TEST 6: Orchestrator state consistency
    print("\n[TEST 6] ORCHESTRATOR STATE CONSISTENCY")
    print("-" * 80)

    with DatabaseContext('read') as cur:
        # 6.1: Check if orchestrator has ever failed to complete
        cur.execute("""
        SELECT overall_status, COUNT(*) as cnt
        FROM orchestrator_execution_log
        WHERE started_at > CURRENT_DATE - INTERVAL '7 days'
        GROUP BY overall_status
        """)
        results = cur.fetchall()
        status_dict = dict(results)
        print(f"  Last 7 days: {status_dict}")

        if status_dict.get('error', 0) > status_dict.get('ok', 0):
            report_issue('CRITICAL', 'Orchestrator', 'High failure rate',
                        f'Error runs {status_dict.get("error", 0)} > success runs {status_dict.get("ok", 0)}')

        # 6.2: Check for orchestrator phases that are consistently failing
        cur.execute("""
        SELECT phase_results->>'phase_6' as phase6_status, COUNT(*)
        FROM orchestrator_execution_log
        WHERE started_at > CURRENT_DATE - INTERVAL '1 day'
        GROUP BY phase_results->>'phase_6'
        """)
        phase_results = cur.fetchall()
        print(f"  Phase 6 last 24h: {dict(phase_results) if phase_results else 'no runs'}")

    # TEST 7: Concurrency safety
    print("\n[TEST 7] CONCURRENCY EDGE CASES")
    print("-" * 80)

    with DatabaseContext('read') as cur:
        # 7.1: Check if multiple orchestrator instances could run simultaneously
        cur.execute("""
        SELECT COUNT(*) FROM orchestrator_execution_log
        WHERE overall_status NOT IN ('ok', 'skipped', 'error')
        """)
        unclosed = cur.fetchone()[0]
        if unclosed > 0:
            report_issue('WARNING', 'Concurrency', 'Unclosed orchestrator runs',
                        f'{unclosed} runs in unclear state - could allow concurrent execution')

        # 7.2: Check if position updates could race with exit execution
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE updated_at > CURRENT_TIMESTAMP - INTERVAL '5 seconds'
        """)
        recent_updates = cur.fetchone()[0]
        if recent_updates > 5:
            print(f"  [INFO] High concurrent update rate: {recent_updates} positions updated in last 5s")

    print("\n" + "="*80)
    print(f"TESTING COMPLETE - Found {len(issues)} issues")
    print("="*80)

    if issues:
        print(f"\n[SUMMARY] Issues by severity:")
        critical = [i for i in issues if i['severity'] == 'CRITICAL']
        errors = [i for i in issues if i['severity'] == 'ERROR']
        warnings = [i for i in issues if i['severity'] == 'WARNING']

        print(f"  CRITICAL: {len(critical)}")
        print(f"  ERROR: {len(errors)}")
        print(f"  WARNING: {len(warnings)}")

        if critical:
            print(f"\n[ACTION REQUIRED] {len(critical)} CRITICAL issues must be fixed:")
            for i, issue in enumerate(critical, 1):
                print(f"\n{i}. {issue['category']}: {issue['title']}")
                print(f"   {issue['details']}")
            sys.exit(1)

        if errors:
            print(f"\n[WARNING] {len(errors)} ERROR issues found:")
            for i, issue in enumerate(errors, 1):
                print(f"  {i}. {issue['title']}")

except Exception as e:
    print(f"\n[CRITICAL] Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
