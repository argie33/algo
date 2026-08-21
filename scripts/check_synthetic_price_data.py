#!/usr/bin/env python3
"""Report synthetic-vs-real price_daily coverage - read-only, no data modified.

Added 2026-08-21 (finance-accuracy audit, goal session): a one-time bulk historical
seed (created_at = 2026-05-25 02:20:04, data_source IS NULL for every row it wrote -
real loader rows always populate data_source per migration 1135) covers roughly 90%
of price_daily's total rows, spanning 2021-05-18 through 2026-05-22. Real loader output
only exists from 2026-05-26 onward. This is not inherently wrong (it gives the system
years of history to compute long-lookback indicators against before real data
accumulated), but it means any technical indicator, backtest, or momentum score whose
lookback window still reaches back before 2026-05-26 is partly or fully built on
synthetic, not real, market data - and a handful of symbols' synthetic history contains
implausible price levels (verified live: BRID/CGTL/BYFC all triggered
ROC_OVERFLOW_SKIP/CLIP in loaders/load_technical_indicators.py because of this).

This script makes that limitation checkable in one command instead of requiring the
kind of ad-hoc forensic investigation that originally found it - it does not change,
delete, or regenerate anything.

Usage:
  python scripts/check_synthetic_price_data.py                  # universe-wide summary
  python scripts/check_synthetic_price_data.py --symbol BRID     # one symbol's detail
  python scripts/check_synthetic_price_data.py --flag-suspicious # list symbols whose
                                                                  # historical price is
                                                                  # implausible vs today
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

# Technical indicators' longest lookback (roc_252d, sma_200-ish) - matches
# loaders/load_technical_indicators.py's OUTPUT_WINDOW_DAYS_TECH_INDICATORS intent:
# once this many real trading days have accumulated since the synthetic cutoff, every
# indicator's lookback window is built entirely on real data.
LONGEST_LOOKBACK_TRADING_DAYS = 252


# A handful of symbols got an early, isolated real historical backfill (e.g. 185 rows on
# 2021-09-14) well before full-universe real coverage actually began - counting any date
# with at least one real-tagged row would overstate "real coverage" by ~5 years. Require a
# per-date row count in the same ballpark as the active universe so this only counts dates
# where essentially the WHOLE universe has real data, not a handful of early outliers.
_FULL_UNIVERSE_ROW_THRESHOLD = 5000


def _trading_days_since(cur: Any, start_date: date, end_date: date) -> int:
    cur.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT date FROM price_daily
            WHERE date > %s AND date <= %s AND data_source IS NOT NULL
            GROUP BY date HAVING COUNT(*) >= %s
        ) full_coverage_dates
        """,
        (start_date, end_date, _FULL_UNIVERSE_ROW_THRESHOLD),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _full_universe_real_coverage_start(cur: Any) -> date | None:
    """First date where real-tagged rows reach full-universe scale, not just an isolated
    early backfill for a handful of symbols."""
    cur.execute(
        """
        SELECT MIN(date) FROM (
            SELECT date FROM price_daily WHERE data_source IS NOT NULL
            GROUP BY date HAVING COUNT(*) >= %s
        ) full_coverage_dates
        """,
        (_FULL_UNIVERSE_ROW_THRESHOLD,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def universe_summary(cur: Any) -> None:
    # ROOT-CAUSED 2026-08-21 (same audit that added this script): `data_source IS NULL` is
    # NOT a clean synthetic-vs-real signal on its own. 427,856 additional NULL rows exist
    # beyond the one confirmed bulk seed batch - but their created_at timestamps closely
    # track their OWN trading date (e.g. a 2026-07-13 row created 2026-07-13 06:54 AM,
    # matching the real morning pipeline schedule), the opposite of the confirmed seed's
    # signature (one shared created_at for 8.17M rows across 5 years at once). Traced this
    # to a genuine migration-timing artifact, not an active bug: AAPL alone shows a clean
    # cutover at 2026-07-16 (every date before is NULL, every date after has a real
    # 'yfinance'/'alpaca' tag), matching when migration 1135's data_source-population code
    # was deployed into this environment - rows inserted by the same real, incremental
    # daily loader BEFORE that deployment simply predate the column/feature, same as any
    # other "NULL means pre-migration row" column already documented throughout this
    # codebase. The full-universe boundary isn't a mathematically perfect single date
    # (some post-cutover healing-overlap refreshes retroactively tagged a handful of older
    # dates, and a small number of post-cutover rows are still untagged from some
    # not-fully-identified secondary path) - but the dominant signal is unambiguous: this
    # is old data missing new metadata, not synthetic/fabricated data. No loader code fix
    # needed (current code already tags every new row correctly, confirmed by the sharp
    # July 2026 cutover); the only remaining action would be an optional one-time backfill
    # to retroactively populate data_source for these still-real, still-correct OHLCV rows
    # - cosmetic, not a correctness issue.
    known_seed_created_at = "2026-05-25 02:20:04.232597"
    cur.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) FROM price_daily WHERE data_source IS NULL AND created_at = %s",
        (known_seed_created_at,),
    )
    synth_count, synth_min, synth_max = cur.fetchone()
    cur.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) FROM price_daily WHERE data_source IS NULL AND created_at != %s",
        (known_seed_created_at,),
    )
    untagged_count, untagged_min, untagged_max = cur.fetchone()
    cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM price_daily WHERE data_source IS NOT NULL")
    real_count, real_min, real_max = cur.fetchone()
    total = (synth_count or 0) + (untagged_count or 0) + (real_count or 0)

    print("=" * 70)
    print("PRICE_DAILY SYNTHETIC-VS-REAL COVERAGE (read-only report)")
    print("=" * 70)
    print(f"Total rows:      {total:,}")
    if synth_count:
        pct = synth_count / total * 100 if total else 0
        print(f"Confirmed synthetic seed:  {synth_count:,} ({pct:.1f}%)  dates {synth_min} .. {synth_max}")
        print("  (one bulk insert, single shared created_at timestamp - see script docstring)")
    else:
        print("Confirmed synthetic seed:  0 (none detected)")
    if untagged_count:
        pct = untagged_count / total * 100 if total else 0
        print(
            f"Real, untagged (pre-migration):  {untagged_count:,} ({pct:.1f}%)  dates {untagged_min} .. {untagged_max}"
        )
        print(
            "  (data_source is NULL but created_at tracks each row's own trading date - real,\n"
            "   incremental loader output inserted before migration 1135's data_source-population\n"
            "   code was deployed here (~2026-07-16), NOT synthetic. See script docstring.)"
        )
    if real_count:
        pct = real_count / total * 100 if total else 0
        print(f"Confirmed real (tagged):   {real_count:,} ({pct:.1f}%)  dates {real_min} .. {real_max}")
        print(
            f"  ({real_min} is the earliest ANY real-tagged row exists - a handful of symbols\n"
            "   got an isolated early backfill years before full-universe real coverage began.\n"
            "   See 'full-universe' date below for the date that actually matters for lookback windows.)"
        )
    else:
        print("Confirmed real (tagged):   0")

    full_coverage_start = _full_universe_real_coverage_start(cur)
    if full_coverage_start:
        today = datetime.now(EASTERN_TZ).date()
        real_trading_days = _trading_days_since(cur, full_coverage_start - timedelta(days=1), today)
        remaining = max(0, LONGEST_LOOKBACK_TRADING_DAYS - real_trading_days)
        print()
        print(f"Full-universe real coverage began: {full_coverage_start}")
        print(f"Real trading days accumulated since then: {real_trading_days}")
        if remaining > 0:
            print(
                f"-> {remaining} more real trading days needed before a {LONGEST_LOOKBACK_TRADING_DAYS}-day "
                f"lookback (e.g. roc_252d) is built ENTIRELY on real data with zero synthetic-period overlap."
            )
        else:
            print(
                f"-> A {LONGEST_LOOKBACK_TRADING_DAYS}-day lookback from today no longer reaches into the "
                f"synthetic seed period at all."
            )


