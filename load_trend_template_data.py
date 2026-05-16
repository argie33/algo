#!/usr/bin/env python3
"""
Trend Template Data Loader - Minervini/Weinstein trend scoring

Populates trend_template_data with:
- minervini_trend_score (0-8 point template)
- percent_from_52w_low/high
- trend_strength, trend_direction
- trend_confirmation flag
- weinstein_stage (1-4)

Deployment: AWS ECS with EventBridge scheduler at 4:15am ET daily

Run:
    python3 load_trend_template_data.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import argparse
import logging
import os
from credential_helper import get_db_password, get_db_config
import sys
from datetime import date, timedelta
from typing import List, Optional, Dict, Any

from optimal_loader import OptimalLoader
try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

_credential_manager = get_credential_manager()

from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class TrendTemplateDataLoader(OptimalLoader):
    table_name = "trend_template_data"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute trend template metrics for symbols."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=365)
        else:
            start = since + timedelta(days=1)

        if start > end:
            return None

        rows = []
        try:
            from algo_signals import SignalComputer
            sig = SignalComputer()
            sig.connect()

            for current_date in self._date_range(start, end):
                try:
                    minervini_result = sig.minervini_trend_template(symbol, current_date)
                    weinstein_stage = sig.weinstein_stage(symbol, current_date)

                    if minervini_result and weinstein_stage is not None:
                        trend_score = minervini_result.get("score", 0)
                        trend_direction = "up" if minervini_result.get("price_above_150sma") else "down"
                        trend_confirmation = minervini_result.get("score", 0) >= 4

                        row = {
                            "symbol": symbol,
                            "date": str(current_date),
                            "minervini_trend_score": float(trend_score),
                            "percent_from_52w_low": float(minervini_result.get("percent_from_52w_low", 0)),
                            "percent_from_52w_high": float(minervini_result.get("percent_from_52w_high", 0)),
                            "trend_direction": trend_direction,
                            "consolidation_flag": trend_confirmation,
                            "weinstein_stage": int(weinstein_stage),
                        }
                        rows.append(row)
                except Exception as e:
                    logging.debug(f"[{symbol}] Failed to compute trend for {current_date}: {e}")
                    continue

            sig.disconnect()
        except ImportError:
            logging.warning("algo_signals module not available; returning empty")
            return None
        except Exception as e:
            logging.error(f"Error computing trend data for {symbol}: {e}")
            return None

        return rows if rows else None

    def _date_range(self, start: date, end: date):
        """Yield each trading day in range (skip weekends)."""
        current = start
        while current <= end:
            if current.weekday() < 5:
                yield current
            current += timedelta(days=1)

    def _validate_row(self, row: dict) -> bool:
        """Validate trend data row."""
        if not super()._validate_row(row):
            return False
        try:
            return (
                0 <= float(row["minervini_trend_score"]) <= 8
                and 1 <= int(row["weinstein_stage"]) <= 4
            )
        except (KeyError, TypeError, ValueError):
            return False


def get_active_symbols() -> List[str]:
    """Pull active symbols from the canonical universe table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=_get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT EXISTS (SELECT 1 FROM information_schema.tables
                           WHERE table_schema='public' AND table_name='stock_symbols')""")
            if cur.fetchone()[0]:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            else:
                cur.execute("SELECT DISTINCT ticker FROM company_profile ORDER BY ticker")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Trend template data loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = TrendTemplateDataLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
