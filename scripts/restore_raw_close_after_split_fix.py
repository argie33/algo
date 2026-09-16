#!/usr/bin/env python3
"""One-off correction for scripts/fix_missing_stock_splits.py's first version: restores
price_daily's raw open/high/low/close/volume to their true historical (unadjusted) values for
every symbol in `stock_splits`, leaving only `adj_close` as the split-adjusted series.

WHY THIS EXISTS (2026-09-15, /goal "get our scores right" session): fix_missing_stock_splits.py
originally multiplied open/high/low/close/volume AND adj_close together for every pre-split row.
That is architecturally wrong for this schema specifically: loaders/load_risk_metrics_daily.py
already fetches `date, close, adj_close` and explicitly PREFERS adj_close over close for every
volatility/beta/drawdown/momentum calc (raw close only as a fallback when adj_close is
genuinely NULL) - `close` is meant to stay the untouched, permanent historical record of what
actually printed that day, and `adj_close` is the ONLY column meant to carry retroactive
corporate-action adjustment. Overwriting raw `close` too blurred that distinction for the 25
symbols the first run touched.

price_weekly/price_monthly have no adj_close column at all, so there is no raw/adjusted
distinction possible there - left as split-adjusted (already correct from the first run;
reverting them would just reintroduce the same kink with no adjusted alternative available).

Re-fetches each split's EXACT ratio from yfinance again (not the stored `stock_splits.
split_ratio`, which is NUMERIC(6,4) and loses precision for a ratio like 0.006666... ->
0.0067) - reversing with a rounded ratio would leave restored raw prices off by a small but
avoidable amount.

Usage:
    python scripts/restore_raw_close_after_split_fix.py            # apply
    python scripts/restore_raw_close_after_split_fix.py --dry-run  # report only
"""

import argparse
import logging
import sys

from utils.db.context import DatabaseContext
from utils.external.yfinance_timeout_wrapper import YFinanceTimeoutWrapper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, split_date FROM stock_splits ORDER BY symbol, split_date")
        splits = [(r[0], str(r[1])) for r in cur.fetchall()]

    logger.info(f"[RESTORE] {len(splits)} recorded splits to reverse raw close/open/high/low/volume for")

    by_symbol: dict[str, list[str]] = {}
    for symbol, split_date in splits:
        by_symbol.setdefault(symbol, []).append(split_date)

    succeeded, failed = [], []
    for symbol, dates in by_symbol.items():
        try:
            t = YFinanceTimeoutWrapper(symbol, timeout_sec=15)
            yf_splits = {ts.date().isoformat(): float(ratio) for ts, ratio in t.splits.items()}
        except Exception as e:
            logger.error(f"[RESTORE] {symbol}: yfinance refetch failed, skipping - {e}")
            failed.append((symbol, str(e)))
            continue

        if args.dry_run:
            for split_date in dates:
                ratio = yf_splits.get(split_date)
                logger.info(f"[RESTORE] (dry-run) {symbol} {split_date}: would reverse with ratio={ratio}")
            continue

        try:
            with DatabaseContext("write") as cur:
                for split_date in sorted(dates):
                    ratio = yf_splits.get(split_date)
                    if ratio is None:
                        raise RuntimeError(f"yfinance no longer reports a split on {split_date} - refusing to guess")
                    cur.execute(
                        """
                        UPDATE price_daily
                        SET open = open * %s, high = high * %s, low = low * %s, close = close * %s,
                            volume = ROUND(volume / %s)
                        WHERE symbol = %s AND date < %s
                        """,
                        (ratio, ratio, ratio, ratio, ratio, symbol, split_date),
                    )
                    logger.info(f"[RESTORE] {symbol}: reversed {cur.rowcount} rows before {split_date} (ratio={ratio})")
            succeeded.append(symbol)
        except Exception as e:
            logger.error(f"[RESTORE] {symbol}: FAILED, rolled back this symbol only - {e}")
            failed.append((symbol, str(e)))

    logger.info(f"\n[RESTORE] Done. {len(succeeded)} symbols restored: {succeeded}")
    if failed:
        logger.warning(f"[RESTORE] {len(failed)} symbols FAILED: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