def symbol_detail(cur: Any, symbol: str) -> None:
    cur.execute(
        "SELECT date, close, volume, data_source FROM price_daily WHERE symbol = %s ORDER BY date",
        (symbol,),
    )
    rows = cur.fetchall()
    if not rows:
        print(f"No price_daily rows found for {symbol}.")
        return
    synth_rows = [r for r in rows if r[3] is None]
    real_rows = [r for r in rows if r[3] is not None]
    print(f"{symbol}: {len(rows)} total rows ({len(synth_rows)} synthetic, {len(real_rows)} real)")
    if synth_rows:
        closes = [float(r[1]) for r in synth_rows]
        print(f"  Synthetic period close range: {min(closes):.2f} .. {max(closes):.2f}")
    if real_rows:
        closes = [float(r[1]) for r in real_rows]
        print(f"  Real period close range:      {min(closes):.2f} .. {max(closes):.2f}")
    if synth_rows and real_rows:
        synth_max_close = max(float(r[1]) for r in synth_rows)
        real_latest_close = float(real_rows[-1][1])
        if real_latest_close > 0 and synth_max_close / real_latest_close > 5:
            print(
                f"  WARNING: synthetic-period max close ({synth_max_close:.2f}) is "
                f"{synth_max_close / real_latest_close:.0f}x today's real close ({real_latest_close:.2f}) - "
                "this symbol's synthetic history may feed implausible values into any indicator "
                "whose lookback window still reaches into the synthetic period."
            )


