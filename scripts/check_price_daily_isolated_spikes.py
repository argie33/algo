#!/usr/bin/env python3
"""Detect isolated-spike price corruption in price_daily - read-only, no data modified.

Added 2026-09-13 (factor-score/XBRL accuracy audit, goal session). A historical-backfill
batch bug (fixed for NEW rows in commit 8f8537816, 2026-08-26 - PriceTransformer.
validate_and_transform() started prior_close_by_symbol empty on every call, so the
sequence/gap/split-ratio check never actually engaged on routine single-row daily loads,
only within a multi-row backfill batch) let implausible closes into price_daily before
that fix landed. That fix stops NEW bad rows; it never retroactively cleaned the ones
already written.

Three cleanup passes so far (see memory: price_daily_retroactive_corruption_never_cleaned_up_20260913
for the full writeup, and this session's scratchpad for pre-delete JSON backups):
- Phase 1 (36a292771): 129 rows, single-day isolated spikes, volume=0.
- Phase 2 (c6a22c3b3): 111 more single-day isolated spikes, volume 1-10.
- Phase 3 (same session): 37,967 more rows discovered via a CONSECUTIVE-RUN signature -
  phases 1/2 only caught a single bad day sandwiched between two real days, but the actual
  corruption often spans a whole contiguous RUN of bad days (e.g. XXII had 2 consecutive
  corrupted days in one place and 2 more a few days later; ABTC had a 9-row run at the very
  start of its price history). A run is confirmed corrupted only when the row(s) immediately
  bracketing it (before and/or after, whichever exist) are >100x away from the run's values -
  the same ratio bar as phases 1/2, just applied to a maximal run instead of one row.
38,207 rows total deleted across 161 symbols. `--auto-clean-threshold` (default 10) still
describes the volume tier this whole signature is restricted to.

STILL OPEN, deliberately not auto-flagged as bugs: candidates with volume > 10 - genuinely
ambiguous (could be the same corrupted batch with a larger garbage volume value, real if
extreme low-float microcap trading days, or the separately-documented 2026-05-25
synthetic-seed batch - see scripts/check_synthetic_price_data.py). These need per-symbol
review against a real market-data source before any deletion, not blanket treatment - use
`--review-queue` to list them without treating them as confirmed bugs. Also NOT caught: a
run with NO real bracketing neighbor on either side (e.g. a symbol whose entire price_daily
history is corrupted) - there is nothing to compare it against, so it can't be confirmed
from this table alone.

This script makes both tiers checkable in one command going forward instead of requiring
another ad-hoc forensic dig - it does not change, delete, or regenerate anything.

Usage:
  python scripts/check_price_daily_isolated_spikes.py                  # auto-clean-tier summary
  python scripts/check_price_daily_isolated_spikes.py --review-queue    # ambiguous higher-volume candidates
  python scripts/check_price_daily_isolated_spikes.py --symbol XXII     # one symbol's detail
"""

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext

_ISOLATED_SPIKE_RATIO = 100.0
_AUTO_CLEAN_VOLUME_THRESHOLD = 10


def _is_batch_row(volume: int | None, data_source: str | None) -> bool:
    return volume is not None and volume <= _AUTO_CLEAN_VOLUME_THRESHOLD and data_source == "yfinance"


def _find_confirmed_bad_runs(cur: Any, volume_predicate: Any) -> list[dict[str, Any]]:
    """Walk each symbol's full price history to find maximal runs of batch-flagged rows
    bracketed by a real (non-batch) neighbor >100x away - the same signature used for the
    2026-09-13 phase-3 cleanup, generalized here for reuse instead of re-deriving it ad hoc.
    """
    cur.execute(
        """
        SELECT DISTINCT symbol FROM price_daily
        WHERE volume <= %(threshold)s AND data_source = 'yfinance'
        """,
        {"threshold": _AUTO_CLEAN_VOLUME_THRESHOLD},
    )
    symbols = [r[0] for r in cur.fetchall()]

    confirmed: list[dict[str, Any]] = []
    for symbol in symbols:
        cur.execute(
            "SELECT date, close, volume, data_source, created_at FROM price_daily "
            "WHERE symbol = %(symbol)s ORDER BY date",
            {"symbol": symbol},
        )
        rows = cur.fetchall()
        is_batch = [_is_batch_row(r[2], r[3]) for r in rows]

        i, n = 0, len(rows)
        while i < n:
            if not is_batch[i]:
                i += 1
                continue
            j = i
            while j < n and is_batch[j]:
                j += 1
            run = rows[i:j]
            prev_close = rows[i - 1][1] if i > 0 else None
            next_close = rows[j][1] if j < n else None
            run_min = min(r[1] for r in run)

            confirmed_bad = (prev_close and prev_close > 0 and run_min / prev_close > _ISOLATED_SPIKE_RATIO) or (
                next_close and next_close > 0 and run_min / next_close > _ISOLATED_SPIKE_RATIO
            )
            if confirmed_bad:
                for r in run:
                    confirmed.append(
                        {"symbol": symbol, "date": r[0], "close": r[1], "volume": r[2], "created_at": r[4]}
                    )
            i = j
    return confirmed


