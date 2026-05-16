#!/usr/bin/env python3
"""
Quality Metrics Loader

Computes fundamental quality metrics from annual financials:
- PEG: Price/Earnings to Growth ratio
- Earnings Growth: YoY earnings growth rate
- ROE: Return on Equity
- Debt/Equity: Financial leverage
- Free Cash Flow Yield: FCF/Market Cap

Requires: annual_income_statement, annual_balance_sheet, annual_cash_flow, key_metrics populated
"""

import os
import psycopg2
import logging
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
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
        """Get list of all active symbols."""
        try:
            self.cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
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
                else:
                    self.failed_symbols.append(symbol)
            except Exception as e:
                logger.warning(f"{symbol}: {e}")
                self.failed_symbols.append(symbol)

        self.conn.commit()
        logger.info(f"Loaded quality metrics: {self.loaded_count}/{len(symbols)} symbols")
        if self.failed_symbols:
            logger.warning(f"Failed ({len(self.failed_symbols)}): {', '.join(self.failed_symbols[:10])}")

    def _compute_metrics(self, symbol: str) -> Optional[Dict]:
        """Compute quality metrics for a symbol from annual financials."""
        try:
            # Get latest annual financials
            self.cur.execute("""
                SELECT fiscal_year, revenue, net_income, operating_cash_flow,
                       investing_cash_flow, free_cash_flow
                FROM annual_cash_flow
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 2
            """, (symbol,))
            cf_rows = self.cur.fetchall()
            if not cf_rows:
                return None

            # Get balance sheet for equity
            self.cur.execute("""
                SELECT fiscal_year, total_liabilities, stockholders_equity
                FROM annual_balance_sheet
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 1
            """, (symbol,))
            bs_row = self.cur.fetchone()
            if not bs_row:
                return None

            # Get key metrics for market cap and PE
            self.cur.execute("""
                SELECT market_cap, pe_ratio
                FROM key_metrics
                WHERE ticker = %s OR ticker = %s
                LIMIT 1
            """, (symbol, symbol.lower()))
            km_row = self.cur.fetchone()

            market_cap = km_row[0] if km_row and km_row[0] else None
            pe_ratio = km_row[1] if km_row and km_row[1] else None

            latest_cf = cf_rows[0]
            prev_cf = cf_rows[1] if len(cf_rows) > 1 else None

            metrics = {}

            # ROE: Net Income / Stockholders Equity
            if bs_row[2] and bs_row[2] > 0:
                # Need net income - get from income statement
                self.cur.execute("""
                    SELECT net_income FROM annual_income_statement
                    WHERE symbol = %s AND fiscal_year = %s
                """, (symbol, latest_cf[0]))
                ni_row = self.cur.fetchone()
                if ni_row and ni_row[0]:
                    metrics['roe_pct'] = round((ni_row[0] / bs_row[2]) * 100, 2)
                else:
                    metrics['roe_pct'] = None
            else:
                metrics['roe_pct'] = None

            # Debt/Equity
            if bs_row[2] and bs_row[2] > 0:
                metrics['debt_to_equity'] = round(bs_row[1] / bs_row[2], 2)
            else:
                metrics['debt_to_equity'] = None

            # Free Cash Flow Yield: FCF / Market Cap
            if latest_cf[5] and market_cap and market_cap > 0:  # free_cash_flow
                metrics['fcf_yield_pct'] = round((latest_cf[5] / market_cap) * 100, 2)
            else:
                metrics['fcf_yield_pct'] = None

            # Earnings Growth: YoY net income growth
            if prev_cf and latest_cf[1]:  # revenue
                self.cur.execute("""
                    SELECT net_income FROM annual_income_statement
                    WHERE symbol = %s AND fiscal_year IN (%s, %s)
                    ORDER BY fiscal_year DESC
                """, (symbol, latest_cf[0], prev_cf[0]))
                ni_rows = self.cur.fetchall()
                if len(ni_rows) == 2 and ni_rows[1][0]:  # Have both years
                    ni_latest = ni_rows[0][0]
                    ni_prev = ni_rows[1][0]
                    if ni_latest and ni_prev and ni_prev != 0:
                        growth = ((ni_latest - ni_prev) / abs(ni_prev)) * 100
                        metrics['earnings_growth_pct'] = round(growth, 2)
                    else:
                        metrics['earnings_growth_pct'] = None
                else:
                    metrics['earnings_growth_pct'] = None
            else:
                metrics['earnings_growth_pct'] = None

            # PEG: PE Ratio / Growth Rate (if both available)
            if pe_ratio and pe_ratio > 0 and metrics.get('earnings_growth_pct') and metrics['earnings_growth_pct'] > 0:
                metrics['peg_ratio'] = round(pe_ratio / metrics['earnings_growth_pct'], 2)
            else:
                metrics['peg_ratio'] = None

            # Quality Score: composite (0-100)
            # High ROE + low debt + positive growth + reasonable PE = high quality
            quality_score = 50.0  # baseline
            components = 0

            if metrics.get('roe_pct') is not None and metrics['roe_pct'] > 0:
                quality_score += min(20, metrics['roe_pct'] / 5)  # max +20 for high ROE
                components += 1

            if metrics.get('debt_to_equity') is not None:
                if metrics['debt_to_equity'] < 1:
                    quality_score += 10
                    components += 1

            if metrics.get('earnings_growth_pct') is not None and metrics['earnings_growth_pct'] > 0:
                quality_score += min(15, metrics['earnings_growth_pct'] / 3)
                components += 1

            if metrics.get('peg_ratio') is not None and 0 < metrics['peg_ratio'] < 2:
                quality_score += 10
                components += 1

            metrics['quality_score'] = round(min(100, quality_score), 1)

            return metrics

        except Exception as e:
            logger.warning(f"{symbol}: compute_metrics failed: {e}")
            return None

    def _insert_metrics(self, symbol: str, metrics: Dict):
        """Insert quality metrics into database."""
        try:
            self.cur.execute("""
                DELETE FROM quality_metrics WHERE symbol = %s
            """, (symbol,))

            self.cur.execute("""
                INSERT INTO quality_metrics (
                    symbol, roe_pct, debt_to_equity, fcf_yield_pct,
                    earnings_growth_pct, peg_ratio, quality_score,
                    computed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                symbol,
                metrics.get('roe_pct'),
                metrics.get('debt_to_equity'),
                metrics.get('fcf_yield_pct'),
                metrics.get('earnings_growth_pct'),
                metrics.get('peg_ratio'),
                metrics.get('quality_score'),
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
