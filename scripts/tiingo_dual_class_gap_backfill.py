#!/usr/bin/env python3
"""Backfill price_daily gaps for dotted/dashed dual-class tickers (WSO.B, AKO.A, MOG.B, ...)
that both Alpaca and yfinance miss.

Added 2026-09-15 (/goal "fix all the data issues" session). Root-caused via
algo/monitoring/data_patrol/checks/price_sanity.py's trading_day_gaps check: a persistent
subset of its quarantined symbols are ALL dotted dual-class tickers (WSO.B, AKO.A, MOG.B,
CIG.C, HDL, WLYB, APGE) - live-confirmed 2026-09-15 these are the exact 5 symbols
utils/data/source_router.py's own load_prices.py run logged as "yfinance itself is behind,
not just Alpaca" for. Tiingo (already integrated for delisted-symbol backfill, see
scripts/tiingo_delisted_price_backfill.py) DOES carry real data for these tickers under a
dash instead of a dot (WSO-B not WSO.B, AKO-A not AKO.A) - live-confirmed via a direct API
call before writing this script (WSO-B returned real bars for the exact dates our own
price_daily was missing; WSO.B/WSO_B/etc. all 404). Reuses
scripts/tiingo_delisted_price_backfill.py's own _fetch_tiingo_prices/_upsert_price_rows
rather than reimplementing the fetch/upsert/rate-limit logic - this script only adds the
dot->dash ticker translation and the "which symbols currently have a real gap" selection,
which that script's own candidate query doesn't cover (it's scoped to delisted symbols only).

NOT every dotted/$-suffixed ticker resolves on Tiingo - preferred-share tickers (SCE$L in
any of SCE-L/SCE-PL/SCE$L form) all 404'd in live testing. Genuinely unavailable at this
vendor too, left to remain flagged rather than silently dropped from the check.

Usage:
    python scripts/tiingo_dual_class_gap_backfill.py                 # auto-detect gapped dotted tickers
    python scripts/tiingo_dual_class_gap_backfill.py --symbols WSO.B,AKO.A
    python scripts/tiingo_dual_class_gap_backfill.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_GAP_LOOKBACK_DAYS = 120


def _to_tiingo_ticker(symbol: str) -> str:
    """WSO.B -> WSO-B, AKO.A -> AKO-A - Tiingo's own dual-class convention, live-confirmed
    2026-09-15 (see module docstring)."""
    return symbol.replace(".", "-")


def _select_gapped_dotted_symbols(cur: Any) -> list[str]:
    """Active symbols containing a "." (dual-class notation) with at least one real missing
    trading day vs SPY's calendar in the last _GAP_LOOKBACK_DAYS - same shape as
    price_sanity.py's own check_trading_day_gaps query, restricted to the ticker pattern this
    script can actually fix."""
    cur.execute(
        f"""
        WITH cal AS (
            SELECT date FROM price_daily
            WHERE symbol = 'SPY' AND date >= CURRENT_DATE - INTERVAL '{_GAP_LOOKBACK_DAYS} days'
        ),
        dotted AS (
            SELECT symbol FROM stock_symbols WHERE active = true AND symbol LIKE '%.%'
        ),
        sym_bounds AS (
            SELECT pd.symbol, min(pd.date) AS min_d, max(pd.date) AS max_d
            FROM price_daily pd
            JOIN dotted d ON d.symbol = pd.symbol
            WHERE pd.date >= CURRENT_DATE - INTERVAL '{_GAP_LOOKBACK_DAYS} days'
            GROUP BY pd.symbol
        ),
        expected AS (
            SELECT sb.symbol, cal.date FROM sym_bounds sb JOIN cal ON cal.date BETWEEN sb.min_d AND sb.max_d
        )
        SELECT DISTINCT e.symbol
        FROM expected e
        LEFT JOIN price_daily pd ON pd.symbol = e.symbol AND pd.date = e.date
        WHERE pd.symbol IS NULL
        """
    )
    return [r[0] for r in cur.fetchall()]


def run(symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from scripts.tiingo_delisted_price_backfill import _fetch_tiingo_prices, _upsert_price_rows
    from utils.db.connection import get_db_connection

    api_key = os.getenv("TIINGO_API_KEY")
    if not api_key:
        raise RuntimeError("TIINGO_API_KEY not set - expected in .env.local for local dev use")

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor()

    symbols = symbols_override or _select_gapped_dotted_symbols(cur)
    logger.info(f"[TIINGO_DUAL_CLASS] {len(symbols)} candidate symbol(s): {symbols}")

    results: dict[str, int] = {}
    for symbol in symbols:
        tiingo_ticker = _to_tiingo_ticker(symbol)
        try:
            bars = _fetch_tiingo_prices(tiingo_ticker, api_key)
        except RuntimeError as e:
            logger.warning(f"[TIINGO_DUAL_CLASS] {symbol} ({tiingo_ticker}) fetch failed: {e}")
            results[symbol] = -1
            continue

        if not bars:
            logger.info(f"[TIINGO_DUAL_CLASS] {symbol} ({tiingo_ticker}): no Tiingo coverage (404/empty)")
            results[symbol] = 0
            continue

        if dry_run:
            logger.info(f"[DRY-RUN] {symbol} ({tiingo_ticker}): {len(bars)} bar(s) available, would upsert")
            results[symbol] = len(bars)
            continue

        inserted = _upsert_price_rows(cur, symbol, bars)
        conn.commit()
        results[symbol] = inserted
        logger.info(f"[TIINGO_DUAL_CLASS] {symbol} ({tiingo_ticker}): inserted {inserted} new row(s)")
        time.sleep(0.5)  # Tiingo free-tier courtesy pacing, same as tiingo_delisted_price_backfill.py

    cur.close()
    conn.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides auto-detection")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be inserted, don't write")
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    results = run(symbols_override, args.dry_run)
    total_inserted = sum(v for v in results.values() if v > 0)
    logger.info(f"[TIINGO_DUAL_CLASS] Done - {total_inserted} total row(s) inserted across {len(results)} symbol(s)")


if __name__ == "__main__":
    main()
