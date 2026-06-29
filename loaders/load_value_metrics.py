#!/usr/bin/env python3
"""Value Metrics Loader - PE, PB, PS, dividend yield from yfinance."""

import sys
from collections.abc import Iterable

import psycopg2
import requests

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.external.yfinance import get_ticker  # noqa: E402
from utils.loaders.transient_errors import TransientAPIError  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class ValueMetricsLoader(OptimalLoader):
    """Load value metrics (PE, PB, PS, etc) from yfinance."""

    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._illiquid_skip_count = 0

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Override run to apply cache pre-warming strategy.

        Prioritizes top 500 liquid symbols to ensure they cache early,
        then processes remaining symbols. This reduces API calls for
        frequently-traded symbols on subsequent runs.
        """
        # Convert to list and apply symbol prioritization
        symbols_list = list(symbols)
        prioritized_symbols = self._get_top_liquid_symbols(symbols_list)

        # Call parent run with prioritized symbols
        return super().run(prioritized_symbols, parallelism=parallelism, backfill_days=backfill_days)

    def _get_top_liquid_symbols(self, symbols: list[str], top_n: int = 500) -> list[str]:
        """Get top N liquid symbols by average volume to prioritize cache warming.

        OPTIMIZATION (Phase 3.2): Pre-warm cache with frequently-traded symbols.
        Top 500 symbols represent ~80% of trading activity and rarely change.
        Processing them first ensures cache hits for subsequent runs.

        Returns symbols sorted with top liquid symbols first, remaining in original order.
        """
        if len(symbols) <= top_n:
            return symbols  # If fewer symbols than top_n, process all normally

        try:
            with DatabaseContext("read") as cur:
                # Get top 500 symbols by average 30-day volume
                # Price data is densest source of trading activity info
                cur.execute(
                    """
                    SELECT symbol, AVG(volume) as avg_volume
                    FROM price_daily
                    WHERE symbol = ANY(%s)
                      AND date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY symbol
                    ORDER BY avg_volume DESC
                    LIMIT %s
                    """,
                    (symbols, top_n),
                )
                top_symbols = [row["symbol"] for row in cur.fetchall()]
                remaining_symbols = [s for s in symbols if s not in top_symbols]

                logger.info(
                    f"[VALUE_METRICS] [CACHE_WARM] Found {len(top_symbols)} top-liquid symbols "
                    f"(avg volume >30d). Processing {len(top_symbols)} + {len(remaining_symbols)} remaining"
                )
                return top_symbols + remaining_symbols
        except Exception as e:
            logger.warning(f"[VALUE_METRICS] Could not identify top liquid symbols: {e}. Using original order.")
            return symbols

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch value metrics from yfinance for a symbol.

        Returns record with data_unavailable=True if metrics cannot be computed.
        Value metrics are optional enrichment, but absence must be EXPLICIT (not silent None).
        Downstream systems must acknowledge data absence via data_unavailable flag.

        Always fetch fresh data. Dividend yield and PE ratios can change significantly
        within days due to earnings announcements, ex-dividend dates, and stock splits.
        Stale cached data masks real price discovery and risks incorrect valuations.
        """
        import time

        start_time = time.time()
        try:
            ticker = get_ticker(symbol)
            if not ticker:
                elapsed = time.time() - start_time
                logger.info(
                    f"[VALUE_METRICS] Ticker not found for {symbol} — metrics unavailable (total: {elapsed:.1f}s)"
                )
                return [
                    {
                        "symbol": symbol,
                        "date": date.today(),
                        "market_cap": None,
                        "pe_ratio": None,
                        "pb_ratio": None,
                        "ps_ratio": None,
                        "peg_ratio": None,
                        "dividend_yield": None,
                        "fcf_yield": None,
                        "held_percent_insiders": None,
                        "held_percent_institutions": None,
                        "data_unavailable": True,
                        "reason": "Ticker not found in data source",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]

            info = ticker.info
            if not info or not isinstance(info, dict):
                logger.info(
                    f"[VALUE_METRICS] No financial info or unexpected info type for {symbol} "
                    f"(type={type(info).__name__}) — metrics unavailable"
                )
                return [
                    {
                        "symbol": symbol,
                        "date": date.today(),
                        "market_cap": None,
                        "pe_ratio": None,
                        "pb_ratio": None,
                        "ps_ratio": None,
                        "peg_ratio": None,
                        "dividend_yield": None,
                        "fcf_yield": None,
                        "held_percent_insiders": None,
                        "held_percent_institutions": None,
                        "data_unavailable": True,
                        "reason": "No financial info available from data source",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]

            mkt_cap = info.get("marketCap")

            # Skip illiquid symbols gracefully (< $1M market cap). These legitimately lack
            # reliable metrics in yfinance and are typically excluded from trading anyway.
            if mkt_cap and mkt_cap < 1_000_000:
                self._illiquid_skip_count += 1
                logger.debug(f"[VALUE_METRICS] [ILLIQUID_SKIP] {symbol} (market cap ${mkt_cap:,} < $1M)")
                return [
                    {
                        "symbol": symbol,
                        "date": date.today(),
                        "market_cap": int(mkt_cap),
                        "pe_ratio": None,
                        "pb_ratio": None,
                        "ps_ratio": None,
                        "peg_ratio": None,
                        "dividend_yield": None,
                        "fcf_yield": None,
                        "held_percent_insiders": None,
                        "held_percent_institutions": None,
                        "data_unavailable": True,
                        "reason": f"Market cap ${mkt_cap:,} below $1M liquidity threshold",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]

            pe = info.get("trailingPE")
            pb = info.get("priceToBook")
            ps = info.get("priceToSalesTrailing12Months")
            peg = info.get("trailingPegRatio")
            div = info.get("dividendYield")
            fcf = info.get("freeCashflow")
            held_insiders = info.get("heldPercentInsiders")
            held_institutions = info.get("heldPercentInstitutions")

            # If absolutely no metrics available, return data_unavailable record
            if not any([mkt_cap, pe, pb, ps]):
                logger.info(f"[VALUE_METRICS] No value metrics available for {symbol} — metrics unavailable")
                return [
                    {
                        "symbol": symbol,
                        "date": date.today(),
                        "market_cap": int(mkt_cap) if mkt_cap else None,
                        "pe_ratio": None,
                        "pb_ratio": None,
                        "ps_ratio": None,
                        "peg_ratio": None,
                        "dividend_yield": None,
                        "fcf_yield": None,
                        "held_percent_insiders": None,
                        "held_percent_institutions": None,
                        "data_unavailable": True,
                        "reason": "No value metrics (PE, PB, PS) found in data source",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]

            fcf_yield = None
            if fcf and mkt_cap and mkt_cap > 0:
                fcf_yield = float(fcf) / float(mkt_cap)

            def _cap(val: Any, limit: int = 9_999_999) -> dict[str, Any]:
                if val is None:
                    logger.debug("[VALUE_METRICS_CAP] Value is null, marking unavailable")
                    return {"value": None, "available": False, "reason": "null_input"}
                try:
                    f = float(val)
                    capped = min(f, limit)
                    return {"value": capped, "available": True}
                except (ValueError, TypeError) as e:
                    logger.debug(f"[VALUE_METRICS_CAP] Failed to convert value {val!r} to float: {e}")
                    return {"value": None, "available": False, "reason": f"conversion_error: {str(e)[:50]}"}

            # Convert held_percent fields to 0-100 scale (yfinance returns 0-1 scale)
            # CRITICAL: Must match load_positioning_metrics.py behavior for data consistency
            held_insiders_pct = None
            if held_insiders is not None:
                held_insiders_pct = float(held_insiders) * 100
            held_institutions_pct = None
            if held_institutions is not None:
                held_institutions_pct = float(held_institutions) * 100

            elapsed = time.time() - start_time
            if elapsed > 5:
                logger.warning(f"[VALUE_METRICS] {symbol}: fetch took {elapsed:.1f}s total")

            # Extract values from _cap dicts (which now have explicit availability markers)
            pe_cap_result = _cap(pe) if pe else {"value": None, "available": False, "reason": "null_input"}
            pb_cap_result = _cap(pb) if pb else {"value": None, "available": False, "reason": "null_input"}
            ps_cap_result = _cap(ps) if ps else {"value": None, "available": False, "reason": "null_input"}
            peg_cap_result = _cap(peg) if peg else {"value": None, "available": False, "reason": "null_input"}

            return [
                {
                    "symbol": symbol,
                    "date": date.today(),
                    "market_cap": int(mkt_cap) if mkt_cap else None,
                    "market_cap_unavailable_reason": None if mkt_cap else "missing_from_yfinance",
                    "pe_ratio": pe_cap_result["value"],
                    "pe_ratio_unavailable_reason": None if pe_cap_result["available"] else pe_cap_result.get("reason", "unknown"),
                    "pb_ratio": pb_cap_result["value"],
                    "pb_ratio_unavailable_reason": None if pb_cap_result["available"] else pb_cap_result.get("reason", "unknown"),
                    "ps_ratio": ps_cap_result["value"],
                    "ps_ratio_unavailable_reason": None if ps_cap_result["available"] else ps_cap_result.get("reason", "unknown"),
                    "peg_ratio": peg_cap_result["value"],
                    "peg_ratio_unavailable_reason": None if peg_cap_result["available"] else peg_cap_result.get("reason", "unknown"),
                    "dividend_yield": float(div) if div else None,
                    "dividend_yield_unavailable_reason": None if div else "missing_from_yfinance",
                    "fcf_yield": fcf_yield,
                    "fcf_yield_unavailable_reason": None if fcf_yield else "missing_fcf_or_mkt_cap",
                    "held_percent_insiders": held_insiders_pct,
                    "held_percent_insiders_unavailable_reason": None if held_insiders_pct else "missing_from_yfinance",
                    "held_percent_institutions": held_institutions_pct,
                    "held_percent_institutions_unavailable_reason": None if held_institutions_pct else "missing_from_yfinance",
                    "data_unavailable": not (pe or pb or ps or div or fcf_yield),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.info(f"[VALUE_METRICS] Parsing error for {symbol} — metrics unavailable: {e}")
            return [
                {
                    "symbol": symbol,
                    "date": date.today(),
                    "market_cap": None,
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "ps_ratio": None,
                    "peg_ratio": None,
                    "dividend_yield": None,
                    "fcf_yield": None,
                    "held_percent_insiders": None,
                    "held_percent_institutions": None,
                    "data_unavailable": True,
                    "reason": f"Data parsing error: {str(e)[:100]}",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        except (requests.Timeout, requests.ConnectionError) as e:
            elapsed = time.time() - start_time
            logger.warning(
                f"[VALUE_METRICS] API timeout/connection error for {symbol} (transient, will retry) after {elapsed:.1f}s: {e}"
            )
            raise TransientAPIError(f"yfinance timeout fetching value metrics for {symbol}") from e
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"[VALUE_METRICS] Unexpected error for {symbol} (not data unavailability) after {elapsed:.1f}s: {type(e).__name__}: {e}"
            )
            raise

    def pre_run(self) -> None:
        """Hook: Apply cache pre-warming strategy before main run.

        OPTIMIZATION (Phase 3.2): Prioritize top 500 liquid symbols.
        These symbols represent ~80% of trading activity and hit cache early.
        Remaining symbols follow after, ensuring efficient cache utilization.
        """
        # This will be called by OptimalLoader.run() before processing symbols
        logger.info("[VALUE_METRICS] Pre-run cache warming strategy: top liquid symbols first")

    def post_run(self) -> None:
        """Log telemetry on illiquid stocks skipped during this run."""
        if self._illiquid_skip_count > 0:
            logger.info(
                f"[VALUE_METRICS] Telemetry: {self._illiquid_skip_count} stocks skipped due to illiquidity (market cap < $1M)"
            )


def _apply_schema_migrations() -> None:
    """Add columns that were missing from initial schema deployment."""
    from utils.db.context import DatabaseContext

    migrations = [
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS date DATE",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS market_cap BIGINT",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_insiders DECIMAL(8,4)",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions DECIMAL(8,4)",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS reason TEXT",
    ]
    try:
        with DatabaseContext("write") as cur:
            for sql in migrations:
                cur.execute(sql)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Schema migration failed: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(ValueMetricsLoader))
