#!/usr/bin/env python3
"""
Value Metrics Loader

Computes value metrics from financials:
- Price to Book: Market Cap / Stockholders Equity
- Price to Sales: Market Cap / Revenue
- Dividend Yield: Annual Dividend / Stock Price
- Value Score: Composite (0-100)

Requires: annual_balance_sheet, annual_income_statement, key_metrics populated
"""

import os
import psycopg2
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("load_value_metrics")

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

class ValueMetricsLoader:
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
        """Get list of all active symbols."""
        try:
            self.cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [row[0] for row in self.cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []

    def load_value_metrics(self):
        """Load value metrics for all symbols."""
        symbols = self.get_symbols()
        logger.info(f"Loading value metrics for {len(symbols)} symbols")

        for symbol in symbols:
            try:
                metrics = self._compute_metrics(symbol)
                if metrics:
                    self._insert_metrics(symbol, metrics)
                    self.loaded_count += 1
                else:
                    self.failed_symbols.append(symbol)
            except Exception as e:
                logger.warning(f"{symbol}: {e}")
                self.failed_symbols.append(symbol)

        self.conn.commit()
        logger.info(f"Loaded value metrics: {self.loaded_count}/{len(symbols)} symbols")
        if self.failed_symbols:
            logger.warning(f"Failed ({len(self.failed_symbols)}): {', '.join(self.failed_symbols[:10])}")

    def _compute_metrics(self, symbol: str) -> Optional[Dict]:
        """Compute value metrics for a symbol."""
        try:
            # Get latest balance sheet for equity
            self.cur.execute("""
                SELECT stockholders_equity FROM annual_balance_sheet
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            bs_row = self.cur.fetchone()
            if not bs_row or not bs_row[0]:
                return None

            # Get latest income statement for revenue
            self.cur.execute("""
                SELECT revenue FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            is_row = self.cur.fetchone()
            if not is_row or not is_row[0]:
                return None

            # Get market cap and price
            self.cur.execute("""
                SELECT market_cap FROM key_metrics
                WHERE ticker = %s OR ticker = %s
                LIMIT 1
            """, (symbol, symbol.lower()))
            km_row = self.cur.fetchone()
            market_cap = km_row[0] if km_row and km_row[0] else None

            if not market_cap or market_cap <= 0:
                return None

            metrics = {}
            equity = bs_row[0]
            revenue = is_row[0]

            # Price to Book: Market Cap / Stockholders Equity
            if equity and equity > 0:
                metrics['pb_ratio'] = round(market_cap / equity, 2)
            else:
                metrics['pb_ratio'] = None

            # Price to Sales: Market Cap / Revenue
            if revenue and revenue > 0:
                metrics['ps_ratio'] = round(market_cap / revenue, 2)
            else:
                metrics['ps_ratio'] = None

            # Dividend Yield (if available - would need dividend data)
            # For now, default to None (would need dividend loader)
            metrics['dividend_yield_pct'] = None

            # Value Score: composite (0-100)
            # Low PB + low PS + high dividend yield = good value
            value_score = 50.0  # baseline
            components = 0

            if metrics.get('pb_ratio') is not None:
                pb = metrics['pb_ratio']
                if 0 < pb < 1:  # Trading below book
                    value_score += 25
                    components += 1
                elif 1 <= pb <= 3:  # Reasonable PB
                    value_score += 15
                    components += 1
                elif pb > 3:  # High PB
                    value_score -= 5
                    components += 1

            if metrics.get('ps_ratio') is not None:
                ps = metrics['ps_ratio']
                if 0 < ps < 1:  # Cheap relative to sales
                    value_score += 25
                    components += 1
                elif 1 <= ps <= 3:  # Reasonable PS
                    value_score += 15
                    components += 1
                elif ps > 3:  # Expensive
                    value_score -= 5
                    components += 1

            metrics['value_score'] = round(min(100, max(0, value_score)), 1)

            return metrics

        except Exception as e:
            logger.warning(f"{symbol}: compute_metrics failed: {e}")
            return None

    def _insert_metrics(self, symbol: str, metrics: Dict):
        """Insert value metrics into database."""
        try:
            self.cur.execute("""
                DELETE FROM value_metrics WHERE symbol = %s
            """, (symbol,))

            self.cur.execute("""
                INSERT INTO value_metrics (
                    symbol, pb_ratio, ps_ratio, dividend_yield_pct,
                    value_score, computed_at
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                symbol,
                metrics.get('pb_ratio'),
                metrics.get('ps_ratio'),
                metrics.get('dividend_yield_pct'),
                metrics.get('value_score'),
            ))
        except Exception as e:
            logger.error(f"{symbol}: insert failed: {e}")
            raise

def main():
    loader = ValueMetricsLoader()
    try:
        loader.connect()
        loader.load_value_metrics()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        loader.disconnect()
    return 0

if __name__ == '__main__':
    exit(main())
