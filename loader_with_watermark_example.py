#!/usr/bin/env python3
"""
Example: Using Watermark Manager for Incremental Data Loading

This demonstrates how to integrate watermark tracking into a loader
to enable incremental loading (only load new data since last run).

Pattern:
    1. Get last watermark timestamp/ID
    2. Query API/data source for only NEW data since watermark
    3. Load data into database
    4. Update watermark with new timestamp/ID
    5. On success: mark watermark as success
    6. On failure: mark watermark as failed (don't update timestamp)

Benefits:
    - Reduce API calls by 80-90% (load only new data)
    - Reduce database writes (less churn)
    - Faster load times
    - Better data freshness tracking
    - Automatic failure recovery (can retry without losing state)

Example: Loading daily stock prices incrementally
    - First run: Load all historical data, set watermark = today
    - Next run: Load only data since yesterday, append to DB, set watermark = today
    - If network error: Retry loads only yesterday's data
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

from loader_base_optimized import OptimizedLoader
from watermark_manager import WatermarkManager, WatermarkBatch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IncrementalPriceLoader(OptimizedLoader):
    """
    Example incremental loader for daily stock prices.

    Uses watermark to track last loaded date and only fetch new data.
    """

    def __init__(self, batch_size: int = 500, commit_every_n_symbols: int = 50):
        super().__init__(batch_size, commit_every_n_symbols)

        # Initialize watermark manager for this data source
        self.watermark = WatermarkManager(source="daily_prices")
        self.symbols = []

    def create_tables(self):
        """Create price table if not exists."""
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS price_daily (
                symbol VARCHAR(20) NOT NULL,
                date DATE NOT NULL,
                open NUMERIC,
                high NUMERIC,
                low NUMERIC,
                close NUMERIC,
                volume BIGINT,
                fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_price_symbol_date ON price_daily(symbol, date DESC);
        """)
        self.conn.commit()
        logger.info("Price table ready")

    def load_incremental(self, symbols: List[str]):
        """
        Load prices incrementally using watermark.

        Strategy:
        1. Get last load date from watermark
        2. For each symbol, fetch only data since that date
        3. Update watermark on success
        """
        self.symbols = symbols

        try:
            # Get last successful load date
            last_date = self.watermark.get_last_timestamp()

            if last_date:
                logger.info(f"Loading prices since {last_date.date()}")
                start_date = last_date.date()
            else:
                logger.info("First run: loading full historical data")
                # For first run, load last 5 years (or configure as needed)
                start_date = (datetime.utcnow() - timedelta(days=365*5)).date()

            # Use context manager to batch watermark updates
            # All symbols succeed together or all fail together
            with WatermarkBatch(self.watermark) as batch:
                self.connect()
                self.create_tables()

                total_rows = 0
                for symbol in symbols:
                    # Fetch only NEW data since last watermark
                    rows = self._fetch_prices(symbol, start_date)

                    if rows:
                        logger.debug(f"{symbol}: {len(rows)} new rows since {start_date}")
                        for row in rows:
                            self.add_row(row)
                        total_rows += len(rows)

                    self.commit_if_needed()

                # Flush remaining rows
                self.finalize()

                # Update watermark to TODAY (all prices loaded through today)
                self.watermark.set_last_timestamp(datetime.utcnow())

                # Mark success with record count
                batch.mark_success(records_loaded=total_rows)
                logger.info(f"✓ Load complete: {total_rows} price rows loaded")

        except Exception as e:
            logger.error(f"✗ Load failed: {e}")
            self.watermark.mark_failure(str(e))
            raise

        finally:
            self.disconnect()

    def load_full_refresh(self, symbols: List[str]):
        """
        Full refresh: reload all data (ignores watermark).
        Use sparingly (only for data corrections or migrations).
        """
        logger.warning("Starting FULL REFRESH (ignoring watermark)")

        self.watermark.clear()  # Reset watermark
        start_date = (datetime.utcnow() - timedelta(days=365*10)).date()

        # Rest of load logic is same, just with earlier start date
        # ...

    def _fetch_prices(self, symbol: str, since_date) -> List[Tuple]:
        """
        Fetch prices from API for given symbol since date.

        Example implementation - replace with actual API call.
        """
        # This is pseudocode - replace with actual API call
        try:
            # Example: Call Alpaca API
            # prices = alpaca.get_daily_bars(symbol, start=since_date)

            # For demo, return empty (represents no new data)
            return []

        except Exception as e:
            logger.error(f"Failed to fetch prices for {symbol}: {e}")
            raise

    def _batch_insert(self, rows: List[Tuple]) -> None:
        """Batch insert price rows."""
        from psycopg2.extras import execute_values

        execute_values(self.cur, """
            INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                fetched_at = CURRENT_TIMESTAMP
        """, rows)


