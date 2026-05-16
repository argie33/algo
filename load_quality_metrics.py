#!/usr/bin/env python3
"""
Quality Metrics Loader

Computes fundamental quality metrics from annual financials:
- Operating Margin: Operating Income / Revenue
- Net Margin: Net Income / Revenue
- ROE: Return on Equity
- ROA: Return on Assets
- Debt/Equity: Financial leverage
- Current Ratio: Current Assets / Current Liabilities
- Quick Ratio: (Current Assets - Inventory) / Current Liabilities
- Interest Coverage: EBIT / Interest Expense

Requires: annual_income_statement, annual_balance_sheet populated
"""

import os
import psycopg2
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("load_quality_metrics")

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

from credential_helper import get_db_password

def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": get_db_password() or os.getenv("DB_PASSWORD", "postgres"),
        "database": os.getenv("DB_NAME", "stocks"),
    }

class QualityMetricsLoader:
    def __init__(self):
        self.config = get_db_config()
        self.conn = None
        self.cur = None
        self.loaded_count = 0
        self.failed_symbols = []

    def connect(self):
        try:
            self.conn = psycopg2.connect(**self.config)
            self.cur = self.conn.cursor()
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_symbols(self) -> List[str]:
        """Get list of symbols with both income AND balance sheet data."""
        try:
            # Only get symbols that have BOTH income statement and balance sheet
            self.cur.execute("""
                SELECT DISTINCT i.symbol
                FROM annual_income_statement i
                INNER JOIN annual_balance_sheet b ON i.symbol = b.symbol
                ORDER BY i.symbol
            """)
            return [row[0] for row in self.cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []

    def load_quality_metrics(self):
        """Load quality metrics for all symbols."""
        symbols = self.get_symbols()
        logger.info(f"Loading quality metrics for {len(symbols)} symbols")

        for symbol in symbols:
            try:
                metrics = self._compute_metrics(symbol)
                if metrics:
                    self._insert_metrics(symbol, metrics)
                    self.loaded_count += 1
            except Exception as e:
                logger.warning(f"{symbol}: {e}")
                self.failed_symbols.append(symbol)

        try:
            self.conn.commit()
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            self.conn.rollback()

        logger.info(f"Loaded quality metrics: {self.loaded_count}/{len(symbols)} symbols")

    def _compute_metrics(self, symbol: str) -> Optional[Dict]:
        """Compute quality metrics for a symbol from annual financials."""
        try:
            # Get latest balance sheet
            self.cur.execute("""
                SELECT total_assets, current_assets, total_liabilities,
                       current_liabilities, stockholders_equity
                FROM annual_balance_sheet
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            bs_row = self.cur.fetchone()
            if not bs_row:
                return None

            # Get latest income statement
            self.cur.execute("""
                SELECT revenue, net_income, operating_income
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            is_row = self.cur.fetchone()
            if not is_row:
                return None

            metrics = {}

            # Operating Margin
            if is_row[2] and is_row[0] and is_row[0] > 0:
                metrics['operating_margin'] = round((is_row[2] / is_row[0]) * 100, 4)
            else:
                metrics['operating_margin'] = None

            # Net Margin
            if is_row[1] and is_row[0] and is_row[0] > 0:
                metrics['net_margin'] = round((is_row[1] / is_row[0]) * 100, 4)
            else:
                metrics['net_margin'] = None

            # ROE: Net Income / Stockholders Equity
            if is_row[1] and bs_row[4] and bs_row[4] > 0:
                metrics['roe'] = round((is_row[1] / bs_row[4]) * 100, 4)
            else:
                metrics['roe'] = None

            # ROA: Net Income / Total Assets
            if is_row[1] and bs_row[0] and bs_row[0] > 0:
                metrics['roa'] = round((is_row[1] / bs_row[0]) * 100, 4)
            else:
                metrics['roa'] = None

            # Debt/Equity
            if bs_row[4] and bs_row[4] > 0:
                metrics['debt_to_equity'] = round(bs_row[2] / bs_row[4], 4)
            else:
                metrics['debt_to_equity'] = None

            # Current Ratio: Current Assets / Current Liabilities
            if bs_row[3] and bs_row[3] > 0 and bs_row[1]:
                metrics['current_ratio'] = round(bs_row[1] / bs_row[3], 4)
            else:
                metrics['current_ratio'] = None

            # Quick Ratio (simplified: current_assets / current_liabilities without inventory)
            # For now, use current_ratio as proxy
            metrics['quick_ratio'] = metrics['current_ratio']

            # Interest Coverage (would need interest expense data - skip for now)
            metrics['interest_coverage'] = None

            return metrics

        except Exception as e:
            logger.debug(f"{symbol}: compute_metrics failed: {e}")
            return None

    def _insert_metrics(self, symbol: str, metrics: Dict):
        """Insert quality metrics into database."""
        try:
            self.cur.execute("""
                INSERT INTO quality_metrics (
                    symbol, operating_margin, net_margin, roe, roa,
                    debt_to_equity, current_ratio, quick_ratio, interest_coverage
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    operating_margin = EXCLUDED.operating_margin,
                    net_margin = EXCLUDED.net_margin,
                    roe = EXCLUDED.roe,
                    roa = EXCLUDED.roa,
                    debt_to_equity = EXCLUDED.debt_to_equity,
                    current_ratio = EXCLUDED.current_ratio,
                    quick_ratio = EXCLUDED.quick_ratio,
                    interest_coverage = EXCLUDED.interest_coverage
            """, (
                symbol,
                metrics.get('operating_margin'),
                metrics.get('net_margin'),
                metrics.get('roe'),
                metrics.get('roa'),
                metrics.get('debt_to_equity'),
                metrics.get('current_ratio'),
                metrics.get('quick_ratio'),
                metrics.get('interest_coverage'),
            ))
        except Exception as e:
            logger.error(f"{symbol}: insert failed: {e}")
            raise

def main():
    loader = QualityMetricsLoader()
    try:
        loader.connect()
        loader.load_quality_metrics()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        loader.disconnect()
    return 0

if __name__ == '__main__':
    exit(main())
