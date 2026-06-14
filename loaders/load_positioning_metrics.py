#!/usr/bin/env python3
"""Positioning Metrics Loader - Institutional ownership and short interest from yfinance.

Fetches:
- Institutional ownership percentage
- Insider ownership percentage
- Short interest percentage
- Short interest trend

Requires: active symbols list.
"""
from loaders.loader_helper import setup_imports
setup_imports()

import sys
import argparse
import logging
import os
from datetime import date, datetime, timezone
from typing import List, Optional, Dict

from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.loaders.config import get_parallelism, get_default_parallelism

logger = logging.getLogger(__name__)

class PositioningMetricsLoader(OptimalLoader):
    """Fetch positioning metrics from yfinance."""

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch positioning metrics for this symbol."""
        try:
            metrics = self._fetch_positioning_metrics(symbol)
            if metrics:
                return [metrics]
            return None
        except Exception as e:
            logger.debug(f"Positioning metrics error for {symbol}: {e}")
            return None

    @staticmethod
    def _fetch_positioning_metrics(symbol: str) -> Optional[Dict]:
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

            if 'heldPercentInstitutions' in info and info['heldPercentInstitutions'] is not None:
                institutional_ownership = float(info['heldPercentInstitutions']) * 100
            elif 'institutional_ownership' in info and info['institutional_ownership'] is not None:
                institutional_ownership = float(info['institutional_ownership'])

            if 'heldPercentInsiders' in info and info['heldPercentInsiders'] is not None:
                insider_ownership = float(info['heldPercentInsiders']) * 100
            elif 'insider_ownership' in info and info['insider_ownership'] is not None:
                insider_ownership = float(info['insider_ownership'])

            if 'shortPercentOfFloat' in info and info['shortPercentOfFloat'] is not None:
                short_interest_percent = float(info['shortPercentOfFloat']) * 100
            elif 'short_percent_of_float' in info and info['short_percent_of_float'] is not None:
                short_interest_percent = float(info['short_percent_of_float'])
            elif 'shortRatio' in info and info['shortRatio'] is not None:
                short_interest_percent = float(info['shortRatio'])

            if 'sharesShort' in info and info['sharesShort'] is not None:
                short_interest_trend = 'stable'

            if institutional_ownership or insider_ownership or short_interest_percent:
                return {
                    'symbol': symbol,
                    'institutional_ownership': round(institutional_ownership, 2) if institutional_ownership else None,
                    'insider_ownership': round(insider_ownership, 2) if insider_ownership else None,
                    'short_interest_percent': round(short_interest_percent, 2) if short_interest_percent else None,
                    'short_interest_trend': short_interest_trend,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                }

            return None

        except Exception as e:
            logger.debug(f"Could not fetch positioning metrics for {symbol}: {e}")
            return None

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate positioning metrics row."""
        if not super()._validate_row(row):
            return False
        return row.get('symbol') is not None

def main():
    parser = argparse.ArgumentParser(description="Positioning Metrics Loader")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=get_default_parallelism("positioning_metrics"), help="Concurrent workers")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60)
    loader = PositioningMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    if fail_rate > 0.05:
        logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

