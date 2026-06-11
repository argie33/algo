#!/usr/bin/env python3
"""
Position Sync Checker - Verify algo_trades is the single source of truth.

This utility verifies that algo_trades has consistent, valid position data.
Since the dashboard and API now derive positions on-the-fly from algo_trades
(not from the algo_positions cache table), this checker validates:
  - Open trades have valid entry prices and quantities
  - Closed trades have valid exit dates and P&L metrics
  - No duplicate symbols in open trades (distinct on symbol)
  - Data integrity of core trade fields

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

        # 1. Check for trades with missing required entry fields
        cur.execute("""
            SELECT trade_id, symbol, status
            FROM algo_trades
            WHERE status IN ('open', 'filled', 'partially_filled', 'active')
              AND (entry_price IS NULL OR entry_quantity IS NULL OR entry_time IS NULL)
        """)
        invalid_entry = cur.fetchall()
        if invalid_entry:
            issues.append({
                'type': 'INVALID_ENTRY_DATA',
                'severity': 'HIGH',
                'count': len(invalid_entry),
                'details': [
                    f"{tid}: {sym} missing entry fields"
                    for tid, sym, st in invalid_entry[:3]
                ]
            })

        # 2. Check for trades with negative prices
        cur.execute("""
            SELECT trade_id, symbol, entry_price, stop_loss_price
            FROM algo_trades
            WHERE status IN ('open', 'filled', 'partially_filled', 'active')
              AND (entry_price <= 0 OR stop_loss_price <= 0)
        """)
        negative_prices = cur.fetchall()
        if negative_prices:
            issues.append({
                'type': 'NEGATIVE_PRICES',
                'severity': 'HIGH',
                'count': len(negative_prices),
                'details': [
                    f"{tid}: {sym} entry={ep} stop={sp}"
                    for tid, sym, ep, sp in negative_prices[:3]
                ]
            })

        # 3. Check for duplicate open symbols (should be DISTINCT ON symbol)
        cur.execute("""
            SELECT symbol, COUNT(*) as count
            FROM algo_trades
            WHERE status IN ('open', 'filled', 'partially_filled', 'active')
            GROUP BY symbol
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()
        if duplicates:
            issues.append({
                'type': 'DUPLICATE_OPEN_POSITIONS',
                'severity': 'MEDIUM',
                'count': len(duplicates),
                'details': [
                    f"{sym}: {cnt} open trades"
                    for sym, cnt in duplicates[:3]
                ]
            })

        # 4. Check for closed trades missing exit data
        cur.execute("""
            SELECT trade_id, symbol
            FROM algo_trades
            WHERE status = 'closed'
              AND (exit_date IS NULL OR exit_price IS NULL)
        """)
        missing_exit = cur.fetchall()
        if missing_exit:
            issues.append({
                'type': 'INCOMPLETE_CLOSED_TRADES',
                'severity': 'MEDIUM',
                'count': len(missing_exit),
                'details': [
                    f"{tid}: {sym} missing exit data"
                    for tid, sym in missing_exit[:3]
                ]
            })

        # 5. Summary counts from algo_trades (single source of truth)
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
== ALGO_TRADES DATA INTEGRITY CHECK ==
{datetime.now(timezone.utc).isoformat()}

ARCHITECTURE: algo_trades is single source of truth
- API and dashboard derive positions on-the-fly from algo_trades
- algo_positions table is no longer used for position lookups

STATUS: {'OK - CONSISTENT' if is_consistent else 'ISSUES FOUND'}

TRADES TABLE (Single Source of Truth):
  - Open/Active: {trades_open}
  - Closed: {trades_closed}
  - Cancelled: {trades_cancelled}

DATA INTEGRITY CHECKS: {len(issues)} issues found
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
                'trades_open': trades_open,
                'trades_closed': trades_closed,
                'trades_cancelled': trades_cancelled
            }
        }

def main():
    """Run checker and log report."""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    checker = PositionSyncChecker()
    report = checker.check_consistency()
    logger.info(report['summary'])
    return 0 if report['is_consistent'] else 1

if __name__ == '__main__':
    exit(main())
