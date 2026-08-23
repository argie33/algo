#!/usr/bin/env python3
"""One-time historical backfill for specific `economic_data` FRED series.

WHY THIS EXISTS: loaders/load_economic_data.py's regular run only fetches a rolling
365-day window each time (`start_date = end_date - timedelta(days=365)`) and
store_economic_data() only deletes/reinserts within that window, preserving whatever
older history already exists - by design, so a normal run can never destroy history a
prior wider pull established (see that file's own "CRITICAL FIX" comment on
store_economic_data). That means any series that never got an initial wide historical
pull stays permanently shallow no matter how many years the regular loader keeps
running - confirmed live 2026-08-23 for T10Y2Y (274 rows, starting 2025-07-21 despite
FRED having this series back to 1976) and BAMLH0A0HYM2 (287 rows, starting 2025-07-21
despite FRED having it back to 1996-12-31). This is NOT a FRED data-availability gap;
it's a one-time local backfill this environment never ran. Several other series in this
DB (ANFCI, STLFSI4, CFNAI) show the same shallow-start pattern but were excluded from
the exposure model for independent redundancy/sparsity reasons (see
algo/risk/market_exposure.py's module docstring) - not backfilled here, out of scope for
what motivated this script (goal: exposure-model integrity review, 2026-08-23).

Reuses load_economic_data.py's own fetch_from_fred/store_economic_data (same API,
same rate-limiting, same storage contract) rather than duplicating that logic - this is
purely a wider `start_date` for a one-off run, not a different data path.

Usage: python scripts/backfill_economic_data_history.py SERIES_ID [SERIES_ID ...]
"""

import logging
import sys
import time
from datetime import date
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.load_economic_data import (  # noqa: E402
    fetch_from_fred,
    get_fred_api_key,
    store_economic_data,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# FRED's actual earliest coverage varies by series; requesting from well before any
# series' real start is safe - FRED simply returns observations from its own true start.
BACKFILL_START = date(1990, 1, 1)


def backfill(series_ids: list[str]) -> dict[str, str]:
    api_key = get_fred_api_key()
    end_date = date.today()
    results: dict[str, str] = {}
    for i, series_id in enumerate(series_ids):
        if i > 0:
            time.sleep(5.0)  # same rate-limit convention as load_economic_data.py
        logger.info(f"[BACKFILL] Fetching full history for {series_id} from {BACKFILL_START}...")
        try:
            records = fetch_from_fred(api_key, series_id, BACKFILL_START, end_date)
            inserted = store_economic_data(series_id, records)
            results[series_id] = (
                f"{inserted} records ({records[0]['date']} to {records[-1]['date']})" if records else "0 records"
            )
            logger.info(f"[BACKFILL] {series_id}: {results[series_id]}")
        except RuntimeError as e:
            logger.error(f"[BACKFILL] {series_id} failed: {e}")
            results[series_id] = f"failed: {e}"
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/backfill_economic_data_history.py SERIES_ID [SERIES_ID ...]")
        sys.exit(1)
    outcome = backfill(sys.argv[1:])
    for sid, msg in outcome.items():
        print(f"{sid}: {msg}")
    sys.exit(0 if all("failed" not in v for v in outcome.values()) else 1)
