#!/usr/bin/env python3
"""NAAIM Exposure Index Loader - Fund Manager Positioning (Market-wide)."""

import sys
import logging
from datetime import date
from typing import Optional, List
import requests
import pandas as pd

from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

from loaders.loader_helper import setup_imports

setup_imports()

class NAAIMExposureLoader(OptimalLoader):
    """Load NAAIM fund manager exposure index."""

    table_name = "naaim"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch NAAIM Exposure Index from website."""
        try:
            url = "https://www.naaim.org/programs/naaim-exposure-index/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Try pandas read_html
            from io import StringIO

            tables = pd.read_html(StringIO(response.text))

            if not tables:
                logger.warning("No tables found in NAAIM page")
                return None

            df = tables[0]
            if len(df.columns) < 3:
                logger.warning(f"Unexpected table format: {df.columns.tolist()}")
                return None

            # Rename columns for consistency — only if exactly 8 columns match expected layout
            if len(df.columns) == 8:
                df.columns = [
                    "Date",
                    "NAAIM Mean",
                    "Bearish",
                    "Q1",
                    "Q2",
                    "Q3",
                    "Bullish",
                    "Deviation",
                ]
            else:
                # Try to find columns by position heuristic (date first, mean second)
                logger.warning(
                    f"NAAIM table has {len(df.columns)} columns (expected 8): {df.columns.tolist()}"
                )
                col_names = [
                    "Date",
                    "NAAIM Mean",
                    "Bearish",
                    "Q1",
                    "Q2",
                    "Q3",
                    "Bullish",
                    "Deviation",
                ]
                df.columns = col_names[: len(df.columns)]

            # Clean data
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            before_dropna = len(df)
            df = df.dropna(subset=["Date"])
            after_dropna = len(df)
            if after_dropna < before_dropna:
                logger.warning(
                    f"Dropped {before_dropna - after_dropna} row(s) with missing/invalid Date "
                    f"— {after_dropna} rows remain"
                )
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

            rows = []
            for _, row in df.iterrows():
                rows.append(
                    {
                        "date": row["Date"],
                        "naaim_number_mean": (
                            float(row["NAAIM Mean"])
                            if pd.notna(row["NAAIM Mean"])
                            else None
                        ),
                        "bullish_alloc": (
                            float(row["Bullish"]) if pd.notna(row["Bullish"]) else None
                        ),
                        "bearish_alloc": (
                            float(row["Bearish"]) if pd.notna(row["Bearish"]) else None
                        ),
                    }
                )

            return rows if rows else None

        except Exception as e:
            logger.error(f"Failed to fetch NAAIM data: {e}")
            return None

def main():
    loader = NAAIMExposureLoader()
    result = loader.load_global()

    if result > 0:
        logger.info("SUCCESS: NAAIM data loaded")
        return 0
    else:
        logger.warning("COMPLETED: No NAAIM data loaded")
        return 0

if __name__ == "__main__":
    sys.exit(main())
