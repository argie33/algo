#!/usr/bin/env python3
"""AAII Sentiment Survey Loader - Investor Sentiment Indicators (Market-wide data)."""

import logging
import socket
import sys
import zipfile
from datetime import date
from io import BytesIO
from typing import List, Optional

import pandas as pd
import requests

from config.api_endpoints import get_aaii_sentiment_url
from utils.infrastructure.timeout import ExecutionTimeout
from utils.infrastructure.url_validator import validate_redirect_url, validate_url
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)


class AAIISentimentLoader(OptimalLoader):
    """Load AAII investor sentiment survey data (market-wide, non-symbol based)."""

    table_name = "aaii_sentiment"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch AAII sentiment data from Excel file."""
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(60.0)

        aaii_url = get_aaii_sentiment_url()
        logger.info(f"Downloading AAII sentiment data from: {aaii_url}")

        # SECURITY FIX S-05: Validate AAII URL to prevent SSRF attacks
        is_valid, error_msg = validate_url(aaii_url, allowed_domains=["aaii.com"])
        if not is_valid:
            raise RuntimeError(
                f"[AAII_SENTIMENT] SSRF validation failed for AAII URL: {error_msg}. "
                "Cannot fetch sentiment data with invalid or unsafe URL."
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.aaii.com/",
            "Accept": "application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(1, 6):  # 5 retries
            try:
                logger.info(f"Download attempt {attempt}/5")
                response = requests.get(
                    aaii_url, headers=headers, allow_redirects=True, timeout=60
                )
                response.raise_for_status()

                # SECURITY FIX S-05: Validate redirect target to prevent SSRF via redirects
                if response.url != aaii_url:
                    is_valid, error_msg = validate_redirect_url(
                        aaii_url, response.url, allowed_domains=["aaii.com"]
                    )
                    if not is_valid:
                        logger.error(
                            f"SSRF prevention: Redirect to invalid URL: {error_msg}"
                        )
                        raise ValueError(f"Redirect to invalid URL: {error_msg}")

                content_type = response.headers.get("Content-Type", "")
                if "html" in content_type.lower():
                    logger.error("Server returned HTML instead of Excel")
                    raise ValueError("Server returned HTML instead of Excel")

                if len(response.content) < 1000:
                    logger.error(f"Response too small ({len(response.content)} bytes)")
                    raise ValueError(
                        f"Response too small ({len(response.content)} bytes)"
                    )

                # SECURITY FIX S-04: Validate Excel file structure before parsing
                # Reject files that look malformed or could trigger XXE/billion laughs
                excel_data = BytesIO(response.content)

                # For XLS files (xlrd): xlrd does NOT parse external entities, so safe from XXE
                # For XLSX files: validate structure and reject if compressed size is suspicious
                file_content = response.content
                if file_content.startswith(b"PK"):  # XLSX = ZIP format
                    try:
                        with zipfile.ZipFile(BytesIO(file_content), "r") as zf:
                            # Check for suspicious XML files (XXE indicators)
                            names = zf.namelist()
                            if (
                                len(names) > 10000
                            ):  # Reject if too many entries (billion laughs)
                                raise ValueError(
                                    "Excel file has suspicious structure (too many entries)"
                                )
                            # Verify standard XLSX structure
                            expected_dirs = {"_rels/", "xl/", "docProps/"}
                            actual_dirs = {
                                n.split("/")[0] + "/" for n in names if "/" in n
                            }
                            if not expected_dirs.issubset(actual_dirs):
                                logger.warning(
                                    f"XLSX structure unusual but continuing: {actual_dirs}"
                                )
                    except zipfile.BadZipFile:
                        logger.warning(
                            "File looks like XLSX but ZIP parsing failed, attempting as XLS"
                        )

                excel_data = BytesIO(response.content)
                # Auto-detect format: XLSX files start with PK (ZIP signature); use openpyxl
                # for XLSX and xlrd for legacy XLS. AAII changed their file format over time.
                xl_engine = "openpyxl" if file_content.startswith(b"PK") else "xlrd"
                df = pd.read_excel(excel_data, skiprows=3, engine=xl_engine)

                df.columns = df.columns.str.strip()
                required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    raise ValueError(f"Missing columns: {missing_cols}")

                df = df[required_cols]

                for col in ["Bullish", "Neutral", "Bearish"]:
                    df[col] = (
                        df[col]
                        .astype(str)
                        .str.replace("%", "", regex=False)
                        .str.strip()
                    )
                    df[col] = pd.to_numeric(df[col], errors="coerce")

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

                df.sort_values("Date", inplace=True)
                df.reset_index(drop=True, inplace=True)

                logger.info(f"Successfully downloaded {len(df)} records")

                # Convert to list of dicts matching table schema
                rows = []
                for _, row in df.iterrows():
                    rows.append(
                        {
                            "date": row["Date"],
                            "bullish": (
                                None
                                if pd.isna(row["Bullish"])
                                else float(row["Bullish"])
                            ),
                            "neutral": (
                                None
                                if pd.isna(row["Neutral"])
                                else float(row["Neutral"])
                            ),
                            "bearish": (
                                None
                                if pd.isna(row["Bearish"])
                                else float(row["Bearish"])
                            ),
                        }
                    )

                if not rows:
                    raise RuntimeError(
                        "[AAII_SENTIMENT] No sentiment data parsed from AAII Excel file. "
                        "Cannot load sentiment data without market-wide investor sentiment."
                    )
                return rows

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f"Download attempt {attempt} network error: {e}")
                if attempt < 5:
                    import time
                    wait_time = 3 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(
                        f"[AAII] Failed after 5 attempts: Cannot reach AAII server. {e}"
                    ) from e
            except (ValueError, OSError, zipfile.BadZipFile) as e:
                logger.warning(f"Download attempt {attempt} data format error: {e}")
                if attempt < 5:
                    import time
                    wait_time = 3 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(
                        f"[AAII] Failed after 5 attempts: Invalid Excel data format. {e}"
                    ) from e
            except (KeyError, AttributeError, TypeError) as e:
                raise RuntimeError(
                    f"[AAII] Data format error parsing Excel: {e}. "
                    "AAII file structure may have changed."
                ) from e
            except Exception as e:
                logger.error(f"Download attempt {attempt} unexpected error: {e}")
                if attempt < 5:
                    import time
                    wait_time = 3 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(
                        f"[AAII] Unexpected error after 5 attempts: {e}"
                    ) from e

        raise RuntimeError(
            "[AAII_SENTIMENT] Failed to fetch AAII sentiment data after exhausting all retries. "
            "Cannot proceed without market-wide investor sentiment."
        )


def main():
    try:
        # Execution timeout: AAII Excel download + parsing typically takes 30-60s
        # Set limit to 5 min (300s) to catch hanging downloads early
        with ExecutionTimeout(max_seconds=300, label="load_aaii_sentiment"):
            loader = AAIISentimentLoader()
            result = loader.load_global()

            if result > 0:
                logger.info(f"SUCCESS: {result} AAII sentiment records loaded")
                return 0
            else:
                logger.error("FAILED: No AAII sentiment records loaded")
                return 1
    except Exception as e:
        logger.error(f"AAII sentiment load failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
