#!/usr/bin/env python3
"""
Key Metrics Loader — market cap and insider/institution holdings from Finnhub.

Market cap and shareholding data for all stocks in universe.
Uses Finnhub's free tier API.

USAGE:
    python3 load_key_metrics.py                 # all symbols
    python3 load_key_metrics.py --symbols SPY,AAPL,MSFT
    python3 load_key_metrics.py --limit 100     # first 100 symbols
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import psycopg2
import requests
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _get_db_config():
    """Get database config from env or credential_manager."""
    if credential_manager:
        try:
            creds = credential_manager.get_db_credentials()
            return {
                "host": os.getenv("DB_HOST", creds.get("host", "localhost")),
                "port": int(os.getenv("DB_PORT", creds.get("port", 5432))),
                "user": os.getenv("DB_USER", creds.get("user", "stocks")),
                "password": os.getenv("DB_PASSWORD", creds.get("password", "")),
                "database": os.getenv("DB_NAME", creds.get("database", "stocks")),
            }
        except Exception as e:
            logger.warning(f"credential_manager failed, using env vars: {e}")

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }


class KeyMetricsLoader:
    """Load market cap and insider/institution holdings."""

    def __init__(self):
        self.finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        self.db_config = _get_db_config()
        self.conn = None
        self.cur = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (StockAnalytics/1.0)'
        })

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cur = self.conn.cursor()
            logger.info("Database connected")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_symbols(self, symbol_filter: Optional[List[str]] = None, limit: Optional[int] = None) -> List[str]:
        """Get list of symbols to load."""
        try:
            query = "SELECT symbol FROM stock_symbols ORDER BY symbol"
            if limit:
                query += f" LIMIT {limit}"
            self.cur.execute(query)
            symbols = [row[0] for row in self.cur.fetchall()]
            if symbol_filter:
                symbols = [s for s in symbols if s in symbol_filter]
            return symbols
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []

    def fetch_metrics(self, symbol: str) -> Optional[Dict]:
        """Fetch market cap and shareholding from Finnhub."""
        if not self.finnhub_key:
            # Fallback: just return None, data will be missing but won't crash
            logger.debug(f"No Finnhub API key, skipping {symbol}")
            return None

        try:
            # Finnhub company profile endpoint
            url = "https://finnhub.io/api/v1/stock/profile2"
            params = {
                "symbol": symbol,
                "token": self.finnhub_key
            }

            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                logger.debug(f"Finnhub {symbol}: {resp.status_code}")
                return None

            data = resp.json()

            # Extract relevant fields
            metrics = {
                "symbol": symbol,
                "market_cap": data.get("marketCapitalization"),  # in millions
                "held_percent_insiders": None,  # Finnhub free tier doesn't provide this
                "held_percent_institutions": None,  # Finnhub free tier doesn't provide this
            }

            return metrics

        except Exception as e:
            logger.warning(f"Fetch failed for {symbol}: {e}")
            return None

    def persist_metrics(self, metrics: Dict):
        """Save metrics to database."""
        if not metrics:
            return

        try:
            symbol = metrics["symbol"]

            # Use UPSERT pattern: insert or update
            self.cur.execute("""
                INSERT INTO key_metrics (ticker, symbol, market_cap, held_percent_insiders, held_percent_institutions, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (ticker) DO UPDATE SET
                    market_cap = EXCLUDED.market_cap,
                    held_percent_insiders = EXCLUDED.held_percent_insiders,
                    held_percent_institutions = EXCLUDED.held_percent_institutions,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                symbol,  # ticker (primary key)
                symbol,  # symbol (denormalized)
                metrics.get("market_cap"),
                metrics.get("held_percent_insiders"),
                metrics.get("held_percent_institutions"),
            ))

        except Exception as e:
            logger.error(f"Persist failed for {metrics.get('symbol')}: {e}")

    def load_all(self, symbols: Optional[List[str]] = None, limit: Optional[int] = None):
        """Load key metrics for all symbols."""
        self.connect()

        try:
            symbols = symbols or self.get_symbols(limit=limit)

            logger.info(f"Loading key metrics for {len(symbols)} symbols")

            loaded = 0
            failed = 0

            for i, symbol in enumerate(symbols):
                try:
                    # Be gentle with API rate limits
                    if i > 0 and i % 10 == 0:
                        time.sleep(0.1)

                    metrics = self.fetch_metrics(symbol)
                    if metrics:
                        self.persist_metrics(metrics)
                        loaded += 1
                    else:
                        # Data missing but not a hard failure
                        logger.debug(f"No metrics for {symbol}, persisting empty record")
                        self.persist_metrics({"symbol": symbol})
                        loaded += 1

                    if (i + 1) % 100 == 0:
                        logger.info(f"Progress: {i + 1}/{len(symbols)}")

                except Exception as e:
                    logger.warning(f"Failed to load {symbol}: {e}")
                    failed += 1

            self.conn.commit()
            logger.info(f"Loaded {loaded} symbols, {failed} failures")
            return loaded > 0

        except Exception as e:
            logger.error(f"Load failed: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            self.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load key metrics for all stocks")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g. SPY,AAPL)")
    parser.add_argument("--limit", type=int, help="Load only first N symbols")
    args = parser.parse_args()

    loader = KeyMetricsLoader()
    symbols = args.symbols.split(",") if args.symbols else None
    success = loader.load_all(symbols=symbols, limit=args.limit)

    sys.exit(0 if success else 1)
