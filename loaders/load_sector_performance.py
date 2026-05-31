#!/usr/bin/env python3
"""Sector Performance Loader - Daily return_pct for each sector via SPDR ETFs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Optional, List

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


def _load_sector_performance(today: date) -> int:
    """Compute and upsert sector performance for `today`.

    return_pct = cumulative YTD return for each sector ETF,
    expressed as a percentage indexed to the first trading day of the year.
    relative_strength = ETF return_pct minus SPY return_pct (same period).
    """
    etf_symbols = list(SECTOR_ETF_MAP.keys()) + ['SPY']
    year_start = date(today.year, 1, 1)

    with DatabaseContext('write') as cur:
        # Fetch closing prices from both tables and merge.
        # SPY lands in price_daily (stock class loader).
        # Sector ETFs (XLK, XLF, etc.) land in etf_price_daily (etf class loader).
        # We must query both and deduplicate so no symbol is missed.
        all_rows_by_key = {}
        for table in ('price_daily', 'etf_price_daily'):
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
                key = (r['symbol'], r['date'])
                if key not in all_rows_by_key:
                    all_rows_by_key[key] = r
        rows = list(all_rows_by_key.values())

        if not rows:
            logger.warning("No ETF price data found for sector performance — skipping")
            return 0

        # Group by symbol → {date: close}
        prices: dict = {}
        for row in rows:
            sym = row['symbol']
            prices.setdefault(sym, {})[row['date']] = float(row['close'])

        # Find first trading date of the year (baseline)
        all_dates = sorted({row['date'] for row in rows})
        if not all_dates:
            return 0
        baseline_date = all_dates[0]

        # Get baseline closes for each ETF
        baseline: dict = {sym: d.get(baseline_date) for sym, d in prices.items()}

        # SPY baseline for relative strength
        spy_baseline = baseline.get('SPY')

        # For each trading date in the fetched range, compute return_pct per sector
        records = []
        for d in all_dates:
            spy_close = prices.get('SPY', {}).get(d)
            spy_ret = ((spy_close - spy_baseline) / spy_baseline * 100) if spy_close and spy_baseline else None

            for etf, sector in SECTOR_ETF_MAP.items():
                close = prices.get(etf, {}).get(d)
                base = baseline.get(etf)
                if close is None or base is None or base == 0:
                    continue
                ret_pct = (close - base) / base * 100
                rel_strength = (ret_pct - spy_ret) if spy_ret is not None else None
                records.append((sector, d, round(ret_pct, 4), round(rel_strength, 4) if rel_strength is not None else None))

        if not records:
            return 0

        # Upsert all records
        cur.executemany("""
            INSERT INTO sector_performance (sector, date, return_pct, relative_strength)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (sector, date) DO UPDATE SET
                return_pct        = EXCLUDED.return_pct,
                relative_strength = EXCLUDED.relative_strength
        """, records)

        inserted = len(records)
        logger.info(f"Upserted {inserted} sector performance records through {today}")

        # Update data_loader_status
        try:
            cur.execute("""
                INSERT INTO data_loader_status (table_name, row_count, latest_date, last_updated)
                VALUES ('sector_performance', %s, %s, NOW())
                ON CONFLICT (table_name) DO UPDATE SET
                    row_count = EXCLUDED.row_count,
                    latest_date = EXCLUDED.latest_date,
                    last_updated = EXCLUDED.last_updated
            """, (inserted, today))
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status: {e}")

        return inserted


def main():
    today = date.today()
    try:
        count = _load_sector_performance(today)
        if count > 0:
            logger.info(f"SUCCESS: {count} sector performance records loaded")
            return 0
        else:
            logger.warning("COMPLETED: No sector performance records loaded")
            return 0
    except Exception as e:
        logger.error(f"Sector performance load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
