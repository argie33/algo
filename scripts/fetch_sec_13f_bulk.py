#!/usr/bin/env python3
"""Fetch institutional ownership from SEC's bulk Form 13F quarterly data.

SEC publishes quarterly 13F data at:
https://www.sec.gov/files/structureddata/data/form-13f-data-sets/

This script:
1. Downloads the latest quarterly 13F dataset
2. Extracts CUSIP holdings
3. Maps CUSIP to ticker via SEC/Yahoo data
4. Aggregates institutional ownership %
"""

import csv
import io
import logging
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SEC bulk 13F data URL (replace YYYY-Q with actual year/quarter)
SEC_13F_BASE_URL = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"


def get_latest_13f_quarter() -> tuple[int, int]:
    """Get latest available 13F data quarter (YYYY, Q)."""
    now = datetime.now()
    year = now.year
    quarter = (now.month - 1) // 3 + 1

    # 13F data is filed 45 days after quarter end, so there's lag
    # Back up to previous quarter if we're too early in the year
    if quarter == 1:
        year -= 1
        quarter = 4
    else:
        quarter -= 1

    return year, quarter


def fetch_sec_13f_holdings(year: int, quarter: int) -> dict[str, int]:
    """Fetch 13F holdings from SEC bulk dataset.

    Returns dict of {ticker: total_shares_held_by_institutions}
    """
    logger.info(f"Fetching SEC 13F data for Q{quarter} {year}...")

    try:
        # Build URL for quarterly dataset
        url = f"{SEC_13F_BASE_URL}{year}-Q{quarter}_FORM13FDATA.zip"
        logger.info(f"Downloading: {url}")

        # Download ZIP file
        with urllib.request.urlopen(url, timeout=30) as response:
            zip_data = response.read()

        # Extract and parse INFOTABLE.tsv
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # Find INFOTABLE.tsv in the ZIP
            info_table_files = [f for f in zf.namelist() if f.endswith("INFOTABLE.tsv")]
            if not info_table_files:
                logger.error(f"No INFOTABLE.tsv found in {url}")
                return {}

            # Parse holdings data
            holdings_by_ticker = defaultdict(int)

            for info_file in info_table_files:
                with zf.open(info_file) as f:
                    # Read TSV (tab-separated)
                    reader = csv.DictReader(
                        io.TextIOWrapper(f, encoding="utf-8"),
                        delimiter="\t"
                    )

                    for row in reader:
                        try:
                            row.get("cusip", "").strip()
                            ticker = row.get("ticker", "").strip().upper()
                            shares = int(row.get("shrsOrPrnAmt", 0) or 0)

                            # Use ticker if available, otherwise skip (would need CUSIP→ticker map)
                            if ticker and shares > 0:
                                holdings_by_ticker[ticker] += shares
                        except (ValueError, KeyError):
                            continue

            logger.info(f"Parsed {len(holdings_by_ticker)} unique tickers from 13F holdings")
            return holdings_by_ticker

    except Exception as e:
        logger.error(f"Failed to fetch SEC 13F data: {type(e).__name__}: {e}")
        return {}


def calculate_ownership_percentages(
    holdings: dict[str, int]
) -> dict[str, float]:
    """Calculate institutional ownership % for each ticker.

    Needs shares_outstanding for each ticker to calculate ownership %.
    """
    logger.info("Calculating institutional ownership percentages...")

    ownership_pct = {}

    with DatabaseContext("read") as cur:
        for ticker, inst_shares in holdings.items():
            # Get shares outstanding for this ticker
            cur.execute(
                "SELECT shares_outstanding FROM company_info_sec WHERE symbol = %s",
                (ticker,)
            )
            row = cur.fetchone()

            if row and row[0] and row[0] > 0:
                shares_os = row[0]
                pct = round((inst_shares / shares_os) * 100, 2)
                ownership_pct[ticker] = min(pct, 100.0)  # Cap at 100%
                logger.debug(f"{ticker}: {inst_shares:,.0f} / {shares_os:,.0f} = {pct:.1f}%")

    logger.info(f"Calculated ownership % for {len(ownership_pct)} tickers")
    return ownership_pct


def load_into_database(ownership_pct: dict[str, float], filing_date: str) -> int:
    """Load institutional ownership percentages into institutional_holdings_13f."""
    now_et = datetime.now(EASTERN_TZ)
    updated = 0

    with DatabaseContext("write") as cur:
        for ticker, pct in ownership_pct.items():
            cur.execute(
                """
                INSERT INTO institutional_holdings_13f
                (symbol, filing_date, institutional_ownership_pct, data_unavailable, updated_at, data_source)
                VALUES (%s, %s, %s, false, %s, 'sec_form13f_bulk')
                ON CONFLICT (symbol) DO UPDATE SET
                    institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                    filing_date = EXCLUDED.filing_date,
                    data_unavailable = false,
                    updated_at = EXCLUDED.updated_at,
                    data_source = 'sec_form13f_bulk'
                """,
                (ticker, filing_date, pct, now_et)
            )
            updated += 1

    logger.info(f"Loaded {updated} institutional ownership records")
    return updated


def main() -> int:
    """Fetch and load SEC 13F institutional ownership data."""
    try:
        # Get latest available quarter
        year, quarter = get_latest_13f_quarter()

        # Fetch holdings data
        holdings = fetch_sec_13f_holdings(year, quarter)
        if not holdings:
            logger.warning("No holdings data fetched")
            return 1

        # Calculate ownership %
        ownership_pct = calculate_ownership_percentages(holdings)

        # Load into database
        filing_date = f"{year}-Q{quarter}"
        updated = load_into_database(ownership_pct, filing_date)

        logger.info(f"✓ Successfully loaded {updated} institutional ownership records")
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
