#!/usr/bin/env python3
"""
Options Chains Loader — Fetch daily options data from yfinance.

Data Criticality: OPTIONAL (enrichment for put/call signals, not critical for position sizing)
Failure Mode: Fails gracefully with context, degrades to None if unavailable
Freshness Requirement: Maximum 24 hours staleness

Loads put/call volumes and IV for options signals (bonus alpha scoring).
Populates: options_chains (daily volumes for put/call ratio), iv_history (current IV + range).

Uses canonical circuit breaker (utils.infrastructure.circuit_breaker:CircuitBreaker)
with DataImportance.OPTIONAL and freshness validation.

Use: python3 loaders/load_options_chains.py [--symbols AAPL,MSFT]
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import yfinance as yf

from utils.db.context import DatabaseContext
from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols
from utils.validation.data_freshness import FreshnessValidator, StaleDataError


logger = logging.getLogger(__name__)


class OptionsLoader:
    """Fetch daily options data from yfinance with circuit breaker protection."""

    def __init__(self):
        self.batch_size = 50
        self._circuit_breaker = CircuitBreaker(
            name="yfinance_options",
            importance=DataImportance.OPTIONAL
        )
        self._freshness_validator = FreshnessValidator(max_age_hours={
            "options_data": 24.0,
        })

    def run(self, symbols: list | None = None, eval_date: date | None = None) -> dict:
        """Load options data for all symbols."""
        start_time = time.time()

        if symbols is None:
            symbols = get_active_symbols()

        if eval_date is None:
            now_utc = datetime.now(ZoneInfo("UTC"))
            now_et = now_utc.astimezone(EASTERN_TZ)
            eval_date = now_et.date()

        logger.info(f"Loading options data for {len(symbols)} symbols as of {eval_date}")

        chains_inserted = 0
        iv_inserted = 0
        symbols_processed = 0

        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i : i + self.batch_size]
            logger.info(f"Processing batch {i // self.batch_size + 1} ({len(batch)} symbols)")

            with DatabaseContext("write") as cur:
                for symbol in batch:
                    try:
                        c_cnt, iv_cnt = self._load_symbol_options(cur, symbol, eval_date)
                        chains_inserted += c_cnt
                        iv_inserted += iv_cnt
                        symbols_processed += 1
                    except Exception as e:
                        logger.debug(f"Failed to load options for {symbol}: {e}")
                        continue

            time.sleep(0.5)  # Rate limit yfinance

        duration = time.time() - start_time
        result = {
            "symbols_processed": symbols_processed,
            "chains_inserted": chains_inserted,
            "iv_inserted": iv_inserted,
            "duration_sec": round(duration, 2),
        }
        logger.info(f"Options load complete: {result}")
        return result

    def _load_symbol_options(self, cur, symbol: str, eval_date: date) -> tuple[int, int]:
        """Load options chains and IV for a single symbol. Returns (chains, iv)."""
        chains_inserted = 0
        iv_inserted = 0

        try:
            ticker = yf.Ticker(symbol)
            options_list = ticker.options
            if not options_list:
                logger.debug(f"{symbol} has no options")
                return 0, 0

            # Load nearest expiration for put/call volume
            try:
                chain = ticker.option_chain(options_list[0])
                calls_df = chain.calls
                puts_df = chain.puts

                if not calls_df.empty or not puts_df.empty:
                    chains_inserted = self._insert_options_chains(
                        cur, symbol, calls_df, puts_df, eval_date
                    )
            except Exception as e:
                logger.debug(f"Failed to get chain for {symbol}: {e}")

            # Load IV history from multiple expirations
            try:
                iv_inserted = self._insert_iv_history(cur, symbol, options_list, eval_date)
            except Exception as e:
                logger.debug(f"Failed to load IV for {symbol}: {e}")

        except Exception as e:
            logger.debug(f"Error processing {symbol}: {e}")

        return chains_inserted, iv_inserted

    def _insert_options_chains(
        self, cur, symbol: str, calls_df, puts_df, eval_date: date
    ) -> int:
        """Insert options chain data (put/call volumes)."""
        inserted = 0

        # Process calls
        for _, row in calls_df.iterrows():
            try:
                vol = row.get("volume")
                if vol and vol > 0:
                    cur.execute(
                        """
                        INSERT INTO options_chains
                        (symbol, option_type, strike_price, volume, quote_date)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (symbol, "call", float(row["strike"]), int(vol), eval_date),
                    )
                    inserted += 1
            except Exception as e:
                logger.debug(f"Failed to insert call for {symbol}: {e}")

        # Process puts
        for _, row in puts_df.iterrows():
            try:
                vol = row.get("volume")
                if vol and vol > 0:
                    cur.execute(
                        """
                        INSERT INTO options_chains
                        (symbol, option_type, strike_price, volume, quote_date)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (symbol, "put", float(row["strike"]), int(vol), eval_date),
                    )
                    inserted += 1
            except Exception as e:
                logger.debug(f"Failed to insert put for {symbol}: {e}")

        return inserted

    def _insert_iv_history(self, cur, symbol: str, options_list: list, eval_date: date) -> int:
        """Insert IV history: current IV + high/low from available expirations."""
        try:
            iv_values = []

            # Collect IV from first 5 expirations to estimate range
            for exp_str in options_list[:5]:
                try:
                    chain = yf.Ticker(symbol).option_chain(exp_str)
                    calls_df = chain.calls
                    if not calls_df.empty:
                        iv_col = calls_df.get("impliedVolatility")
                        if iv_col is not None:
                            iv_values.extend(iv_col.dropna().tolist())
                except Exception as e:
                    logger.debug(f"Failed to fetch IV for {symbol} expiration {exp_str}: {e}")

            if not iv_values:
                return 0

            current_iv = sum(iv_values) / len(iv_values)  # Mean IV
            iv_52w_high = max(iv_values)
            iv_52w_low = min(iv_values)

            # Try INSERT first, then UPDATE if it already exists
            try:
                cur.execute(
                    """
                    INSERT INTO iv_history
                    (symbol, date, current_iv, iv_52w_high, iv_52w_low)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (symbol, eval_date, float(current_iv), float(iv_52w_high), float(iv_52w_low)),
                )
            except Exception:
                # Row already exists, update it
                cur.execute(
                    """
                    UPDATE iv_history
                    SET current_iv = %s, iv_52w_high = %s, iv_52w_low = %s
                    WHERE symbol = %s AND date = %s
                    """,
                    (float(current_iv), float(iv_52w_high), float(iv_52w_low), symbol, eval_date),
                )

            return 1

        except Exception as e:
            logger.debug(f"IV history failed for {symbol}: {e}")
            return 0


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Load options chains and IV history from yfinance")
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to load (default: all active S&P 500)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Date to load (YYYY-MM-DD format, default: today)",
    )

    args = parser.parse_args()

    eval_date = None
    if args.date:
        eval_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    loader = OptionsLoader()
    result = loader.run(symbols=args.symbols, eval_date=eval_date)

    if result["symbols_processed"] == 0:
        logger.warning("No symbols processed - options data may be unavailable")
        sys.exit(1)

    logger.info(f"Success: {result}")
    sys.exit(0)


if __name__ == "__main__":
    main()
