#!/usr/bin/env python3
"""Quick check: are metrics tables fresh?"""

from datetime import datetime, timedelta, timezone
from utils.db import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT
            COALESCE(MAX(updated_at), NOW() - INTERVAL '48 hours') as latest_growth,
            (SELECT COALESCE(MAX(updated_at), NOW() - INTERVAL '48 hours')
             FROM quality_metrics) as latest_quality,
            (SELECT COUNT(*) FROM growth_metrics) as growth_count,
            (SELECT COUNT(*) FROM quality_metrics) as quality_count
        FROM growth_metrics
    """)
    row = cur.fetchone()

    now = datetime.now(timezone.utc)
    latest_growth = row[0] if isinstance(row[0], datetime) else now
    latest_quality = row[1] if isinstance(row[1], datetime) else now

    # Ensure tz-aware
    if latest_growth.tzinfo is None:
        latest_growth = latest_growth.replace(tzinfo=timezone.utc)
    if latest_quality.tzinfo is None:
        latest_quality = latest_quality.replace(tzinfo=timezone.utc)

    growth_hours = (now - latest_growth).total_seconds() / 3600
    quality_hours = (now - latest_quality).total_seconds() / 3600

    print(f"Growth metrics:  {growth_hours:.1f}h old ({row[2]} records)")
    print(f"Quality metrics: {quality_hours:.1f}h old ({row[3]} records)")

    if growth_hours > 24 or quality_hours > 24:
        print("⚠️  STALE - metrics pipeline should have run")
    else:
        print("✓ FRESH - metrics pipeline succeeded")
