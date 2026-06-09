#!/usr/bin/env python3
"""
Position Sync Checker - Verify algo_trades and algo_positions alignment.

This utility checks that open positions in the database correctly match
the open trades in algo_trades. It identifies:
  - Orphaned positions (in algo_positions but not in algo_trades)
  - Missing positions (in algo_trades but not in algo_positions)
  - Stale positions (marked open but trade is closed)
  - Quantity mismatches

Usage:
  from utils.position_sync_checker import PositionSyncChecker
  checker = PositionSyncChecker()
  report = checker.check_consistency()
  print(report['summary'])

This is a READ-ONLY diagnostic tool. It reports issues but doesn't auto-fix.
"""

import logging
from datetime import datetime, timezone
from utils.database_context import DatabaseContext
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class PositionSyncChecker:
    """Check data consistency between algo_trades and algo_positions."""

    def check_consistency(self) -> Dict[str, Any]:
        """Run full consistency check. Returns report dict."""
        with DatabaseContext('read') as cur:
            return self._do_check(cur)

    def _do_check(self, cur) -> Dict[str, Any]:
        """Perform consistency checks against database."""
        issues = []

        # 1. Check for orphaned positions (exist in positions table but no matching trade)
        cur.execute("""
            SELECT ap.position_id, ap.symbol, ap.status, ap.quantity
            FROM algo_positions ap
            WHERE NOT EXISTS (
                SELECT 1 FROM algo_trades at
                WHERE at.symbol = ap.symbol
                  AND at.status IN ('open', 'filled', 'partially_filled', 'active')
            )
            AND ap.status IN ('open', 'partial', 'pending_close')
        """)
        orphaned = cur.fetchall()
        if orphaned:
            issues.append({
                'type': 'ORPHANED_POSITIONS',
                'severity': 'HIGH',
                'count': len(orphaned),
                'details': [
                    f"{sym}: {pos_id} qty={qty} status={st}"
                    for pos_id, sym, st, qty in orphaned
                ]
            })

        # 2. Check for stale positions (marked open but trade is closed)
        cur.execute("""
            SELECT ap.position_id, ap.symbol, ap.status, at.status as trade_status
            FROM algo_positions ap
            JOIN algo_trades at ON at.symbol = ap.symbol
            WHERE ap.status IN ('open', 'partial', 'pending_close')
              AND at.status IN ('closed', 'cancelled', 'orphaned')
        """)
        stale = cur.fetchall()
        if stale:
            issues.append({
                'type': 'STALE_POSITIONS',
                'severity': 'MEDIUM',
                'count': len(stale),
                'details': [
                    f"{sym}: {pos_id} pos_status={ps} but trade_status={ts}"
                    for pos_id, sym, ps, ts in stale
                ]
            })

        # 3. Check for missing positions (trade is open but no position record)
        cur.execute("""
            SELECT at.trade_id, at.symbol, at.entry_quantity
            FROM algo_trades at
            WHERE at.status IN ('open', 'filled', 'partially_filled', 'active')
              AND (at.exit_date IS NULL OR at.exit_date > CURRENT_DATE - 1)
              AND NOT EXISTS (
                  SELECT 1 FROM algo_positions ap
                  WHERE ap.symbol = at.symbol AND ap.status IN ('open', 'partial', 'pending_close')
              )
        """)
        missing = cur.fetchall()
        if missing:
            issues.append({
                'type': 'MISSING_POSITIONS',
                'severity': 'HIGH',
                'count': len(missing),
                'details': [
                    f"{sym}: {tid} qty={qty}"
                    for tid, sym, qty in missing
                ]
            })

        # 4. Quantity check (for positions with multiple entries/pyramiding)
        cur.execute("""
            SELECT ap.symbol, ap.quantity, SUM(at.entry_quantity) as total_entry_qty,
                   COUNT(*) as trade_count
            FROM algo_positions ap
            JOIN algo_trades at ON at.symbol = ap.symbol
            WHERE ap.status IN ('open', 'partial', 'pending_close')
              AND at.status IN ('open', 'filled', 'partially_filled', 'active')
            GROUP BY ap.symbol, ap.quantity
            HAVING ap.quantity != SUM(at.entry_quantity)
        """)
        qty_mismatch = cur.fetchall()
        if qty_mismatch:
            issues.append({
                'type': 'QUANTITY_MISMATCH',
                'severity': 'MEDIUM',
                'count': len(qty_mismatch),
                'details': [
                    f"{sym}: position_qty={pq} but sum(trade_qty)={teq} ({tc} trades)"
                    for sym, pq, teq, tc in qty_mismatch
                ]
            })

        # 5. Summary counts
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('open', 'partial', 'pending_close')) as positions_open,
                COUNT(*) FILTER (WHERE status = 'closed') as positions_closed,
                COUNT(*) FILTER (WHERE status = 'orphaned') as positions_orphaned
            FROM algo_positions
        """)
        pos_counts = cur.fetchone()
        pos_open, pos_closed, pos_orphaned = pos_counts if pos_counts else (0, 0, 0)

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('open', 'filled', 'partially_filled', 'active')) as trades_open,
                COUNT(*) FILTER (WHERE status = 'closed') as trades_closed,
                COUNT(*) FILTER (WHERE status = 'cancelled') as trades_cancelled
            FROM algo_trades
        """)
        trade_counts = cur.fetchone()
        trades_open, trades_closed, trades_cancelled = trade_counts if trade_counts else (0, 0, 0)

        # Build report
        is_consistent = len(issues) == 0
        summary = f"""
== POSITION SYNC CONSISTENCY CHECK ==
{datetime.now(timezone.utc).isoformat()}

STATUS: {'OK - CONSISTENT' if is_consistent else 'ISSUES FOUND'}

POSITIONS TABLE:
  - Open/Partial/Pending Close: {pos_open}
  - Closed: {pos_closed}
  - Orphaned: {pos_orphaned}

TRADES TABLE:
  - Open/Active: {trades_open}
  - Closed: {trades_closed}
  - Cancelled: {trades_cancelled}

ISSUES FOUND: {len(issues)}
"""
        if issues:
            summary += "\n"
            for i, issue in enumerate(issues, 1):
                summary += f"\n{i}. [{issue['severity']}] {issue['type']} ({issue['count']} found)\n"
                for detail in issue['details'][:3]:
                    summary += f"   - {detail}\n"
                if len(issue['details']) > 3:
                    summary += f"   ... and {len(issue['details']) - 3} more\n"

        return {
            'summary': summary,
            'is_consistent': is_consistent,
            'issues': issues,
            'counts': {
                'positions_open': pos_open,
                'positions_closed': pos_closed,
                'trades_open': trades_open,
                'trades_closed': trades_closed
            }
        }

def main():
    """Run checker and print report."""
    checker = PositionSyncChecker()
    report = checker.check_consistency()
    print(report['summary'])
    return 0 if report['is_consistent'] else 1

if __name__ == '__main__':
    exit(main())
