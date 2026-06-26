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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Fetch value metrics from yfinance for a symbol.

        Returns None if metrics are unavailable (normal for illiquid stocks, penny stocks, etc).
        Value metrics are optional enrichment; their absence does not prevent trading.
        """
        try:
            ticker = get_ticker(symbol)
            if not ticker:
                logger.debug(f"[VALUE_METRICS] Ticker not found for {symbol} (skipping)")
                return None

            info = ticker.info
            if not info:
                logger.debug(f"[VALUE_METRICS] No financial info for {symbol} (skipping)")
                return None

            mkt_cap = info.get("marketCap")

            # Skip illiquid symbols gracefully (< $1M market cap). These legitimately lack
            # reliable metrics in yfinance and are typically excluded from trading anyway.
            if mkt_cap and mkt_cap < 1_000_000:
                logger.debug(f"[VALUE_METRICS] Skipping {symbol} (market cap ${mkt_cap:,} < $1M)")
                return None

            pe = info.get("trailingPE")
            pb = info.get("priceToBook")
            ps = info.get("priceToSalesTrailing12Months")
            peg = info.get("trailingPegRatio")
            div = info.get("dividendYield")
            fcf = info.get("freeCashflow")
            held_insiders = info.get("heldPercentInsiders")
            held_institutions = info.get("heldPercentInstitutions")

            # If absolutely no metrics available, skip (but this is rare)
            if not any([mkt_cap, pe, pb, ps]):
                logger.debug(f"[VALUE_METRICS] No value metrics available for {symbol} (skipping)")
                return None

            fcf_yield = None
            if fcf and mkt_cap and mkt_cap > 0:
                fcf_yield = float(fcf) / float(mkt_cap)

            def _cap(val: Any, limit: int = 9_999_999) -> float | None:
                return min(float(val), limit) if val else None

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
                    "held_percent_insiders": (float(held_insiders) if held_insiders else None),
                    "held_percent_institutions": (float(held_institutions) if held_institutions else None),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"[VALUE_METRICS] Parsing error for {symbol} (skipping): {e}")
            return None
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(f"[VALUE_METRICS] API timeout/connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"yfinance timeout fetching value metrics for {symbol}") from e
        except Exception as e:
            logger.debug(f"[VALUE_METRICS] Error fetching for {symbol} (skipping): {e}")
            return None


def _apply_schema_migrations() -> None:
    """Add columns that were missing from initial schema deployment."""
    from utils.db.context import DatabaseContext

    migrations = [
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS date DATE",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS market_cap BIGINT",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_insiders DECIMAL(8,4)",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions DECIMAL(8,4)",
        "ALTER TABLE value_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]
    try:
        with DatabaseContext("write") as cur:
            for sql in migrations:
                cur.execute(sql)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Schema migration failed: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(ValueMetricsLoader))
