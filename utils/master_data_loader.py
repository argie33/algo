#!/usr/bin/env python3
"""Base class for master data loaders (non-timeseries, non-per-symbol data).

Master data loaders handle:
- Reference data (stock symbols, company profiles, industry rankings)
- Aggregate data (market-wide indices like VIX, AAII sentiment)
- Constituent lists (S&P 500, Russell 2000)
- Earnings calendars and similar lookup tables

All master data loaders follow the same pattern:
1. Fetch data from external source (API, web scrape, etc.)
2. Validate and transform data
3. Upsert into database with consistent error handling
4. Return standard result dict
"""

import logging
from typing import Dict, Any, Optional
import psycopg2

from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


class MasterDataLoader:
    """Base class for master data loaders with consistent error handling."""

    def __init__(self):
        """Initialize loader with standard logging."""
        self.logger = logger

    def run(self) -> Dict[str, Any]:
        """Execute loader. Must be implemented by subclasses."""
        raise NotImplementedError("Subclass must implement run()")

    def _safe_run(self, operation_name: str) -> Dict[str, Any]:
        """Execute loader with standard exception handling and logging.

        Args:
            operation_name: Name of operation for logging (e.g., 'load_company_profiles')

        Returns:
            {'success': bool, 'rows': int, 'error': str (if failed)}
        """
        try:
            return self.run()
        except Exception as e:
            self.logger.error(f'{operation_name} failed: {e}', exc_info=True)
            return {'success': False, 'rows': 0, 'error': str(e)}

    @staticmethod
    def execute_with_db(fn, operation_name: str, mode: str = 'write') -> Dict[str, Any]:
        """Execute function with DatabaseContext, standardized error handling.

        Args:
            fn: Function that takes cursor as argument
            operation_name: Name for logging
            mode: 'read' or 'write' for DatabaseContext

        Returns:
            Result from fn, or {'success': False, 'error': str} on failure
        """
        try:
            with DatabaseContext(mode) as cur:
                return fn(cur)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Schema issue in {operation_name}: {e}', extra={'operation': operation_name})
            return {'success': False, 'rows': 0, 'error': f'Table/schema not ready: {e}'}
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error in {operation_name}: {e}', extra={'operation': operation_name})
            return {'success': False, 'rows': 0, 'error': f'Database unavailable: {e}'}
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error in {operation_name}: {e}', extra={'operation': operation_name, 'error_type': type(e).__name__})
            return {'success': False, 'rows': 0, 'error': f'Database error: {e}'}
        except Exception as e:
            logger.error(f'Unexpected error in {operation_name}: {e}', exc_info=True, extra={'operation': operation_name})
            return {'success': False, 'rows': 0, 'error': f'Unexpected error: {e}'}
