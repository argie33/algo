#!/usr/bin/env python3
"""
Emergency fix for position quantity issues (negative, fractional, unrealistic values).

Detects and fixes positions with:
- Negative quantities (impossible)
- Fractional shares (indicates stock split bug)
- Unrealistic quantities (> 10000)

Usage:
    python scripts/fix_position_quantities.py --dry-run  # Review what would be fixed
    python scripts/fix_position_quantities.py --fix      # Actually make fixes
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext


class PositionQuantityFixer:
    """Fix position quantity issues."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.issues_found = 0
        self.issues_fixed = 0

    def find_problematic_positions(self) -> list:
        """Find positions with quantity issues.

        Returns:
            List of position records with issues
        """
        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                query = """
                SELECT
                    position_id,
                    symbol,
                    quantity,
                    average_cost,
                    entry_date,
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
                ORDER BY entry_date DESC
                """

                cur.execute(query)
                return cur.fetchall()
        except Exception as e:
            if 'does not exist' in str(e).lower():
                print("[INFO] Positions table not found")
                return []
            raise

    def review_trade_history(self, symbol: str, position_id=None) -> dict:
        """Review recent trades for this symbol to understand the issue.

        Returns:
            Dict with trade history analysis
        """
        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                # Get recent trades for this symbol
                query = """
                SELECT
                    symbol,
                    quantity,
                    price,
                    trade_type,
                    execution_time
                FROM trade_log
                WHERE symbol = %s
                ORDER BY execution_time DESC
                LIMIT 10
                """

                cur.execute(query, (symbol,))
                trades = cur.fetchall()

                if trades:
                    total_bought = sum(t['quantity'] for t in trades if t['trade_type'] == 'BUY')
                    total_sold = sum(t['quantity'] for t in trades if t['trade_type'] == 'SELL')
                    return {
                        'total_trades': len(trades),
                        'total_bought': total_bought,
                        'total_sold': total_sold,
                        'expected_qty': total_bought - total_sold,
                        'last_trade': trades[0]['execution_time'] if trades else None
                    }
                else:
                    return {'total_trades': 0, 'expected_qty': 0}
        except:
            # Trade log might not exist
            return {}

    def fix_negative_quantity(self, position_id, symbol: str, quantity: float) -> bool:
        """Fix negative quantity by closing the position.

        Args:
            position_id: The position to close
            symbol: Stock symbol
            quantity: Current (negative) quantity

        Returns:
            True if fixed successfully
        """
        print(f"    Action: Close position (was negative: {quantity})")

        if self.dry_run:
            return True

        try:
            with DatabaseContext('write', timeout=10, enable_correlation_tracking=False) as cur:
                cur.execute("""
                    UPDATE positions
                    SET status = 'closed', closed_at = NOW()
                    WHERE position_id = %s
                """, (position_id,))
                return True
        except Exception as e:
            print(f"    ERROR: Could not close position: {e}")
            return False

    def fix_fractional_quantity(self, position_id, symbol: str, quantity: float) -> bool:
        """Fix fractional shares by rounding.

        Stock splits can cause fractional shares. This rounds to nearest integer.

        Args:
            position_id: The position to fix
            symbol: Stock symbol
            quantity: Current (fractional) quantity

        Returns:
            True if fixed successfully
        """
        rounded_qty = round(quantity)
        print(f"    Action: Round {quantity} -> {rounded_qty} shares")

        if self.dry_run:
            return True

        try:
            with DatabaseContext('write', timeout=10, enable_correlation_tracking=False) as cur:
                cur.execute("""
                    UPDATE positions
                    SET quantity = %s, updated_at = NOW()
                    WHERE position_id = %s
                """, (rounded_qty, position_id))
                return True
        except Exception as e:
            print(f"    ERROR: Could not fix fractional shares: {e}")
            return False

    def fix_unrealistic_quantity(self, position_id, symbol: str, quantity: float) -> bool:
        """Fix unrealistic quantity (> 10000 for normal stocks).

        These are likely data corruption. Review trade history to determine correct amount.

        Args:
            position_id: The position to fix
            symbol: Stock symbol
            quantity: Current (unrealistic) quantity

        Returns:
            True if fixed successfully
        """
        # Review trade history
        history = self.review_trade_history(symbol, position_id)

        if history.get('expected_qty'):
            print(f"    Action: Correct to expected quantity {history['expected_qty']} (based on trades)")
            target_qty = history['expected_qty']
        else:
            print(f"    Action: MANUAL REVIEW REQUIRED")
            print(f"      Current: {quantity} (unrealistic)")
            print(f"      Trade history: {history}")
            return False  # Don't auto-fix if we can't determine correct amount

        if self.dry_run:
            return True

        try:
            with DatabaseContext('write', timeout=10, enable_correlation_tracking=False) as cur:
                cur.execute("""
                    UPDATE positions
                    SET quantity = %s, updated_at = NOW()
                    WHERE position_id = %s
                """, (target_qty, position_id))
                return True
        except Exception as e:
            print(f"    ERROR: Could not fix unrealistic quantity: {e}")
            return False

    def process_issues(self, issues: list) -> int:
        """Process found issues.

        Returns:
            Count of issues fixed
        """
        if not issues:
            print("No position quantity issues found")
            return 0

        print(f"Found {len(issues)} position(s) with issues:")
        print()

        fixed_count = 0
        for issue in issues:
            self.issues_found += 1
            print(f"Position: {issue['symbol']} (qty={issue['quantity']})")
            print(f"  Issue: {issue['issue_type']}")
            print(f"  ID: {issue['position_id']}")

            if issue['issue_type'] == 'NEGATIVE':
                if self.fix_negative_quantity(issue['position_id'], issue['symbol'], issue['quantity']):
                    self.issues_fixed += 1
                    fixed_count += 1
            elif issue['issue_type'] == 'FRACTIONAL':
                if self.fix_fractional_quantity(issue['position_id'], issue['symbol'], issue['quantity']):
                    self.issues_fixed += 1
                    fixed_count += 1
            elif issue['issue_type'] == 'UNREALISTIC':
                if self.fix_unrealistic_quantity(issue['position_id'], issue['symbol'], issue['quantity']):
                    self.issues_fixed += 1
                    fixed_count += 1
            print()

        return fixed_count

    def run(self) -> int:
        """Run position quantity fixes.

        Returns:
            Exit code (0 = success)
        """
        mode = "DRY-RUN" if self.dry_run else "FIX"
        print(f"Position Quantity Fixer - {mode} MODE")
        print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
        print("=" * 60)
        print()

        try:
            issues = self.find_problematic_positions()
            self.process_issues(issues)

            print("=" * 60)
            print(f"SUMMARY: {self.issues_found} issue(s) found, {self.issues_fixed} fixed")

            if self.dry_run:
                print("\nTo apply fixes, run:")
                print("  python scripts/fix_position_quantities.py --fix")

            return 0 if self.issues_fixed >= self.issues_found else 1

        except Exception as e:
            print(f"ERROR: {e}")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description='Fix position quantity issues (negative, fractional, unrealistic)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview fixes without making changes (default)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Actually apply the fixes'
    )

    args = parser.parse_args()

    # Determine mode
    dry_run = not args.fix

    if args.fix:
        print("WARNING: This will modify position data. Please review carefully.")
        response = input("Type 'YES' to confirm: ").strip().upper()
        if response != 'YES':
            print("Cancelled.")
            return 1

    fixer = PositionQuantityFixer(dry_run=dry_run)
    exit_code = fixer.run()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
