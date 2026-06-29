#!/usr/bin/env python3
"""AAII Sentiment Survey Loader - Investor Sentiment Indicators (Market-wide data)."""

import json
import logging
import socket
import sys
import time
import zipfile
from datetime import date, datetime
from io import BytesIO
from typing import Any, cast

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
        """Fetch AAII file using proven hybrid Playwright+requests approach.

        AAII website uses Imperva/Incapsula bot protection. This approach:
        1. Uses Playwright to navigate and pass Incapsula challenge
        2. Extracts established session cookies
        3. Uses requests library with those cookies to download file

        This hybrid approach successfully bypasses the protection by:
        - Letting Playwright handle the JavaScript challenge
        - Using realistic Chrome headers
        - Simulating human-like navigation and interaction
        - Reusing the authenticated session from Playwright

        Args:
            aaii_url: URL to fetch

        Returns:
            File content bytes if successful, None on failure
        """
        if not HAS_PLAYWRIGHT:
            error_msg = (
                "[AAII_SENTIMENT] CRITICAL: Playwright not installed - cannot bypass Imperva bot protection. "
                "AAII sentiment data requires Playwright for hybrid authentication. "
                "Install with: pip install playwright && playwright install chromium"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            logger.debug("Attempting hybrid Playwright+requests approach...")
            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
                )

                # Create context with realistic browser profile
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080},
                    ignore_https_errors=True,
                )

                page = context.new_page()

                try:
                    # Step 1: Visit main AAII site
                    logger.debug("Visiting AAII main site to establish baseline...")
                    page.goto("https://www.aaii.com", timeout=15000, wait_until="domcontentloaded")
                    time.sleep(1)

                    # Step 2: Navigate to sentiment survey page (passes Incapsula challenge)
                    logger.debug("Navigating to sentiment survey page...")
                    page.goto("https://www.aaii.com/sentiment-survey", timeout=15000, wait_until="domcontentloaded")
                    time.sleep(3)  # CRITICAL: Wait 3 seconds for Incapsula to recognize browser

                    # Step 3: Simulate human interaction
                    logger.debug("Simulating human mouse movement...")
                    page.mouse.move(500, 500)
                    time.sleep(1)

                    # Step 4: Extract cookies from Playwright's authenticated session
                    logger.debug("Extracting session cookies from Playwright...")
                    cookies = context.cookies()
                    logger.debug(f"Got {len(cookies)} session cookies")

                    # Step 5: Use requests library with Playwright's cookies
                    logger.debug(f"Fetching {aaii_url} with established session...")
                    session = requests.Session()

                    # Set all cookies from Playwright
                    for cookie in cookies:
                        cookie_name = cookie.get('name')
                        cookie_value = cookie.get('value')
                        cookie_domain = cookie.get('domain')

                        if not cookie_name or not cookie_value:
                            logger.warning(f"[AAII_SENTIMENT] Skipping invalid cookie: name={cookie_name}, value present={bool(cookie_value)}")
                            continue

                        session.cookies.set(cookie_name, cookie_value, domain=cookie_domain)

                    # Use Chrome-like headers
                    session.headers.update({
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Referer": "https://www.aaii.com/sentiment-survey",
                        "Accept": "*/*",
                    })

                    # Download file
                    response = session.get(aaii_url, timeout=20, allow_redirects=True)
                    logger.debug(f"Response status: {response.status_code}, size: {len(response.content)} bytes")

                    if response.status_code == 200 and len(response.content) > 100000:
                        logger.info(f"Successfully fetched {len(response.content)} bytes via hybrid approach")
                        return cast(bytes, response.content)

                except Exception as e:
                    logger.warning(f"[AAII_SENTIMENT] Playwright page fetch failed: {type(e).__name__}: {str(e)[:100]}")
                finally:
                    try:
                        page.close()
                        context.close()
                        browser.close()
                    except Exception as cleanup_err:
                        logger.warning(f"[AAII_SENTIMENT] Error closing Playwright resources: {cleanup_err}")

        except Exception as e:
            logger.error(f"[AAII_SENTIMENT] CRITICAL: Playwright hybrid fetch failed: {type(e).__name__}: {str(e)[:200]}")
            error_msg = (
                f"[AAII_SENTIMENT] Failed to fetch data via Playwright hybrid approach after browser launch failed. "
                f"Error: {type(e).__name__}: {str(e)[:200]}. "
                f"Cannot proceed without AAII sentiment data."
            )
            raise RuntimeError(error_msg) from e

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:  # noqa: C901
        """Fetch AAII sentiment data from Excel file.

        Uses hybrid Playwright+requests approach to bypass Imperva bot protection.
        This approach has been proven to successfully retrieve current AAII data.
        """
        # Set socket-level timeout
        socket.setdefaulttimeout(20.0)

        aaii_url = get_aaii_sentiment_url()
        logger.info(f"Downloading AAII sentiment data from: {aaii_url}")

        # SECURITY: Validate URL to prevent SSRF
        is_valid, error_msg = validate_url(aaii_url, allowed_domains=["aaii.com"])
        if not is_valid:
            raise RuntimeError(
                f"[AAII_SENTIMENT] SSRF validation failed: {error_msg}. "
                "Cannot fetch sentiment data with invalid URL."
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.aaii.com/",
            "Accept": "application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Try regular request first (in case protection is relaxed), then hybrid approach
        for attempt in range(1, 3):
            try:
                if attempt == 1:
                    logger.info("Download attempt 1/2: Regular HTTP request")
                    response = requests.get(aaii_url, headers=headers, allow_redirects=True, timeout=15)
                    response.raise_for_status()
                    file_content = response.content
                else:
                    logger.info("Download attempt 2/2: Hybrid Playwright+requests approach")
                    file_content = self._fetch_with_playwright_hybrid(aaii_url)
                    if not file_content:
                        raise ValueError("Playwright hybrid fetch returned no data")

                # Validate file size
                if len(file_content) < 1000:
                    raise ValueError(f"[AAII_SENTIMENT] Response too small ({len(file_content)} bytes) - invalid Excel file")

                # Validate Excel structure (basic check for ZIP signature)
                if file_content.startswith(b"PK"):  # XLSX
                    try:
                        with zipfile.ZipFile(BytesIO(file_content), "r") as zf:
                            if len(zf.namelist()) > 10000:
                                raise ValueError("[AAII_SENTIMENT] Excel file has suspicious structure (>10000 entries)")
                    except zipfile.BadZipFile:
                        logger.warning("[AAII_SENTIMENT] File looks like XLSX but ZIP parse failed, attempting XLS parser")

                # Parse Excel with correct skiprows for AAII format
                logger.debug("Parsing Excel file...")
                excel_data = BytesIO(file_content)
                xl_engine = "openpyxl" if file_content.startswith(b"PK") else "xlrd"
                df = pd.read_excel(excel_data, skiprows=3, engine=xl_engine)

                df.columns = df.columns.str.strip()

                # Remove rows where all main columns are NaN (header artifacts)
                df = df.dropna(subset=["Date", "Bullish", "Neutral", "Bearish"], how="all")
                df = df.reset_index(drop=True)

                required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
                missing = [c for c in required_cols if c not in df.columns]
                if missing:
                    raise ValueError(f"[AAII_SENTIMENT] Missing required columns: {missing}. Found columns: {list(df.columns)}")

                df = df[required_cols]

                # Clean and parse numeric columns
                for col in ["Bullish", "Neutral", "Bearish"]:
                    # Handle both percentage strings and numeric values
                    df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                    before = df[col].copy()
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                    # Check for unparseable values (excluding NaN which is expected for some rows)
                    bad = before[(df[col].isna()) & (before.notna()) & (before != "nan") & (before != "NaN")]
                    if len(bad) > 10:  # Allow some NaN but not too many
                        sample_bad = bad.head(5).tolist()
                        raise ValueError(f"[AAII_SENTIMENT] {col} has {len(bad)} unparseable values (samples: {sample_bad})")

                # Parse and validate dates
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                before = df["Date"].copy()
                bad_dates = before[df["Date"].isna() & before.notna()]
                if len(bad_dates) > 10:  # Allow some parsing issues
                    sample_bad_dates = bad_dates.head(5).tolist()
                    raise ValueError(f"[AAII_SENTIMENT] Date column has {len(bad_dates)} unparseable values (samples: {sample_bad_dates})")

                # Remove rows with missing dates or sentiment data
                df = df.dropna(subset=["Date"])
                df = df.dropna(subset=["Bullish", "Neutral", "Bearish"], how="any")

                df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                df.sort_values("Date", inplace=True)
                df.reset_index(drop=True, inplace=True)

                logger.info(f"Successfully parsed {len(df)} records from AAII file")

                # Convert to table format
                rows = []
                for _, row in df.iterrows():
                    rows.append({
                        "date": row["Date"],
                        "bullish": (None if pd.isna(row["Bullish"]) else float(row["Bullish"])),
                        "neutral": (None if pd.isna(row["Neutral"]) else float(row["Neutral"])),
                        "bearish": (None if pd.isna(row["Bearish"]) else float(row["Bearish"])),
                    })

                if not rows:
                    logger.error("[AAII_SENTIMENT] No sentiment data parsed from Excel file - all rows filtered out")
                    return [{
                        "data_unavailable": True,
                        "reason": "No sentiment data in parsed Excel file - all rows filtered out due to missing values",
                        "created_at": datetime.now().isoformat(),
                    }]

                logger.info(f"Successfully loaded {len(rows)} AAII sentiment records")
                return rows

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                error_type = type(e).__name__
                logger.warning(f"[AAII_SENTIMENT] Attempt {attempt} network error ({error_type}): {str(e)[:100]}")
                if attempt >= 2:
                    logger.error("[AAII_SENTIMENT] Failed to fetch AAII sentiment after all network attempts")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Network error ({error_type}): {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except (ValueError, json.JSONDecodeError, zipfile.BadZipFile, KeyError, AttributeError, TypeError) as e:
                error_type = type(e).__name__
                logger.warning(f"[AAII_SENTIMENT] Attempt {attempt} format/parsing error ({error_type}): {str(e)[:100]}")
                if attempt >= 2:
                    logger.error("[AAII_SENTIMENT] Failed to parse AAII sentiment data after all attempts")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Data format error ({error_type}): {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]
            except Exception as e:
                error_type = type(e).__name__
                logger.error(f"[AAII_SENTIMENT] Attempt {attempt} unexpected error ({error_type}): {str(e)[:100]}")
                if attempt >= 2:
                    logger.error("[AAII_SENTIMENT] Failed to fetch AAII sentiment due to unexpected error")
                    return [{
                        "data_unavailable": True,
                        "reason": f"Unexpected error ({error_type}): {str(e)[:100]}",
                        "created_at": datetime.now().isoformat(),
                    }]

        logger.error("[AAII_SENTIMENT] Exhausted all download attempts - returning data unavailable marker")
        return [{
            "data_unavailable": True,
            "reason": "Failed to fetch AAII sentiment after all attempts",
            "created_at": datetime.now().isoformat(),
        }]


if __name__ == "__main__":
    sys.exit(run_loader(AAIISentimentLoader, global_mode=True))
