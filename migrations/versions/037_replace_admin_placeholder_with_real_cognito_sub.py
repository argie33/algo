"""Replace admin-user placeholder with real Cognito sub.

This migration updates all database records from the hardcoded 'admin-user'
placeholder to the real admin user's Cognito sub.

IMPORTANT: Set ADMIN_COGNITO_SUB environment variable before running:
    $env:ADMIN_COGNITO_SUB = "us-east-1_XXXXX:12345678-1234-1234-1234-123456789abc"

Get the real admin Cognito sub from AWS Cognito console:
1. Go to AWS Cognito → User pools → algo-trading
2. Find the admin user (email: edgebrookecapital@gmail.com)
3. Copy the "Sub" value
4. Set it as ADMIN_COGNITO_SUB environment variable
5. Run migration

Tables affected:
- algo_portfolio_snapshots
- algo_trade_adds
- algo_trades (if applicable)
- Any other tables with cognito_sub column using 'admin-user'
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Replace admin-user placeholder with real Cognito sub"


def up():
    """Update all 'admin-user' references to real admin Cognito sub."""
    # Get real admin Cognito sub from environment
    admin_cognito_sub = os.getenv('ADMIN_COGNITO_SUB', '').strip()

    if not admin_cognito_sub:
        raise ValueError(
            "ADMIN_COGNITO_SUB environment variable not set!\n"
            "Set it to the real admin user's Cognito sub from AWS Cognito console:\n"
            "  $env:ADMIN_COGNITO_SUB = 'us-east-1_XXXXX:12345678-1234-1234-1234-123456789abc'\n"
            "Then run: python -m alembic upgrade head"
        )

    if admin_cognito_sub == 'admin-user':
        raise ValueError(
            "ADMIN_COGNITO_SUB should be the REAL Cognito sub, not the placeholder 'admin-user'\n"
            "Get the real sub from AWS Cognito console → User pools → algo-trading → admin user\n"
            "Copy the 'Sub' value and set it as the environment variable"
        )

    with DatabaseContext('write') as cur:
        # Tables to update: find all columns named cognito_sub with 'admin-user'
        tables_to_update = [
            'algo_portfolio_snapshots',
            'algo_trade_adds',
            'algo_trades',
            'algo_positions',
        ]

        for table_name in tables_to_update:
            try:
                # Check if table exists
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table_name,)
                )
                if not cur.fetchone():
                    continue  # Table doesn't exist, skip

                # Update all 'admin-user' to real Cognito sub
                cur.execute(
                    f"UPDATE {table_name} SET cognito_sub = %s WHERE cognito_sub = 'admin-user'",
                    (admin_cognito_sub,)
                )
                rows_updated = cur.rowcount
                if rows_updated > 0:
                    print(f"  ✓ {table_name}: {rows_updated} rows updated")
            except Exception as e:
                print(f"  ✗ {table_name}: {e}")
                raise

        print(f"\nAdmin Cognito sub replaced in all tables: {admin_cognito_sub}")


def down():
    """Revert back to 'admin-user' placeholder (for rollback only)."""
    # This is a destructive operation - we're reverting to a placeholder
    # Only do this if migration failed and needs rollback
    with DatabaseContext('write') as cur:
        tables_to_revert = [
            'algo_portfolio_snapshots',
            'algo_trade_adds',
            'algo_trades',
            'algo_positions',
        ]

        for table_name in tables_to_revert:
            try:
                cur.execute(
                    f"SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table_name,)
                )
                if not cur.fetchone():
                    continue

                # Revert to placeholder
                cur.execute(
                    f"""
                    UPDATE {table_name}
                    SET cognito_sub = 'admin-user'
                    WHERE cognito_sub IS NOT NULL AND cognito_sub != 'admin-user'
                    """,
                    ()
                )
                rows_reverted = cur.rowcount
                if rows_reverted > 0:
                    print(f"  ✓ {table_name}: {rows_reverted} rows reverted to placeholder")
            except Exception as e:
                print(f"  ✗ {table_name}: {e}")
                raise

        print("\nReverted to 'admin-user' placeholder (rollback complete)")
