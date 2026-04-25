#!/usr/bin/env python3
"""
Universal Loader Utilities - Fix timeout issues and improve reliability
Handles: graceful timeouts, progress tracking, Windows compatibility
"""

import logging
import sys
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Callable, Any, Optional
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import json

# Load env
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class LoaderHelper:
    """Universal helper for reliable data loading with timeout handling"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.skipped_symbols = []
        self.failed_symbols = []
        self.successful_symbols = []

    @staticmethod
    def get_db_connection():
        """Get database connection"""
        return psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME', 'stocks')
        )

    @staticmethod
    def get_sp500_symbols() -> List[str]:
        """Get S&P 500 symbols from database"""
        try:
            conn = LoaderHelper.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
            return symbols
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []

    def process_symbols_parallel(
        self,
        symbols: List[str],
        process_func: Callable,
        batch_size: int = 10
    ) -> Dict[str, Any]:
        """
        Process symbols in parallel with proper error handling

        Args:
            symbols: List of ticker symbols
            process_func: Function that takes symbol and returns data or None
            batch_size: Batch size for committing to DB

        Returns:
            Dict with results and statistics
        """
        results = []

        logger.info(f"Processing {len(symbols)} symbols with {self.max_workers} workers")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(process_func, symbol): symbol
                for symbol in symbols
            }

            completed = 0
            for future in as_completed(futures):
                symbol = futures[future]
                completed += 1

                try:
                    data = future.result(timeout=5)
                    if data is not None:
                        results.append(data)
                        self.successful_symbols.append(symbol)
                    else:
                        self.skipped_symbols.append(symbol)
                except Exception as e:
                    logger.warning(f"[{symbol}] Failed: {str(e)[:50]}")
                    self.failed_symbols.append(symbol)

                if completed % 50 == 0:
                    logger.info(f"  Progress: {completed}/{len(symbols)}")

        return {
            'results': results,
            'successful': len(self.successful_symbols),
            'skipped': len(self.skipped_symbols),
            'failed': len(self.failed_symbols),
        }

    def batch_insert(
        self,
        table: str,
        data: List[Dict],
        columns: List[str],
        batch_size: int = 100
    ) -> int:
        """
        Insert data in batches

        Args:
            table: Table name
            data: List of dictionaries
            columns: Column names
            batch_size: Rows per batch

        Returns:
            Number of rows inserted
        """
        if not data:
            return 0

        conn = self.get_db_connection()
        cur = conn.cursor()

        inserted = 0
        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]
            try:
                # Convert dicts to tuples in correct column order
                rows = [tuple(d.get(col) for col in columns) for d in batch]

                placeholders = ','.join(['%s'] * len(columns))
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

                execute_values(cur, sql, rows, page_size=1000)
                inserted += len(batch)
            except Exception as e:
                logger.error(f"Batch insert failed: {e}")

        conn.commit()
        cur.close()
        conn.close()

        return inserted

    def report(self, loader_name: str):
        """Log final report"""
        logger.info(f"\n{'='*60}")
        logger.info(f"{loader_name} COMPLETED")
        logger.info(f"{'='*60}")
        logger.info(f"✅ Successful: {len(self.successful_symbols)}")
        logger.info(f"⚠️  Skipped: {len(self.skipped_symbols)}")
        logger.info(f"❌ Failed: {len(self.failed_symbols)}")

        if self.failed_symbols and len(self.failed_symbols) <= 20:
            logger.info(f"\nFailed symbols: {', '.join(self.failed_symbols)}")


def safe_yfinance_call(symbol: str, attr: str, timeout_sec: int = 5) -> Optional[Any]:
    """
    Safely get yfinance data with timeout and error handling

    Args:
        symbol: Ticker symbol
        attr: Attribute to fetch (e.g., 'info', 'analyst_info')
        timeout_sec: Timeout in seconds

    Returns:
        Data or None if timeout/error
    """
    try:
        import yfinance as yf
        from threading import Thread

        ticker = yf.Ticker(symbol)
        result = [None]

        def get_attr():
            try:
                result[0] = getattr(ticker, attr)
            except Exception:
                result[0] = None

        thread = Thread(target=get_attr, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            # Thread is still running - timeout
            return None

        return result[0] if result[0] else None

    except Exception as e:
        logger.debug(f"[{symbol}] yfinance error: {str(e)[:50]}")
        return None
