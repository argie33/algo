#!/usr/bin/env python3
"""Portfolio Exposure Daily Loader - Pre-compute portfolio metrics and risk indicators."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import statistics
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.timezone_utils import EASTERN_TZ
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


class PortfolioExposureDailyLoader(OptimalLoader):
    """Pre-compute daily portfolio exposure metrics (heat, concentration, metrics)."""

    table_name = "portfolio_exposure_daily"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute portfolio exposure metrics for today."""
        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            run_date = now_et.date()

            with DatabaseContext('read') as cur:
                # Get portfolio total
                cur.execute("""
                    SELECT total_balance FROM algo_portfolio WHERE portfolio_id = 1
                """)
                portfolio_row = cur.fetchone()
                total_portfolio_value = float(portfolio_row[0]) if portfolio_row and portfolio_row[0] else 0

                # Get position aggregations
                cur.execute("""
                    SELECT
                        COUNT(*) as position_count,
                        SUM(position_value) as total_position_value,
                        AVG(position_value) as avg_position_value,
                        MAX(position_value) as largest_position_value,
                        AVG(EXTRACT(DAY FROM CURRENT_DATE - date_entered)) as avg_days_held,
                        SUM(unrealized_pnl) as total_pnl,
                        SUM(entry_value) as total_entry_value,
                        SUM(unrealized_pnl_pct) / COUNT(*) as avg_unrealized_pnl_pct
                    FROM algo_positions
                    WHERE status = 'open'
                """)

                position_row = cur.fetchone()

                if not position_row or not position_row[0]:
                    logger.info(f"No open positions for {run_date}")
                    return [{
                        'date': run_date,
                        'total_portfolio_value': round(total_portfolio_value, 2),
                        'total_position_value': 0,
                        'cash_available': round(total_portfolio_value, 2),
                        'total_position_count': 0,
                        'avg_position_value': 0,
                        'avg_days_in_trade': 0,
                        'portfolio_heat': 'cold',
                        'largest_position_pct': 0,
                        'total_unrealized_pnl_pct': 0,
                        'avg_stop_distance_r': 0,
                    }]

                position_count = int(position_row[0]) if position_row[0] else 0
                total_position_value = float(position_row[1]) if position_row[1] else 0
                avg_position_value = float(position_row[2]) if position_row[2] else 0
                largest_position = float(position_row[3]) if position_row[3] else 0
                avg_days_held = float(position_row[4]) if position_row[4] else 0
                total_pnl = float(position_row[5]) if position_row[5] else 0
                total_entry_value = float(position_row[6]) if position_row[6] else 0
                avg_pnl_pct = float(position_row[7]) if position_row[7] else 0

                # Calculate derived metrics
                cash_available = total_portfolio_value - total_position_value
                largest_position_pct = 0
                if total_portfolio_value > 0 and largest_position > 0:
                    largest_position_pct = round((largest_position / total_portfolio_value) * 100, 4)

                total_pnl_pct = 0
                if total_entry_value > 0:
                    total_pnl_pct = round((total_pnl / total_entry_value) * 100, 4)

                # Determine portfolio "heat" (risk/volatility level)
                portfolio_heat = self._calculate_heat(total_position_value, total_portfolio_value)

                # Calculate average stop distance R
                avg_stop_distance_r = self._calculate_avg_stop_distance_r(cur)

                return [{
                    'date': run_date,
                    'total_portfolio_value': round(total_portfolio_value, 2),
                    'total_position_value': round(total_position_value, 2),
                    'cash_available': round(cash_available, 2),
                    'total_position_count': position_count,
                    'avg_position_value': round(avg_position_value, 2) if avg_position_value > 0 else 0,
                    'avg_days_in_trade': round(avg_days_held, 2) if avg_days_held > 0 else 0,
                    'portfolio_heat': portfolio_heat,
                    'largest_position_pct': largest_position_pct,
                    'total_unrealized_pnl_pct': total_pnl_pct,
                    'avg_stop_distance_r': avg_stop_distance_r,
                }]

        except Exception as e:
            logger.error(f"Failed to compute portfolio exposure: {e}", exc_info=True)
            return None

    def _calculate_heat(self, position_value: float, portfolio_value: float) -> str:
        """Determine portfolio heat (risk level) based on deployment %.

        Heat levels:
        - cold: < 20% deployed
        - warm: 20-40% deployed
        - hot: > 40% deployed
        """
        if portfolio_value <= 0:
            return 'cold'

        deployed_pct = (position_value / portfolio_value) * 100

        if deployed_pct < 20:
            return 'cold'
        elif deployed_pct <= 40:
            return 'warm'
        else:
            return 'hot'

    def _calculate_avg_stop_distance_r(self, cur) -> float:
        """Calculate average risk ratio (stop distance) across positions."""
        try:
            cur.execute("""
                SELECT
                    AVG(CASE
                        WHEN (ap.avg_entry_price - at.stop_loss_price) > 0
                            AND (at.target_1_price - ap.avg_entry_price) > 0
                        THEN (ap.avg_entry_price - at.stop_loss_price) /
                             (at.target_1_price - ap.avg_entry_price)
                        ELSE NULL
                    END) as avg_stop_distance
                FROM algo_positions ap
                LEFT JOIN algo_trades at ON ap.symbol = at.symbol AND at.status = 'open'
                WHERE ap.status = 'open'
                    AND ap.avg_entry_price > 0
                    AND at.stop_loss_price IS NOT NULL
                    AND at.target_1_price IS NOT NULL
            """)

            row = cur.fetchone()
            avg_distance = float(row[0]) if row and row[0] else 0
            return round(avg_distance, 4)

        except Exception as e:
            logger.warning(f"Failed to calculate avg stop distance: {e}")
            return 0


def main():
    loader = PortfolioExposureDailyLoader()
    result = loader.load_global()

    if result and result > 0:
        logger.info(f"SUCCESS: {result} portfolio exposure metrics computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No metrics computed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
