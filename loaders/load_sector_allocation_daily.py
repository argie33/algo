#!/usr/bin/env python3
"""Sector Allocation Daily Loader - Pre-compute sector exposures and aggregations."""
import sys
import logging
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.timezone_utils import EASTERN_TZ
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

class SectorAllocationDailyLoader(OptimalLoader):
    """Pre-compute daily sector allocations from current positions."""
from loaders.loader_helper import setup_imports
setup_imports()

    table_name = "sector_allocation_daily"
    primary_key = ("date", "sector_name")
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute sector allocations for today from algo_positions."""
        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            run_date = now_et.date()

            with DatabaseContext('read') as cur:
                # Aggregate positions by sector
                cur.execute("""
                    SELECT
                        COALESCE(csm.sector_name, 'Unknown') as sector,
                        COUNT(DISTINCT ap.symbol) as symbol_count,
                        SUM(ap.position_value) as total_value,
                        AVG(ap.unrealized_pnl_pct) as avg_pnl_pct
                    FROM algo_positions ap
                    LEFT JOIN company_sector_mapping csm ON ap.symbol = csm.symbol
                    WHERE ap.status = 'open'
                    GROUP BY csm.sector_name
                """)

                rows = cur.fetchall()
                if not rows:
                    logger.info(f"No open positions for {run_date}")
                    return []

                # Get total portfolio value for % calculations
                cur.execute("""
                    SELECT total_balance FROM algo_portfolio WHERE portfolio_id = 1
                """)
                total_value_row = cur.fetchone()
                total_portfolio_value = float(total_value_row[0]) if total_value_row and total_value_row[0] else 0

                # Build results
                results = []
                for row in rows:
                    sector_name = row[0] or 'Unknown'
                    symbol_count = int(row[1]) if row[1] else 0
                    sector_value = float(row[2]) if row[2] else 0
                    avg_pnl = float(row[3]) if row[3] else 0

                    pct_portfolio = 0.0
                    if total_portfolio_value > 0:
                        pct_portfolio = round((sector_value / total_portfolio_value) * 100, 4)

                    results.append({
                        'date': run_date,
                        'sector_name': sector_name,
                        'symbol_count': symbol_count,
                        'total_position_value': round(sector_value, 2),
                        'pct_portfolio': pct_portfolio,
                        'avg_unrealized_pnl_pct': round(avg_pnl, 4),
                        'sector_day_return_pct': None,  # Computed from market data if available
                    })

                return results if results else None

        except Exception as e:
            logger.error(f"Failed to compute sector allocations: {e}", exc_info=True)
            return None

def main():
    loader = SectorAllocationDailyLoader()
    result = loader.load_global()

    if result and result > 0:
        logger.info(f"SUCCESS: {result} sector allocations computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No allocations computed")
        return 0

if __name__ == "__main__":
    sys.exit(main())
