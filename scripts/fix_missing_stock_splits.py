#!/usr/bin/env python3
"""Backfill missing stock splits and retroactively split-adjust price history.

ROOT CAUSE (found 2026-09-15, /goal "get our scores right" session): `stock_splits` has
zero rows and no loader has ever written to it - completely dead table. `loaders/load_prices.py`
has a guard (PRICE_HISTORY_PROTECTED_AFTER_DAYS/PRICE_HISTORY_MAX_SILENT_REVISION_PCT, added
2026-09-01) that blocks a large silent REVISION of an already-settled historical close - but
that only stops Yahoo's retroactive re-adjustment from corrupting an OLD row differently on a
later run (the MNST oscillation bug it was built for). It does nothing to properly split-adjust
history when a NEW post-split close first lands next to an un-adjusted pre-split close - that
permanent kink feeds straight into every price-return-based pillar input (Risk's
volatility_60d/252d/max_drawdown_1y, Momentum's mom_12_1/mom_6m), corrupting them for the full
252-trading-day window the kink sits inside.

`algo/monitoring/data_patrol/checks/price_sanity.py`'s `check_corporate_actions` DOES detect
this correctly and has been firing every DataPatrol run today ("50 symbols with >30% single-day
drop") - it is WARN-tier, purely informational, and nothing downstream ever reads that finding
and acts on it. It is also DROP-only (`patrol_corporate_action_drop_ratio` is negative) - a
REVERSE split (price jumps UP) produces zero alert at all, a real blind spot.

This script is the actual remediation the WARN finding was missing: for each candidate symbol,
fetch yfinance's real split-event history (ground truth, not price-jump inference) via
YFinanceTimeoutWrapper, confirm a split actually occurred near the suspicious date, record it in
`stock_splits`, then retroactively adjust every price_daily/price_weekly/price_monthly row dated
strictly BEFORE the split date: OHLC *= (1/ratio), volume *= ratio. Idempotent - skips any
split already present in `stock_splits`.

Usage:
    python scripts/fix_missing_stock_splits.py                  # auto-detect candidates, apply
    python scripts/fix_missing_stock_splits.py --dry-run        # detect + report only
    python scripts/fix_missing_stock_splits.py --symbols APH,MNST
"""

import argparse
import logging
import sys
import time
from datetime import timedelta
from typing import Any

from utils.db.context import DatabaseContext
from utils.external.yfinance_timeout_wrapper import YFinanceTimeoutWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Same threshold class as price_sanity.py's corporate_action check, but BOTH directions -
# that check is drop-only (reverse splits are a real blind spot there, see module docstring).
CANDIDATE_MOVE_THRESHOLD = 0.35
CANDIDATE_LOOKBACK_DAYS = 400  # covers a full 252-trading-day window plus margin
MIN_MARKET_CAP = 300_000_000.0


def find_candidates(cur: Any) -> list[tuple[str, str, float]]:
    """Symbols with an unexplained big single-day move (either direction) and no existing
    stock_splits record covering it - the same detection shape as check_corporate_actions,
    generalized to catch reverse splits (rises) too."""
    cur.execute(
        """
        WITH moves AS (
            SELECT symbol, date, close,
                   LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '%s days'
              AND COALESCE(data_unavailable, false) = false AND close IS NOT NULL
        )
        SELECT m.symbol, m.date, (m.close - m.prev) / m.prev AS pct_move
        FROM moves m
        JOIN stock_symbols sy ON sy.symbol = m.symbol
        LEFT JOIN value_metrics vm ON vm.symbol = m.symbol
        WHERE m.prev IS NOT NULL
          AND ABS((m.close - m.prev) / m.prev) > %s
          AND COALESCE(vm.market_cap, 0) >= %s
          AND NOT EXISTS (
              SELECT 1 FROM stock_splits ss
              WHERE ss.symbol = m.symbol
                AND ss.split_date BETWEEN m.date - INTERVAL '5 days' AND m.date + INTERVAL '5 days'
          )
        ORDER BY m.symbol, m.date
        """,
        (CANDIDATE_LOOKBACK_DAYS, CANDIDATE_MOVE_THRESHOLD, MIN_MARKET_CAP),
    )
    return [(r[0], str(r[1]), float(r[2])) for r in cur.fetchall()]


