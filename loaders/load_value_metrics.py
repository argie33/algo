#!/usr/bin/env python3
"""Value Metrics Loader - PE, PB, PS, dividend yield from yfinance."""

import sys
import argparse
import logging
from datetime import date, datetime, timezone
from typing import Optional, List
import time

from utils.external.yfinance import get_ticker
from utils.optimal_loader import OptimalLoader
from utils.loaders.helpers import get_active_symbols
from utils.loaders.config import get_default_parallelism

logger = logging.getLogger(__name__)

from loaders.loader_helper import setup_imports

setup_imports()


class ValueMetricsLoader(OptimalLoader):
    """Load value metrics (PE, PB, PS, etc) from yfinance."""

    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(
        self, symbol: str, since: Optional[date]
    ) -> Optional[List[dict]]:
        """Fetch value metrics from yfinance for a symbol."""
        for attempt in range(3):
            try:
                ticker = get_ticker(symbol)
                if not ticker:
                    return None

                info = ticker.info
                if not info:
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
                    return None

                fcf_yield = None
                if fcf and mkt_cap and mkt_cap > 0:
                    fcf_yield = float(fcf) / float(mkt_cap)

                return [
                    {
                        "symbol": symbol,
                        "date": date.today(),
                        "market_cap": int(mkt_cap) if mkt_cap else None,
                        "pe_ratio": float(pe) if pe and pe > 0 else None,
                        "pb_ratio": float(pb) if pb and pb > 0 else None,
                        "ps_ratio": float(ps) if ps and ps > 0 else None,
                        "peg_ratio": float(peg) if peg and peg > 0 else None,
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
                logger.debug(f"yfinance failed for {symbol}: {e}")
                return None

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


def main():
    parser = argparse.ArgumentParser(description="Value Metrics Loader")
    parser.add_argument(
        "--symbols", type=str, help="Comma-separated symbols or blank for all"
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("value_metrics"),
        help="Parallel workers",
    )
    args = parser.parse_args()

    _apply_schema_migrations()

    loader = ValueMetricsLoader()

    if args.symbols:
        symbols = args.symbols.split(",")
    else:
        symbols = get_active_symbols()

    result = loader.run(symbols, parallelism=args.parallelism)

    if result["rows_inserted"] > 0:
        logger.info(f"SUCCESS: {result['rows_inserted']} value metrics loaded")
        return 0
    else:
        logger.warning(
            f"COMPLETED: No metrics loaded (rows_fetched={result['rows_fetched']})"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
