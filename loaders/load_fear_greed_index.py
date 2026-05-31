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

logger = logging.getLogger(__name__)


class FearGreedIndexLoader(OptimalLoader):
    """Load CNN Fear & Greed Index sentiment data."""

    table_name = "fear_greed"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch Fear & Greed Index from CNN."""
        try:
            url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
            headers = {'User-Agent': 'Mozilla/5.0'}

            response = requests.get(url, headers=headers, timeout=30)
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
            logger.error(f"Failed to fetch Fear & Greed index: {e}")
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
