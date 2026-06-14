#!/usr/bin/env python3
"""Algo Daily Metrics Loader - Portfolio stats and execution summary (Market-wide compute)."""
import sys
import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class AlgoMetricsDailyLoader(OptimalLoader):
    """Compute and store daily algo performance metrics."""
    table_name = "algo_metrics_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute daily algo metrics from audit log."""
        try:
            from datetime import datetime, timezone, timedelta as td
            # CRITICAL: Use ET (trading hours), not UTC, to determine date.
            # FIXED: Use ZoneInfo instead of hardcoded -5 offset to handle EDT properly.
            from zoneinfo import ZoneInfo
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            run_date = now_et.date()

            with DatabaseContext('read') as cur:
                # Compute portfolio stats from algo_audit_log
                cur.execute("""
                    SELECT
                        DATE(created_at) as trading_date,
                        COUNT(*) as total_actions,
                        SUM(CASE WHEN action_type = 'BUY' THEN 1 ELSE 0 END) as entries,
                        SUM(CASE WHEN action_type = 'SELL' THEN 1 ELSE 0 END) as exits,
                        AVG(CAST(details->>'score' AS FLOAT)) as avg_signal_score
                    FROM algo_audit_log
                    WHERE DATE(created_at) = %s
                    GROUP BY DATE(created_at)
                """, (run_date,))

                row = cur.fetchone()
                if not row:
                    logger.info(f"No metrics available for {run_date}")
                    return None

                return [{
                    'date': row[0],
                    'total_actions': row[1],
                    'entries': row[2],
                    'exits': row[3],
                    'avg_signal_score': float(row[4]) if row[4] else None,
                }]

        except Exception as e:
            logger.error(f"Failed to compute daily metrics: {e}")
            return None

def main():
    loader = AlgoMetricsDailyLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} daily metrics computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No metrics computed")
        return 0

if __name__ == "__main__":
    sys.exit(main())
