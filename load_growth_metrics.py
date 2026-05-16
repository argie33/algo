#!/usr/bin/env python3
"""
Growth Metrics Loader

Computes growth metrics from annual financials:
- Revenue Growth: YoY revenue growth
- EPS Growth: YoY earnings per share growth
- Gross Margin Expansion: Change in gross margin
- Operating Margin Trend: Change in operating margin
- Growth Score: Composite (0-100)

Requires: annual_income_statement populated
"""

import os
import psycopg2
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("load_growth_metrics")

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

class GrowthMetricsLoader:
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

    def load_growth_metrics(self):
        """Load growth metrics for all symbols."""
        symbols = self.get_symbols()
        logger.info(f"Loading growth metrics for {len(symbols)} symbols")

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
        logger.info(f"Loaded growth metrics: {self.loaded_count}/{len(symbols)} symbols")
        if self.failed_symbols:
            logger.warning(f"Failed ({len(self.failed_symbols)}): {', '.join(self.failed_symbols[:10])}")

    def _compute_metrics(self, symbol: str) -> Optional[Dict]:
        """Compute growth metrics from annual financials."""
        try:
            self.cur.execute("""
                SELECT fiscal_year, revenue, cost_of_revenue, gross_profit,
                       operating_income, net_income, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 2
            """, (symbol,))
            rows = self.cur.fetchall()
            if not rows or len(rows) < 1:
                return None

            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None

            metrics = {}

            # Revenue Growth: YoY
            if prev and latest[1] and prev[1]:  # revenue
                rev_growth = ((latest[1] - prev[1]) / abs(prev[1])) * 100
                metrics['revenue_growth_pct'] = round(rev_growth, 2)
            else:
                metrics['revenue_growth_pct'] = None

            # EPS Growth: YoY
            if prev and latest[6] and prev[6]:  # EPS
                eps_growth = ((latest[6] - prev[6]) / abs(prev[6])) * 100
                metrics['eps_growth_pct'] = round(eps_growth, 2)
            else:
                metrics['eps_growth_pct'] = None

            # Gross Margin: (Gross Profit / Revenue) * 100
            if latest[1] and latest[1] > 0 and latest[3]:  # revenue, gross_profit
                latest_gm = (latest[3] / latest[1]) * 100
                metrics['gross_margin_pct'] = round(latest_gm, 2)

                # Gross Margin Expansion
                if prev and prev[1] and prev[1] > 0 and prev[3]:
                    prev_gm = (prev[3] / prev[1]) * 100
                    metrics['gross_margin_expansion_pct'] = round(latest_gm - prev_gm, 2)
                else:
                    metrics['gross_margin_expansion_pct'] = None
            else:
                metrics['gross_margin_pct'] = None
                metrics['gross_margin_expansion_pct'] = None

            # Operating Margin: (Operating Income / Revenue) * 100
            if latest[1] and latest[1] > 0 and latest[4] is not None:  # revenue, operating_income
                latest_om = (latest[4] / latest[1]) * 100
                metrics['operating_margin_pct'] = round(latest_om, 2)

                # Operating Margin Trend
                if prev and prev[1] and prev[1] > 0 and prev[4] is not None:
                    prev_om = (prev[4] / prev[1]) * 100
                    metrics['operating_margin_trend_pct'] = round(latest_om - prev_om, 2)
                else:
                    metrics['operating_margin_trend_pct'] = None
            else:
                metrics['operating_margin_pct'] = None
                metrics['operating_margin_trend_pct'] = None

            # Growth Score: composite (0-100)
            # Strong revenue growth + EPS growth + margin expansion = high growth
            growth_score = 50.0  # baseline
            components = 0

            if metrics.get('revenue_growth_pct') is not None:
                growth = metrics['revenue_growth_pct']
                if growth > 20:  # Strong growth
                    growth_score += min(20, growth / 2)
                    components += 1
                elif growth > 0:
                    growth_score += growth / 2
                    components += 1
                elif growth < 0:
                    growth_score -= min(10, abs(growth) / 3)
                    components += 1

            if metrics.get('eps_growth_pct') is not None:
                growth = metrics['eps_growth_pct']
                if growth > 20:
                    growth_score += min(20, growth / 2)
                    components += 1
                elif growth > 0:
                    growth_score += growth / 2
                    components += 1
                elif growth < 0:
                    growth_score -= min(10, abs(growth) / 3)
                    components += 1

            if metrics.get('gross_margin_expansion_pct') is not None and metrics['gross_margin_expansion_pct'] > 0:
                growth_score += min(10, metrics['gross_margin_expansion_pct'] * 2)
                components += 1

            if metrics.get('operating_margin_trend_pct') is not None and metrics['operating_margin_trend_pct'] > 0:
                growth_score += min(10, metrics['operating_margin_trend_pct'] * 2)
                components += 1

            metrics['growth_score'] = round(min(100, max(0, growth_score)), 1)

            return metrics

        except Exception as e:
            logger.warning(f"{symbol}: compute_metrics failed: {e}")
            return None

    def _insert_metrics(self, symbol: str, metrics: Dict):
        """Insert growth metrics into database."""
        try:
            self.cur.execute("""
                DELETE FROM growth_metrics WHERE symbol = %s
            """, (symbol,))

            self.cur.execute("""
                INSERT INTO growth_metrics (
                    symbol, revenue_growth_pct, eps_growth_pct,
                    gross_margin_pct, gross_margin_expansion_pct,
                    operating_margin_pct, operating_margin_trend_pct,
                    growth_score, computed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                symbol,
                metrics.get('revenue_growth_pct'),
                metrics.get('eps_growth_pct'),
                metrics.get('gross_margin_pct'),
                metrics.get('gross_margin_expansion_pct'),
                metrics.get('operating_margin_pct'),
                metrics.get('operating_margin_trend_pct'),
                metrics.get('growth_score'),
            ))
        except Exception as e:
            logger.error(f"{symbol}: insert failed: {e}")
            raise

def main():
    loader = GrowthMetricsLoader()
    try:
        loader.connect()
        loader.load_growth_metrics()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        loader.disconnect()
    return 0

if __name__ == '__main__':
    exit(main())
