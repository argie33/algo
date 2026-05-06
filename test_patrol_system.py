#!/usr/bin/env python3
"""
Comprehensive patrol + alert system test

Tests all 16 patrol checks + alerts + reconciliation without trading.
Use this to verify everything works before running in production.

Usage:
  python3 test_patrol_system.py                 # full test
  python3 test_patrol_system.py --quick         # data patrol only
  python3 test_patrol_system.py --alerts        # test alerts
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, date as _date

def test_data_patrol(quick=False):
    """Run all patrol checks."""
    print("\n" + "="*70)
    print("TEST 1: DATA PATROL")
    print("="*70)

    try:
        from algo_data_patrol import DataPatrol
        patrol = DataPatrol()
        result = patrol.run(quick=quick)

        print(f"\nResults:")
        print(f"  CRITICAL: {result['counts'].get('critical', 0)}")
        print(f"  ERROR:    {result['counts'].get('error', 0)}")
        print(f"  WARN:     {result['counts'].get('warn', 0)}")
        print(f"  INFO:     {result['counts'].get('info', 0)}")

        if result['flagged']:
            print(f"\nFlagged findings ({len(result['flagged'])}):")
            for f in result['flagged'][:10]:
                print(f"  [{f['severity'].upper()}] {f['check']:20s} {f['target']:25s}: {f['message']}")

        return result['ready']
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_position_monitor():
    """Review positions."""
    print("\n" + "="*70)
    print("TEST 2: POSITION MONITOR")
    print("="*70)

    try:
        from algo_position_monitor import PositionMonitor
        from algo_config import get_config
        monitor = PositionMonitor(get_config())

        # Check stale orders
        stale = monitor.check_stale_orders(_date.today())
        if stale['count'] > 0:
            print(f"  [ALERT] {stale['count']} stale orders found")
        else:
            print(f"  [OK] No stale orders")

        # Review positions
        recs = monitor.review_positions(_date.today())
        if recs:
            print(f"\n  Reviewed {len(recs)} positions")
            n_hold = sum(1 for r in recs if r and r.get('action') == 'HOLD')
            n_exit = sum(1 for r in recs if r and r.get('action') == 'EARLY_EXIT')
            n_stop = sum(1 for r in recs if r and r.get('action') == 'RAISE_STOP')
            print(f"    {n_hold} HOLD / {n_stop} RAISE_STOP / {n_exit} EARLY_EXIT")
        else:
            print(f"  No open positions")

        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_reconciliation():
    """Verify DB positions match Alpaca."""
    print("\n" + "="*70)
    print("TEST 3: POSITION RECONCILIATION")
    print("="*70)

    try:
        from algo_reconciliation import PositionReconciler
        reconciler = PositionReconciler()
        result = reconciler.reconcile()

        if result.get('status') == 'skipped':
            print(f"  SKIPPED: {result.get('reason', 'unknown')}")
            return True

        print(f"\nResults:")
        print(f"  DB positions:      {result.get('db_positions', 0)}")
        print(f"  Alpaca positions:  {result.get('alpaca_positions', 0)}")
        print(f"  Critical issues:   {result.get('critical_count', 0)}")
        print(f"  Error issues:      {result.get('error_count', 0)}")

        if result.get('issues'):
            print(f"\nIssues ({len(result['issues'])}):")
            for issue in result['issues'][:5]:
                print(f"  [{issue['severity']}] {issue['symbol']}: {issue['type']} "
                      f"(DB={issue['db_qty']} vs Alpaca={issue['alpaca_qty']})")

        return result.get('critical_count', 0) == 0
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_alerts(send_test=False):
    """Test alert configuration."""
    print("\n" + "="*70)
    print("TEST 4: ALERT CONFIGURATION")
    print("="*70)

    try:
        from algo_alerts import AlertManager
        alerts = AlertManager()

        print(f"\nEmail configured:")
        print(f"  From: {alerts.email_from}")
        print(f"  To:   {', '.join(alerts.email_to) if alerts.email_to else '(none)'}")
        print(f"  SMTP: {alerts.smtp_host}:{alerts.smtp_port}")

        print(f"\nSMS configured:")
        print(f"  Twilio:  {'YES' if alerts.twilio_client else 'NO (skipped)'}")
        print(f"  Numbers: {', '.join(alerts.phone_numbers) if alerts.phone_numbers else '(none)'}")

        print(f"\nWebhook configured:")
        print(f"  Slack: {'YES' if alerts.webhook_url else 'NO'}")

        if send_test:
            print(f"\nSending test alert...")
            alerts.send_patrol_alert(
                'TEST-PATROL-20250505-120000',
                {'critical': 1, 'error': 1, 'warn': 2, 'info': 5},
                [
                    {'check': 'ohlc_sanity', 'severity': 'critical', 'target': 'price_daily',
                     'message': '1 row with NEGATIVE prices (TEST)'},
                    {'check': 'staleness', 'severity': 'error', 'target': 'price_daily',
                     'message': 'Data 8d old (TEST)'},
                ]
            )
            print("  Test alert sent (check email/SMS/Slack)")

        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_orchestrator_dry_run():
    """Run orchestrator in dry-run (paper) mode."""
    print("\n" + "="*70)
    print("TEST 5: ORCHESTRATOR DRY RUN")
    print("="*70)

    try:
        from algo_orchestrator import Orchestrator
        orch = Orchestrator(dry_run=True, verbose=True)

        # Just run phase 1 (data freshness) as a test
        print("\nRunning Phase 1 (Data Freshness Check)...")
        result = orch.phase_1_data_freshness()
        print(f"  Result: {'PASS' if result else 'FAIL'}")

        if orch.phase_results.get(1):
            print(f"  {orch.phase_results[1]}")

        return result
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description='Patrol system test')
    parser.add_argument('--quick', action='store_true', help='Quick patrol check only')
    parser.add_argument('--alerts', action='store_true', help='Test alerts only')
    parser.add_argument('--send-test-alert', action='store_true', help='Actually send test alert')
    parser.add_argument('--monitor-only', action='store_true', help='Position monitor only')
    parser.add_argument('--reconcile-only', action='store_true', help='Reconciliation only')
    parser.add_argument('--orchestra-only', action='store_true', help='Orchestrator phase 1 only')
    args = parser.parse_args()

    print(f"\n{'#'*70}")
    print(f"#  PATROL SYSTEM TEST — {datetime.now().isoformat()}")
    print(f"{'#'*70}")

    results = {}

    if args.quick or (not args.alerts and not args.monitor_only and not args.reconcile_only and not args.orchestra_only):
        results['patrol'] = test_data_patrol(quick=args.quick)

    if args.alerts or (not args.quick and not args.monitor_only and not args.reconcile_only and not args.orchestra_only):
        results['alerts'] = test_alerts(send_test=args.send_test_alert)

    if not args.quick and not args.alerts:
        if args.monitor_only or (not args.reconcile_only and not args.orchestra_only):
            results['monitor'] = test_position_monitor()

        if args.reconcile_only or (not args.monitor_only and not args.orchestra_only):
            results['reconciliation'] = test_reconciliation()

        if args.orchestra_only or (not args.monitor_only and not args.reconcile_only):
            results['orchestrator'] = test_orchestrator_dry_run()

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    for name, passed in results.items():
        status = '✓ PASS' if passed else '✗ FAIL'
        print(f"  {name:20s} {status}")

    print(f"\n{'='*70}\n")

    all_passed = all(results.values())
    if all_passed:
        print("ALL TESTS PASSED ✓\n")
        print("Ready to run orchestrator in production mode.")
        return 0
    else:
        print("SOME TESTS FAILED ✗\n")
        print("Fix issues above before running orchestrator.")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
