#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Fear & Greed Index Loader — Alternative.me free API.

Fetches daily Fear & Greed values and stores in fear_greed_index table.
Alternative.me provides a free, public API with no key required.

Run:
    python3 loadfeargreed.py
"""

import logging
from datetime import date, datetime
from typing import List, Optional

import requests

from config.env_loader import load_env
from utils.db_connection import get_db_connection

log = logging.getLogger(__name__)

API_URL = "https://api.alternative.me/fng/?limit=365&format=json"


def fetch_fear_greed() -> List[dict]:
    """Fetch last 365 days of Fear & Greed data."""
    try:
        resp = requests.get(API_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        log.error("Fear & Greed API failed: %s", e)
        return []

    rows = []
    for entry in data:
        try:
            ts = int(entry["timestamp"])
            dt = datetime.utcfromtimestamp(ts).date()
            rows.append({
                "date": str(dt),
                "fear_greed_value": float(entry["value"]),
                "fear_greed_label": entry.get("value_classification", ""),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return rows


def upsert_rows(rows: List[dict]) -> int:
    """Upsert rows into fear_greed_index."""
    if not rows:
        return 0
    conn = get_db_connection()
    cur = conn.cursor()
    inserted = 0
    try:
        for row in rows:
            cur.execute(
                """
                INSERT INTO fear_greed_index (date, fear_greed_value, fear_greed_label)
                VALUES (%(date)s, %(fear_greed_value)s, %(fear_greed_label)s)
                ON CONFLICT (date) DO UPDATE SET
                    fear_greed_value = EXCLUDED.fear_greed_value,
                    fear_greed_label = EXCLUDED.fear_greed_label
                """,
                row,
            )
            inserted += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return inserted


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rows = fetch_fear_greed()
    if not rows:
        log.error("No Fear & Greed data fetched")
        return 1

    inserted = upsert_rows(rows)
    log.info("Fear & Greed: %d rows upserted", inserted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