def _print_rows(rows: list[dict[str, Any]], label: str) -> None:
    if not rows:
        print(f"Clean: no {label} rows found in price_daily.")
        return
    symbols = {r["symbol"] for r in rows}
    print(f"{len(rows)} {label} row(s) across {len(symbols)} symbol(s):")
    for r in rows[:50]:
        print(f"  {r['symbol']} {r['date']}: close={r['close']} volume={r['volume']} inserted={r['created_at']}")
    if len(rows) > 50:
        print(f"  ... and {len(rows) - 50} more (truncated)")


def auto_clean_tier(cur: Any) -> None:
    rows = _find_confirmed_bad_runs(cur, None)
    _print_rows(rows, f"auto-clean-tier (volume<={_AUTO_CLEAN_VOLUME_THRESHOLD}) confirmed-bad")


def review_queue(cur: Any) -> None:
    cur.execute(
        """
        WITH w AS (
            SELECT symbol, date, close, volume, data_source, created_at,
                   LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close,
                   LEAD(close) OVER (PARTITION BY symbol ORDER BY date) AS next_close
            FROM price_daily
            WHERE close IS NOT NULL AND close > 0
        )
        SELECT symbol, date, close, volume, created_at
        FROM w
        WHERE prev_close > 0 AND next_close > 0
          AND close / prev_close > %(ratio)s AND close / next_close > %(ratio)s
          AND volume > %(threshold)s
        ORDER BY symbol, date
        """,
        {"ratio": _ISOLATED_SPIKE_RATIO, "threshold": _AUTO_CLEAN_VOLUME_THRESHOLD},
    )
    rows = [{"symbol": r[0], "date": r[1], "close": r[2], "volume": r[3], "created_at": r[4]} for r in cur.fetchall()]
    _print_rows(rows, "ambiguous higher-volume isolated-spike (needs manual review)")


def symbol_detail(cur: Any, symbol: str) -> None:
    cur.execute(
        "SELECT date, close, volume, data_source, created_at FROM price_daily WHERE symbol = %(symbol)s ORDER BY date",
        {"symbol": symbol},
    )
    rows = cur.fetchall()
    if not rows:
        print(f"No price_daily rows found for {symbol}.")
        return
    is_batch = [_is_batch_row(r[2], r[3]) for r in rows]
    for i, (dt, close, volume, data_source, created_at) in enumerate(rows):
        flag = ""
        if is_batch[i]:
            prev_close = rows[i - 1][1] if i > 0 else None
            next_close = rows[i + 1][1] if i + 1 < len(rows) else None
            if (prev_close and prev_close > 0 and close / prev_close > _ISOLATED_SPIKE_RATIO) or (
                next_close and next_close > 0 and close / next_close > _ISOLATED_SPIKE_RATIO
            ):
                flag = "  <-- confirmed-bad (batch tier)"
        print(f"  {dt}  close={close}  volume={volume}  source={data_source}  inserted={created_at}{flag}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", help="Show full price history detail for one symbol")
    parser.add_argument("--review-queue", action="store_true", help="List ambiguous higher-volume candidates instead")
    args = parser.parse_args()

    with DatabaseContext("read") as cur:
        if args.symbol:
            symbol_detail(cur, args.symbol.upper())
        elif args.review_queue:
            review_queue(cur)
        else:
            auto_clean_tier(cur)


if __name__ == "__main__":
    main()
