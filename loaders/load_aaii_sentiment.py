#!/usr/bin/env python3
"""AAII Sentiment Survey Loader - Investor Sentiment Indicators (Market-wide data)."""

import json
import logging
import socket
import sys
import zipfile
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd
import requests

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from config.api_endpoints import get_aaii_sentiment_url
from loaders.runner import run_loader
from utils.infrastructure.url_validator import validate_redirect_url, validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AAIISentimentLoader(OptimalLoader):
    """Load AAII investor sentiment survey data (market-wide, non-symbol based)."""

    table_name = "aaii_sentiment"
    primary_key = ("date",)
    watermark_field = "date"

    @staticmethod
    def _fetch_with_playwright(aaii_url: str) -> bytes | None:
        """Fetch AAII sentiment file using Playwright to bypass bot detection.

        AAII website uses Imperva bot protection that blocks regular HTTP requests.
        Playwright renders JavaScript which bypasses the Imperva challenge.

        Args:
            aaii_url: URL to fetch

        Returns:
            File content bytes if successful, None on failure
        """
        if not HAS_PLAYWRIGHT:
            logger.debug("Playwright not available for bot detection bypass")
            return None

        try:
            logger.debug("Attempting fetch with Playwright (JavaScript rendering)...")
            with sync_playwright() as p:
                # Launch headless browser with minimal overhead
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )

                try:
                    # First visit sentiment survey page to establish cookies/session
                    logger.debug("Visiting AAII sentiment page to establish session...")
                    page.goto("https://www.aaii.com/sentiment-survey", timeout=30000)

                    # Now fetch the file with proper session/cookies
                    logger.debug(f"Downloading file from {aaii_url}...")
                    response = page.goto(aaii_url, timeout=30000)

                    if response and response.status == 200:
                        logger.debug("File response received")
                        body = response.body()
                        if body and len(body) > 1000:
                            logger.debug(f"Successfully fetched {len(body)} bytes with Playwright")
                            return body

                except Exception as e:
                    logger.debug(f"Playwright page navigation error: {e}")
                finally:
                    page.close()
                    browser.close()

        except Exception as e:
            logger.debug(f"Playwright fetch failed: {e}")

        return None

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:  # noqa: C901
        """Fetch AAII sentiment data from Excel file.

        Complexity justified: Data integrity checks (SSRF validation, zip structure,
        coerce validation, date validation) are essential for financial data
        security and correctness. Cannot be factored without losing failure context.

        Falls back to Playwright for Imperva bot detection bypass if regular requests fail.
        """
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(20.0)

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

        for attempt in range(1, 4):  # 3 retries (faster failure)
            try:
                logger.info(f"Download attempt {attempt}/3")
                response = requests.get(aaii_url, headers=headers, allow_redirects=True, timeout=15)
                response.raise_for_status()

                # SECURITY FIX S-05: Validate redirect target to prevent SSRF via redirects
                if response.url != aaii_url:
                    is_valid, error_msg = validate_redirect_url(aaii_url, response.url, allowed_domains=["aaii.com"])
                    if not is_valid:
                        logger.error(f"SSRF prevention: Redirect to invalid URL: {error_msg}")
                        raise ValueError(f"Redirect to invalid URL: {error_msg}")

                content_type = response.headers.get("Content-Type")
                if not content_type:
                    logger.error("Missing Content-Type header in AAII response")
                    raise ValueError("Missing Content-Type header in AAII response (cannot verify Excel file)")
                if "html" in content_type.lower():
                    logger.error("Server returned HTML instead of Excel (likely Imperva bot detection)")
                    raise ValueError("Server returned HTML instead of Excel")

                if len(response.content) < 1000:
                    logger.error(f"Response too small ({len(response.content)} bytes)")
                    raise ValueError(f"Response too small ({len(response.content)} bytes)")

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
                            if len(names) > 10000:  # Reject if too many entries (billion laughs)
                                raise ValueError("Excel file has suspicious structure (too many entries)")
                            # Verify standard XLSX structure
                            expected_dirs = {"_rels/", "xl/", "docProps/"}
                            actual_dirs = {n.split("/")[0] + "/" for n in names if "/" in n}
                            if not expected_dirs.issubset(actual_dirs):
                                logger.warning(f"XLSX structure unusual but continuing: {actual_dirs}")
                    except zipfile.BadZipFile:
                        logger.warning("File looks like XLSX but ZIP parsing failed, attempting as XLS")

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
                    df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                    # CRITICAL: Validate BEFORE coercion to detect corruption
                    before_coerce = df[col].copy()
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    newly_nan = before_coerce[df[col].isna() & before_coerce.notna()]
                    if len(newly_nan) > 0:
                        bad_values = newly_nan.unique()[:5]
                        raise ValueError(
                            f"[AAII_SENTIMENT] {col} contains unparseable values (data corruption): {bad_values}. "
                            f"Cannot load sentiment data with corrupted numeric fields."
                        )

                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                # CRITICAL: Validate dates before dropping
                before_coerce = df["Date"].copy()
                invalid_dates = before_coerce[df["Date"].isna() & before_coerce.notna()]
                if len(invalid_dates) > 0:
                    bad_dates = invalid_dates.unique()[:5]
                    raise ValueError(
                        f"[AAII_SENTIMENT] Date column contains unparseable values (data corruption): {bad_dates}. "
                        f"Cannot load sentiment data with corrupted dates."
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
                            "bullish": (None if pd.isna(row["Bullish"]) else float(row["Bullish"])),
                            "neutral": (None if pd.isna(row["Neutral"]) else float(row["Neutral"])),
                            "bearish": (None if pd.isna(row["Bearish"]) else float(row["Bearish"])),
                        }
                    )

                if not rows:
                    logger.warning(
                        "[AAII_SENTIMENT] No sentiment data parsed from AAII Excel file."
                    )
                    return [{
                        "data_unavailable": True,
                        "reason": "No sentiment data parsed from AAII Excel file",
                        "created_at": datetime.now().isoformat(),
                    }]
                return rows

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as e:
                logger.warning(f"Download attempt {attempt} network error: {e}")
                if attempt < 3:
                    import time

                    wait_time = 2 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(
                        f"[AAII] Failed after 3 attempts: Cannot reach AAII server. {e}"
                    )
                    return [{
                        "data_unavailable": True,
                        "reason": f"Cannot reach AAII server after 3 attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except (json.JSONDecodeError, zipfile.BadZipFile) as e:
                logger.warning(f"Download attempt {attempt} data format error: {e}")
                if attempt < 3:
                    import time

                    wait_time = 2 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(
                        f"[AAII] Failed after 3 attempts: Invalid Excel data format. {e}"
                    )
                    return [{
                        "data_unavailable": True,
                        "reason": f"Invalid Excel data format after 3 attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except ValueError as e:
                # If getting HTML (Imperva bot detection), try Playwright fallback on last attempt
                error_str = str(e)
                if "HTML instead of Excel" in error_str and attempt == 3 and HAS_PLAYWRIGHT:
                    logger.info("Regular request failed with bot detection, trying Playwright fallback...")
                    file_content = self._fetch_with_playwright(aaii_url)
                    if file_content:
                        try:
                            # Parse the Playwright-fetched content
                            excel_data = BytesIO(file_content)
                            xl_engine = "openpyxl" if file_content.startswith(b"PK") else "xlrd"
                            df = pd.read_excel(excel_data, skiprows=3, engine=xl_engine)

                            df.columns = df.columns.str.strip()
                            required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
                            df = df[required_cols]

                            for col in ["Bullish", "Neutral", "Bearish"]:
                                df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                                df[col] = pd.to_numeric(df[col], errors="coerce")

                            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                            df.sort_values("Date", inplace=True)
                            df.reset_index(drop=True, inplace=True)

                            logger.info(f"Playwright fallback succeeded! Parsed {len(df)} records")

                            rows = []
                            for _, row in df.iterrows():
                                rows.append({
                                    "date": row["Date"],
                                    "bullish": (None if pd.isna(row["Bullish"]) else float(row["Bullish"])),
                                    "neutral": (None if pd.isna(row["Neutral"]) else float(row["Neutral"])),
                                    "bearish": (None if pd.isna(row["Bearish"]) else float(row["Bearish"])),
                                })
                            return rows if rows else [{
                                "data_unavailable": True,
                                "reason": "No sentiment data in Playwright fallback file",
                                "created_at": datetime.now().isoformat(),
                            }]
                        except Exception as pw_error:
                            logger.warning(f"Playwright fallback parsing failed: {pw_error}")

                # Standard ValueError handling
                logger.warning(f"Download attempt {attempt} data format error: {e}")
                if attempt < 3:
                    import time

                    wait_time = 2 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(
                        f"[AAII] Failed after 3 attempts: Invalid Excel data format. {e}"
                    )
                    return [{
                        "data_unavailable": True,
                        "reason": f"Invalid Excel data format after 3 attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except (KeyError, AttributeError, TypeError) as e:
                logger.warning(
                    f"[AAII] Data format error parsing Excel: {e}. AAII file structure may have changed."
                )
                return [{
                    "data_unavailable": True,
                    "reason": f"Data format error parsing Excel: {str(e)[:100]}",
                    "created_at": datetime.now().isoformat(),
                }]
            except (OSError, requests.RequestException) as e:
                logger.error(f"Download attempt {attempt} unexpected error: {e}")
                if attempt < 3:
                    import time

                    wait_time = 2 * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.warning(
                        f"[AAII] Unexpected error after 3 attempts: {e}"
                    )
                    return [{
                        "data_unavailable": True,
                        "reason": f"Unexpected error after 3 attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]

        logger.warning(
            "[AAII_SENTIMENT] Failed to fetch AAII sentiment data after exhausting all retries. "
            "AAII server is unreachable."
        )
        return [{
            "data_unavailable": True,
            "reason": "Failed to fetch AAII sentiment after exhausting all retries",
            "created_at": datetime.now().isoformat(),
        }]


if __name__ == "__main__":
    sys.exit(run_loader(AAIISentimentLoader, global_mode=True))
