"""Replace admin-user placeholder with real Cognito sub.

This migration updates all database records from the hardcoded 'admin-user'
placeholder to the real admin user's Cognito sub.

If ADMIN_COGNITO_SUB is not set, this migration skips gracefully and is marked
as applied. Run manually later with the env var set if tables have placeholder rows.

Tables affected:
- algo_portfolio_snapshots
- algo_trade_adds
- algo_trades (if applicable)
- algo_positions
"""

import os

from utils.db.context import DatabaseContext


DESCRIPTION = "Replace admin-user placeholder with real Cognito sub"


def up():
    """Update all 'admin-user' references to real admin Cognito sub."""
    admin_cognito_sub = os.getenv("ADMIN_COGNITO_SUB", "").strip()

    if not admin_cognito_sub or admin_cognito_sub == "admin-user":
        print("  [WARN] ADMIN_COGNITO_SUB not set or is placeholder - skipping.")
        print("  Set ADMIN_COGNITO_SUB to the real Cognito sub and re-run if needed.")
        return

    tables_to_update = [
        "algo_portfolio_snapshots",
        "algo_trade_adds",
        "algo_trades",
        "algo_positions",
    ]

    with DatabaseContext("write") as cur:
        for table_name in tables_to_update:
            try:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table_name,),
                )
                if not cur.fetchone():
                    continue

                cur.execute(
                    "UPDATE "
                    + table_name
                    + " SET cognito_sub = %s WHERE cognito_sub = 'admin-user'",
                    (admin_cognito_sub,),
                )
                rows_updated = cur.rowcount
                if rows_updated > 0:
                    print(
                        "  [OK] "
                        + table_name
                        + ": "
                        + str(rows_updated)
                        + " rows updated"
                    )
            except Exception as e:
                print("  [ERR] " + table_name + ": " + str(e))
                raise

    print("Admin Cognito sub replaced in all tables: " + admin_cognito_sub)


def down():
    """Revert to 'admin-user' placeholder (rollback only)."""
    with DatabaseContext("write") as cur:
        tables_to_revert = [
            "algo_portfolio_snapshots",
            "algo_trade_adds",
            "algo_trades",
            "algo_positions",
        ]

        for table_name in tables_to_revert:
            try:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table_name,),
                )
                if not cur.fetchone():
                    continue

                cur.execute(
                    "UPDATE " + table_name + " SET cognito_sub = 'admin-user'"
                    " WHERE cognito_sub IS NOT NULL AND cognito_sub != 'admin-user'"
                )
                rows_reverted = cur.rowcount
                if rows_reverted > 0:
                    print(
                        "  [OK] "
                        + table_name
                        + ": "
                        + str(rows_reverted)
                        + " rows reverted"
                    )
            except Exception as e:
                print("  [ERR] " + table_name + ": " + str(e))
                raise

    print("Reverted to 'admin-user' placeholder (rollback complete)")