class SymbolWatermarkLoader(OptimizedLoader):
    """
    Example: Load symbols using ID-based watermark.

    For APIs that provide cursor/ID for pagination.
    """

    def __init__(self):
        super().__init__()
        self.watermark = WatermarkManager(source="stock_symbols")

    def load_incremental(self):
        """Load symbols using cursor-based pagination."""
        try:
            # Get last cursor position
            last_cursor = self.watermark.get_last_id()

            if last_cursor:
                logger.info(f"Resuming from cursor: {last_cursor}")
                start_cursor = last_cursor
            else:
                logger.info("Starting fresh symbol load")
                start_cursor = None

            with WatermarkBatch(self.watermark) as batch:
                self.connect()

                rows_loaded = 0
                cursor = start_cursor

                # Paginated load
                while True:
                    # Fetch next page
                    page = self._fetch_symbols_page(cursor)

                    if not page["symbols"]:
                        break

                    # Add rows to batch
                    for symbol_data in page["symbols"]:
                        row = (symbol_data["symbol"], symbol_data["name"])
                        self.add_row(row)
                        rows_loaded += 1

                    # Update cursor for next page
                    cursor = page.get("next_cursor")
                    if not cursor:
                        break

                    self.commit_if_needed()

                self.finalize()

                # Update watermark with final cursor
                if cursor:
                    self.watermark.set_last_id(cursor)

                batch.mark_success(records_loaded=rows_loaded)
                logger.info(f"✓ Loaded {rows_loaded} symbols")

        except Exception as e:
            logger.error(f"✗ Symbol load failed: {e}")
            self.watermark.mark_failure(str(e))
            raise

        finally:
            self.disconnect()

    def _fetch_symbols_page(self, cursor=None) -> Dict:
        """Fetch next page of symbols."""
        # Replace with actual API call
        return {
            "symbols": [],
            "next_cursor": None
        }

    def _batch_insert(self, rows: List[Tuple]) -> None:
        from psycopg2.extras import execute_values

        execute_values(self.cur, """
            INSERT INTO stock_symbols (symbol, name) VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name
        """, rows)


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Example 1: Incremental price loading (time-based watermark)
    price_loader = IncrementalPriceLoader(batch_size=500, commit_every_n_symbols=50)

    symbols = ["AAPL", "GOOGL", "MSFT"]  # Replace with actual symbols

    try:
        # First run: loads 5 years of historical data
        # Subsequent runs: load only new data since last timestamp
        price_loader.load_incremental(symbols)

    except Exception as e:
        logger.error(f"Price load failed: {e}")
        # On next retry, watermark marks this as failed
        # Next load attempt will start over with same date (no data lost)

    # Example 2: Check watermark status
    watermark = WatermarkManager(source="daily_prices")
    status = watermark.get_status()
    print(f"\nWatermark Status: {status}")
    # Output:
    # {
    #     'source': 'daily_prices',
    #     'status': 'success',
    #     'last_timestamp': '2026-05-09T12:34:56.123456',
    #     'last_load_at': '2026-05-09T12:34:56.123456',
    #     'records_loaded': 1000,
    #     'error': None
    # }

    # Example 3: Manual watermark manipulation (for testing/maintenance)
    # watermark.clear()  # Reset for full reload
    # watermark.set_last_timestamp(datetime(2025, 1, 1))  # Reload from specific date
