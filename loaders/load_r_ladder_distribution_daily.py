#!/usr/bin/env python3
"""R-Ladder Distribution Daily Loader - Pre-compute R-multiple risk distribution."""
import sys
import logging
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.timezone_utils import EASTERN_TZ
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

class RLadderDistributionDailyLoader(OptimalLoader):
    """Pre-compute daily R-ladder distribution across 6 risk buckets."""
from loaders.loader_helper import setup_imports
setup_imports()

    table_name = "r_ladder_distribution_daily"
    primary_key = ("date", "r_multiple_bucket")
    watermark_field = "date"

    # Risk buckets: < -2R, -2R to -1R, -1R to 0R, 0R to 1R, 1R to 2R, > 2R
    BUCKETS = ['< -2R', '-2R to -1R', '-1R to 0R', '0R to 1R', '1R to 2R', '> 2R']

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute R-ladder distribution for today from positions."""
        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            run_date = now_et.date()

            with DatabaseContext('read') as cur:
                # Get all open positions with R-multiple calculation
                cur.execute("""
                    SELECT
                        ap.symbol,
                        ap.position_value,
                        ap.unrealized_pnl_pct,
                        EXTRACT(DAY FROM CURRENT_DATE - ap.date_entered) as days_held,
                        ap.avg_entry_price,
                        at.stop_loss_price,
                        at.target_1_price
                    FROM algo_positions ap
                    LEFT JOIN algo_trades at ON ap.symbol = at.symbol AND at.status = 'open'
                    WHERE ap.status = 'open'
                    ORDER BY ap.symbol
                """)

                rows = cur.fetchall()
                if not rows:
                    logger.info(f"No open positions for {run_date}")
                    return []

                # Group positions into R-ladder buckets
                buckets = {bucket: {'count': 0, 'value': 0, 'days': [], 'pnl': []} for bucket in self.BUCKETS}

                for row in rows:
                    symbol = row[0]
                    position_value = float(row[1]) if row[1] else 0
                    pnl_pct = float(row[2]) if row[2] else 0
                    days_held = float(row[3]) if row[3] else 0
                    entry_price = float(row[4]) if row[4] else 0
                    stop_price = float(row[5]) if row[5] else None
                    target_price = float(row[6]) if row[6] else None

                    # Calculate R-multiple for this position
                    r_multiple = self._calculate_r_multiple(entry_price, stop_price, target_price)

                    # Determine bucket
                    bucket = self._get_bucket(r_multiple)

                    # Add to bucket
                    buckets[bucket]['count'] += 1
                    buckets[bucket]['value'] += position_value
                    buckets[bucket]['days'].append(days_held)
                    buckets[bucket]['pnl'].append(pnl_pct)

                # Build results
                results = []
                for bucket in self.BUCKETS:
                    data = buckets[bucket]

                    avg_days = round(sum(data['days']) / len(data['days']), 2) if data['days'] else 0
                    avg_pnl = round(sum(data['pnl']) / len(data['pnl']), 4) if data['pnl'] else 0

                    results.append({
                        'date': run_date,
                        'r_multiple_bucket': bucket,
                        'position_count': data['count'],
                        'total_position_value': round(data['value'], 2),
                        'avg_days_in_trade': avg_days,
                        'avg_unrealized_pnl_pct': avg_pnl,
                    })

                return results if results else None

        except Exception as e:
            logger.error(f"Failed to compute R-ladder distribution: {e}", exc_info=True)
            return None

    def _calculate_r_multiple(self, entry: float, stop: Optional[float], target: Optional[float]) -> float:
        """Calculate R-multiple for a position."""
        if not entry or entry <= 0:
            return 0.0

        if stop is None or target is None:
            return 0.0

        if entry <= stop or entry >= target:
            return 0.0

        try:
            risk = entry - stop
            reward = target - entry
            if reward > 0:
                return round(risk / reward, 2)
            return 0.0
        except Exception:
            return 0.0

    def _get_bucket(self, r_multiple: float) -> str:
        """Determine which bucket this R-multiple falls into."""
        if r_multiple < -2.0:
            return '< -2R'
        elif r_multiple < -1.0:
            return '-2R to -1R'
        elif r_multiple < 0.0:
            return '-1R to 0R'
        elif r_multiple < 1.0:
            return '0R to 1R'
        elif r_multiple < 2.0:
            return '1R to 2R'
        else:
            return '> 2R'

def main():
    loader = RLadderDistributionDailyLoader()
    result = loader.load_global()

    if result and result > 0:
        logger.info(f"SUCCESS: {result} R-ladder buckets computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No buckets computed")
        return 0

if __name__ == "__main__":
    sys.exit(main())