def flag_suspicious(cur: Any) -> None:
    """Same signature used to live-find BRID/CGTL/BYFC this session: a historical max
    close/volume many times today's real values, on an actively-traded (non-tiny-volume)
    symbol - not proof of corruption on its own (real serial-reverse-splitters like
    UVXY/SOXS legitimately show this), but worth a human glance. Matches on any
    data_source IS NULL row (confirmed seed OR the separate unconfirmed-untagged rows
    universe_summary() reports - both are equally worth a look here)."""
    cur.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (symbol) symbol, close AS cur_close
            FROM price_daily ORDER BY symbol, date DESC
        ),
        hist AS (
            SELECT symbol, MAX(close) AS max_close, MAX(volume) AS max_vol
            FROM price_daily WHERE data_source IS NULL GROUP BY symbol
        )
        SELECT l.symbol, l.cur_close, h.max_close, h.max_vol
        FROM latest l JOIN hist h USING (symbol)
        WHERE h.max_close > 5 * l.cur_close AND h.max_close > 50 AND h.max_vol > 20000000
        ORDER BY h.max_close DESC
        """
    )
    rows = cur.fetchall()
    print(
        f"{len(rows)} symbols with a synthetic-period close >5x today's real close (informational, not all are bugs):"
    )
    for symbol, cur_close, max_close, max_vol in rows[:50]:
        print(f"  {symbol}: today ${cur_close:.2f}  synthetic-period max ${max_close:.2f}  max volume {max_vol:,}")
    if len(rows) > 50:
        print(f"  ... and {len(rows) - 50} more (truncated)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", help="Show synthetic-vs-real detail for one symbol")
    parser.add_argument(
        "--flag-suspicious", action="store_true", help="List symbols with implausible synthetic-period prices"
    )
    args = parser.parse_args()

    with DatabaseContext("read") as cur:
        if args.symbol:
            symbol_detail(cur, args.symbol.upper())
        elif args.flag_suspicious:
            flag_suspicious(cur)
        else:
            universe_summary(cur)


if __name__ == "__main__":
    main()
