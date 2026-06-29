#!/usr/bin/env python3
"""Fear & Greed Index Loader - Market Sentiment Indicators (Market-wide)."""

import logging
import socket
import sys
from datetime import date
from typing import Any

import requests

from loaders.runner import run_loader
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class FearGreedIndexLoader(OptimalLoader):
    """Load CNN Fear & Greed Index sentiment data."""

    table_name = "fear_greed_index"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:  # noqa: C901
        """Fetch Fear & Greed Index from CNN.

        Returns list of fear/greed records on success.
        Returns data_unavailable marker if CNN API cannot be reached or data is invalid.
        """
        import time
        from datetime import datetime as _dt

        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(30.0)

        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

        # SECURITY FIX S-05: Validate URL to prevent SSRF attacks
        is_valid, error_msg = validate_url(url, allowed_domains=["cnn.io", "dataviz.cnn.io"])
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
                    logger.warning(f"CNN 418 block (attempt {attempt + 1}/3), retrying in {wait}s")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()

                if not data or ("fear_and_greed" not in data and "fear_and_greed_historical" not in data):
                    logger.error(
                        "Invalid Fear & Greed data format from CNN API. Response is missing expected data fields."
                    )
                    return [
                        {
                            "date": _dt.utcnow().strftime("%Y-%m-%d"),
                            "fear_greed_value": None,
                            "fear_greed_label": None,
                            "data_unavailable": True,
                            "reason": "invalid_response_format",
                        }
                    ]

                # CNN API two known formats:
                # New: {"fear_and_greed": {...current dict[str, Any]...}, "fear_and_greed_historical": {"data": [{"x": ms_ts, "y": val, "rating": "..."}]}}
                # Old: {"fear_and_greed": [{"x": ms_ts, "y": val, "rating": "..."}]}
                raw = data.get("fear_and_greed")
                if isinstance(raw, dict):
                    historical = data.get("fear_and_greed_historical")
                    if historical is None:
                        logger.error(
                            "[FEAR_GREED] CNN API response missing fear_and_greed_historical field. "
                            "API response format may have changed."
                        )
                        return [
                            {
                                "date": _dt.utcnow().strftime("%Y-%m-%d"),
                                "fear_greed_value": None,
                                "fear_greed_label": None,
                                "data_unavailable": True,
                                "reason": "missing_historical_field",
                            }
                        ]
                    historical_data = historical.get("data")
                    if historical_data is None:
                        logger.error(
                            "[FEAR_GREED] CNN API fear_and_greed_historical.data field missing or invalid. "
                            "Cannot extract historical Fear & Greed data from response."
                        )
                        return [
                            {
                                "date": _dt.utcnow().strftime("%Y-%m-%d"),
                                "fear_greed_value": None,
                                "fear_greed_label": None,
                                "data_unavailable": True,
                                "reason": "missing_historical_data",
                            }
                        ]
                    entries = list(historical_data)
                    # Validate current reading score field
                    score = raw.get("score")
                    if score is None:
                        logger.error(
                            "[FEAR_GREED] CNN API current fear_and_greed missing required 'score' field. "
                            "Cannot assess market sentiment without this metric."
                        )
                        return [
                            {
                                "date": _dt.utcnow().strftime("%Y-%m-%d"),
                                "fear_greed_value": None,
                                "fear_greed_label": None,
                                "data_unavailable": True,
                                "reason": "missing_current_score",
                            }
                        ]

                    rating = raw.get("rating")
                    if rating is None:
                        logger.error(
                            "[FEAR_GREED] CNN API entry missing required 'rating' field. "
                            "Sentiment classification is required for trading decisions."
                        )
                        return [
                            {
                                "date": _dt.utcnow().strftime("%Y-%m-%d"),
                                "fear_greed_value": None,
                                "fear_greed_label": None,
                                "data_unavailable": True,
                                "reason": "missing_current_rating",
                            }
                        ]

                    entries.append(
                        {
                            "_date": _dt.utcnow().strftime("%Y-%m-%d"),
                            "y": score,
                            "rating": rating,
                        }
                    )
                else:
                    entries = raw

                rows: list[dict[str, Any]] = []
                skipped_count = 0
                for entry in entries:
                    try:
                        x_val = entry.get("x")
                        date_str = entry.get("_date")
                        if date_str is None:
                            date_str = entry.get("date")
                        if x_val is not None:
                            entry_date = _dt.utcfromtimestamp(int(x_val) / 1000).strftime("%Y-%m-%d")
                        elif date_str:
                            entry_date = str(date_str)[:10]
                        else:
                            logger.warning(
                                "Fear & Greed entry skipped — missing date field "
                                f"(x={x_val}, _date={entry.get('_date')}, date={entry.get('date')})"
                            )
                            skipped_count += 1
                            continue
                        value = entry.get("y")
                        if value is None:
                            logger.warning(
                                f"[FEAR_GREED] Entry on {entry_date} missing required 'y' (value) field. "
                                "Cannot use incomplete Fear & Greed data for sentiment analysis."
                            )
                            skipped_count += 1
                            continue
                        label = entry.get("rating")
                        if label is None:
                            logger.warning(
                                f"[FEAR_GREED] Entry on {entry_date} missing required 'rating' (label) field. "
                                "Sentiment classification is required."
                            )
                            skipped_count += 1
                            continue
                        rows.append(
                            {
                                "date": entry_date,
                                "fear_greed_value": float(value),
                                "fear_greed_label": str(label),
                            }
                        )
                    except (ValueError, KeyError, TypeError, AttributeError) as e:
                        logger.warning(f"Fear & Greed entry parsing error: {e}")
                        skipped_count += 1
                        continue

                # CNN API includes today's date in both fear_and_greed_historical
                # AND the current reading appended above. Deduplicate by date,
                # keeping the last occurrence (current reading wins).
                seen: dict[str, Any] = {}
                for r in rows:
                    seen[r["date"]] = r
                rows = list(seen.values())

                if not rows:
                    logger.error(
                        f"No valid Fear & Greed index entries parsed from CNN API response. "
                        f"Processed {len(entries)} entries, {skipped_count} skipped due to missing required fields."
                    )
                    return [
                        {
                            "date": _dt.utcnow().strftime("%Y-%m-%d"),
                            "fear_greed_value": None,
                            "fear_greed_label": None,
                            "data_unavailable": True,
                            "reason": "no_valid_entries",
                        }
                    ]

                if skipped_count > 0:
                    logger.warning(
                        f"Fear & Greed loader: {skipped_count} entries skipped due to missing fields. "
                        f"Returned {len(rows)} valid entries from {len(entries)} total."
                    )

                return rows

            except requests.exceptions.Timeout as e:
                if attempt < 2:
                    logger.warning(f"Fear & Greed timeout (attempt {attempt + 1}/3), retrying...")
                    time.sleep((attempt + 1) * 5)
                else:
                    logger.error(
                        "Failed to fetch Fear & Greed index after 3 timeout attempts. CNN API is unreachable or slow."
                    )
                    return [
                        {
                            "date": _dt.utcnow().strftime("%Y-%m-%d"),
                            "fear_greed_value": None,
                            "fear_greed_label": None,
                            "data_unavailable": True,
                            "reason": "fetch_timeout",
                        }
                    ]
            except requests.exceptions.ConnectionError as e:
                if attempt < 2:
                    logger.warning(f"Fear & Greed connection error (attempt {attempt + 1}/3), retrying...")
                    time.sleep((attempt + 1) * 5)
                else:
                    logger.error(
                        "Failed to fetch Fear & Greed index after 3 connection errors. Cannot reach CNN API."
                    )
                    return [
                        {
                            "date": _dt.utcnow().strftime("%Y-%m-%d"),
                            "fear_greed_value": None,
                            "fear_greed_label": None,
                            "data_unavailable": True,
                            "reason": "connection_error",
                        }
                    ]
            except requests.exceptions.HTTPError as e:
                logger.error(
                    f"[FEAR_GREED] HTTP error from CNN: {e}. Check CNN API status and rate limits."
                )
                return [
                    {
                        "date": _dt.utcnow().strftime("%Y-%m-%d"),
                        "fear_greed_value": None,
                        "fear_greed_label": None,
                        "data_unavailable": True,
                        "reason": "http_error",
                    }
                ]
            except (ValueError, KeyError, TypeError) as e:
                logger.error(
                    f"[FEAR_GREED] Data format error parsing CNN response: {e}. "
                    "CNN API response format may have changed."
                )
                return [
                    {
                        "date": _dt.utcnow().strftime("%Y-%m-%d"),
                        "fear_greed_value": None,
                        "fear_greed_label": None,
                        "data_unavailable": True,
                        "reason": "parse_error",
                    }
                ]
            except requests.RequestException as e:
                logger.error(f"[FEAR_GREED] Unexpected error fetching Fear & Greed index: {e}.")
                return [
                    {
                        "date": _dt.utcnow().strftime("%Y-%m-%d"),
                        "fear_greed_value": None,
                        "fear_greed_label": None,
                        "data_unavailable": True,
                        "reason": "unexpected_error",
                    }
                ]

        # Final fallback after all retry attempts exhausted (CNN 418 blocking)
        logger.error(
            "Failed to fetch Fear & Greed index after 3 attempts (CNN 418 block). "
            "CNN API is blocking requests (rate limit or access restriction)."
        )
        return [
            {
                "date": _dt.utcnow().strftime("%Y-%m-%d"),
                "fear_greed_value": None,
                "fear_greed_label": None,
                "data_unavailable": True,
                "reason": "cnn_blocking_418",
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(FearGreedIndexLoader, global_mode=True))
