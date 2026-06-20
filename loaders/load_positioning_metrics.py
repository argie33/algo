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

import logging
from datetime import date, datetime, timezone
from typing import Dict, Optional

from loaders.runner import run_loader
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class PositioningMetricsLoader(OptimalLoader):
    """Fetch positioning metrics from yfinance."""

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None):
        """Fetch positioning metrics for this symbol."""
        try:
            metrics = self._fetch_positioning_metrics(symbol)
            if metrics:
                return [metrics]
            return None
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    @staticmethod
    def _fetch_positioning_metrics(symbol: str) -> dict | None:
        """Fetch institutional ownership and short interest from yfinance via the rate-limiting wrapper."""
        from utils.external.yfinance import get_ticker

        ticker = get_ticker(symbol)
        if not ticker:
            return None

        try:
            info = ticker.info

            institutional_ownership = None
            insider_ownership = None
            short_interest_percent = None
            short_interest_trend = None

            if (
                "heldPercentInstitutions" in info
                and info["heldPercentInstitutions"] is not None
            ):
                institutional_ownership = float(info["heldPercentInstitutions"]) * 100
            elif (
                "institutional_ownership" in info
                and info["institutional_ownership"] is not None
            ):
                institutional_ownership = float(info["institutional_ownership"])

            if (
                "heldPercentInsiders" in info
                and info["heldPercentInsiders"] is not None
            ):
                insider_ownership = float(info["heldPercentInsiders"]) * 100
            elif "insider_ownership" in info and info["insider_ownership"] is not None:
                insider_ownership = float(info["insider_ownership"])

            if (
                "shortPercentOfFloat" in info
                and info["shortPercentOfFloat"] is not None
            ):
                short_interest_percent = float(info["shortPercentOfFloat"]) * 100
            elif (
                "short_percent_of_float" in info
                and info["short_percent_of_float"] is not None
            ):
                short_interest_percent = float(info["short_percent_of_float"])
            elif "shortRatio" in info and info["shortRatio"] is not None:
                short_interest_percent = float(info["shortRatio"])

            if "sharesShort" in info and info["sharesShort"] is not None:
                short_interest_trend = "stable"

            if institutional_ownership or insider_ownership or short_interest_percent:
                return {
                    "symbol": symbol,
                    "institutional_ownership": (
                        round(institutional_ownership, 2)
                        if institutional_ownership
                        else None
                    ),
                    "insider_ownership": (
                        round(insider_ownership, 2) if insider_ownership else None
                    ),
                    "short_interest_percent": (
                        round(short_interest_percent, 2)
                        if short_interest_percent
                        else None
                    ),
                    "short_interest_trend": short_interest_trend,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            return None

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate positioning metrics row."""
        if not super()._validate_row(row):
            return False
        return row.get("symbol") is not None



if __name__ == "__main__":
    sys.exit(run_loader(PositioningMetricsLoader))
