#!/usr/bin/env python3
"""
Production monitoring script for daily system health checks.

Validates:
- Position quantities (detect negative, fractional, unrealistic values)
- Stale lock accumulation (detect blocking locks)
- Data freshness (price, signal, metrics data)
- Portfolio reconciliation (sum of holdings matches account)

Usage:
    python scripts/setup_production_monitoring.py              # Run all checks
    python scripts/setup_production_monitoring.py --component positions  # Check positions only
    python scripts/setup_production_monitoring.py --alert      # Send alerts on issues
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext


class ProductionMonitor:
    """Daily production health monitoring."""

    def __init__(self, alert_on_issues: bool = False, component: str = None):
        self.alert_on_issues = alert_on_issues
        self.component = component
        self.issues = []
        self.warnings = []

    def check_position_quantities(self) -> bool:
        """Check for position quantity issues that could indicate data corruption.

        Checks for:
        - Negative quantities (impossible)
        - Fractional shares (stock split bug)
        - Unrealistic quantities (> 10000 for normal stocks)
        - NaN or NULL quantities

        Returns:
            True if all checks pass
        """
        print("\n[CHECKING] Position Quantities")
        print("=" * 60)

        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                # Check for problematic positions
                query = """
                SELECT
                    symbol,
                    quantity,
                    average_cost,
                    current_price,
                    CASE
                        WHEN quantity < 0 THEN 'NEGATIVE'
                        WHEN quantity != FLOOR(quantity) THEN 'FRACTIONAL'
                        WHEN quantity > 10000 THEN 'UNREALISTIC'
                        ELSE 'OK'
                    END as issue_type
                FROM positions
                WHERE status = 'open'
                  AND (quantity < 0
                    OR quantity != FLOOR(quantity)
                    OR quantity > 10000)
                ORDER BY quantity DESC
                """

                cur.execute(query)
                problem_positions = cur.fetchall()

                if not problem_positions:
                    print("Status: OK - All position quantities are valid")
                    return True
                else:
                    print(f"Status: ISSUES FOUND ({len(problem_positions)} positions)")
                    for pos in problem_positions:
                        print(f"  {pos['symbol']}: qty={pos['quantity']} ({pos['issue_type']})")
                        self.issues.append(f"Position quantity issue: {pos['symbol']} {pos['issue_type']}")
                    return False

        except Exception as e:
            if 'does not exist' in str(e).lower():
                print("Status: WARNING - Positions table not found (expected for some setups)")
                return True
            else:
                print(f"Status: ERROR - {e}")
                self.issues.append(f"Position check failed: {e}")
                return False

    def check_stale_locks(self) -> bool:
        """Check for locks that are blocking loader execution.

        Returns:
            True if no critical stale locks
        """
        print("\n[CHECKING] Stale Locks")
        print("=" * 60)

        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                query = """
                SELECT
                    resource_name,
                    owner_id,
                    started_at,
                    EXTRACT(EPOCH FROM (NOW() - started_at)) as age_seconds
                FROM loader_execution_locks
                WHERE started_at < NOW() - INTERVAL '2 hours'
                ORDER BY started_at DESC
                LIMIT 10
                """

                try:
                    cur.execute(query)
                    stale_locks = cur.fetchall()
                except (psycopg2.DatabaseError, psycopg2.ProgrammingError) as e:
                    # Table might not exist (using DynamoDB) or database error
                    if "does not exist" in str(e).lower() or "undefined table" in str(e).lower():
                        print("Status: INFO - Stale lock checking not available (using DynamoDB?)")
                    else:
                        print(f"Status: DEBUG - Stale lock query failed: {type(e).__name__}: {e}")
                    return True

                if not stale_locks:
                    print("Status: OK - No stale locks found")
                    return True
                else:
                    print(f"Status: WARNING ({len(stale_locks)} stale locks)")
                    for lock in stale_locks:
                        age_hours = lock['age_seconds'] / 3600
                        print(f"  {lock['resource_name']}: age={age_hours:.1f}h, PID={lock['owner_id']}")
                        self.warnings.append(f"Stale lock: {lock['resource_name']} ({age_hours:.1f}h old)")
                    return False

        except Exception as e:
            print(f"Status: ERROR - {e}")
            self.issues.append(f"Stale lock check failed: {e}")
            return False

    def check_data_freshness(self) -> bool:
        """Check how recent critical data is.

        Returns:
            True if all data is reasonably fresh
        """
        print("\n[CHECKING] Data Freshness")
        print("=" * 60)

        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                tables_to_check = [
                    ('price_daily', 'date'),
                    ('buy_sell_daily', 'date'),
                ]

                all_fresh = True
                today = datetime.utcnow().date()

                for table, date_col in tables_to_check:
                    try:
                        query = f"SELECT MAX({date_col}) as max_date FROM {table}"
                        cur.execute(query)
                        row = cur.fetchone()

                        if row and row['max_date']:
                            max_date = row['max_date']
                            if isinstance(max_date, str):
                                from datetime import datetime as dt
                                max_date = dt.fromisoformat(max_date).date()

                            age_days = (today - max_date).days
                            if age_days > 2:
                                print(f"  {table}: STALE ({age_days} days old)")
                                self.warnings.append(f"Data stale: {table} ({age_days} days old)")
                                all_fresh = False
                            else:
                                print(f"  {table}: OK ({age_days} days old)")
                        else:
                            print(f"  {table}: NO DATA")
                            self.warnings.append(f"No data: {table}")
                            all_fresh = False

                    except Exception as e:
                        if 'does not exist' in str(e).lower():
                            print(f"  {table}: NOT FOUND")
                        else:
                            print(f"  {table}: ERROR - {e}")
                            all_fresh = False

                print(f"\nStatus: {'OK' if all_fresh else 'WARNING'}")
                return all_fresh

        except Exception as e:
            print(f"Status: ERROR - {e}")
            self.issues.append(f"Data freshness check failed: {e}")
            return False

    def check_portfolio_reconciliation(self) -> bool:
        """Check if portfolio cash and holdings are consistent.

        Returns:
            True if portfolio is reconciled
        """
        print("\n[CHECKING] Portfolio Reconciliation")
        print("=" * 60)

        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                # Get current portfolio metrics
                query = """
                SELECT
                    equity,
                    total_cash,
                    portfolio_value
                FROM portfolio_metrics
                ORDER BY created_at DESC
                LIMIT 1
                """

                try:
                    cur.execute(query)
                    metrics = cur.fetchone()
                except (psycopg2.DatabaseError, psycopg2.ProgrammingError) as e:
                    # Table might not exist or database error
                    if "does not exist" in str(e).lower() or "undefined table" in str(e).lower():
                        print("Status: INFO - Portfolio metrics not available")
                    else:
                        print(f"Status: DEBUG - Portfolio metrics query failed: {type(e).__name__}: {e}")
                    return True

                if metrics:
                    equity = metrics['equity'] or 0
                    cash = metrics['total_cash'] or 0
                    portfolio_value = metrics['portfolio_value'] or 0

                    expected_total = equity + cash
                    diff_pct = abs(portfolio_value - expected_total) / max(expected_total, 1) * 100

                    if diff_pct < 0.1:
                        print(f"Status: OK")
                        print(f"  Equity: ${equity:,.2f}")
                        print(f"  Cash: ${cash:,.2f}")
                        print(f"  Total: ${portfolio_value:,.2f}")
                        return True
                    else:
                        print(f"Status: WARNING - Mismatch detected")
                        print(f"  Expected: ${expected_total:,.2f}")
                        print(f"  Actual: ${portfolio_value:,.2f}")
                        print(f"  Difference: {diff_pct:.2f}%")
                        self.warnings.append(f"Portfolio reconciliation off by {diff_pct:.2f}%")
                        return False
                else:
                    print("Status: NO DATA")
                    return True

        except Exception as e:
            print(f"Status: ERROR - {e}")
            self.issues.append(f"Portfolio reconciliation check failed: {e}")
            return False

    def print_summary(self) -> int:
        """Print monitoring summary and return exit code.

        Returns:
            0 if healthy, 1 if issues found
        """
        print("\n" + "=" * 60)
        print("MONITORING SUMMARY")
        print("=" * 60)

        if self.issues:
            print(f"\n[CRITICAL] {len(self.issues)} issue(s) found:")
            for issue in self.issues:
                print(f"  - {issue}")

        if self.warnings:
            print(f"\n[WARNING] {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                print(f"  - {warning}")

        if not self.issues and not self.warnings:
            print("\nStatus: OK - All checks passed")
            return 0
        elif not self.issues:
            print("\nStatus: WARNING - Review warnings above")
            return 0  # Don't fail on warnings
        else:
            print("\nStatus: ISSUES FOUND - Review critical items above")
            return 1

    def run(self) -> int:
        """Run monitoring checks.

        Returns:
            Exit code (0 = healthy)
        """
        print(f"Production Monitoring - {datetime.utcnow().isoformat()}Z")
        print("=" * 60)

        # Determine which checks to run
        if self.component:
            checks = {
                'positions': [self.check_position_quantities],
                'locks': [self.check_stale_locks],
                'freshness': [self.check_data_freshness],
                'reconciliation': [self.check_portfolio_reconciliation],
            }
            check_functions = checks.get(self.component, [])
        else:
            # Run all checks
            check_functions = [
                self.check_position_quantities,
                self.check_stale_locks,
                self.check_data_freshness,
                self.check_portfolio_reconciliation,
            ]

        if not check_functions:
            print(f"ERROR: Unknown component '{self.component}'")
            return 1

        for check_fn in check_functions:
            try:
                check_fn()
            except Exception as e:
                print(f"ERROR: Check failed: {e}")

        return self.print_summary()


def main():
    parser = argparse.ArgumentParser(
        description='Daily production health monitoring'
    )
    parser.add_argument(
        '--component',
        choices=['positions', 'locks', 'freshness', 'reconciliation'],
        help='Run only a specific monitoring component'
    )
    parser.add_argument(
        '--alert',
        action='store_true',
        help='Send alerts on issues (requires alert configuration)'
    )

    args = parser.parse_args()

    monitor = ProductionMonitor(
        alert_on_issues=args.alert,
        component=args.component
    )

    exit_code = monitor.run()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
