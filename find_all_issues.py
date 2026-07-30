#!/usr/bin/env python3
"""
Comprehensive issue finder - scans database and logs for all problems.
"""

from utils.db.context import DatabaseContext
from datetime import datetime, timedelta
import sys

def check_trades():
    """Find all trade data integrity issues"""
    issues = []

    with DatabaseContext(role='read') as ctx:
        cursor = ctx.connection.cursor()

        # 1. Closed trades missing P&L calculations
        cursor.execute('''
            SELECT trade_id, symbol, entry_price, exit_price, entry_quantity,
                   profit_loss_dollars, profit_loss_pct
            FROM algo_trades
            WHERE status = 'closed'
              AND exit_price IS NOT NULL
              AND (profit_loss_dollars IS NULL OR profit_loss_pct IS NULL)
            LIMIT 20
        ''')
        for row in cursor.fetchall():
            issues.append({
                'severity': 'HIGH',
                'category': 'TRADE_P&L_CALCULATION',
                'item': row[0],
                'detail': f'{row[1]}: entry={row[2]}, exit={row[3]}, qty={row[4]} => pnl_dollars={row[5]}, pnl_pct={row[6]}'
            })

        # 2. Duplicate trades (same symbol, same trade_date)
        cursor.execute('''
            SELECT symbol, trade_date, COUNT(*) as cnt
            FROM algo_trades
            GROUP BY symbol, trade_date
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        ''')
        for row in cursor.fetchall():
            issues.append({
                'severity': 'HIGH',
                'category': 'DUPLICATE_TRADES',
                'item': f'{row[0]} on {row[1]}',
                'detail': f'{row[2]} trades created on same day'
            })

        # 3. Open trades with exit prices (should not happen)
        cursor.execute('''
            SELECT trade_id, symbol, status, exit_price, exit_date
            FROM algo_trades
            WHERE status = 'open' AND exit_price IS NOT NULL
            LIMIT 20
        ''')
        for row in cursor.fetchall():
            issues.append({
                'severity': 'MEDIUM',
                'category': 'OPEN_TRADE_WITH_EXIT',
                'item': row[0],
                'detail': f'{row[1]}: status={row[2]}, but has exit_price={row[3]} on {row[4]}'
            })

        # 4. Positions missing critical fields
        cursor.execute('''
            SELECT symbol, status,
                   CASE WHEN current_price IS NULL THEN 'NULL' ELSE 'OK' END,
                   CASE WHEN stop_loss_price IS NULL THEN 'NULL' ELSE 'OK' END,
                   CASE WHEN entry_price IS NULL THEN 'NULL' ELSE 'OK' END
            FROM algo_positions
            WHERE status = 'open'
              AND (current_price IS NULL OR stop_loss_price IS NULL OR entry_price IS NULL)
        ''')
        for row in cursor.fetchall():
            issues.append({
                'severity': 'HIGH',
                'category': 'POSITION_MISSING_FIELDS',
                'item': row[0],
                'detail': f'current_price={row[2]}, stop={row[3]}, entry={row[4]}'
            })

        # 5. Orphaned trades (no matching position)
        cursor.execute('''
            SELECT DISTINCT t.symbol, COUNT(t.trade_id) as trade_count
            FROM algo_trades t
            WHERE t.status = 'open'
              AND NOT EXISTS (SELECT 1 FROM algo_positions p WHERE p.symbol = t.symbol AND p.status = 'open')
            GROUP BY t.symbol
        ''')
        for row in cursor.fetchall():
            issues.append({
                'severity': 'MEDIUM',
                'category': 'ORPHANED_TRADES',
                'item': row[0],
                'detail': f'{row[1]} open trades with no matching position'
            })

        # 6. Position-signal misalignment
        cursor.execute('''
            SELECT p.symbol
            FROM algo_positions p
            WHERE p.status = 'open'
              AND NOT EXISTS (
                SELECT 1 FROM algo_signals s
                WHERE s.symbol = p.symbol
                  AND s.signal_date >= NOW()::date - 30
              )
        ''')
        missing_signals = cursor.fetchall()
        if missing_signals:
            issues.append({
                'severity': 'MEDIUM',
                'category': 'POSITION_NO_RECENT_SIGNAL',
                'item': f'{len(missing_signals)} positions',
                'detail': f'Open positions without signals in last 30 days: {[r[0] for r in missing_signals[:5]]}'
            })

    return issues

def check_orchestrator_runs():
    """Find recurring orchestrator failures"""
    issues = []

    with DatabaseContext(role='read') as ctx:
        cursor = ctx.connection.cursor()

        # 1. Runs ending in error/halted status
        cursor.execute('''
            SELECT overall_status, COUNT(*) as cnt,
                   MAX(started_at) as last_occurrence
            FROM algo_orchestrator_runs
            WHERE started_at >= NOW() - interval '3 days'
            GROUP BY overall_status
            HAVING overall_status IN ('error', 'halted')
        ''')
        for row in cursor.fetchall():
            issues.append({
                'severity': 'CRITICAL',
                'category': 'ORCH_FAILED_RUNS',
                'item': row[0],
                'detail': f'{row[1]} runs in last 3 days, last: {row[2]}'
            })

        # 2. Specific halt reasons
        cursor.execute('''
            SELECT halt_reason, COUNT(*) as cnt
            FROM algo_orchestrator_runs
            WHERE overall_status IN ('error', 'halted')
              AND started_at >= NOW() - interval '3 days'
            GROUP BY halt_reason
            ORDER BY cnt DESC
            LIMIT 5
        ''')
        for row in cursor.fetchall():
            if row[0]:
                issues.append({
                    'severity': 'HIGH',
                    'category': 'ORCH_HALT_REASON',
                    'item': row[0][:80],
                    'detail': f'Occurred {row[1]} times'
                })

    return issues

def main():
    print('=' * 80)
    print('COMPREHENSIVE ISSUE SCAN')
    print('=' * 80)

    all_issues = []

    print('\n[1/2] Scanning trade data...')
    all_issues.extend(check_trades())

    print('[2/2] Scanning orchestrator runs...')
    all_issues.extend(check_orchestrator_runs())

    # Group by severity
    by_severity = {}
    for issue in all_issues:
        sev = issue['severity']
        if sev not in by_severity:
            by_severity[sev] = []
        by_severity[sev].append(issue)

    # Print results
    for severity in ['CRITICAL', 'HIGH', 'MEDIUM']:
        if severity in by_severity:
            print(f'\n{severity} ({len(by_severity[severity])} issues)')
            print('-' * 80)
            for issue in by_severity[severity][:10]:  # Show first 10
                print(f"  [{issue['category']}] {issue['item']}")
                print(f"      {issue['detail']}")

    total = sum(len(v) for v in by_severity.values())
    print(f'\n\nTOTAL ISSUES: {total}')
    print(f"  CRITICAL: {len(by_severity.get('CRITICAL', []))}")
    print(f"  HIGH: {len(by_severity.get('HIGH', []))}")
    print(f"  MEDIUM: {len(by_severity.get('MEDIUM', []))}")

if __name__ == '__main__':
    main()
