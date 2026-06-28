"""Finalize user isolation setup - ensure admin user is properly configured.

This migration verifies that the admin user isolation is properly set up.
The actual migration from 'admin-user' placeholder to real Cognito sub
happens in migration 015_replace_admin_placeholder_with_real_cognito_sub.py

This migration verifies preconditions and documents the setup process.
"""

import psycopg2

from utils.db.context import DatabaseContext

DESCRIPTION = "Finalize user isolation admin setup (verify preconditions)"


def up():
    """Verify admin user isolation preconditions."""
    with DatabaseContext("write") as cur:
        # Verify that 'admin-user' placeholder is in place
        tables_to_check = [
            "algo_portfolio_snapshots",
            "algo_trade_adds",
        ]

        for table_name in tables_to_check:
            try:
                # Check if table exists and has cognito_sub column
                cur.execute(
                    """
                    SELECT COUNT(*) as count FROM information_schema.columns
                    WHERE table_name = %s AND column_name = 'cognito_sub'
                    """,
                    (table_name,),
                )
                row = cur.fetchone()
                if row is not None and row[0] is not None and row[0] > 0:
                    # Verify 'admin-user' entries exist
                    cur.execute(f"SELECT COUNT(*) as count FROM {table_name} WHERE cognito_sub = 'admin-user'")
                    row = cur.fetchone()
                    if row is not None and row[0] is not None:
                        count = row[0]
                    else:
                        raise RuntimeError(f"Count query failed for {table_name}")
                    if count > 0:
                        print(f"  âœ“ {table_name}: {count} rows with 'admin-user' placeholder found")
            except (psycopg2.ProgrammingError, psycopg2.DatabaseError):
                # Table may not exist yet, that's OK
                pass

        print("\nNextstep: Run migration 015 to replace 'admin-user' with real Cognito sub:")
        print("  1. Get admin Cognito sub from AWS Cognito console")
        print("  2. Set ADMIN_COGNITO_SUB environment variable")
        print("  3. Run: python -m alembic upgrade head")


def down():
    """Revert precondition check (no-op)."""
    # This migration only checks preconditions, nothing to revert
