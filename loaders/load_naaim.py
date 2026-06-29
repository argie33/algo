#!/usr/bin/env python3
"""NAAIM Exposure Index Loader - Fund Manager Positioning (Market-wide)."""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date  # noqa: E402
from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.infrastructure.url_validator import validate_url  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class NAAIMExposureLoader(OptimalLoader):
    """Load NAAIM fund manager exposure index."""

    table_name = "naaim"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Fetch NAAIM Exposure Index from website. FAIL-FAST on missing data.

        NAAIM sentiment is CRITICAL for market regime detection. Returns explicit
        data_unavailable marker when data cannot be fetched or parsed.

        Returns:
            List with single dict containing either:
            - Valid NAAIM sentiment records (date, naaim_number_mean, bullish_alloc, bearish_alloc)
            - Explicit {data_unavailable: True, reason: ...} marker when data unavailable
        """
        try:
            url = "https://www.naaim.org/programs/naaim-exposure-index/"

            # SECURITY FIX S-05: Validate URL to prevent SSRF attacks
            is_valid, error_msg = validate_url(url, allowed_domains=["naaim.org"])
            if not is_valid:
                raise RuntimeError(
                    f"SSRF validation failed for NAAIM URL: {error_msg}. "
                    f"Cannot fetch market sentiment data without valid URL."
                )

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Try pandas read_html
            from io import StringIO

            tables = pd.read_html(StringIO(response.text), flavor="lxml")

            if not tables:
                logger.warning(
                    "NAAIM page contains no data tables. "
                    "Website format may have changed or data is temporarily unavailable."
                )
                return [{"data_unavailable": True, "reason": "no_data_tables_found"}]

            df = tables[0]

            # Skip header row if first row contains 'Date' column name
            if len(df) > 0 and "Date" in df.iloc[0].values:
                logger.info("Skipping header row from HTML table parsing")
                df = df.iloc[1:].reset_index(drop=True)

            if len(df) == 0:
                logger.warning("NAAIM table is empty after header skipping")
                return [{"data_unavailable": True, "reason": "no_rows_in_table"}]

            if len(df.columns) < 3:
                raise RuntimeError(
                    f"NAAIM table format unexpected: got {len(df.columns)} columns, need ≥3. "
                    f"Columns found: {df.columns.tolist()}. "
                    f"Website format may have changed."
                )

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
                logger.warning(f"NAAIM table has {len(df.columns)} columns (expected 8): {df.columns.tolist()}")
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

            # Clean data with strict validation
            before_coerce = df["Date"].copy()
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            # CRITICAL: Validate dates before dropping
            invalid_dates = before_coerce[df["Date"].isna() & before_coerce.notna()]
            if len(invalid_dates) > 0:
                bad_dates = invalid_dates.unique()[:5]
                raise ValueError(
                    f"[NAAIM] Date column contains unparseable values (data corruption): {bad_dates}. "
                    f"Cannot load NAAIM sentiment data with corrupted dates."
                )
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

            rows = []
            for _, row in df.iterrows():
                # Validate that at least one metric is present
                naaim_mean = float(row["NAAIM Mean"]) if pd.notna(row["NAAIM Mean"]) else None
                bullish = float(row["Bullish"]) if pd.notna(row["Bullish"]) else None
                bearish = float(row["Bearish"]) if pd.notna(row["Bearish"]) else None

                # Skip rows where all metrics are None (no actual data)
                if all(v is None for v in [naaim_mean, bullish, bearish]):
                    logger.debug(f"Skipping NAAIM row for {row['Date']}: all metrics are None")
                    continue

                rows.append(
                    {
                        "date": row["Date"],
                        "naaim_number_mean": naaim_mean,
                        "bullish_alloc": bullish,
                        "bearish_alloc": bearish,
                    }
                )

            # If no valid rows found, return explicit marker
            if not rows:
                logger.warning("NAAIM table parsed but contains no valid sentiment data (all rows have null metrics)")
                return [{"data_unavailable": True, "reason": "no_valid_sentiment_records"}]

            return rows

        except ValueError as e:
            # Data validation error (corrupted dates, etc.)
            logger.error(f"[NAAIM] Data validation failed: {e}")
            raise RuntimeError(f"NAAIM data validation error: {e}") from e
        except (requests.RequestException, RuntimeError, ZeroDivisionError, TypeError) as e:
            # Network, parsing, or other errors
            logger.error(f"[NAAIM] Failed to fetch or parse NAAIM sentiment data: {e}")
            raise RuntimeError(f"NAAIM fetch/parse error: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(NAAIMExposureLoader, global_mode=True))
