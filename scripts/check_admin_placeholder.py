#!/usr/bin/env python3
"""Check if admin-user placeholder is still in database (should be replaced before production)."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db import DatabaseContext  # noqa: E402

CRITICAL_TABLES = [
    "algo_portfolio_snapshots",
    "algo_trade_adds",
    "algo_trades",
    "algo_positions",
]


def check_admin_placeholder() -> bool:
    """Check if admin-user placeholder exists in any critical tables.

    Returns True if placeholder found (needs fixing), False if all replaced.
    """
    found_placeholder = False

    try:
        with DatabaseContext("read") as cur:
            for table_name in CRITICAL_TABLES:
                # Check if table exists
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table_name,),
                )
                if not cur.fetchone():
                    continue

                # Check for admin-user placeholder
                cur.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE cognito_sub = 'admin-user'",
                )
                count = cur.fetchone()[0] if cur.fetchone() else 0

                if count > 0:
                    print(f"[WARN] Found {count} rows with 'admin-user' placeholder in {table_name}")
                    found_placeholder = True
                else:
                    print(f"[OK] {table_name}: No admin-user placeholder")

    except Exception as e:
        print(f"[ERROR] Failed to check admin-user placeholder: {e}")
        return True  # Assume problem exists if we can't verify

    if found_placeholder:
        print("\n[CRITICAL] Admin-user placeholder still exists in database.")
        print("Set ADMIN_COGNITO_SUB environment variable and run:")
        print("  python -m alembic upgrade head")
        print("Or manually run migration 037_replace_admin_placeholder_with_real_cognito_sub.py")
        return True

    print("\n[OK] All admin-user placeholders have been replaced with real Cognito subs")
    return False


if __name__ == "__main__":
    found = check_admin_placeholder()
    sys.exit(1 if found else 0)
