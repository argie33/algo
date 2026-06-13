#!/usr/bin/env python3
"""Sector Performance Loader - Daily return_pct for each sector via SPDR ETFs."""
import sys
import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

# SPDR sector ETF → sector name mapping (matches company_profile.sector values)
SECTOR_ETF_MAP = {
    'XLK':  'Technology',
    'XLF':  'Financial Services',
    'XLV':  'Healthcare',
    'XLY':  'Consumer Cyclical',
    'XLC':  'Communication Services',
    'XLI':  'Industrials',
    'XLP':  'Consumer Defensive',
    'XLE':  'Energy',
    'XLU':  'Utilities',
    'XLRE': 'Real Estate',
    'XLB':  'Basic Materials',
}


class SectorPerformanceLoader(OptimalLoader):
    """Load daily return_pct and relative_strength for each sector via SPDR ETFs."""

    table_name = "sector_performance"
    primary_key = ("sector", "date")
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute sector performance data.

        return_pct = cumulative YTD return for each sector ETF,
        expressed as a percentage indexed to the first trading day of the year.
        relative_strength = ETF return_pct minus SPY return_pct (same period).
        """
        today = date.today()
        etf_symbols = list(SECTOR_ETF_MAP.keys()) + ['SPY']
        year_start = date(today.year, 1, 1)

        try:
            with DatabaseContext('read') as cur:
                # Fetch closing prices from both tables and merge
                all_rows_by_key = {}
                for table in ('price_daily', 'etf_price_daily'):
                    try:
                        cur.execute(f"""
                            SELECT symbol, date, close
                            FROM {table}
                            WHERE symbol = ANY(%s)
                              AND date >= %s
                              AND date <= %s
                              AND close > 0
                            ORDER BY symbol, date ASC
                        """, (etf_symbols, year_start, today))
                        for r in cur.fetchall():
                            key = (r[0], r[1])
                            if key not in all_rows_by_key:
                                all_rows_by_key[key] = {'symbol': r[0], 'date': r[1], 'close': r[2]}
                    except Exception as e:
                        logger.debug(f"Could not query {table}: {e}")

                rows = list(all_rows_by_key.values())
                if not rows:
                    logger.warning("No ETF price data found for sector performance")
                    return None

                # Group by symbol -> {date: close}
                prices: dict = {}
                for row in rows:
                    sym = row['symbol']
                    prices.setdefault(sym, {})[row['date']] = float(row['close'])

                # Find first trading date (baseline)
                all_dates = sorted({row['date'] for row in rows})
                if not all_dates:
                    return None
                baseline_date = all_dates[0]

                # Get baseline closes
                baseline: dict = {sym: d.get(baseline_date) for sym, d in prices.items()}
                spy_baseline = baseline.get('SPY')

                # Compute return_pct per sector for each date
                records = []
                skipped_count = 0
                for d in all_dates:
                    spy_close = prices.get('SPY', {}).get(d)
                    spy_ret = ((spy_close - spy_baseline) / spy_baseline * 100) if spy_close and spy_baseline else None

                    for etf, sector in SECTOR_ETF_MAP.items():
                        close = prices.get(etf, {}).get(d)
                        base = baseline.get(etf)
                        if close is None or base is None or base == 0:
                            skipped_count += 1
                            logger.debug(f"{sector} [{d}]: skipped (missing price data)")
                            continue
                        ret_pct = (close - base) / base * 100
                        rel_strength = (ret_pct - spy_ret) if spy_ret is not None else None
                        records.append({
                            'sector': sector,
                            'date': d,
                            'return_pct': round(ret_pct, 4),
                            'relative_strength': round(rel_strength, 4) if rel_strength is not None else None
                        })

                if not records:
                    logger.warning(f"No sector performance records computed (skipped {skipped_count})")
                    return None

                logger.info(f"Computed {len(records)} sector performance records through {today}")
                return records

        except Exception as e:
            logger.error(f"Failed to fetch sector performance data: {e}")
            return None


def main():
    loader = SectorPerformanceLoader()
    try:
        result = loader.load_global()
        if result > 0:
            logger.info(f"SUCCESS: {result} sector performance records loaded")
            return 0
        else:
            logger.warning("COMPLETED: No sector performance records loaded")
            return 0
    except Exception as e:
        logger.error(f"Sector performance load failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
