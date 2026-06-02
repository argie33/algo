#!/usr/bin/env python3
"""Fear & Greed Index Loader - Market Sentiment Indicators (Market-wide)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Optional, List
import requests

from utils.optimal_loader import OptimalLoader
from utils.url_validator import validate_url

logger = logging.getLogger(__name__)


class FearGreedIndexLoader(OptimalLoader):
    """Load CNN Fear & Greed Index sentiment data."""

    table_name = "fear_greed_index"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch Fear & Greed Index from CNN."""
        import time
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

        # SECURITY FIX S-05: Validate URL to prevent SSRF attacks
        is_valid, error_msg = validate_url(url, allowed_domains=['cnn.io', 'dataviz.cnn.io'])
        if not is_valid:
            logger.error(f"SSRF prevention: Invalid URL {url}: {error_msg}")
            return None
        # CNN blocks plain User-Agent strings from data centers. Mimic a real browser.
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://edition.cnn.com/markets/fear-and-greed',
            'Origin': 'https://edition.cnn.com',
            'Connection': 'keep-alive',
        }

        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 418:
                    # CNN blocking — back off and retry
                    wait = (attempt + 1) * 10
                    logger.warning(f"CNN 418 block (attempt {attempt + 1}/3), retrying in {wait}s")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()

                if not data or 'fear_and_greed' not in data:
                    logger.warning("Invalid Fear & Greed data format")
                    return None

                rows = []
                for entry in data.get('fear_and_greed', []):
                    try:
                        rows.append({
                            'date': entry.get('date'),
                            'fear_greed_value': float(entry.get('value', 0)),
                            'fear_greed_label': entry.get('description', 'Neutral'),
                        })
                    except (ValueError, KeyError):
                        continue

                return rows if rows else None

            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Fear & Greed fetch error (attempt {attempt + 1}/3): {e}")
                    time.sleep((attempt + 1) * 5)
                else:
                    logger.error(f"Failed to fetch Fear & Greed index: {e}")
                    return None

        logger.error("Failed to fetch Fear & Greed index after 3 attempts (CNN 418 block)")
        return None


def main():
    loader = FearGreedIndexLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: Fear & Greed data loaded")
        return 0
    else:
        logger.warning(f"COMPLETED: No data loaded")
        return 0


if __name__ == "__main__":
    sys.exit(main())
