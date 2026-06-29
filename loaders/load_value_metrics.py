#!/usr/bin/env python3
"""Value Metrics Loader - PE, PB, PS, dividend yield from yfinance."""

import sys

import psycopg2
import requests

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch value metrics from yfinance for a symbol.

        Returns record with data_unavailable=True if metrics cannot be computed.
        Value metrics are optional enrichment, but absence must be EXPLICIT (not silent None).
        Downstream systems must acknowledge data absence via data_unavailable flag.
        """
        try:
            ticker = get_ticker(symbol)
            if not ticker:
                logger.info(f"[VALUE_METRICS] Ticker not found for {symbol} — metrics unavailable")
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
            if not info:
                logger.info(f"[VALUE_METRICS] No financial info for {symbol} — metrics unavailable")
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

            def _cap(val: Any, limit: int = 9_999_999) -> float | None:
                if val is None:
                    return None
                try:
                    f = float(val)
                    return min(f, limit)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to convert value {val!r} to float: {e}")
                    return None

            # Convert held_percent fields to 0-100 scale (yfinance returns 0-1 scale)
            # CRITICAL: Must match load_positioning_metrics.py behavior for data consistency
            held_insiders_pct = None
            if held_insiders is not None:
                held_insiders_pct = float(held_insiders) * 100
            held_institutions_pct = None
            if held_institutions is not None:
                held_institutions_pct = float(held_institutions) * 100

            return [
                {
                    "symbol": symbol,
                    "date": date.today(),
                    "market_cap": int(mkt_cap) if mkt_cap else None,
                    "pe_ratio": _cap(pe) if pe and pe > 0 else None,
                    "pb_ratio": _cap(pb) if pb and pb > 0 else None,
                    "ps_ratio": _cap(ps) if ps and ps > 0 else None,
                    "peg_ratio": _cap(peg) if peg and peg > 0 else None,
                    "dividend_yield": float(div) if div else None,
                    "fcf_yield": fcf_yield,
                    "held_percent_insiders": held_insiders_pct,
                    "held_percent_institutions": held_institutions_pct,
                    "data_unavailable": False,
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
            logger.warning(f"[VALUE_METRICS] API timeout/connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"yfinance timeout fetching value metrics for {symbol}") from e
        except Exception as e:
            logger.error(f"[VALUE_METRICS] Unexpected error for {symbol} (not data unavailability): {type(e).__name__}: {e}")
            raise

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
