#!/usr/bin/env python3
"""Fear & Greed Index Loader - Market Sentiment Indicators (Market-wide)."""

import logging
import socket
import sys
from datetime import date
from typing import List, Optional

import requests

from loaders.runner import run_loader
from utils.infrastructure.timeout import ExecutionTimeout
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

class FearGreedIndexLoader(OptimalLoader):
    """Load CNN Fear & Greed Index sentiment data."""

    table_name = "fear_greed_index"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch Fear & Greed Index from CNN."""
        import time

        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(30.0)

        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

        # SECURITY FIX S-05: Validate URL to prevent SSRF attacks
        is_valid, error_msg = validate_url(
            url, allowed_domains=["cnn.io", "dataviz.cnn.io"]
        )
        if not is_valid:
            raise RuntimeError(f"SSRF prevention: Invalid URL {url}: {error_msg}")
        # CNN blocks plain User-Agent strings from data centers. Mimic a real browser.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed",
            "Origin": "https://edition.cnn.com",
            "Connection": "keep-alive",
        }

        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 418:
                    # CNN blocking — back off and retry
                    wait = (attempt + 1) * 10
                    logger.warning(
                        f"CNN 418 block (attempt {attempt + 1}/3), retrying in {wait}s"
                    )
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()

                if not data or (
                    "fear_and_greed" not in data
                    and "fear_and_greed_historical" not in data
                ):
                    raise RuntimeError(
                        "Invalid Fear & Greed data format from CNN API. "
                        "Response is missing expected data fields."
                    )

                # CNN API two known formats:
                # New: {"fear_and_greed": {...current dict...}, "fear_and_greed_historical": {"data": [{"x": ms_ts, "y": val, "rating": "..."}]}}
                # Old: {"fear_and_greed": [{"x": ms_ts, "y": val, "rating": "..."}]}
                raw = data.get("fear_and_greed")
                if isinstance(raw, dict):
                    entries = list(
                        data.get("fear_and_greed_historical").get("data")
                    )
                    score = raw.get("score") or raw.get("value")
                    if score is not None:
                        from datetime import datetime as _dt

                        rating = raw.get("rating")
                        if rating is None:
                            logger.warning("Fear & Greed entry missing 'rating' field; skipping")
                            continue
                        entries.append(
                            {
                                "_date": _dt.utcnow().strftime("%Y-%m-%d"),
                                "y": score,
                                "rating": rating,
                            }
                        )
                else:
                    entries = raw

                rows = []
                for entry in entries:
                    try:
                        from datetime import datetime as _dt

                        x_val = entry.get("x")
                        date_str = entry.get("_date") or entry.get("date")
                        if x_val is not None:
                            entry_date = _dt.utcfromtimestamp(
                                int(x_val) / 1000
                            ).strftime("%Y-%m-%d")
                        elif date_str:
                            entry_date = str(date_str)[:10]
                        else:
                            logger.debug(
                                "Fear & Greed entry skipped — missing date field "
                                f"(x={x_val}, _date={entry.get('_date')}, date={entry.get('date')})"
                            )
                            continue
                        value = entry.get("y", entry.get("value"))
                        if value is None:
                            logger.debug(
                                f"Fear & Greed entry skipped — missing value field on {entry_date} "
                                f"(y={entry.get('y')}, value={entry.get('value')})"
                            )
                            continue
                        label = entry.get("rating") or entry.get("description", "Neutral")
                        rows.append(
                            {
                                "date": entry_date,
                                "fear_greed_value": float(value),
                                "fear_greed_label": str(label),
                            }
                        )
                    except (ValueError, KeyError, TypeError, AttributeError) as e:
                        logger.debug(f"Fear & Greed entry parsing error: {e}")
                        continue

                # CNN API includes today's date in both fear_and_greed_historical
                # AND the current reading appended above. Deduplicate by date,
                # keeping the last occurrence (current reading wins).
                seen: dict = {}
                for r in rows:
                    seen[r["date"]] = r
                rows = list(seen.values())

                if not rows:
                    raise RuntimeError(
                        "No valid Fear & Greed index entries parsed from CNN API response. "
                        "All entries were rejected during parsing."
                    )
                return rows

            except requests.exceptions.Timeout:
                if attempt < 2:
                    logger.warning(
                        f"Fear & Greed timeout (attempt {attempt + 1}/3), retrying..."
                    )
                    time.sleep((attempt + 1) * 5)
                else:
                    raise RuntimeError(
                        "Failed to fetch Fear & Greed index after 3 timeout attempts. "
                        "CNN API is unreachable or slow."
                    )
            except requests.exceptions.ConnectionError:
                if attempt < 2:
                    logger.warning(
                        f"Fear & Greed connection error (attempt {attempt + 1}/3), retrying..."
                    )
                    time.sleep((attempt + 1) * 5)
                else:
                    raise RuntimeError(
                        "Failed to fetch Fear & Greed index after 3 connection errors. "
                        "Cannot reach CNN API."
                    )
            except (ValueError, KeyError, TypeError) as e:
                raise RuntimeError(
                    f"[FEAR_GREED] Data format error parsing CNN response: {e}. "
                    "CNN API response format may have changed."
                ) from e
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(
                    f"[FEAR_GREED] HTTP error from CNN: {e}. "
                    "Check CNN API status and rate limits."
                ) from e
            except (requests.RequestException, requests.Timeout) as e:
                raise RuntimeError(
                    f"[FEAR_GREED] Unexpected error fetching Fear & Greed index: {e}."
                ) from e

        raise RuntimeError(
            "Failed to fetch Fear & Greed index after 3 attempts (CNN 418 block). "
            "CNN API is blocking requests (rate limit or access restriction)."
        )

if __name__ == "__main__":
    sys.exit(run_loader(FearGreedIndexLoader, global_mode=True))
