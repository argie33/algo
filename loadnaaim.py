#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
NAAIM Manager Exposure Data Loader - Market-level indicator (not symbol-based).

Generates and loads 60 days of NAAIM (National Association of Active Investment Managers)
quarterly exposure data with valid min/median/max ordering.

Run:
    python3 loadnaaim.py
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


def load_naaim_data():
    """Load synthetic NAAIM manager exposure data for the last 60 days."""
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
            CREATE TABLE IF NOT EXISTS naaim (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL UNIQUE,
                naaim_number_mean DOUBLE PRECISION,
                bearish DOUBLE PRECISION,
                quart1 DOUBLE PRECISION,
                quart2 DOUBLE PRECISION,
                quart3 DOUBLE PRECISION,
                bullish DOUBLE PRECISION,
                deviation DOUBLE PRECISION,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Clear and reload
        cur.execute("DELETE FROM naaim")

        start_date = date.today() - timedelta(days=60)
        records = []

        for i in range(60):
            current_date = start_date + timedelta(days=i)
            # Generate valid quartile data: quart1 < quart2 < quart3
            quart1 = round(random.uniform(30, 50), 2)
            quart2 = round(random.uniform(quart1 + 1, quart1 + 30), 2)
            quart3 = round(random.uniform(quart2 + 1, 90), 2)

            bullish = round(random.uniform(40, 75), 2)
            bearish = round(random.uniform(20, 50), 2)
            naaim_number_mean = round((quart1 + quart2 + quart3) / 3, 2)
            deviation = round(quart3 - quart1, 2)

            records.append((
                current_date,
                naaim_number_mean,
                bearish,
                quart1,
                quart2,
                quart3,
                bullish,
                deviation
            ))

        cur.executemany(
            """INSERT INTO naaim (date, naaim_number_mean, bearish, quart1, quart2, quart3, bullish, deviation)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            records
        )

        conn.commit()
        log.info(f"Loaded {len(records)} NAAIM manager exposure records")
        return len(records)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="NAAIM manager exposure data loader (market-level)")
    args = parser.parse_args()

    try:
        count = load_naaim_data()
        log.info(f"Success: {count} records loaded")
        return 0
    except Exception as e:
        log.error(f"Failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
