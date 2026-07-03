#!/usr/bin/env python3
"""Value Metrics Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls into single yfinance_snapshot loader.
This loader reads PE, PB, PS, dividend yield from yfinance_snapshot table instead of calling yfinance.

Result: Eliminates 5000 redundant yfinance API calls per run, prevents rate limiting, parallelism can be 4+ instead of 1.
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class ValueMetricsLoader(OptimalLoader):
    """Load value metrics from yfinance_snapshot table (cached snapshot, not API)."""

    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    REQUIRED_COLUMNS = {
        "value_score": "DECIMAL(5, 2)",
        "market_cap": "BIGINT",
        "market_cap_unavailable_reason": "VARCHAR(255)",
        "pe_ratio": "DECIMAL(10, 2)",
        "pe_ratio_unavailable_reason": "VARCHAR(255)",
        "pb_ratio": "DECIMAL(10, 2)",
        "pb_ratio_unavailable_reason": "VARCHAR(255)",
        "ps_ratio": "DECIMAL(10, 2)",
        "ps_ratio_unavailable_reason": "VARCHAR(255)",
        "peg_ratio": "DECIMAL(10, 2)",
        "peg_ratio_unavailable_reason": "VARCHAR(255)",
        "dividend_yield": "DECIMAL(10, 4)",
        "dividend_yield_unavailable_reason": "VARCHAR(255)",
        "fcf_yield": "DECIMAL(10, 4)",
        "fcf_yield_unavailable_reason": "VARCHAR(255)",
        "held_percent_insiders": "DECIMAL(8, 2)",
        "held_percent_insiders_unavailable_reason": "VARCHAR(255)",
        "held_percent_institutions": "DECIMAL(8, 2)",
        "held_percent_institutions_unavailable_reason": "VARCHAR(255)",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._ensure_schema_ready()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read value metrics from yfinance_snapshot table.

        yfinance_snapshot loader (run BEFORE this) fetches all yfinance data once per symbol
        and stores in yfinance_snapshot table. This loader reads from that table.

        Returns data_unavailable=True if metrics not in snapshot or yfinance_snapshot not yet run.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield,
                           market_cap, data_available, unavailable_reason
                    FROM yfinance_snapshot
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if not row:
                logger.info(f"[VALUE_METRICS] No snapshot for {symbol} — yfinance_snapshot loader not yet run?")
                return [self._unavailable_record(symbol, "No yfinance_snapshot record")]

            if not row.get("data_available"):
                logger.info(
                    f"[VALUE_METRICS] Snapshot unavailable for {symbol}: {row.get('unavailable_reason')}"
                )
                return [self._unavailable_record(symbol, row.get("unavailable_reason", "Unknown"))]

            return [
                {
                    "symbol": symbol,
                    "date": date.today(),
                    "market_cap": row["market_cap"],
                    "market_cap_unavailable_reason": None if row["market_cap"] else "missing_from_snapshot",
                    "pe_ratio": row["pe_ratio"],
                    "pe_ratio_unavailable_reason": None if row["pe_ratio"] else "missing_from_snapshot",
                    "pb_ratio": row["pb_ratio"],
                    "pb_ratio_unavailable_reason": None if row["pb_ratio"] else "missing_from_snapshot",
                    "ps_ratio": row["ps_ratio"],
                    "ps_ratio_unavailable_reason": None if row["ps_ratio"] else "missing_from_snapshot",
                    "peg_ratio": row["peg_ratio"],
                    "peg_ratio_unavailable_reason": None if row["peg_ratio"] else "missing_from_snapshot",
                    "dividend_yield": row["dividend_yield"],
                    "dividend_yield_unavailable_reason": None
                    if row["dividend_yield"]
                    else "missing_from_snapshot",
                    "fcf_yield": row["fcf_yield"],
                    "fcf_yield_unavailable_reason": None if row["fcf_yield"] else "missing_from_snapshot",
                    "held_percent_insiders": None,
                    "held_percent_insiders_unavailable_reason": "moved_to_positioning_metrics",
                    "held_percent_institutions": None,
                    "held_percent_institutions_unavailable_reason": "moved_to_positioning_metrics",
                    "data_unavailable": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

        except Exception as e:
            logger.error(f"[VALUE_METRICS] Error reading snapshot for {symbol}: {e}")
            return [self._unavailable_record(symbol, str(e)[:255])]

    def _unavailable_record(self, symbol: str, reason: str) -> dict[str, Any]:
        """Return unavailable record."""
        return {
            "symbol": symbol,
            "date": date.today(),
            "market_cap": None,
            "market_cap_unavailable_reason": reason,
            "pe_ratio": None,
            "pe_ratio_unavailable_reason": reason,
            "pb_ratio": None,
            "pb_ratio_unavailable_reason": reason,
            "ps_ratio": None,
            "ps_ratio_unavailable_reason": reason,
            "peg_ratio": None,
            "peg_ratio_unavailable_reason": reason,
            "dividend_yield": None,
            "dividend_yield_unavailable_reason": reason,
            "fcf_yield": None,
            "fcf_yield_unavailable_reason": reason,
            "held_percent_insiders": None,
            "held_percent_insiders_unavailable_reason": reason,
            "held_percent_institutions": None,
            "held_percent_institutions_unavailable_reason": reason,
            "data_unavailable": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _ensure_schema_ready(self) -> None:
        """Ensure all required columns exist, auto-creating if needed."""
        from utils.schema_healer import ensure_columns_exist

        try:
            with DatabaseContext("write") as cur:
                _all_exist, created = ensure_columns_exist(cur, self.table_name, self.REQUIRED_COLUMNS)
                if created:
                    logger.warning(
                        f"[VALUE_METRICS] Auto-healed {len(created)} missing columns: {created}. "
                        f"Schema was incomplete in this environment."
                    )
        except Exception as e:
            logger.error(f"[VALUE_METRICS] Schema healing failed: {e}")
            raise RuntimeError(f"[VALUE_METRICS] Cannot verify schema is ready: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(ValueMetricsLoader))
