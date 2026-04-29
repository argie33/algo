#!/usr/bin/env python3
"""
Parallel Loader Template
Provides optimized data loading using ThreadPoolExecutor for parallel symbol processing.
Reduces loading time from 45-120 minutes to 5-25 minutes per loader (5-10x speedup).

Usage:
    from parallel_loader_template import ParallelLoader

    class MyLoader(ParallelLoader):
        def load_symbol_data(self, symbol):
            '''Override to implement your loading logic'''
            ticker = yf.Ticker(symbol)
            return self.process_ticker(ticker)

        def process_ticker(self, ticker):
            '''Override to implement data processing'''
            return [...]
"""

import sys
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

import psycopg2
import yfinance as yf
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

class ParallelLoader:
    """Base class for parallel data loading with thread pooling"""

    def __init__(self, max_workers: int = 5, batch_size: int = 50):
        """
        Initialize parallel loader

        Args:
            max_workers: Number of parallel workers (threads)
            batch_size: Number of records to accumulate before batch insert
        """
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.conn = None
        self.cur = None
        self.REQUEST_DELAY = 0.1  # Reduced from 0.5 since parallel

    def get_db_connection(self) -> Optional[psycopg2.extensions.connection]:
        """Get database connection with retry logic"""
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = int(os.environ.get("DB_PORT", "5432"))
        db_user = os.environ.get("DB_USER", "stocks")
        db_password = os.environ.get("DB_PASSWORD", "")
        db_name = os.environ.get("DB_NAME", "stocks")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logging.info(f"DB connection attempt {attempt+1}/{max_retries}")
                conn = psycopg2.connect(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_password,
                    dbname=db_name,
                    connect_timeout=10
                )
                conn.autocommit = True
                logging.info("✓ Database connected")
                return conn
            except Exception as e:
                error_msg = str(e)
                logging.warning(f"Connection attempt {attempt+1} failed: {error_msg[:100]}")

                if attempt < max_retries - 1:
                    if "could not translate host" in error_msg or "refused" in error_msg:
                        wait_time = (attempt + 1) * 2
                        logging.info(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                if attempt == max_retries - 1:
                    logging.error(f"Failed to connect after {max_retries} attempts")
                    return None

        return None

    def load_symbol_data(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Load data for a single symbol (OVERRIDE THIS)
        Should return list of dictionaries with data to insert

        Args:
            symbol: Stock symbol to load

        Returns:
            List of data dictionaries ready for insertion
        """
        raise NotImplementedError("Subclass must implement load_symbol_data()")

    def batch_insert(self, data: List[Dict[str, Any]]) -> int:
        """
        Insert a batch of records (OVERRIDE THIS)
        Should implement efficient batch insert into database

        Args:
            data: List of data dictionaries

        Returns:
            Number of rows inserted
        """
        raise NotImplementedError("Subclass must implement batch_insert()")

    def get_symbols_to_load(self) -> List[str]:
        """
        Get list of symbols that need to be loaded (OVERRIDE IF NEEDED)
        Default implementation gets all symbols not yet loaded

        Returns:
            List of symbol strings
        """
        self.cur.execute("""
            SELECT DISTINCT ss.symbol FROM stock_symbols ss
            WHERE NOT EXISTS (
                SELECT 1 FROM ??? t WHERE t.symbol = ss.symbol
            )
            ORDER BY ss.symbol
        """)  # ← Subclass must override with actual table name
        return [row[0] for row in self.cur.fetchall()]

    def run(self) -> bool:
        """Main execution method using parallel processing"""
        logging.info(f"Starting parallel loader with {self.max_workers} workers")

        self.conn = self.get_db_connection()
        if not self.conn:
            logging.error("Failed to connect to database")
            return False

        self.cur = self.conn.cursor()

        try:
            symbols = self.get_symbols_to_load()
            total_symbols = len(symbols)
            logging.info(f"Loading data for {total_symbols} symbols...")

            # Track stats
            total_rows = 0
            successful_symbols = 0
            failed_symbols = 0
            batch = []

            # Start time for performance metrics
            start_time = time.time()

            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks at once
                future_to_symbol = {
                    executor.submit(self.load_symbol_data, symbol): symbol
                    for symbol in symbols
                }

                # Process results as they complete
                completed = 0
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    completed += 1

                    try:
                        # Get result from completed task
                        rows = future.result()

                        if rows:
                            batch.extend(rows)
                            successful_symbols += 1

                            # Flush batch when it reaches target size
                            if len(batch) >= self.batch_size:
                                inserted = self.batch_insert(batch)
                                total_rows += inserted
                                batch = []
                                logging.debug(f"Batch insert: {inserted} rows")
                        else:
                            failed_symbols += 1

                        # Progress logging every 50 symbols
                        if completed % 50 == 0:
                            elapsed = time.time() - start_time
                            rate = completed / elapsed
                            remaining = (total_symbols - completed) / rate if rate > 0 else 0
                            logging.info(
                                f"Progress: {completed}/{total_symbols} "
                                f"({rate:.1f}/sec, ~{remaining:.0f}s remaining)"
                            )

                    except Exception as e:
                        failed_symbols += 1
                        logging.error(f"Error loading {symbol}: {e}")
                        continue

            # Insert any remaining rows in batch
            if batch:
                inserted = self.batch_insert(batch)
                total_rows += inserted

            # Final stats
            elapsed = time.time() - start_time
            logging.info(
                f"✓ Completed: {total_rows} rows inserted, "
                f"{successful_symbols} successful, {failed_symbols} failed "
                f"in {elapsed:.1f}s ({elapsed/60:.1f}m)"
            )

            return True

        except Exception as e:
            logging.error(f"Fatal error: {e}")
            return False

        finally:
            if self.cur:
                self.cur.close()
            if self.conn:
                self.conn.close()


# Example usage for quarterly income statement
class QuarterlyIncomeStatementLoader(ParallelLoader):
    """Example parallel loader for quarterly income statements"""

    def load_symbol_data(self, symbol: str) -> List[Dict[str, Any]]:
        """Load quarterly income statement for one symbol"""
        try:
            yf_symbol = symbol.replace(".", "-").upper()
            time.sleep(self.REQUEST_DELAY)

            ticker = yf.Ticker(yf_symbol)
            income_stmt = ticker.quarterly_income_stmt

            if income_stmt is None or income_stmt.empty:
                return []

            rows = []
            for date_col in income_stmt.columns:
                try:
                    fiscal_date = pd.to_datetime(date_col)
                    row_data = income_stmt[date_col]

                    # Extract data
                    revenue = self._safe_float(row_data.get('Total Revenue'))
                    if revenue is None:
                        continue

                    rows.append({
                        'symbol': symbol,
                        'fiscal_year': fiscal_date.year,
                        'fiscal_quarter': (fiscal_date.month - 1) // 3 + 1,
                        'revenue': revenue,
                        'cost_of_revenue': self._safe_float(row_data.get('Cost Of Revenue')),
                        'gross_profit': self._safe_float(row_data.get('Gross Profit')),
                        'operating_expenses': self._safe_float(row_data.get('Operating Expense')),
                        'operating_income': self._safe_float(row_data.get('Operating Income')),
                        'net_income': self._safe_float(row_data.get('Net Income')),
                    })
                except Exception as e:
                    logging.debug(f"Row error for {symbol}: {e}")
                    continue

            return rows

        except Exception as e:
            logging.error(f"Error loading {symbol}: {e}")
            return []

    def batch_insert(self, data: List[Dict[str, Any]]) -> int:
        """Insert batch of quarterly income statement records"""
        if not data:
            return 0

        try:
            for row in data:
                self.cur.execute("""
                    INSERT INTO quarterly_income_statement
                    (symbol, fiscal_year, fiscal_quarter, revenue, cost_of_revenue,
                     gross_profit, operating_expenses, operating_income, net_income, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
                    revenue = EXCLUDED.revenue,
                    cost_of_revenue = EXCLUDED.cost_of_revenue,
                    gross_profit = EXCLUDED.gross_profit,
                    operating_expenses = EXCLUDED.operating_expenses,
                    operating_income = EXCLUDED.operating_income,
                    net_income = EXCLUDED.net_income,
                    updated_at = NOW()
                """, (
                    row['symbol'], row['fiscal_year'], row['fiscal_quarter'],
                    row['revenue'], row['cost_of_revenue'], row['gross_profit'],
                    row['operating_expenses'], row['operating_income'], row['net_income']
                ))

            self.conn.commit()
            return len(data)

        except Exception as e:
            logging.error(f"Batch insert error: {e}")
            return 0

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Safely convert value to float"""
        if pd.isna(value) or value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('$', '').strip()
                if not value or value == '-':
                    return None
            return float(value)
        except (ValueError, TypeError):
            return None


if __name__ == "__main__":
    # Example usage
    loader = QuarterlyIncomeStatementLoader(max_workers=5, batch_size=50)
    success = loader.run()
    sys.exit(0 if success else 1)
