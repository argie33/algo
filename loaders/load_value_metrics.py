#!/usr/bin/env python3
"""Value Metrics Loader - PE, PB, PS, dividend yield from yfinance."""

import sys

from loaders.loader_helper import setup_imports


setup_imports()

import logging
import time
from datetime import date, datetime, timezone

from loaders.runner import run_loader
from utils.external.yfinance import get_ticker
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class ValueMetricsLoader(OptimalLoader):
    """Load value metrics (PE, PB, PS, etc) from yfinance."""

    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(
        self, symbol: str, since: date | None
    ) -> list[dict] | None:
        """Fetch value metrics from yfinance for a symbol."""
        for attempt in range(3):
            try:
                ticker = get_ticker(symbol)
                if not ticker:
                    logger.debug(f"Ticker not found for {symbol} (no data available)")
                    return None

                info = ticker.info
                if not info:
                    logger.debug(f"No info available for {symbol}")
                    return None

                mkt_cap = info.get("marketCap")
                pe = info.get("trailingPE")
                pb = info.get("priceToBook")
                ps = info.get("priceToSalesTrailing12Months")
                peg = info.get("trailingPegRatio")
                div = info.get("dividendYield")
                fcf = info.get("freeCashflow")
                held_insiders = info.get("heldPercentInsiders")
                held_institutions = info.get("heldPercentInstitutions")

                if not any([mkt_cap, pe, pb, ps]):
                    logger.debug(f"Insufficient metrics for {symbol}: no market cap, PE, PB, or PS")
                    return None

                fcf_yield = None
                if fcf and mkt_cap and mkt_cap > 0:
                    fcf_yield = float(fcf) / float(mkt_cap)

                def _cap(val, limit=9_999_999):
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
                        "held_percent_insiders": (
                            float(held_insiders) if held_insiders else None
                        ),
                        "held_percent_institutions": (
                            float(held_institutions) if held_institutions else None
                        ),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]

            except Exception as e:
                err = str(e)
                if "RateLimit" in err or "Too Many Requests" in err or "429" in err:
                    if attempt < 2:
                        wait = (attempt + 1) * 30
                        logger.warning(f"Rate limited on {symbol}, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    else:
                        logger.error(f"Rate limit persisted after retries for {symbol}")
                        raise RuntimeError(f"API rate limited for {symbol} after retries") from e
                logger.error(f"API error fetching value metrics for {symbol}: {e}")
                raise RuntimeError(f"Failed to fetch value metrics for {symbol}") from e

        return None


def _apply_schema_migrations():
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
    except Exception as e:
        logger.warning(f"Schema migration failed (non-fatal): {e}")



if __name__ == "__main__":
    sys.exit(run_loader(ValueMetricsLoader))
