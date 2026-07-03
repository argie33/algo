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
import math
import sys
import time
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
import requests

from utils.db.context import DatabaseContext
from utils.external.yfinance import get_ticker
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders import create_circuit_breaker, get_active_symbols
from utils.validation.data_freshness import FreshnessValidator

logger = logging.getLogger(__name__)


class OptionsLoader:
    """Fetch daily options data from yfinance with circuit breaker protection."""

    def __init__(self) -> None:
        self.batch_size = 50
        self._circuit_breaker = create_circuit_breaker("yfinance_options", importance_name="OPTIONAL")
        self._freshness_validator = FreshnessValidator(
            max_age_hours={
                "options_data": 24.0,
            }
        )

    def run(self, symbols: list[str] | None = None, eval_date: date | None = None) -> dict[str, Any]:
        """Load options data for all symbols.

        Returns dict with explicit data_unavailable marker if no data collected.
        Validates: symbols list not empty, eval_date is recent.

        OPTIMIZATION: Only fetches options for symbols likely to have them (liquid, large-cap).
        Filters out penny stocks, micro-caps, and small symbols that rarely have options.
        This eliminates ~2000-3000 wasted API calls per run.
        """
        start_time = time.time()

        # Validate inputs
        if symbols is None:
            symbols = get_active_symbols()

        if not symbols:
            raise ValueError("[OPTIONS_CHAINS] No symbols provided to load")

        # OPTIMIZATION: Filter to only symbols likely to have options
        # Only fetch options for symbols in market_constituents (ensures S&P 500, NASDAQ 100, etc.)
        # This eliminates wasted API calls on penny stocks, micro-caps, OTC, etc.
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM market_constituents WHERE symbol IS NOT NULL")
                constituent_symbols = {row[0] for row in cur.fetchall()}

            symbols = [s for s in symbols if s in constituent_symbols]
            logger.info(
                f"Filtered to {len(symbols)} symbols with active options (from {len(symbols)} total). "
                "Skipping penny stocks, micro-caps, and symbols without known options."
            )

            if not symbols:
                raise RuntimeError(
                    "[OPTIONS_CHAINS] No symbols with active options found after filtering. "
                    "Cannot proceed with options data loading without valid symbols. "
                    "Check constituent list or symbol filtering logic."
                )
        except RuntimeError:
            # Re-raise filtering result errors (no symbols after filter)
            raise
        except Exception as e:
            logger.critical(
                f"[OPTIONS_CHAINS CRITICAL] Constituent filtering failed: {e}. "
                f"Cannot proceed with fallback (all symbols) — this degrades precision and would slow down loader. "
                f"Check market_constituents table and filtering logic."
            )
            raise RuntimeError(
                f"[OPTIONS_CHAINS CRITICAL] Symbol filtering by constituents failed: {e}. "
                f"Cannot load options chains with degraded scope. "
                f"Constituent filtering is REQUIRED to avoid loading options for penny stocks and micro-caps. "
                f"Check market_constituents table availability and symbol filtering logic."
            ) from e

        if eval_date is None:
            now_utc = datetime.now(ZoneInfo("UTC"))
            now_et = now_utc.astimezone(EASTERN_TZ)
            eval_date = now_et.date()

        logger.info(f"Loading options data for {len(symbols)} symbols as of {eval_date}")

        chains_inserted = 0
        iv_inserted = 0
        symbols_processed = 0
        symbols_no_options = 0

        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i : i + self.batch_size]
            logger.info(f"Processing batch {i // self.batch_size + 1} ({len(batch)} symbols)")

            with DatabaseContext("write") as cur:
                for symbol in batch:
                    try:
                        c_cnt, iv_cnt, no_opts = self._load_symbol_options(cur, symbol, eval_date)
                        chains_inserted += c_cnt
                        iv_inserted += iv_cnt
                        symbols_processed += 1
                        if no_opts:
                            symbols_no_options += 1
                    except Exception as e:
                        logger.error(f"Failed to load options for {symbol}: {e}")
                        raise RuntimeError(f"Options data loading failed on symbol {symbol}: {e}") from e

            time.sleep(0.5)  # Rate limit yfinance

        duration = time.time() - start_time

        # Mark as unavailable if no data collected OR coverage too low
        # (e.g., only 3 of 10+ expected expirations retrieved)
        data_unavailable = chains_inserted == 0 and iv_inserted == 0
        coverage_pct = (symbols_processed / len(symbols) * 100) if symbols else 0

        # Flag if coverage is too low (less than 80% of symbols had options data)
        if not data_unavailable and coverage_pct < 80 and symbols_no_options > 0:
            logger.warning(
                f"[OPTIONS_CHAINS] Low coverage: only {symbols_processed}/{len(symbols)} symbols "
                f"({coverage_pct:.0f}%) had options data. {symbols_no_options} symbols skipped. "
                f"This may indicate incomplete market data or options data issues."
            )
            # Still mark as partial/degraded, not unavailable (some data is better than none)
            result_reason = "partial_options_coverage"
        elif data_unavailable:
            result_reason = "no_options_data_collected"
            logger.warning(f"Options load complete but NO DATA COLLECTED: {symbols_no_options} symbols have no options")
        else:
            result_reason = None

        result: dict[str, Any] = {
            "symbols_processed": symbols_processed,
            "symbols_no_options": symbols_no_options,
            "chains_inserted": chains_inserted,
            "iv_inserted": iv_inserted,
            "coverage_pct": round(coverage_pct, 1),
            "duration_sec": round(duration, 2),
            "data_unavailable": data_unavailable,
        }
        if result_reason:
            result["reason"] = result_reason
        else:
            logger.info(f"Options load complete: {result}")
        return result

    def _load_symbol_options(self, cur: Any, symbol: str, eval_date: date) -> tuple[int, int, bool]:
        """Load options chains and IV for a single symbol. Returns (chains, iv, has_no_options).

        Validates: symbol string, eval_date is recent.
        Fails fast: raises exception if data cannot be loaded (no fallback to zero counts).
        Returns: (chains_inserted, iv_inserted, symbol_has_no_options_flag)
        """
        # Validate inputs
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"[OPTIONS_CHAINS] Invalid symbol: {symbol}")

        if not isinstance(eval_date, date):
            raise ValueError(f"[OPTIONS_CHAINS] Invalid eval_date: {eval_date}")

        try:
            ticker = get_ticker(symbol)
        except requests.Timeout as e:
            raise RuntimeError(f"[OPTIONS_CHAINS] Timeout fetching ticker for {symbol}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"[OPTIONS_CHAINS] Failed to fetch ticker for {symbol}: {e}") from e

        try:
            options_list = ticker.options
        except requests.Timeout as e:
            raise RuntimeError(f"[OPTIONS_CHAINS] Timeout fetching options list for {symbol}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"[OPTIONS_CHAINS] Failed to fetch options list for {symbol}: {e}") from e

        # No options available for this symbol (legitimate case, not an error)
        if not options_list:
            logger.debug(f"[OPTIONS_CHAINS] {symbol} has no options available")
            return 0, 0, True

        chains_inserted = 0
        iv_inserted = 0

        # Load nearest expiration for put/call volume
        try:
            chain = ticker.option_chain(options_list[0])
            calls_df = chain.calls
            puts_df = chain.puts

            if not calls_df.empty or not puts_df.empty:
                chains_inserted = self._insert_options_chains(cur, symbol, calls_df, puts_df, eval_date)
            else:
                logger.warning(f"[OPTIONS_CHAINS] {symbol} has empty call/put dataframes for nearest expiration")
        except Exception as e:
            raise RuntimeError(f"[OPTIONS_CHAINS] Failed to get chain for {symbol}: {e}") from e

        # Load IV history from multiple expirations
        try:
            iv_inserted = self._insert_iv_history(cur, symbol, options_list, eval_date)
        except Exception as e:
            raise RuntimeError(f"[OPTIONS_CHAINS] Failed to load IV for {symbol}: {e}") from e

        return chains_inserted, iv_inserted, False

    def _insert_options_chains(self, cur: Any, symbol: str, calls_df: Any, puts_df: Any, eval_date: date) -> int:
        """Insert options chain data (put/call volumes).

        Validates: symbol, eval_date, dataframes have required columns.
        Fails fast: raises exception on database errors or missing columns (no silent skips).
        """
        # Validate inputs
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"[OPTIONS_CHAINS] Invalid symbol for insert: {symbol}")

        if not isinstance(eval_date, date):
            raise ValueError(f"[OPTIONS_CHAINS] Invalid eval_date for insert: {eval_date}")

        inserted = 0

        # Process calls
        if not calls_df.empty:
            required_cols = {"volume", "strike"}
            if not required_cols.issubset(calls_df.columns):
                raise ValueError(
                    f"[OPTIONS_CHAINS] Missing required columns in calls_df for {symbol}: "
                    f"expected {required_cols}, got {set(calls_df.columns)}"
                )

            for idx, row in calls_df.iterrows():
                vol = row.get("volume")
                strike = row.get("strike")

                # Validate volume and strike are valid (not None, not NaN)
                if vol is None or (isinstance(vol, float) and math.isnan(vol)):
                    logger.warning(
                        f"[OPTIONS_CHAINS] WARN: Call option for {symbol} at index {idx} has missing volume. Skipping."
                    )
                    continue
                if strike is None or (isinstance(strike, float) and math.isnan(strike)):
                    logger.warning(
                        f"[OPTIONS_CHAINS] WARN: Call option for {symbol} at index {idx} has missing strike. Skipping."
                    )
                    continue

                # Only insert if volume is positive
                if vol > 0:
                    try:
                        cur.execute(
                            """
                            INSERT INTO options_chains
                            (symbol, option_type, strike_price, volume, quote_date)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (symbol, "call", float(strike), int(vol), eval_date),
                        )
                        inserted += 1
                    except Exception as e:
                        raise RuntimeError(
                            f"[OPTIONS_CHAINS] Database insert failed for call option {symbol} strike={strike}: {e}"
                        ) from e

        # Process puts
        if not puts_df.empty:
            required_cols = {"volume", "strike"}
            if not required_cols.issubset(puts_df.columns):
                raise ValueError(
                    f"[OPTIONS_CHAINS] Missing required columns in puts_df for {symbol}: "
                    f"expected {required_cols}, got {set(puts_df.columns)}"
                )

            for idx, row in puts_df.iterrows():
                vol = row.get("volume")
                strike = row.get("strike")

                # Validate volume and strike are valid (not None, not NaN)
                if vol is None or (isinstance(vol, float) and math.isnan(vol)):
                    logger.warning(
                        f"[OPTIONS_CHAINS] WARN: Put option for {symbol} at index {idx} has missing volume. Skipping."
                    )
                    continue
                if strike is None or (isinstance(strike, float) and math.isnan(strike)):
                    logger.warning(
                        f"[OPTIONS_CHAINS] WARN: Put option for {symbol} at index {idx} has missing strike. Skipping."
                    )
                    continue

                # Only insert if volume is positive
                if vol > 0:
                    try:
                        cur.execute(
                            """
                            INSERT INTO options_chains
                            (symbol, option_type, strike_price, volume, quote_date)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (symbol, "put", float(strike), int(vol), eval_date),
                        )
                        inserted += 1
                    except Exception as e:
                        raise RuntimeError(
                            f"[OPTIONS_CHAINS] Database insert failed for put option {symbol} strike={strike}: {e}"
                        ) from e

        if inserted == 0:
            logger.info(f"[OPTIONS_CHAINS] No volume data inserted for {symbol} (all volumes zero or missing)")

        return inserted

    def _insert_iv_history(self, cur: Any, symbol: str, options_list: list[str], eval_date: date) -> int:
        """Insert IV history: current IV + high/low from available expirations.

        Validates: symbol, eval_date, options_list not empty.
        Fails fast: raises exception if IV data cannot be collected or historical data insufficient.
        No fallback patterns - all errors explicit with actionable messages.
        """
        # Validate inputs
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"[IV_HISTORY] Invalid symbol: {symbol}")

        if not isinstance(eval_date, date):
            raise ValueError(f"[IV_HISTORY] Invalid eval_date: {eval_date}")

        if not options_list:
            raise ValueError(f"[IV_HISTORY] Empty options list for {symbol}")

        iv_values = []

        # Collect IV from first 5 expirations to estimate range
        for exp_str in options_list[:5]:
            try:
                ticker_for_chain = get_ticker(symbol)
                chain = ticker_for_chain.option_chain(exp_str)
                calls_df = chain.calls

                if calls_df.empty:
                    logger.debug(f"[IV_HISTORY] Empty calls dataframe for {symbol} expiration {exp_str}")
                    continue

                if "impliedVolatility" not in calls_df.columns:
                    raise ValueError(
                        f"[IV_HISTORY] Missing 'impliedVolatility' column for {symbol} expiration {exp_str}. "
                        f"Available columns: {list(calls_df.columns)}"
                    )

                iv_col = calls_df["impliedVolatility"]
                iv_values.extend(iv_col.dropna().tolist())

            except requests.Timeout as e:
                raise RuntimeError(f"[IV_HISTORY] Timeout fetching IV for {symbol} expiration {exp_str}: {e}") from e
            except ValueError:
                raise
            except Exception as e:
                raise RuntimeError(f"[IV_HISTORY] Failed to fetch IV for {symbol} expiration {exp_str}: {e}") from e

        if not iv_values:
            raise RuntimeError(
                f"[IV_HISTORY] No IV data available for {symbol} across first 5 expirations. "
                f"Cannot compute current IV for signal validation."
            )

        # Compute current IV as average of collected values
        current_iv = sum(iv_values) / len(iv_values)

        # Query actual 52-week historical IV extremes (past 252 trading days)
        try:
            cur.execute(
                """
                SELECT MAX(current_iv), MIN(current_iv) FROM iv_history
                WHERE symbol = %s AND date >= %s - INTERVAL '252 days'
                """,
                (symbol, eval_date),
            )
            hist_row = cur.fetchone()
        except Exception as e:
            raise RuntimeError(f"[IV_HISTORY] Database query failed for {symbol} historical extremes: {e}") from e

        # Validate historical data exists
        if hist_row is None:
            raise RuntimeError(
                f"[IV_HISTORY] Database query returned NULL for {symbol} extremes. "
                f"Cannot proceed without valid database query result."
            )

        if hist_row[0] is None or hist_row[1] is None:
            raise RuntimeError(
                f"[IV_HISTORY] Cannot compute 52-week IV extremes for {symbol}: "
                f"insufficient historical data in iv_history table (need 252+ days). "
                f"Current data: max={hist_row[0]}, min={hist_row[1]}. "
                f"This is required for accurate signal validation."
            )

        iv_52w_high = float(hist_row[0])
        iv_52w_low = float(hist_row[1])

        # Validate computed IV values
        if current_iv <= 0:
            raise ValueError(f"[IV_HISTORY] Invalid current IV for {symbol}: {current_iv} (must be positive)")

        if iv_52w_high <= 0 or iv_52w_low <= 0:
            raise ValueError(
                f"[IV_HISTORY] Invalid 52-week IV extremes for {symbol}: "
                f"high={iv_52w_high}, low={iv_52w_low} (must be positive)"
            )

        # Try INSERT first, then UPDATE if row already exists
        try:
            cur.execute(
                """
                INSERT INTO iv_history
                (symbol, date, current_iv, iv_52w_high, iv_52w_low)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    symbol,
                    eval_date,
                    float(current_iv),
                    float(iv_52w_high),
                    float(iv_52w_low),
                ),
            )
        except psycopg2.IntegrityError:
            # Row already exists for this symbol/date, update it
            try:
                cur.execute(
                    """
                    UPDATE iv_history
                    SET current_iv = %s, iv_52w_high = %s, iv_52w_low = %s
                    WHERE symbol = %s AND date = %s
                    """,
                    (
                        float(current_iv),
                        float(iv_52w_high),
                        float(iv_52w_low),
                        symbol,
                        eval_date,
                    ),
                )
            except Exception as e:
                raise RuntimeError(f"[IV_HISTORY] Database update failed for {symbol}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"[IV_HISTORY] Database insert failed for {symbol}: {e}") from e

        return 1


def main() -> None:
    """Load options chains and IV history from yfinance.

    Validates: symbols list not empty, date format valid.
    Exits with code 1 if no data collected, 0 on success.
    """
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
        try:
            eval_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD format. Error: {e}")
            sys.exit(1)

    try:
        loader = OptionsLoader()
        result = loader.run(symbols=args.symbols, eval_date=eval_date)

        if result["symbols_processed"] == 0:
            logger.error("No symbols processed - options data collection failed")
            sys.exit(1)

        if result.get("data_unavailable"):
            logger.warning(f"Options data unavailable: {result.get('reason', 'unknown')}. Details: {result}")
            sys.exit(1)

        logger.info(f"Success: {result}")
        sys.exit(0)

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
