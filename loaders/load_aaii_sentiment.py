#!/usr/bin/env python3
"""AAII Sentiment Survey Loader - Investor Sentiment Indicators (Market-wide data)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Optional, List
import os
import requests
from io import BytesIO
import pandas as pd

from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

AAII_EXCEL_URL = os.getenv("AAII_SENTIMENT_URL", "https://www.aaii.com/files/surveys/sentiment.xls")


class AAIISentimentLoader(OptimalLoader):
    """Load AAII investor sentiment survey data (market-wide, non-symbol based)."""

    table_name = "aaii_sentiment"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch AAII sentiment data from Excel file."""
        logging.info(f"Downloading AAII sentiment data from: {AAII_EXCEL_URL}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.aaii.com/",
            "Accept": "application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(1, 6):  # 5 retries
            try:
                logging.info(f"Download attempt {attempt}/5")
                response = requests.get(AAII_EXCEL_URL, headers=headers, allow_redirects=True, timeout=60)
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "")
                if "html" in content_type.lower():
                    logging.error("Server returned HTML instead of Excel")
                    raise ValueError("Server returned HTML instead of Excel")

                if len(response.content) < 1000:
                    logging.error(f"Response too small ({len(response.content)} bytes)")
                    raise ValueError(f"Response too small ({len(response.content)} bytes)")

                excel_data = BytesIO(response.content)
                df = pd.read_excel(excel_data, skiprows=3, engine="xlrd")

                df.columns = df.columns.str.strip()
                required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    raise ValueError(f"Missing columns: {missing_cols}")

                df = df[required_cols]

                for col in ["Bullish", "Neutral", "Bearish"]:
                    df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                df = df.dropna(subset=["Date"])
                df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

                df.sort_values("Date", inplace=True)
                df.reset_index(drop=True, inplace=True)

                logging.info(f"Successfully downloaded {len(df)} records")

                # Convert to list of dicts matching table schema
                rows = []
                for _, row in df.iterrows():
                    rows.append({
                        'date': row["Date"],
                        'bullish': None if pd.isna(row["Bullish"]) else float(row["Bullish"]),
                        'neutral': None if pd.isna(row["Neutral"]) else float(row["Neutral"]),
                        'bearish': None if pd.isna(row["Bearish"]) else float(row["Bearish"]),
                    })

                return rows if rows else None

            except Exception as e:
                logging.error(f"Download attempt {attempt} failed: {e}")
                if attempt < 5:
                    import time
                    wait_time = 3 * (2 ** (attempt - 1))  # 3s, 6s, 12s, 24s, 48s
                    logging.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Failed after 5 attempts: {e}")

        return None


def main():
    loader = AAIISentimentLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} AAII sentiment records loaded")
        return 0
    else:
        logger.warning(f"COMPLETED: No records loaded")
        return 0


if __name__ == "__main__":
    sys.exit(main())
