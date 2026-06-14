#!/usr/bin/env python3
"""Fear & Greed Index Loader - Market Sentiment Indicators (Market-wide)."""
from loaders.loader_helper import setup_imports
setup_imports()

import sys
import logging
from datetime import date
from typing import Optional, List
import requests
import socket

from utils.optimal_loader import OptimalLoader
from utils.infrastructure.url_validator import validate_url
from utils.infrastructure.timeout import ExecutionTimeout

logger = logging.getLogger(__name__)

class FearGreedIndexLoader(OptimalLoader):
    """Load CNN Fear & Greed Index sentiment data."""

    table_name = "fear_greed_index"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch Fear & Greed Index from CNN."""
        import time
        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(30.0)

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

                if not data or ('fear_and_greed' not in data and 'fear_and_greed_historical' not in data):
                    logger.warning("Invalid Fear & Greed data format")
                    return None

                # CNN API two known formats:
                # New: {"fear_and_greed": {...current dict...}, "fear_and_greed_historical": {"data": [{"x": ms_ts, "y": val, "rating": "..."}]}}
                # Old: {"fear_and_greed": [{"x": ms_ts, "y": val, "rating": "..."}]}
                raw = data.get('fear_and_greed', [])
                if isinstance(raw, dict):
                    entries = list(data.get('fear_and_greed_historical', {}).get('data', []))
                    score = raw.get('score') or raw.get('value')
                    if score is not None:
                        from datetime import datetime as _dt
                        entries.append({
                            '_date': _dt.utcnow().strftime('%Y-%m-%d'),
                            'y': score,
                            'rating': raw.get('rating', 'Neutral'),
                        })
                else:
                    entries = raw

                rows = []
                for entry in entries:
                    try:
                        from datetime import datetime as _dt
                        x_val = entry.get('x')
                        date_str = entry.get('_date') or entry.get('date')
                        if x_val is not None:
                            entry_date = _dt.utcfromtimestamp(int(x_val) / 1000).strftime('%Y-%m-%d')
                        elif date_str:
                            entry_date = str(date_str)[:10]
                        else:
                            logger.debug(
                                f"Fear & Greed entry skipped — missing date field "
                                f"(x={x_val}, _date={entry.get('_date')}, date={entry.get('date')})"
                            )
                            continue
                        value = entry.get('y', entry.get('value', 0))
                        label = entry.get('rating', entry.get('description', 'Neutral'))
                        rows.append({
                            'date': entry_date,
                            'fear_greed_value': float(value),
                            'fear_greed_label': str(label),
                        })
                    except (ValueError, KeyError, TypeError, AttributeError) as e:
                        logger.debug(f"Fear & Greed entry parsing error: {e}")
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
    try:
        # Execution timeout: CNN API typically responds in 1-5s
        # Set limit to 2 min (120s) to catch blocking/rate limiting early
        with ExecutionTimeout(max_seconds=120, label="load_fear_greed_index"):
            loader = FearGreedIndexLoader()
            result = loader.load_global()

            if result > 0:
                logger.info(f"SUCCESS: Fear & Greed data loaded")
                return 0
            else:
                logger.warning(f"COMPLETED: No data loaded")
                return 0
    except Exception as e:
        logger.error(f"Fear & Greed load failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
