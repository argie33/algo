#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Earnings Surprise Loader - Optimal Pattern.

Loads earnings surprise metrics (actual vs estimate).
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningssurprise.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
from utils.structured_logger import get_logger

import argparse
from utils.loader_helpers import get_active_symbols
import logging
logger = get_logger(__name__)
import os
from config.env_loader import load_env
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader

class EarningsSurpriseLoader(OptimalLoader):
    table_name = "earnings_surprise"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "earnings_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch earnings surprise from yfinance earnings_dates."""
        try:
            from utils.yfinance_wrapper import get_ticker
            from datetime import datetime
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)
            df = ticker.earnings_dates
            if df is None or (hasattr(df, "empty") and df.empty):
                return []

            rows = []
            cutoff = since.isoformat() if since else "2000-01-01"
            for idx, row in df.iterrows():
                try:
                    if hasattr(idx, "date"):
                        ed = idx.date().isoformat()
                    else:
                        ed = str(idx)[:10]
                    if ed < cutoff:
                        continue
                    eps_est = row.get("EPS Estimate")
                    eps_actual = row.get("Reported EPS")
                    surprise_pct = row.get("Surprise(%)")

                    def _safe_float(v):
                        try:
                            import math
                            f = float(v)
                            return None if math.isnan(f) else round(f, 4)
                        except (TypeError, ValueError):
                            return None

                    rows.append({
                        "symbol": symbol,
                        "earnings_date": ed,
                        "eps_estimate": _safe_float(eps_est),
                        "eps_actual": _safe_float(eps_actual),
                        "surprise_percent": _safe_float(surprise_pct),
                    })
                except Exception as e:
                    logging.debug(f"Earnings surprise row error {symbol} {idx}: {e}")

            return rows
        except Exception as e:
            logging.debug(f"Earnings surprise fetch error for {symbol}: {e}")
            return []
