#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
AAII Sentiment Data Loader - Market-level indicator (not symbol-based).

Generates and loads 60 days of AAII investor sentiment data where
bullish + neutral + bearish = 100%.

Run:
    python3 loadaaiidata.py
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional
import random
import psycopg2

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)


def load_aaii_sentiment():
    """Load synthetic AAII sentiment data for the last 60 days."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=credential_manager.get_password("db/password"),
        database=os.getenv("DB_NAME", "stocks"),
    )

    try:
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS aaii_sentiment (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL UNIQUE,
                bullish NUMERIC(5,2),
                neutral NUMERIC(5,2),
                bearish NUMERIC(5,2),
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Clear and reload
        cur.execute("DELETE FROM aaii_sentiment")

        start_date = date.today() - timedelta(days=60)
        records = []

        for i in range(60):
            current_date = start_date + timedelta(days=i)
            bullish = round(random.uniform(30, 60), 2)
            bearish = round(random.uniform(20, 45), 2)
            neutral = round(100 - bullish - bearish, 2)
            records.append((current_date, bullish, neutral, bearish))

        cur.executemany(
            "INSERT INTO aaii_sentiment (date, bullish, neutral, bearish) VALUES (%s, %s, %s, %s)",
            records
        )

        conn.commit()
        log.info(f"Loaded {len(records)} AAII sentiment records")
        return len(records)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="AAII sentiment data loader (market-level)")
    args = parser.parse_args()

    try:
        count = load_aaii_sentiment()
        log.info(f"Success: {count} records loaded")
        return 0
    except Exception as e:
        log.error(f"Failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
