#!/usr/bin/env python3
"""Algo Daily Metrics Loader - Portfolio stats and execution summary (Market-wide compute)."""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AlgoMetricsDailyLoader(OptimalLoader):
    """Compute and store daily algo performance metrics."""

    table_name = "algo_metrics_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:
        """Compute daily algo metrics from audit log."""
        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            run_date = now_et.date()

            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        DATE(created_at) as trading_date,
                        COUNT(*) as total_actions,
                        SUM(CASE WHEN action_type = 'BUY' THEN 1 ELSE 0 END) as entries,
                        SUM(CASE WHEN action_type = 'SELL' THEN 1 ELSE 0 END) as exits,
                        AVG(CAST(details->>'score' AS FLOAT)) as avg_signal_score
                    FROM algo_audit_log
                    WHERE DATE(created_at) = %s
                    GROUP BY DATE(created_at)
                """,
                    (run_date,),
                )

                row = cur.fetchone()
                if not row:
                    raise RuntimeError(
                        f"[ALGO_METRICS] No audit log data found for {run_date}. "
                        "Cannot compute performance metrics without trade data."
                    )

                return [
                    {
                        "date": row[0],
                        "total_actions": row[1],
                        "entries": row[2],
                        "exits": row[3],
                        "avg_signal_score": float(row[4]) if row[4] else None,
                    }
                ]

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[ALGO_METRICS] Failed to compute daily metrics: {e}. Cannot proceed without performance tracking."
            ) from e


if __name__ == "__main__":
    sys.exit(run_loader(AlgoMetricsDailyLoader, global_mode=True))
