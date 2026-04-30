#!/usr/bin/env python3
"""
Incremental Load Helpers - Utilities for incremental data loading

Provides helper functions for loaders to support:
- Only loading new data since last_load_date
- Updating state after successful loads
- Logging incremental load progress
"""

import logging
from datetime import datetime, timedelta
from load_state import LoadState

logger = logging.getLogger(__name__)


class IncrementalLoader:
    """Helper for loaders to support incremental loading"""

    def __init__(self, loader_name: str, is_incremental: bool = False):
        """Initialize incremental loader helper

        Args:
            loader_name: Name of the loader (e.g. 'price_daily')
            is_incremental: True if this is incremental load, False for full reload
        """
        self.loader_name = loader_name
        self.is_incremental = is_incremental
        self.state = LoadState()
        self.rows_loaded = 0
        self.start_time = datetime.now()

    def get_load_date_range(self):
        """Get date range for this load

        Returns:
            (start_date, end_date) tuple
        """
        if not self.is_incremental:
            # Full reload: go back 1 year to catch everything
            return datetime.now() - timedelta(days=365), datetime.now()

        # Incremental: only load since last successful load
        last_load = self.state.get_last_load(self.loader_name)
        if not last_load:
            # No previous load: go back 30 days
            return datetime.now() - timedelta(days=30), datetime.now()

        # Load from last_load_date to now
        return last_load, datetime.now()

    def log_progress(self, message: str, rows: int = 0):
        """Log progress with row count

        Args:
            message: Progress message
            rows: Rows loaded in this batch
        """
        self.rows_loaded += rows
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.rows_loaded / elapsed if elapsed > 0 else 0

        mode = "INCREMENTAL" if self.is_incremental else "FULL"
        logger.info(f"[{mode}] {message} | Rows: {self.rows_loaded:,} | Rate: {rate:.0f} rows/sec")

    def success(self, rows_loaded: int, end_date: datetime = None):
        """Mark load as successful

        Args:
            rows_loaded: Total rows loaded
            end_date: End date of load (default: now)
        """
        self.rows_loaded = rows_loaded
        end = end_date or datetime.now()
        start, _ = self.get_load_date_range()

        self.state.update_load(
            self.loader_name,
            start_date=start,
            end_date=end,
            row_count=rows_loaded,
            status='success'
        )

        elapsed = (datetime.now() - self.start_time).total_seconds()
        logger.info(f"✓ {self.loader_name}: {rows_loaded:,} rows in {elapsed:.1f}s")

    def error(self, error_message: str):
        """Mark load as failed

        Args:
            error_message: Error description
        """
        self.state.update_load(
            self.loader_name,
            status='error',
            error=error_message
        )

        logger.error(f"✗ {self.loader_name}: {error_message}")


def should_run_incremental(force_full: bool = False):
    """Determine if should run incremental or full load

    Args:
        force_full: Force full reload (overrides state check)

    Returns:
        True if incremental, False for full reload
    """
    if force_full:
        logger.info("FULL RELOAD: Forced via --full flag")
        return False

    state = LoadState()
    is_incremental = state.is_incremental_load()

    if is_incremental:
        logger.info("INCREMENTAL LOAD: All loaders have previous runs")
    else:
        logger.info("FULL RELOAD: First run or state reset")

    return is_incremental


def get_symbols_to_reload(cursor, days_back: int = 30):
    """Get list of symbols with changed data in past N days

    For incremental loads: only recalculate metrics/scores for
    symbols that have new price or earnings data.

    Args:
        cursor: Database cursor
        days_back: Number of days to check for changes

    Returns:
        List of symbols with recent data changes
    """
    try:
        cursor.execute(f"""
            SELECT DISTINCT symbol FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '{days_back} days'
            ORDER BY symbol
        """)

        symbols = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(symbols)} symbols with data changes in past {days_back} days")
        return symbols

    except Exception as e:
        logger.warning(f"Could not get changed symbols: {e}")
        return None  # Return None = reload all symbols


def partition_symbols(symbols: list, partition_size: int = 100):
    """Partition symbols into chunks for batch processing

    Args:
        symbols: List of symbols
        partition_size: Size of each partition

    Yields:
        List chunks of size partition_size
    """
    for i in range(0, len(symbols), partition_size):
        yield symbols[i:i+partition_size]


def log_state_summary():
    """Print load state summary"""
    state = LoadState()
    state.print_summary()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test helper
    loader = IncrementalLoader("test_loader", is_incremental=False)
    start, end = loader.get_load_date_range()
    print(f"Date range: {start.date()} to {end.date()}")

    log_state_summary()
