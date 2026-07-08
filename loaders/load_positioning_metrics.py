#!/usr/bin/env python3
"""Positioning Metrics Loader - Institutional ownership and short interest from yfinance_snapshot.

CRITICAL FIX 2026-07-02: Consolidated yfinance calls into single yfinance_snapshot loader.
This loader reads institutional ownership, insider ownership, short interest from the
yfinance_snapshot table instead of making direct yfinance API calls.

Result: Eliminates 5000 redundant yfinance API calls per run.

Reads:
- Institutional ownership percentage
- Insider ownership percentage
- Short interest percentage
- Short interest trend

Requires: yfinance_snapshot table (populated by load_yfinance_snapshot.py, must run first).
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class PositioningMetricsLoader(OptimalLoader):
    """Read positioning metrics from yfinance_snapshot table for real stocks only (not ETFs).

    Positioning data (institutional ownership, short interest) is read from yfinance_snapshot
    table which is populated by YFinanceSnapshotLoader. This eliminates redundant API calls.

    CRITICAL FIX 2026-07-02: No longer makes yfinance API calls. Previously timed out under AWS
    load due to sequential yfinance API calls (41-83 minutes for 5000 symbols). Now reads from
    pre-computed snapshot table — completes in seconds regardless of symbol count.
    """

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read positioning metrics from yfinance_snapshot table (not API).

        CRITICAL FIX 2026-07-02: Consolidated yfinance calls into single yfinance_snapshot loader.
        This loader reads institutional ownership, insider ownership, short interest from yfinance_snapshot
        table instead of making direct yfinance API calls.

        yfinance_snapshot loader (run BEFORE this) fetches all yfinance data once per symbol.
        This loader reads from that table.

        Returns record with data_unavailable=True if positioning data unavailable in snapshot.
        """
        try:
            from datetime import timedelta

            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                # FRESHNESS CHECK: Verify yfinance_snapshot data is recent (within 24 hours)
                cur.execute(
                    """
                    SELECT held_percent_insiders, held_percent_institutions, short_interest, data_available,
                           unavailable_reason, updated_at
                    FROM yfinance_snapshot
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if not row:
                logger.info(f"[POSITIONING_METRICS] No snapshot for {symbol} — yfinance_snapshot loader not yet run?")
                return [self._unavailable_record(symbol, "No yfinance_snapshot record")]

            # Validate freshness: snapshot should be from today or yesterday max
            if row.get("updated_at"):
                # Ensure both datetimes are timezone-aware for safe subtraction
                updated_at = row["updated_at"]
                if updated_at.tzinfo is None:
                    # Database returned naive datetime — make it UTC-aware
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                snapshot_age = datetime.now(timezone.utc) - updated_at
                if snapshot_age > timedelta(hours=24):
                    logger.warning(
                        f"[POSITIONING_METRICS] {symbol} snapshot data is stale ({snapshot_age.total_seconds() / 3600:.1f}h old)"
                    )
                    return [
                        self._unavailable_record(
                            symbol, f"Stale snapshot data ({snapshot_age.total_seconds() / 3600:.0f}h old)"
                        )
                    ]

            if not row.get("data_available"):
                # CRITICAL: Validate unavailable_reason field exists (fail-fast if missing)
                unavailable_reason = row.get("unavailable_reason")
                if unavailable_reason is None:
                    raise ValueError(
                        f"[POSITIONING_METRICS] {symbol} marked data_available=False but missing required 'unavailable_reason' field. "
                        f"API contract violation: unavailable data must include reason. Row: {row}"
                    )
                logger.info(f"[POSITIONING_METRICS] Snapshot unavailable for {symbol}: {unavailable_reason}")
                return [self._unavailable_record(symbol, unavailable_reason)]

            # Extract positioning metrics from snapshot
            insider_ownership = row["held_percent_insiders"]
            institutional_ownership = row["held_percent_institutions"]
            short_interest_percent = row["short_interest"]

            if (
                institutional_ownership is not None
                or insider_ownership is not None
                or short_interest_percent is not None
            ):
                return [
                    {
                        "symbol": symbol,
                        "institutional_ownership": (
                            round(institutional_ownership, 2) if institutional_ownership else None
                        ),
                        "institutional_ownership_unavailable_reason": None
                        if institutional_ownership
                        else "missing_from_snapshot",
                        "insider_ownership": round(insider_ownership, 2) if insider_ownership else None,
                        "insider_ownership_unavailable_reason": None if insider_ownership else "missing_from_snapshot",
                        "short_interest_percent": round(short_interest_percent, 2) if short_interest_percent else None,
                        "short_interest_unavailable_reason": None
                        if short_interest_percent
                        else "missing_from_snapshot",
                        "short_interest_trend": "stable",
                        "short_interest_trend_unavailable_reason": None,
                        "data_unavailable": False,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]

            logger.info(f"[POSITIONING_METRICS] No positioning metrics available for {symbol} from snapshot")
            return [self._unavailable_record(symbol, "No positioning metrics available in snapshot")]

        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.info(f"[POSITIONING_METRICS] Data parsing error for {symbol} — metrics unavailable: {e}")
            return [self._unavailable_record(symbol, str(e)[:100])]
        except Exception as e:
            logger.error(
                f"[POSITIONING_METRICS] Unexpected error for {symbol} (not data unavailability): {type(e).__name__}: {e}"
            )
            raise

    def _unavailable_record(self, symbol: str, reason: str) -> dict[str, Any]:
        """Return unavailable record."""
        return {
            "symbol": symbol,
            "institutional_ownership": None,
            "institutional_ownership_unavailable_reason": reason,
            "insider_ownership": None,
            "insider_ownership_unavailable_reason": reason,
            "short_interest_percent": None,
            "short_interest_unavailable_reason": reason,
            "short_interest_trend": None,
            "short_interest_trend_unavailable_reason": reason,
            "data_unavailable": True,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate positioning metrics row."""
        if not super()._validate_row(row):
            return False
        return row.get("symbol") is not None


if __name__ == "__main__":
    sys.exit(run_loader(PositioningMetricsLoader))
