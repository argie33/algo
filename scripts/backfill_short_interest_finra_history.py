#!/usr/bin/env python3
"""Backfill historical FINRA short-interest settlement cycles.

ADDED 2026-09-14 (scores-input data-depth investigation): `load_short_interest_finra.py`'s
regular run only ever fetches the CURRENT settlement cycle via `fetch_latest()`. The table's
primary key is already `(symbol, settlement_date)` - it can hold real history, it just never
had it fetched. `FINRAShortInterestFetcher.fetch_date(target_date)` accepts any specific
settlement date and works for old dates too (live-confirmed: real data back to 2019-01-15;
2018-01-15 and earlier return 0 rows - FINRA's own API history boundary, not a bug on our
side). This script walks every 15th/end-of-month settlement date from a start date to today,
fetches each, and upserts using the EXACT SAME classification/insert logic
`ShortInterestFinraLoader.run()` uses (reuses its static helpers directly, not a reimplementation)
so historical rows are indistinguishable in shape/quality from a normal run's rows.

This is purely additive: it does not change `load_short_interest_finra.py`'s regular
`fetch_latest()`-based incremental refresh path at all - that keeps running exactly as before.

Run:
    python scripts/backfill_short_interest_finra_history.py --start-date 2019-01-15
    python scripts/backfill_short_interest_finra_history.py --start-date 2019-01-15 --dry-run
"""

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.load_short_interest_finra import (  # noqa: E402
    ShortInterestFinraLoader,
    _classify_availability,
    _lookup_finra_row,
)
from utils.db.context import DatabaseContext  # noqa: E402
from utils.finra_short_interest import FINRAShortInterestFetcher  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.loaders.helpers import get_active_symbols  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Being polite to FINRA's public API even though it documents no hard rate limit for
# reasonable use - this script makes dozens of sequential date-scoped requests in one run,
# unlike the normal loader's single-cycle-per-day usage pattern.
_INTER_DATE_SLEEP_SEC = 1.0


def _settlement_dates_since(start: date, end: date) -> list[date]:
    """Every real FINRA settlement date (15th and last day of each month) in [start, end]."""
    dates: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        mid = date(year, month, 15)
        if month == 12:
            eom = date(year, 12, 31)
        else:
            eom = date(year, month + 1, 1) - timedelta(days=1)
        for d in (mid, eom):
            if start <= d <= end:
                dates.append(d)
        month += 1
        if month == 13:
            month = 1
            year += 1
    return sorted(dates)


def backfill(start_date: date, end_date: date, dry_run: bool) -> None:
    symbols = list(get_active_symbols(exclude_etfs=True))
    shares_outstanding = ShortInterestFinraLoader._load_shares_outstanding()
    foreign_private_issuers = ShortInterestFinraLoader._load_foreign_private_issuers()
    fetcher = FINRAShortInterestFetcher()
    now_et = None

    # Skip settlement dates already fully populated (idempotent re-runs, resuming an
    # interrupted backfill) - a date counts as "done" if ANY row exists for it already.
    with DatabaseContext("read") as cur:
        cur.execute("SELECT DISTINCT settlement_date FROM short_interest_finra")
        already_have = {row[0] for row in cur.fetchall()}

    candidate_dates = _settlement_dates_since(start_date, end_date)
    logger.info(
        f"[BACKFILL] {len(candidate_dates)} candidate settlement dates from {start_date} to {end_date}, "
        f"{len(already_have)} already present in DB"
    )

    total_rows_written = 0
    total_dates_with_data = 0
    for target_date in candidate_dates:
        if target_date in already_have:
            logger.debug(f"[BACKFILL] {target_date}: already present, skipping")
            continue
        try:
            finra_data = fetcher.fetch_date(target_date)
        except RuntimeError as e:
            logger.warning(f"[BACKFILL] {target_date}: fetch failed ({e}), skipping")
            time.sleep(_INTER_DATE_SLEEP_SEC)
            continue

        if not finra_data:
            logger.info(f"[BACKFILL] {target_date}: no data published (before FINRA's own API history, or gap)")
            time.sleep(_INTER_DATE_SLEEP_SEC)
            continue

        from datetime import datetime

        now_et = datetime.now(EASTERN_TZ)
        rows_this_date = 0
        if not dry_run:
            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    finra_row = _lookup_finra_row(finra_data, symbol)
                    if finra_row is None:
                        continue  # don't manufacture data_unavailable rows for history we never observed
                    outstanding = shares_outstanding.get(symbol)
                    short_pct, short_shares, data_unavailable, reason = _classify_availability(
                        finra_row, outstanding, symbol in foreign_private_issuers, True
                    )
                    cur.execute(
                        """
                        INSERT INTO short_interest_finra
                        (symbol, settlement_date, short_shares, short_pct, finra_report_date,
                         days_to_cover, avg_daily_volume, data_unavailable, reason, data_source, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, settlement_date) DO NOTHING
                        """,
                        (
                            symbol,
                            target_date,
                            short_shares,
                            short_pct,
                            target_date,
                            finra_row.get("days_to_cover"),
                            finra_row.get("avg_daily_volume"),
                            data_unavailable,
                            reason,
                            "finra_query_api_backfill",
                            now_et,
                        ),
                    )
                    rows_this_date += 1
        else:
            rows_this_date = sum(1 for s in symbols if _lookup_finra_row(finra_data, s) is not None)

        logger.info(f"[BACKFILL] {target_date}: {rows_this_date} rows {'(dry-run)' if dry_run else 'written'}")
        total_rows_written += rows_this_date
        total_dates_with_data += 1
        time.sleep(_INTER_DATE_SLEEP_SEC)

    logger.info(
        f"[BACKFILL] Done: {total_dates_with_data} settlement dates with real data, "
        f"{total_rows_written} total rows {'(dry-run, not written)' if dry_run else 'written'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD, earliest settlement date to backfill")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, don't write to DB")
    args = parser.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    backfill(start, end, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