def confirm_splits(symbol: str) -> list[tuple[float, str]]:
    """Fetch yfinance's real split-event history and return every (ratio, split_date_str)
    within CANDIDATE_LOOKBACK_DAYS of today, regardless of which specific price-jump date
    first flagged this symbol as a candidate.

    FIXED (same session): originally matched against a single `move_date` within +-3 days -
    a symbol whose history has the MNST-style oscillating-corruption bug (see module
    docstring) can have several spurious "big move" candidate dates, none matching the real
    split date closely enough, causing a real split to go unconfirmed. Decoupled: once a
    symbol is worth checking at all, pull its full recent split history directly rather than
    validating against one specific (possibly wrong) candidate date. `ratio` follows yfinance
    convention (new shares per old share - 2.0 for a 2-for-1, 0.5 for a 1-for-2 reverse split).
    """
    try:
        t = YFinanceTimeoutWrapper(symbol, timeout_sec=15)
        splits = t.splits
    except Exception as e:
        logger.warning(f"[SPLITS] {symbol}: yfinance splits fetch failed: {e}")
        return []
    if splits is None or len(splits) == 0:
        return []
    cutoff = __import__("datetime").date.today() - timedelta(days=CANDIDATE_LOOKBACK_DAYS)
    return [(float(ratio), ts.date().isoformat()) for ts, ratio in splits.items() if ts.date() >= cutoff]


_NUMERIC_12_4_MAX = 99_999_999.9999  # price_daily/weekly/monthly's OHLC columns are all NUMERIC(12,4)


