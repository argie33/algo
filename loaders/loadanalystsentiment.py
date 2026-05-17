#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Analyst Sentiment Loader - Optimal Pattern.

Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadanalystsentiment.py [--symbols AAPL,MSFT] [--parallelism 8]
"""


try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
import logging
from config.credential_helper import get_db_password, get_db_config
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

from utils.optimal_loader import OptimalLoader

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class AnalystSentimentLoader(OptimalLoader):
    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch analyst recommendations from yfinance."""
        try:
            import yfinance as yf
        except ImportError:
            return None

        try:
            ticker = yf.Ticker(symbol)
            recs = ticker.recommendations

            if recs is None or recs.empty:
                return None

            results = []
            for idx, row in recs.iterrows():
                # yfinance returns DatetimeIndex and columns: Firm, To Grade, From Grade, Action
                rec_date = idx.date() if hasattr(idx, 'date') else idx
                results.append({
                    'symbol': symbol,
                    'date': rec_date,
                    'firm': row.get('Firm', ''),
                    'to_grade': row.get('To Grade', ''),
                    'from_grade': row.get('From Grade'),
                    'action': row.get('Action', '')
                })

            return results if results else None
        except Exception as e:
            return None

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        return super()._validate_row(row)


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal analyst_sentiment loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = AnalystSentimentLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

