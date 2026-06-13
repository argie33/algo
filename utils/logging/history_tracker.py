#!/usr/bin/env python3
"""Track loader execution history in database.

Records execution metadata to loader_execution_history table after each loader completes.

Usage:
  from utils.logging import LoaderHistoryTracker
  tracker = LoaderHistoryTracker('stock_prices_daily')
  tracker.start()
  try:
      loader.run()
      tracker.complete(symbols_processed=1000)
  except Exception as e:
      tracker.failed(error_message=str(e))
"""

import logging
from datetime import datetime
from typing import Optional
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)

class LoaderHistoryTracker:
    """Track and log loader execution to database."""

    def __init__(self, loader_name: str):
        self.loader_name = loader_name
        self.start_time = None
        self.end_time = None

    def start(self):
        """Mark execution start."""
        self.start_time = datetime.utcnow()

    def complete(self, symbols_processed: int = 0, errors: int = 0):
        """Log successful completion."""
        self.end_time = datetime.utcnow()
        self._log(status='success', symbols_processed=symbols_processed, error_count=errors)

    def failed(self, error_message: str = None):
        """Log failed execution."""
        self.end_time = datetime.utcnow()
        self._log(status='failed', error_message=error_message)

    def _log(self, status: str, symbols_processed: int = 0, error_count: int = 0, error_message: str = None):
        """Write to database."""
        if not self.start_time:
            return

        try:
            with DatabaseContext('write') as cur:
                cur.execute("""
                    INSERT INTO loader_execution_history
                    (loader_name, execution_start, execution_end, status, rows_processed, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    self.loader_name,
                    self.start_time,
                    self.end_time,
                    status,
                    symbols_processed or None,
                    error_message,
                ))

            logger.info(f"Logged {self.loader_name}: {status}")
        except Exception as e:
            logger.error(f"Failed to log loader history: {e}")
