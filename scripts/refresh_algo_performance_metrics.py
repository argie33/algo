#!/usr/bin/env python3
"""Refresh algo_performance_metrics from algo_performance_daily.

Keeps the legacy metrics table fresh by syncing latest performance data.
This is run as part of the orchestrator's post-execution cleanup (Phase 9).

Background: algo_performance_metrics is a legacy table from the schema design phase.
The orchestrator now writes to algo_performance_daily instead. This script ensures
the metrics table stays synchronized for any dashboards or external tools that read it.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger

logger = get_logger(__name__)


def refresh_performance_metrics() -> bool:
    """Refresh algo_performance_metrics from daily performance data.

    Returns:
        bool: True if successful, False on error
    """
    try:
        with DatabaseContext("write") as cur:
            logger.info("Refreshing algo_performance_metrics from algo_performance_daily...")

            # Upsert last 30 days of performance data
            cur.execute(
                """
                INSERT INTO algo_performance_metrics (
                    metric_date,
                    total_trades, winning_trades, losing_trades,
                    win_rate_pct, profit_factor,
                    sharpe_ratio, sortino_ratio, max_drawdown_pct, calmar_ratio,
                    expectancy, avg_win_r, avg_loss_r, avg_win_pct, avg_loss_pct,
                    updated_at
                )
                SELECT
                    report_date as metric_date,
                    total_trades,
                    num_wins,
                    num_losses,
                    win_rate_50t,
                    profit_factor,
                    rolling_sharpe_252d,
                    rolling_sortino_252d,
                    max_drawdown_pct,
                    calmar_ratio,
                    expectancy,
                    avg_win_r_50t,
                    avg_loss_r_50t,
                    avg_win,
                    avg_loss,
                    NOW()::timestamp
                FROM algo_performance_daily
                WHERE report_date >= (CURRENT_DATE - INTERVAL '30 days')
                ORDER BY report_date
                ON CONFLICT (metric_date) DO UPDATE SET
                    total_trades = EXCLUDED.total_trades,
                    winning_trades = EXCLUDED.winning_trades,
                    losing_trades = EXCLUDED.losing_trades,
                    win_rate_pct = EXCLUDED.win_rate_pct,
                    profit_factor = EXCLUDED.profit_factor,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    sortino_ratio = EXCLUDED.sortino_ratio,
                    max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                    calmar_ratio = EXCLUDED.calmar_ratio,
                    expectancy = EXCLUDED.expectancy,
                    avg_win_r = EXCLUDED.avg_win_r,
                    avg_loss_r = EXCLUDED.avg_loss_r,
                    avg_win_pct = EXCLUDED.avg_win_pct,
                    avg_loss_pct = EXCLUDED.avg_loss_pct,
                    updated_at = EXCLUDED.updated_at
            """
            )

            # Get count of records updated
            cur.execute("SELECT COUNT(*) FROM algo_performance_metrics WHERE updated_at >= NOW() - INTERVAL '1 hour'")
            count_row = cur.fetchone()
            count = count_row[0] if count_row else 0

            logger.info(f"Refreshed {count} performance metrics records")
            return True

    except Exception as e:
        logger.error(f"Failed to refresh performance metrics: {e}")
        return False


if __name__ == "__main__":
    success = refresh_performance_metrics()
    sys.exit(0 if success else 1)
