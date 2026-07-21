#!/usr/bin/env python3
"""Algo Daily Metrics Loader - Portfolio stats and execution summary (Market-wide compute)."""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class AlgoMetricsDailyLoader(OptimalLoader):
    table_name = "algo_metrics_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        run_date = now_et.date()

        try:
            with DatabaseContext("read") as cur:
                # entries/exits used to be counted via algo_audit_log.action_type =
                # 'BUY'/'SELL' - those literal values are never written anywhere in this
                # codebase (real trade actions log under names like
                # 'phase_8_entry_execution'/'exit_stop'), so this column pair was silently
                # 0 every day regardless of real trading activity. algo/orchestrator/
                # phase9_reconciliation.py's _update_algo_metrics already fixed this by
                # counting from algo_trades directly - but that fix only applied there;
                # this loader (a separate scheduled writer to the same
                # `algo_metrics_daily` primary key) kept the old audit_log-based query, so
                # whichever of the two ran later for a given date clobbered the other's
                # entries/exits back to 0 via their shared ON CONFLICT (date) DO UPDATE.
                # Mirror phase9's counting here too so both writers agree regardless of
                # run order.
                cur.execute(
                    """
                    SELECT COUNT(*) as total_actions,
                           AVG(CAST(details->>'score' AS FLOAT)) as avg_signal_score
                    FROM algo_audit_log
                    WHERE DATE(created_at) = %s
                """,
                    (run_date,),
                )
                audit_row = cur.fetchone()

                cur.execute(
                    """
                    SELECT COUNT(*) FILTER (WHERE entry_date = %s) as entries,
                           COUNT(*) FILTER (WHERE exit_date = %s) as exits
                    FROM algo_trades
                """,
                    (run_date, run_date),
                )
                trade_row = cur.fetchone()

                if not audit_row or not trade_row:
                    raise RuntimeError(
                        f"[ALGO_METRICS] No audit log/trade data found for {run_date}. "
                        "Cannot compute performance metrics without trade data."
                    )
                row = (run_date, audit_row[0], trade_row[0], trade_row[1], audit_row[1])

                # VALIDATION: Tuple structure check before unpacking
                expected_fields = 5
                expected_names = ["trading_date", "total_actions", "entries", "exits", "avg_signal_score"]
                if len(row) < expected_fields:
                    logger.error(
                        f"[ALGO_METRICS] Malformed metrics tuple: expected {expected_fields} fields "
                        f"({expected_names}), got {len(row)}. Row data: {row}"
                    )
                    raise ValueError(
                        f"Algo metrics tuple has incorrect structure, expected {expected_fields}+ fields "
                        f"({expected_names}), got {len(row)}"
                    )

                # VALIDATION: Required fields must be present and non-negative
                total_actions = row[1]
                entries = row[2]
                exits = row[3]
                score = row[4]

                # Validate required fields
                if total_actions is None:
                    raise ValueError("total_actions cannot be NULL (required field)")
                if entries is None:
                    raise ValueError("entries cannot be NULL (required field)")
                if exits is None:
                    raise ValueError("exits cannot be NULL (required field)")

                # Validate value ranges
                if total_actions < 0:
                    raise ValueError(f"total_actions must be non-negative, got {total_actions}")
                if entries < 0:
                    raise ValueError(f"entries must be non-negative, got {entries}")
                if exits < 0:
                    raise ValueError(f"exits must be non-negative, got {exits}")

                # Validate logical consistency
                if entries + exits > total_actions:
                    raise ValueError(
                        f"entries ({entries}) + exits ({exits}) cannot exceed total_actions ({total_actions})"
                    )

                # Validate and coerce score
                avg_signal_score = None
                if score is not None:
                    try:
                        avg_signal_score = float(score)
                        if avg_signal_score < 0 or avg_signal_score > 100:
                            raise ValueError(f"avg_signal_score must be 0-100, got {avg_signal_score}")
                    except (ValueError, TypeError) as e:
                        raise ValueError(f"avg_signal_score must be numeric, got {score}") from e

                return [
                    {
                        "date": row[0],
                        "total_actions": total_actions,
                        "entries": entries,
                        "exits": exits,
                        "avg_signal_score": avg_signal_score,
                        "data_unavailable": False,
                        "reason": None,
                    }
                ]

        except (ValueError, ZeroDivisionError, TypeError) as e:
            reason_msg = f"metrics_computation_failed: {e}"
            logger.error(f"[ALGO_METRICS] {reason_msg}")
            return [
                {
                    "date": run_date,
                    "data_unavailable": True,
                    "reason": reason_msg,
                    "reason_type": "loader_failed",
                }
            ]


if __name__ == "__main__":
    sys.exit(run_loader(AlgoMetricsDailyLoader, global_mode=True))
