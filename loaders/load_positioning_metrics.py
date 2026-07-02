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
    """Fetch positioning metrics from yfinance for real stocks only (not ETFs).

    Positioning data (institutional ownership, short interest) is collected for individual stocks.
    ETFs don't have meaningful positioning metrics in the same way.

    PERFORMANCE NOTE: This loader has historically timed out under AWS load due to sequential
    yfinance API calls. Timeout threshold: 15 minutes for 5000+ symbols.
    At ~0.5-1 sec per symbol, sequential execution = 41-83 minutes (exceeds timeout).

    CRITICAL FIX: fetch_incremental now retries on transient errors (timeouts, connection errors)
    instead of immediately failing, allowing more resilience to network hiccups.
    For systemic slowness, consider parallelism tuning in LOADER_PARALLELISM env var.
    """

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch positioning metrics for this symbol.

        Returns record with data_unavailable=True if positioning data is unavailable
        (many symbols lack institutional ownership, short interest, or other metrics in yfinance).
        This is normal for illiquid stocks but absence must be EXPLICIT (not silent None).

        Raises:
            Unexpected exceptions are re-raised to surface programming errors immediately.
        """
        try:
            metrics = self._fetch_positioning_metrics(symbol)
            return [metrics]
        except (ValueError, TypeError, ZeroDivisionError) as e:
            # Expected errors: parsing issues, type mismatches
            logger.info(f"[POSITIONING_METRICS] Data parsing error for {symbol} — metrics unavailable: {e}")
            return [
                {
                    "symbol": symbol,
                    "institutional_ownership": None,
                    "insider_ownership": None,
                    "short_interest_percent": None,
                    "short_interest_trend": None,
                    "data_unavailable": True,
                    "reason": f"Data parsing error: {str(e)[:100]}",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        except Exception as e:
            # HTTP 404: symbol not found on yfinance (expected for depositary shares, illiquid stocks)
            # Other errors (database errors, network issues, bugs) should surface immediately
            import requests as req_module

            if isinstance(e, req_module.HTTPError) and "404" in str(e):
                logger.info(
                    f"[POSITIONING_METRICS] Symbol not found on yfinance for {symbol} (404 Not Found). "
                    f"Depositary shares and illiquid symbols often unavailable. Marking data unavailable."
                )
                return [
                    {
                        "symbol": symbol,
                        "institutional_ownership": None,
                        "insider_ownership": None,
                        "short_interest_percent": None,
                        "short_interest_trend": None,
                        "data_unavailable": True,
                        "reason": "Symbol not found on yfinance (depositary share or illiquid security)",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            # Other unexpected errors should surface immediately
            logger.error(
                f"[POSITIONING_METRICS] Unexpected error for {symbol} (not data unavailability): {type(e).__name__}: {e}"
            )
            raise

    @staticmethod
    def _fetch_positioning_metrics(symbol: str) -> dict[str, Any]:
        """Fetch institutional ownership and short interest from yfinance via the rate-limiting wrapper.

        Skips symbols with market cap < $1M (illiquid stocks typically lack positioning data).
        This reduces unnecessary API calls and improves loader throughput.

        Returns dict with data_unavailable=True if positioning data unavailable (not silent None).

        Raises:
            TransientAPIError: On timeouts/connection errors (orchestrator will retry with backoff)
        """
        from utils.external.yfinance import get_ticker

        try:
            ticker = get_ticker(symbol)
        except requests.Timeout as e:
            logger.warning(f"[POSITIONING_METRICS] Timeout fetching ticker for {symbol} (transient, will retry): {e}")
            # CRITICAL: Mark as transient so orchestrator retries this symbol instead of failing entire loader
            raise TransientAPIError(f"Timeout fetching ticker for {symbol}") from e
        except requests.ConnectionError as e:
            logger.warning(f"[POSITIONING_METRICS] Connection error for {symbol} (transient, will retry): {e}")
            # CRITICAL: Mark as transient so orchestrator retries this symbol instead of failing entire loader
            raise TransientAPIError(f"Connection error fetching ticker for {symbol}") from e

        if not ticker:
            logger.info(f"[POSITIONING_METRICS] No ticker data available for {symbol}")
            return {
                "symbol": symbol,
                "institutional_ownership": None,
                "insider_ownership": None,
                "short_interest_percent": None,
                "short_interest_trend": None,
                "data_unavailable": True,
                "reason": "Ticker object unavailable from yfinance",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        try:
            try:
                info = ticker.info
            except requests.Timeout as e:
                logger.warning(
                    f"[POSITIONING_METRICS] Timeout accessing ticker.info for {symbol} (transient, will retry): {e}"
                )
                raise TransientAPIError(f"Timeout accessing ticker.info for {symbol}") from e
            except requests.ConnectionError as e:
                logger.warning(f"[POSITIONING_METRICS] Connection error for {symbol} (transient, will retry): {e}")
                raise TransientAPIError(f"Connection error accessing ticker.info for {symbol}") from e

            # Early exit for extremely illiquid symbols (< $1M market cap)
            # These symbols typically lack reliable positioning data and aren't trading candidates
            mkt_cap = info.get("marketCap")
            if mkt_cap is not None and mkt_cap < 1_000_000:
                logger.info(f"[POSITIONING_METRICS] Skipping {symbol} (market cap ${mkt_cap:,} < $1M threshold)")
                return {
                    "symbol": symbol,
                    "institutional_ownership": None,
                    "insider_ownership": None,
                    "short_interest_percent": None,
                    "short_interest_trend": None,
                    "data_unavailable": True,
                    "reason": "Market cap below $1M threshold (illiquid stock)",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            institutional_ownership = None
            institutional_ownership_reason = "field_missing_from_source"
            insider_ownership = None
            insider_ownership_reason = "field_missing_from_source"
            short_interest_percent = None
            short_interest_reason = "field_missing_from_source"
            short_interest_trend = None
            short_interest_trend_reason = "field_missing_from_source"

            if "heldPercentInstitutions" in info and info["heldPercentInstitutions"] is not None:
                institutional_ownership = float(info["heldPercentInstitutions"]) * 100
                institutional_ownership_reason = None

            if "heldPercentInsiders" in info and info["heldPercentInsiders"] is not None:
                insider_ownership = float(info["heldPercentInsiders"]) * 100
                insider_ownership_reason = None

            if "shortPercentOfFloat" in info and info["shortPercentOfFloat"] is not None:
                short_interest_percent = float(info["shortPercentOfFloat"]) * 100
                short_interest_reason = None

            if "sharesShort" in info and info["sharesShort"] is not None:
                short_interest_trend = "stable"
                short_interest_trend_reason = None

            if (
                institutional_ownership is not None
                or insider_ownership is not None
                or short_interest_percent is not None
            ):
                return {
                    "symbol": symbol,
                    "institutional_ownership": (round(institutional_ownership, 2) if institutional_ownership else None),
                    "institutional_ownership_unavailable_reason": institutional_ownership_reason,
                    "insider_ownership": (round(insider_ownership, 2) if insider_ownership else None),
                    "insider_ownership_unavailable_reason": insider_ownership_reason,
                    "short_interest_percent": (round(short_interest_percent, 2) if short_interest_percent else None),
                    "short_interest_unavailable_reason": short_interest_reason,
                    "short_interest_trend": short_interest_trend,
                    "short_interest_trend_unavailable_reason": short_interest_trend_reason,
                    "data_unavailable": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            # CRITICAL FIX 2026-07-01: Removed synthetic volume-based proxy for new listings
            # Reason: User requires only REAL data, no synthetic/fake metrics
            # New listings without yfinance positioning data now return explicit data_unavailable=True
            # instead of computing fake positioning scores from volume patterns

            # Fallback: no positioning data available at all
            logger.info(f"[POSITIONING_METRICS] No positioning metrics found for {symbol} (all fields unavailable)")
            return {
                "symbol": symbol,
                "institutional_ownership": None,
                "institutional_ownership_unavailable_reason": institutional_ownership_reason,
                "insider_ownership": None,
                "insider_ownership_unavailable_reason": insider_ownership_reason,
                "short_interest_percent": None,
                "short_interest_unavailable_reason": short_interest_reason,
                "short_interest_trend": None,
                "short_interest_trend_unavailable_reason": short_interest_trend_reason,
                "data_unavailable": True,
                "reason": "No positioning metrics available in data source",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(
                f"[POSITIONING_METRICS] Cannot parse positioning data for {symbol}: {e}. "
                f"Data may be corrupted or API format changed."
            )
            raise RuntimeError(
                f"[POSITIONING_METRICS] Positioning metrics data for {symbol} is corrupted. "
                f"Cannot parse positioning information. Error: {e}"
            ) from e

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