def apply_split_adjustment(cur: Any, symbol: str, split_date: str, ratio: float) -> dict[str, int]:
    """Retroactively adjusts every price_daily/price_weekly/price_monthly row for `symbol`
    dated strictly before `split_date`: OHLC *= (1/ratio), volume *= ratio. Idempotent guard is
    the caller's stock_splits INSERT (ON CONFLICT DO NOTHING) - this function is only invoked
    once per confirmed new split.

    OVERFLOW GUARD (fixed same session, live-caught on FXHO): a stock with several cascading
    reverse splits compounds adjust_factor across each one applied in this run - a pre-split
    close that's already a genuine (if visually alarming) 5-6 figure historical price (see
    module docstring re: FXHO's real, uncorrupted $100K+ pre-split history) can overflow
    NUMERIC(12,4)'s ~1e8 cap once multiplied again. Previously this raised and rolled back the
    WHOLE symbol's transaction, discarding every other, non-overflowing row's correct
    adjustment along with it. Now the UPDATE's WHERE clause excludes only the specific rows
    that would overflow - they're left unadjusted (still correctly flagged as a real,
    unresolved kink for that date range) and counted/logged separately, while every row that
    fits proceeds normally in the same transaction."""
    counts = {}
    skipped = {}
    adjust_factor = 1.0 / ratio
    for table in ("price_daily", "price_weekly", "price_monthly"):
        # BUG FIX (same session, live-caught on FXHO): adj_close only exists on price_daily but
        # can hold a LARGER historical value than open/high/low/close (e.g. FXHO's adj_close max
        # was $597,500 vs close's $112,500 pre-split) and is multiplied by the same UPDATE - the
        # bounds check must cover it too or the guard misses exactly the row that overflows.
        bound_cols = (
            "GREATEST(open, high, low, close, adj_close)"
            if table == "price_daily"
            else "GREATEST(open, high, low, close)"
        )
        cur.execute(
            f"""
            SELECT count(*) FROM {table}
            WHERE symbol = %s AND date < %s
              AND {bound_cols} * %s >= %s
            """,
            (symbol, split_date, adjust_factor, _NUMERIC_12_4_MAX),
        )
        skip_count = cur.fetchone()[0]
        if skip_count:
            skipped[table] = skip_count

        cur.execute(
            f"""
            UPDATE {table}
            SET open = open * %s, high = high * %s, low = low * %s, close = close * %s,
                volume = ROUND(volume * %s)
                {", adj_close = adj_close * %s" if table == "price_daily" else ""}
            WHERE symbol = %s AND date < %s
              AND {bound_cols} * %s < %s
            """,
            (
                adjust_factor,
                adjust_factor,
                adjust_factor,
                adjust_factor,
                ratio,
                *((adjust_factor,) if table == "price_daily" else ()),
                symbol,
                split_date,
                adjust_factor,
                _NUMERIC_12_4_MAX,
            ),
        )
        counts[table] = cur.rowcount

    if skipped:
        logger.warning(
            f"[SPLITS] {symbol}: {skipped} row(s) left UN-adjusted (would overflow NUMERIC(12,4) "
            "at this ratio) - needs manual review, not auto-fixable by widening this script's math alone"
        )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--symbols", type=str, default=None, help="comma-separated symbol list, skips auto-detection")
    args = parser.parse_args()

    with DatabaseContext("write" if not args.dry_run else "read") as cur:
        if args.symbols:
            candidates = []
            for sym in args.symbols.split(","):
                sym = sym.strip().upper()
                cur.execute(
                    """
                    WITH moves AS (
                        SELECT date, close, LAG(close) OVER (ORDER BY date) AS prev
                        FROM price_daily WHERE symbol = %s
                          AND date >= CURRENT_DATE - INTERVAL '%s days'
                    )
                    SELECT date, (close - prev) / prev AS pct_move
                    FROM moves WHERE prev IS NOT NULL AND ABS((close - prev) / prev) > %s
                    """,
                    (sym, CANDIDATE_LOOKBACK_DAYS, CANDIDATE_MOVE_THRESHOLD),
                )
                for date, pct in cur.fetchall():
                    candidates.append((sym, str(date), float(pct)))
        else:
            candidates = find_candidates(cur)

        logger.info(
            f"[SPLITS] {len(candidates)} unexplained big-move candidates to check against yfinance ground truth"
        )

        confirmed = []
        checked_symbols: set[str] = set()
        for symbol, _move_date, _pct in candidates:
            if symbol in checked_symbols:
                continue
            checked_symbols.add(symbol)
            splits_found = confirm_splits(symbol)
            time.sleep(0.3)  # LOADER_PARALLELISM=1-equivalent pacing - avoid self-triggering a yfinance ban
            if not splits_found:
                logger.info(f"[SPLITS] {symbol}: no real split found in yfinance's recent history - not a split")
                continue
            cur.execute(
                "SELECT split_date FROM stock_splits WHERE symbol = %s",
                (symbol,),
            )
            already_recorded = {str(r[0]) for r in cur.fetchall()}
            for ratio, split_date in splits_found:
                if split_date in already_recorded:
                    continue
                confirmed.append((symbol, split_date, ratio))
                logger.info(f"[SPLITS] {symbol}: CONFIRMED real split on {split_date}, ratio={ratio}")

        logger.info(f"\n[SPLITS] {len(confirmed)}/{len(checked_symbols)} candidate symbols confirmed as real splits")

        if args.dry_run:
            logger.info("[SPLITS] --dry-run: not writing anything")
            return 0

    # ISOLATED PER-SYMBOL TRANSACTIONS (fixed same session - live-caught on FXHO): the apply
    # phase originally ran inside the SAME single write transaction as the whole script, so one
    # symbol's failure rolled back every OTHER symbol's already-successful, already-logged
    # adjustment too - live-reproduced when FXHO's second of three reverse splits hit a
    # pre-existing, unrelated data-corruption value ($102,500 close on a stock that opened
    # around $39 - a bad tick from well before any split this run touched, not something this
    # script caused or should try to silently paper over) and overflowed price_daily's
    # NUMERIC(12,4) column, discarding ABTC/AGL/ALIT/ANAB/APH/ASST/BRAI/BRCC/FFAI's real,
    # correct adjustments along with it. Each symbol now gets its own DatabaseContext (its own
    # commit boundary); a failure is caught, logged, and skipped - it does not touch any other
    # symbol's work. Failed symbols are reported at the end for manual follow-up, not silently
    # dropped.
    by_symbol: dict[str, list[tuple[str, float]]] = {}
    for symbol, split_date, ratio in confirmed:
        by_symbol.setdefault(symbol, []).append((split_date, ratio))

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    for symbol, splits in by_symbol.items():
        try:
            with DatabaseContext("write") as cur:
                for split_date, ratio in sorted(
                    splits
                ):  # chronological - see apply_split_adjustment's compounding note
                    cur.execute(
                        """
                        INSERT INTO stock_splits (symbol, split_date, split_from, split_to, split_ratio)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (symbol, split_date, 1.0, ratio, ratio),
                    )
                    counts = apply_split_adjustment(cur, symbol, split_date, ratio)
                    logger.info(f"[SPLITS] {symbol}: adjusted {counts} rows before {split_date} (ratio={ratio})")
            succeeded.append(symbol)
        except Exception as e:
            logger.error(f"[SPLITS] {symbol}: FAILED, rolled back this symbol only - {e}")
            failed.append((symbol, str(e)))

    logger.info(f"\n[SPLITS] Done. {len(succeeded)} symbols fixed: {succeeded}")
    if failed:
        logger.warning(f"[SPLITS] {len(failed)} symbols FAILED (needs manual investigation, not auto-fixed): {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
