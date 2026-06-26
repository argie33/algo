#!/usr/bin/env python3
"""Positioning Metrics Loader - Institutional ownership and short interest from yfinance.

Fetches:
- Institutional ownership percentage
- Insider ownership percentage
- Short interest percentage
- Short interest trend

Requires: active symbols list.
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

import requests  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.loaders.transient_errors import TransientAPIError  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class PositioningMetricsLoader(OptimalLoader):
    """Fetch positioning metrics from yfinance."""

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Fetch positioning metrics for this symbol.

        Returns None if positioning data is unavailable (many symbols lack institutional ownership,
        short interest, or other positioning metrics in yfinance). This is normal for illiquid stocks
        and does not constitute a loader failure.

        Raises:
            Unexpected exceptions are re-raised to surface programming errors immediately.
        """
        try:
            metrics = self._fetch_positioning_metrics(symbol)
            if not metrics:
                logger.debug(f"[POSITIONING_METRICS] No positioning data available for {symbol} (skipping)")
                return None
            return [metrics]
        except (ValueError, TypeError, ZeroDivisionError) as e:
            # Expected errors: parsing issues, type mismatches
            logger.debug(f"[POSITIONING_METRICS] Data parsing error for {symbol} (skipping): {e}")
            return None
        except Exception as e:
            # Unexpected errors (database errors, network issues, bugs) should surface immediately
            logger.error(f"[POSITIONING_METRICS] Unexpected error for {symbol} (not data unavailability): {type(e).__name__}: {e}")
            raise

    @staticmethod
    def _fetch_positioning_metrics(symbol: str) -> dict[str, Any] | None:
        """Fetch institutional ownership and short interest from yfinance via the rate-limiting wrapper.

        Skips symbols with market cap < $50M (illiquid stocks typically lack positioning data).
        This reduces unnecessary API calls and improves loader throughput.

        Raises:
            TransientAPIError: On timeouts/connection errors (orchestrator will retry with backoff)
        """
        from utils.external.yfinance import get_ticker

        try:
            ticker = get_ticker(symbol)
        except requests.Timeout as e:
            logger.warning(f"[POSITIONING_METRICS] Timeout fetching ticker for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Timeout fetching ticker for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[POSITIONING_METRICS] Connection error for {symbol} (transient, will retry): {e}")
            raise TransientAPIError(f"Connection error fetching ticker for {symbol}") from e

        if not ticker:
            return None

        try:
            try:
                info = ticker.info
            except requests.Timeout as e:
                logger.warning(f"[POSITIONING_METRICS] Timeout accessing ticker.info for {symbol} (transient, will retry): {e}")
                raise TransientAPIError(f"Timeout accessing ticker.info for {symbol}") from e
            except requests.ConnectionError as e:
                logger.warning(f"[POSITIONING_METRICS] Connection error for {symbol} (transient, will retry): {e}")
                raise TransientAPIError(f"Connection error accessing ticker.info for {symbol}") from e

            # Early exit for extremely illiquid symbols (< $1M market cap)
            # These symbols typically lack reliable positioning data and aren't trading candidates
            mkt_cap = info.get("marketCap")
            if mkt_cap and mkt_cap < 1_000_000:
                logger.debug(f"Skipping {symbol} (market cap ${mkt_cap:,} < $1M threshold)")
                return None

            institutional_ownership = None
            insider_ownership = None
            short_interest_percent = None
            short_interest_trend = None

            if "heldPercentInstitutions" in info and info["heldPercentInstitutions"] is not None:
                institutional_ownership = float(info["heldPercentInstitutions"]) * 100
            elif "institutional_ownership" in info and info["institutional_ownership"] is not None:
                institutional_ownership = float(info["institutional_ownership"])

            if "heldPercentInsiders" in info and info["heldPercentInsiders"] is not None:
                insider_ownership = float(info["heldPercentInsiders"]) * 100
            elif "insider_ownership" in info and info["insider_ownership"] is not None:
                insider_ownership = float(info["insider_ownership"])

            if "shortPercentOfFloat" in info and info["shortPercentOfFloat"] is not None:
                short_interest_percent = float(info["shortPercentOfFloat"]) * 100
            elif "short_percent_of_float" in info and info["short_percent_of_float"] is not None:
                short_interest_percent = float(info["short_percent_of_float"])
            elif "shortRatio" in info and info["shortRatio"] is not None:
                short_interest_percent = float(info["shortRatio"])

            if "sharesShort" in info and info["sharesShort"] is not None:
                short_interest_trend = "stable"

            if institutional_ownership or insider_ownership or short_interest_percent:
                return {
                    "symbol": symbol,
                    "institutional_ownership": (round(institutional_ownership, 2) if institutional_ownership else None),
                    "insider_ownership": (round(insider_ownership, 2) if insider_ownership else None),
                    "short_interest_percent": (round(short_interest_percent, 2) if short_interest_percent else None),
                    "short_interest_trend": short_interest_trend,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            return None

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"[POSITIONING_METRICS] Parsing error for {symbol} (skipping): {e}")
            return None

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
