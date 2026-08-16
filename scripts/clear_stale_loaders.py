#!/usr/bin/env python3
"""Clear stale loader statuses to allow fresh test runs."""

import sys

sys.path.insert(0, ".")

from utils.db.connection import get_db_connection

stale_loaders = [
    "company_info_sec",
    "company_profile",
    "sec_valuations",
    "dividend_data",
    "sec_segment_info",
    "earnings_calendar",
    "current_reports_8k",
    "analyst_upgrade_downgrade",
]

print("Clearing stale loader statuses...")

try:
    conn = get_db_connection()
    cur = conn.cursor()

    for table_name in stale_loaders:
        cur.execute(
            """
            UPDATE data_loader_status
            SET status = 'FAILED',
                error_message = 'Cleared stale status - ready for fresh run',
                last_updated = NOW()
            WHERE table_name = %s
        """,
            (table_name,),
        )

    conn.commit()
    print(f"[OK] Cleared {len(stale_loaders)} stale loader statuses")

    # Verify
    cur.execute(
        """
        SELECT table_name, status
        FROM data_loader_status
        WHERE table_name = ANY(%s)
        ORDER BY table_name
    """,
        (stale_loaders,),
    )

    for row in cur.fetchall():
        print(f"  {row[0]:30} → {row[1]:8}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
