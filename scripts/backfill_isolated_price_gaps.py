#!/usr/bin/env python3
"""Backfill isolated 1-2 day gaps in price_daily from yfinance when the primary
source (Alpaca) simply dropped a bar for an otherwise-healthy symbol.

ROOT CAUSE (found 2026-09-15, /goal "we need to fix the data issues" session): DataPatrol's
`trading_day_gaps` check (algo/monitoring/data_patrol/checks/price_sanity.py's
check_trading_day_gaps) flags 88 symbols missing rows vs SPY's calendar over the last 120d.
Live-verified this is NOT one bug: the top of that list (largest gap counts, e.g. BURU/FORTY/
SIM/GENVR) are illiquid/thin-float/halted names where yfinance itself has no real data for the
missing dates (confirmed via direct yfinance fetch - either "possibly delisted" for the window,
or flat OHLC + volume=0 placeholder rows that loaders/load_prices.py's `_validate_row` correctly
rejects as vendor noise, same shape as the EA incident its own docstring describes). Those are
not fixable here - there is no real data to backfill.

But 71 of the 88 symbols (81%) have only a 1-2 day gap, scattered across unrelated dates, in
otherwise perfectly liquid names (DELL, MRNA, MRVL, OKTA, SNOW, ZS, DKS, RARE, QDEL, ...) -
live-verified on DELL: Alpaca has 2026-05-27, 05-28, then jumps straight to 06-01, while
yfinance has a real 05-29 bar (41.8M volume, not a placeholder). The loader has no fallback
logic to backfill an isolated single-day miss from yfinance when Alpaca is otherwise healthy
for that symbol - that gap just sits there forever. This script is that backfill: for each
candidate symbol/date, fetch the exact missing date from yfinance, apply the same "reject
flat/zero-volume placeholder" guard load_prices.py uses, and insert only if it looks like real
data. A date with no usable yfinance data either (the illiquid/halted case) is simply skipped -
this script does not attempt to fabricate or approximate a missing price.

Usage:
    python scripts/backfill_isolated_price_gaps.py                   # auto-detect, apply
    python scripts/backfill_isolated_price_gaps.py --dry-run         # detect + report only
    python scripts/backfill_isolated_price_gaps.py --max-gap 2       # only symbols with <= N missing days (default 2)
    python scripts/backfill_isolated_price_gaps.py --symbols DELL,MRNA
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Any

from utils.db.context import DatabaseContext
from utils.external.yfinance_symbol import to_yfinance_symbol
from utils.external.yfinance_timeout_wrapper import call_with_timeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

GAP_LOOKBACK_DAYS = 120
GAP_MIN_MARKET_CAP = 300_000_000
DEFAULT_MAX_GAP = 2


def find_candidates(cur: Any, max_gap: int) -> dict[str, list[str]]:
    """Symbols with <= max_gap missing trading days vs SPY's calendar, same shape as
    DataPatrol's check_trading_day_gaps - restricted to a small gap count because a large
    gap count is the thin-float/halted pattern with no real data to backfill (see module
    docstring), not something this script should chase."""
    cur.execute(
        f"""
        WITH cal AS (
            SELECT date FROM price_daily
            WHERE symbol = 'SPY' AND date >= CURRENT_DATE - INTERVAL '{GAP_LOOKBACK_DAYS} days'
        ),
        sym_bounds AS (
            SELECT pd.symbol, min(pd.date) AS min_d, max(pd.date) AS max_d
            FROM price_daily pd
            JOIN value_metrics vm ON vm.symbol = pd.symbol
            WHERE pd.date >= CURRENT_DATE - INTERVAL '{GAP_LOOKBACK_DAYS} days'
              AND COALESCE(vm.market_cap, 0) >= %(min_cap)s
            GROUP BY pd.symbol
        ),
        expected AS (
            SELECT sb.symbol, cal.date
            FROM sym_bounds sb
            JOIN cal ON cal.date BETWEEN sb.min_d AND sb.max_d
        ),
        missing AS (
            SELECT e.symbol, e.date
            FROM expected e
            LEFT JOIN price_daily pd ON pd.symbol = e.symbol AND pd.date = e.date
            WHERE pd.symbol IS NULL
        )
        SELECT symbol, array_agg(date ORDER BY date) AS missing_dates
        FROM missing
        GROUP BY symbol
        HAVING count(*) <= %(max_gap)s
        ORDER BY symbol
        """,
        {"min_cap": GAP_MIN_MARKET_CAP, "max_gap": max_gap},
    )
    return {r[0]: [str(d) for d in r[1]] for r in cur.fetchall()}


def _looks_like_placeholder(open_: float, high: float, low: float, close: float, volume: int) -> bool:
    """Same guard as loaders/load_prices.py's _validate_row: a flat OHLC with zero volume is
    vendor placeholder noise (live-confirmed on EA), not real market data - never backfill it."""
    return open_ == high == low == close and volume == 0


def _fetch_history(symbol: str, date: str) -> Any:
    import yfinance as yf

    start = datetime.strptime(date, "%Y-%m-%d").date()
    end = start + timedelta(days=1)
    return yf.Ticker(to_yfinance_symbol(symbol)).history(start=start.isoformat(), end=end.isoformat())


def fetch_day(symbol: str, date: str) -> dict[str, Any] | None:
    """YFinanceTimeoutWrapper's __getattr__ only times attribute access (e.g. `.splits`), not a
    method call like `.history(...)` - call_with_timeout directly here wraps the whole
    Ticker-creation-plus-history-fetch instead, same hard-timeout protection."""
    try:
        hist = call_with_timeout(_fetch_history, 15, symbol, date)
    except Exception as e:
        logger.warning(f"[GAPFILL] {symbol} {date}: yfinance fetch failed: {e}")
        return None
    if hist is None or len(hist) == 0:
        return None
    row = hist.iloc[0]
    try:
        open_, high, low, close, volume = (
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            int(row["Volume"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if not (
        low > 0
        and high > 0
        and close > 0
        and open_ > 0
        and high >= low
        and low <= close <= high
        and low <= open_ <= high
    ):
        return None
    if _looks_like_placeholder(open_, high, low, close, volume):
        return None
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-gap", type=int, default=DEFAULT_MAX_GAP)
    parser.add_argument("--symbols", type=str, default=None, help="comma-separated symbol list, skips auto-detection")
    args = parser.parse_args()

    with DatabaseContext("read") as cur:
        if args.symbols:
            all_candidates = find_candidates(cur, max_gap=10_000)
            wanted = {s.strip().upper() for s in args.symbols.split(",")}
            candidates = {s: d for s, d in all_candidates.items() if s in wanted}
        else:
            candidates = find_candidates(cur, args.max_gap)

    total_dates = sum(len(v) for v in candidates.values())
    logger.info(f"[GAPFILL] {len(candidates)} symbol(s), {total_dates} missing date(s) to check against yfinance")

    filled = 0
    unavailable = 0
    for symbol, dates in candidates.items():
        rows_to_insert: list[tuple[str, dict[str, Any]]] = []
        for date in dates:
            data = fetch_day(symbol, date)
            time.sleep(0.3)  # LOADER_PARALLELISM=1-equivalent pacing, same as fix_missing_stock_splits.py
            if data is None:
                logger.info(f"[GAPFILL] {symbol} {date}: no usable yfinance data - skipping (not backfillable)")
                unavailable += 1
                continue
            logger.info(f"[GAPFILL] {symbol} {date}: real data found, close={data['close']}, volume={data['volume']}")
            rows_to_insert.append((date, data))

        if not rows_to_insert or args.dry_run:
            continue

        try:
            with DatabaseContext("write") as cur:
                for date, data in rows_to_insert:
                    cur.execute(
                        """
                        INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close,
                                                  volume, data_source, data_unavailable)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'yfinance', false)
                        ON CONFLICT (symbol, date) DO NOTHING
                        """,
                        (
                            symbol,
                            date,
                            data["open"],
                            data["high"],
                            data["low"],
                            data["close"],
                            data["close"],
                            data["volume"],
                        ),
                    )
                    filled += cur.rowcount
        except Exception as e:
            logger.error(f"[GAPFILL] {symbol}: FAILED, rolled back this symbol only - {e}")

    logger.info(
        f"\n[GAPFILL] Done. {filled} row(s) backfilled, {unavailable} date(s) had no usable data (thin-float/halted, left as-is)"
    )
    if args.dry_run:
        logger.info("[GAPFILL] --dry-run: nothing was written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
