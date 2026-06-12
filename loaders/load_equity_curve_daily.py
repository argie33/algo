#!/usr/bin/env python3
"""Equity Curve Daily Loader - Pre-compute rolling Sharpe, Sortino, max drawdown, Calmar."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import statistics
from datetime import date, timedelta, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.timezone_utils import EASTERN_TZ
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


class EquityCurveDailyLoader(OptimalLoader):
    """Pre-compute daily equity curve metrics (Sharpe, Sortino, max drawdown, Calmar)."""

    table_name = "equity_curve_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch daily snapshots and compute rolling metrics."""
        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            run_date = now_et.date()

            with DatabaseContext('read') as cur:
                # Get last 252 trading days of snapshots for rolling metrics
                cur.execute("""
                    SELECT
                        DATE(snapshot_date) as snapshot_date,
                        total_portfolio_value,
                        daily_return_pct
                    FROM algo_portfolio_snapshots
                    WHERE DATE(snapshot_date) >= %s - INTERVAL '365 days'
                    ORDER BY snapshot_date ASC
                """, (run_date,))

                rows = cur.fetchall()
                if not rows:
                    logger.warning(f"No snapshots available for {run_date}")
                    return None

                # Build historical data indexed by date
                snapshots = {}
                for row in rows:
                    snapshots[row[0]] = {
                        'value': float(row[1]) if row[1] else 0.0,
                        'return_pct': float(row[2]) if row[2] else 0.0
                    }

                # Compute rolling metrics for today
                result = self._compute_metrics(snapshots, run_date)
                if result:
                    return [result]
                return None

        except Exception as e:
            logger.error(f"Failed to compute equity curve daily: {e}", exc_info=True)
            return None

    def _compute_metrics(self, snapshots: dict, target_date: date) -> Optional[dict]:
        """Compute rolling metrics for target_date from historical snapshots."""
        if target_date not in snapshots:
            logger.warning(f"No snapshot for {target_date}")
            return None

        today_value = snapshots[target_date]['value']

        # Get past 252 trading days (approximately 1 year)
        min_date = target_date - timedelta(days=365)
        relevant_dates = sorted([d for d in snapshots.keys() if min_date <= d <= target_date])

        if len(relevant_dates) < 10:
            logger.warning(f"Insufficient historical data: {len(relevant_dates)} days < 10")
            return None

        # Extract returns for rolling metrics
        returns = []
        for d in relevant_dates:
            r = snapshots[d]['return_pct']
            returns.append(float(r) / 100.0)  # Convert % to decimal

        # Compute Sharpe ratio (252-day rolling)
        sharpe = None
        if len(returns) > 1:
            try:
                mean_ret = statistics.mean(returns)
                std_ret = statistics.stdev(returns)
                if std_ret > 0:
                    sharpe = round(mean_ret / std_ret * (252 ** 0.5), 4)
            except Exception as e:
                logger.warning(f"Failed to compute Sharpe: {e}")

        # Compute Sortino ratio (downside deviation only)
        sortino = None
        if len(returns) > 1:
            try:
                mean_ret = statistics.mean(returns)
                downside = [r for r in returns if r < 0]
                if downside:
                    downside_std = statistics.stdev(downside + [0] * (len(returns) - len(downside)))
                    if downside_std > 0:
                        sortino = round(mean_ret / downside_std * (252 ** 0.5), 4)
                else:
                    sortino = round(mean_ret / 0.001 * (252 ** 0.5), 4)  # Near-zero downside
            except Exception as e:
                logger.warning(f"Failed to compute Sortino: {e}")

        # Compute max drawdown YTD
        year_start = date(target_date.year, 1, 1)
        ytd_dates = [d for d in snapshots.keys() if year_start <= d <= target_date]
        ytd_values = [snapshots[d]['value'] for d in ytd_dates]

        max_dd_ytd = None
        if ytd_values:
            peak = 0
            max_dd = 0.0
            for v in ytd_values:
                if v > peak:
                    peak = v
                if peak > 0:
                    dd = (peak - v) / peak * 100
                    max_dd = max(max_dd, dd)
            max_dd_ytd = round(max_dd, 4)

        # Compute Calmar ratio = annual return / max drawdown
        calmar = None
        if max_dd_ytd and max_dd_ytd > 0:
            days_elapsed = (target_date - year_start).days
            if days_elapsed > 0:
                # Annualize return
                ytd_return_pct = 0.0
                if ytd_values and ytd_values[0] > 0:
                    ytd_return_pct = (ytd_values[-1] - ytd_values[0]) / ytd_values[0] * 100
                annual_return = ytd_return_pct * (365 / days_elapsed)
                calmar = round(annual_return / max_dd_ytd, 4)

        # Get daily return for today
        daily_return = snapshots[target_date]['return_pct']

        return {
            'date': target_date,
            'total_portfolio_value': round(today_value, 2),
            'daily_return_pct': round(float(daily_return), 4),
            'daily_return_dollars': None,  # Computed from daily change if available
            'rolling_sharpe_252d': sharpe,
            'rolling_sortino_252d': sortino,
            'max_drawdown_ytd_pct': max_dd_ytd,
            'calmar_ratio': calmar,
            'equity_curve_sparkline': None,  # Computed separately if needed
        }


def main():
    loader = EquityCurveDailyLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} equity curve metrics computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No metrics computed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
