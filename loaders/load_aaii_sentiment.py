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
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AAIISentimentLoader(OptimalLoader):
    """Load AAII investor sentiment survey data (market-wide, non-symbol based)."""

    table_name = "aaii_sentiment"
    primary_key = ("date",)
    watermark_field = "date"

    @staticmethod
    def _fetch_with_playwright_hybrid(aaii_url: str) -> bytes | None:
        """Fetch AAII file using Playwright to establish session, then requests to get file.

        AAII website uses Imperva/Incapsula bot protection that blocks direct requests.
        Solution: Use Playwright to bypass the challenge and establish cookies, then use
        those cookies in a normal requests session to fetch the actual file.

        Args:
            aaii_url: URL to fetch

        Returns:
            File content bytes if successful, None on failure
        """
        if not HAS_PLAYWRIGHT:
            logger.debug("Playwright not available for Incapsula bypass")
            return None

        try:
            logger.debug("Attempting hybrid Playwright+requests fetch...")
            with sync_playwright() as p:
                # Step 1: Launch browser and establish session
                logger.debug("Launching browser and establishing Incapsula session...")
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
                )

                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080},
                    ignore_https_errors=True,
                )

                page = context.new_page()

                try:
                    # Visit main AAII site to establish baseline
                    logger.debug("Visiting AAII main site...")
                    page.goto("https://www.aaii.com", timeout=15000, wait_until="domcontentloaded")

                    # Visit sentiment survey page (passes Incapsula check)
                    import time
                    logger.debug("Navigating to sentiment survey page...")
                    page.goto("https://www.aaii.com/sentiment-survey", timeout=15000, wait_until="domcontentloaded")
                    time.sleep(2)

                    # Simulate human interaction
                    logger.debug("Simulating human mouse movement...")
                    page.mouse.move(500, 500)
                    time.sleep(1)

                    # Step 2: Extract cookies from Playwright session
                    logger.debug("Extracting session cookies from Playwright...")
                    cookies = context.cookies()
                    logger.debug(f"Got {len(cookies)} cookies")

                    # Step 3: Use requests with Playwright's cookies to fetch file
                    logger.debug(f"Fetching {aaii_url} with established session...")
                    session = requests.Session()

                    for cookie in cookies:
                        session.cookies.set(
                            cookie['name'],
                            cookie['value'],
                            domain=cookie.get('domain')
                        )

                    session.headers.update({
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://www.aaii.com/sentiment-survey",
                    })

                    response = session.get(aaii_url, timeout=15)
                    logger.debug(f"Response status: {response.status_code}")

                    if response.status_code == 200:
                        content = response.content
                        if len(content) > 100000:  # Real Excel file is >1MB
                            logger.info(f"Successfully fetched {len(content)} bytes via hybrid approach")
                            return content
                        else:
                            logger.debug(f"File too small ({len(content)} bytes)")

                except Exception as e:
                    logger.debug(f"Hybrid fetch error: {e}")
                finally:
                    page.close()
                    context.close()
                    browser.close()

        except Exception as e:
            logger.debug(f"Playwright hybrid fetch failed: {e}")

        return None

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:  # noqa: C901
        """Fetch AAII sentiment data from Excel file.

        Complexity justified: Data integrity checks (SSRF validation, zip structure,
        coerce validation, date validation) are essential for financial data
        security and correctness. Cannot be factored without losing failure context.

        Uses hybrid Playwright+requests approach to bypass Imperva bot protection.
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

        for attempt in range(1, 3):  # 2 attempts: regular request, then hybrid Playwright
            try:
                if attempt == 1:
                    logger.info(f"Download attempt {attempt}/2: Regular request")
                    response = requests.get(aaii_url, headers=headers, allow_redirects=True, timeout=15)
                    response.raise_for_status()
                    file_content = response.content
                else:
                    logger.info(f"Download attempt {attempt}/2: Hybrid Playwright+requests")
                    file_content = self._fetch_with_playwright_hybrid(aaii_url)
                    if not file_content:
                        raise ValueError("Playwright hybrid fetch returned no data")

                # Validate content type
                if len(file_content) < 1000:
                    raise ValueError(f"Response too small ({len(file_content)} bytes)")

                # SECURITY FIX S-04: Validate Excel file structure
                if file_content.startswith(b"PK"):  # XLSX = ZIP format
                    try:
                        with zipfile.ZipFile(BytesIO(file_content), "r") as zf:
                            names = zf.namelist()
                            if len(names) > 10000:
                                raise ValueError("Excel file has suspicious structure")
                    except zipfile.BadZipFile:
                        logger.warning("File looks like XLSX but ZIP parsing failed, attempting as XLS")

                # Parse Excel file
                excel_data = BytesIO(file_content)
                xl_engine = "openpyxl" if file_content.startswith(b"PK") else "xlrd"
                df = pd.read_excel(excel_data, skiprows=3, engine=xl_engine)

                df.columns = df.columns.str.strip()
                required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    raise ValueError(f"Missing columns: {missing_cols}")

                df = df[required_cols]

                # Clean and validate data
                for col in ["Bullish", "Neutral", "Bearish"]:
                    df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                    before_coerce = df[col].copy()
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    newly_nan = before_coerce[df[col].isna() & before_coerce.notna()]
                    if len(newly_nan) > 0:
                        bad_values = newly_nan.unique()[:5]
                        raise ValueError(
                            f"[AAII_SENTIMENT] {col} contains unparseable values: {bad_values}. "
                            f"Cannot load sentiment data with corrupted numeric fields."
                        )

                # Parse and validate dates
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                before_coerce = df["Date"].copy()
                invalid_dates = before_coerce[df["Date"].isna() & before_coerce.notna()]
                if len(invalid_dates) > 0:
                    bad_dates = invalid_dates.unique()[:5]
                    raise ValueError(
                        f"[AAII_SENTIMENT] Date column contains unparseable values: {bad_dates}. "
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
                    logger.warning("[AAII_SENTIMENT] No sentiment data parsed from Excel file")
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
                if attempt >= 2:
                    logger.warning(f"[AAII] Failed after all attempts: Cannot reach AAII server. {e}")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Cannot reach AAII server: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except ValueError as e:
                logger.warning(f"Download attempt {attempt} validation error: {e}")
                if attempt >= 2:
                    logger.warning(f"[AAII] Failed after all attempts: {e}")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Data validation error after all attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except (json.JSONDecodeError, zipfile.BadZipFile, KeyError, AttributeError, TypeError) as e:
                logger.warning(f"Download attempt {attempt} format error: {e}")
                if attempt >= 2:
                    logger.warning(f"[AAII] Failed after all attempts: Invalid Excel data format. {e}")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Invalid data format after all attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except Exception as e:
                logger.error(f"Download attempt {attempt} unexpected error: {e}")
                if attempt >= 2:
                    logger.warning(f"[AAII] Unexpected error after all attempts: {e}")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Unexpected error after all attempts: {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]

        logger.warning("[AAII_SENTIMENT] Failed to fetch AAII sentiment data after exhausting all attempts")
        return [{
            "data_unavailable": True,
            "reason": "Failed to fetch AAII sentiment after all attempts",
            "created_at": datetime.now().isoformat(),
        }]


if __name__ == "__main__":
    sys.exit(run_loader(AAIISentimentLoader, global_mode=True))
