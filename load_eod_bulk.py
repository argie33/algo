#!/usr/bin/env python3
"""
EOD Bulk Price Loader - Fast batch download for daily EOD data refresh.

Optimized for 5000+ symbols in ~5 minutes using batched yfinance downloads.
NOT for backfilling — use loadpricedaily.py for that (slower but handles throttling).

Run:
    python3 load_eod_bulk.py [--days 10] [--batch-size 100]

Environment:
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (from .env.local)
    BACKFILL_DAYS (override --days via env)
"""

import argparse
import logging
import os
import sys
import psycopg2
import pandas as pd
from datetime import date, timedelta
from typing import List, Dict, Any
import yfinance as yf

from credential_helper import get_db_password, get_db_config
from pathlib import Path as _DotenvPath

# >>> dotenv-autoload >>>
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class BulkPriceLoader:
    """Batch yfinance downloader for EOD price refresh."""

    table_name = "price_daily"

    def __init__(self, days: int = 10, batch_size: int = 100):
        self.days = days
        self.batch_size = batch_size
        self.conn = None
        self.stats = {
            "symbols_total": 0,
            "symbols_fetched": 0,
            "symbols_failed": 0,
            "rows_inserted": 0,
        }

    def connect(self):
        """Connect to database."""
        self.conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=get_db_password(),
            database=os.getenv("DB_NAME", "stocks"),
        )

    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_symbols(self) -> List[str]:
        """Fetch all active symbols from stock_symbols table."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT symbol FROM stock_symbols WHERE is_active = true ORDER BY symbol")
            return [row[0] for row in cur.fetchall()]

    def fetch_batch(self, symbols: List[str], start_date: date, end_date: date) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch OHLCV for multiple symbols at once using yfinance batch API.
        Returns dict: { symbol: [{ date, open, high, low, close, volume }, ...], ... }
        """
        results = {}

        try:
            # yfinance batch download: fetch all symbols together
            data = yf.download(
                tickers=" ".join(symbols),
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                progress=False,
                threads=True,
                group_by="ticker",
            )

            for symbol in symbols:
                try:
                    if len(symbols) == 1:
                        # Single symbol returns Series, not DataFrame
                        df = data
                    else:
                        # Multiple symbols — get the symbol's dataframe
                        if symbol in data.columns.get_level_values(0):
                            df = data[symbol]
                        else:
                            logger.warning(f"[{symbol}] Not found in yfinance response")
                            continue

                    if df.empty:
                        logger.debug(f"[{symbol}] No data for date range {start_date} to {end_date}")
                        continue

                    # Convert to list of dicts with proper column names
                    rows = []
                    for idx, row in df.iterrows():
                        if pd.isna(row.get('Close', None)):
                            continue  # Skip incomplete bars

                        rows.append({
                            'symbol': symbol,
                            'date': idx.date() if hasattr(idx, 'date') else idx,
                            'open': float(row['Open']),
                            'high': float(row['High']),
                            'low': float(row['Low']),
                            'close': float(row['Close']),
                            'volume': int(row['Volume'] or 0),
                        })

                    if rows:
                        results[symbol] = rows
                        self.stats["symbols_fetched"] += 1

                except Exception as e:
                    logger.error(f"[{symbol}] Error parsing: {e}")
                    self.stats["symbols_failed"] += 1

        except Exception as e:
            logger.error(f"Batch download failed: {e}")
            # Fail-open: if batch fails, just return empty rather than blocking

        return results

    def upsert_rows(self, rows: List[Dict[str, Any]]) -> int:
        """
        Upsert rows using ON CONFLICT DO UPDATE.
        Returns count of rows inserted.
        """
        if not rows:
            return 0

        with self.conn.cursor() as cur:
            # Build INSERT ... ON CONFLICT statement
            cur.executemany(
                """
                INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
                VALUES (%(symbol)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
                """,
                rows
            )

        self.conn.commit()
        return len(rows)

    def run(self):
        """Main loader run."""
        try:
            self.connect()
            logger.info(f"Loading last {self.days} days of price data in batches of {self.batch_size}...")

            symbols = self.get_symbols()
            self.stats["symbols_total"] = len(symbols)
            logger.info(f"Fetching {len(symbols)} symbols")

            end_date = date.today()
            start_date = end_date - timedelta(days=self.days)

            # Process symbols in batches
            all_rows = []
            for i in range(0, len(symbols), self.batch_size):
                batch = symbols[i:i+self.batch_size]
                logger.info(f"Batch {i//self.batch_size + 1}/{(len(symbols)-1)//self.batch_size + 1}: {len(batch)} symbols")

                batch_data = self.fetch_batch(batch, start_date, end_date)

                for symbol, rows in batch_data.items():
                    all_rows.extend(rows)

            # Insert all rows at once
            if all_rows:
                inserted = self.upsert_rows(all_rows)
                self.stats["rows_inserted"] = inserted
                logger.info(f"Inserted {inserted} price rows")
            else:
                logger.warning("No rows to insert")

            logger.info(f"EOD bulk load complete: {self.stats}")

        finally:
            self.disconnect()


def main():
    parser = argparse.ArgumentParser(description="EOD Bulk Price Loader")
    parser.add_argument("--days", type=int, default=10, help="Days of history to fetch (default 10)")
    parser.add_argument("--batch-size", type=int, default=100, help="Symbols per yfinance batch (default 100)")
    args = parser.parse_args()

    # Override from env if set
    days = int(os.getenv("BACKFILL_DAYS", args.days))

    loader = BulkPriceLoader(days=days, batch_size=args.batch_size)
    loader.run()


if __name__ == "__main__":
    import pandas as pd
    main()
