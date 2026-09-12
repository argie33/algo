#!/usr/bin/env python3
"""Slow, budget-limited backfill of historical prices for delisted/inactive symbols from
Tiingo's free tier - the no-budget mitigation for this repo's confirmed survivorship bias.

Added 2026-09-12 (goal session continuation, "we don't have a paid subscription - find
another way"). Prior sessions confirmed price_daily has ZERO rows for any of Lehman/Bear
Stearns/Enron/SVB/Signature Bank/WorldCom/WaMu/etc under any ticker variant (see memory
survivorship_bias_concretely_reverified_zero_rows_named_failures_20260912) and exhausted
yfinance/Alpaca (confirmed empty for delisted names) and Stooq (bot-blocked) as free
sources. Signing up for Tiingo's free tier and live-testing it (memory
tiingo_free_tier_verified_but_too_limited_20260912) found real delisted-company coverage -
SIVB (SVB Financial) and SBNY (Signature Bank) both came back with full price history - but
the free tier caps at 25 requests/day, far too slow to backfill in one run.

This is the buildable piece: a daily-drip backfill, same "accumulate coverage across many
runs" pattern this repo already uses for its rate-limited XBRL second-opinion scripts
(scripts/xbrl_yfinance_crosscheck.py, scripts/xbrl_calculation_linkbase_check.py). Run it
by hand or from a low-frequency schedule; each run spends at most --budget (default 20,
leaving headroom under the 25/day cap for other ad hoc Tiingo use) requests on symbols never
attempted before, tracked permanently in tiingo_backfill_status (migration 1282) so repeat
runs make forward progress instead of re-discovering the same already-resolved symbols.

DELIBERATELY sources candidates from the existing `stock_symbols WHERE active = false`
population (540 symbols spanning every sector - SPACs, utilities, insurers, REITs, cable,
pharma, banks, software - not just the handful of famous bank failures named in the
original audit), prioritizing symbols with a real detected delisting_events row first. This
keeps the backfill broad/unbiased the way Fama-MacBeth needs, per the same-session decision
in memory xbrl_revenue... (see xbrl_under300 session log family) that a curated list of only
famous failures would introduce a NEW survivor-of-fame bias rather than fixing the original
one. It does NOT add brand-new symbols to stock_symbols for famous failures that were never
tracked here at all (e.g. Lehman/Enron/WorldCom, confirmed 2026-09-12 to not even be
inactive rows, not just missing prices) - that's a separate, larger scope decision left for
later.

Usage:
    python scripts/tiingo_delisted_price_backfill.py                  # spend up to 20 requests
    python scripts/tiingo_delisted_price_backfill.py --budget 10
    python scripts/tiingo_delisted_price_backfill.py --symbols SIVB,SBNY
    python scripts/tiingo_delisted_price_backfill.py --dry-run          # print only, no writes
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import utils.dotenv_loader  # noqa: F401,E402  (loads .env.local, including TIINGO_API_KEY)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TIINGO_PRICES_URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices"
# Tiingo's own oldest coverage predates any symbol this repo could plausibly still track as
# "delisted" (nothing here goes back before the 1960s price_daily floor) - starting from 1990
# comfortably covers every candidate without wasting response payload on decades of data no
# candidate symbol could have traded during.
BACKFILL_START_DATE = "1990-01-01"
DEFAULT_DAILY_BUDGET = 20
REQUEST_TIMEOUT_SEC = 30
# Be polite between calls - this is a slow drip by design, not a race to spend the budget.
INTER_REQUEST_SLEEP_SEC = 1.0


def _select_candidate_symbols(cur: Any, limit: int, explicit_symbols: list[str] | None) -> list[str]:
    if explicit_symbols:
        return explicit_symbols

    cur.execute(
        """
        SELECT s.symbol
        FROM stock_symbols s
        LEFT JOIN tiingo_backfill_status t ON t.symbol = s.symbol
        WHERE s.active = FALSE
          AND t.symbol IS NULL
        ORDER BY
            (EXISTS (SELECT 1 FROM delisting_events de WHERE de.symbol = s.symbol)) DESC,
            s.symbol
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _fetch_tiingo_prices(symbol: str, api_key: str) -> list[dict[str, Any]]:
    """Returns the raw Tiingo daily-bar list for symbol, or [] if the vendor has no data.

    [] here is the correct, checked "no candidates" outcome (Tiingo genuinely doesn't cover
    this symbol), not a silent fallback - callers record it explicitly as status=
    'no_data_at_vendor' in tiingo_backfill_status rather than treating it as success.
    """
    import requests

    url = TIINGO_PRICES_URL.format(ticker=symbol.lower())
    resp = requests.get(
        url,
        params={"startDate": BACKFILL_START_DATE, "format": "json", "token": api_key},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    if resp.status_code == 404:
        return []
    if resp.status_code == 429:
        raise RuntimeError(f"Tiingo rate limit hit (429) on {symbol} - stop here, budget likely exhausted for today")
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected Tiingo response shape for {symbol}: {type(data).__name__}")
    return data


def _upsert_price_rows(cur: Any, symbol: str, bars: list[dict[str, Any]]) -> int:
    # Live DB schema (verified 2026-09-12) has no split_coefficient column despite
    # lambda/db-init/schema.sql's aspirational version listing one - matches this repo's
    # long-documented pattern of the checked-in schema.sql drifting from the real applied
    # migration history. Tiingo's own splitFactor is dropped rather than stored: adjClose
    # already carries the split-adjusted price, which is what every downstream reader here
    # (technical indicators, backtests) actually consumes.
    rows = [
        (
            symbol,
            bar["date"][:10],
            bar.get("open"),
            bar.get("high"),
            bar.get("low"),
            bar.get("close"),
            bar.get("adjClose"),
            bar.get("volume"),
            "tiingo",
        )
        for bar in bars
        if bar.get("close") is not None
    ]
    if not rows:
        return 0

    import psycopg2.extras

    # BUG FOUND 2026-09-12 (live-caught on SIVB: cur.rowcount reported 67 while 8867 rows
    # actually landed): execute_values splits a large VALUES list into multiple internal
    # INSERT batches (default page_size=100) - cur.rowcount after the call only reflects the
    # LAST batch's affected rows, not the cumulative total, silently undercounting every
    # multi-page insert. RETURNING + fetch=True makes execute_values collect every batch's
    # result rows across all pages, giving the real total.
    inserted = psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, data_source)
        VALUES %s
        ON CONFLICT (symbol, date) DO NOTHING
        RETURNING symbol
        """,
        rows,
        fetch=True,
    )
    return len(inserted)


def _record_status(cur: Any, symbol: str, status: str, rows_inserted: int, detail: str) -> None:
    cur.execute(
        """
        INSERT INTO tiingo_backfill_status (symbol, status, rows_inserted, last_attempt_at, detail)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
        ON CONFLICT (symbol) DO UPDATE SET
            status = EXCLUDED.status,
            rows_inserted = EXCLUDED.rows_inserted,
            last_attempt_at = EXCLUDED.last_attempt_at,
            detail = EXCLUDED.detail
        """,
        (symbol, status, rows_inserted, detail[:500]),
    )


def run(budget: int, explicit_symbols: list[str] | None, dry_run: bool) -> dict[str, Any]:
    import os

    api_key = os.getenv("TIINGO_API_KEY")
    if not api_key:
        raise RuntimeError("TIINGO_API_KEY not set - expected in .env.local for local dev use")

    from utils.db.context import DatabaseContext

    mode = "read" if dry_run else "write"
    summary: dict[str, Any] = {"attempted": 0, "backfilled": 0, "no_data": 0, "errors": 0, "rows_inserted": 0}

    with DatabaseContext(mode) as cur:
        symbols = _select_candidate_symbols(cur, budget, explicit_symbols)
        if not symbols:
            logger.info("No unattempted delisted/inactive symbols left to try - nothing to do")
            return summary

        logger.info(f"Attempting {len(symbols)} symbol(s) this run (budget={budget}, dry_run={dry_run})")

        for i, symbol in enumerate(symbols):
            summary["attempted"] += 1
            try:
                bars = _fetch_tiingo_prices(symbol, api_key)
            except RuntimeError as e:
                if "rate limit" in str(e).lower():
                    logger.warning(f"{e} - stopping early after {i} symbol(s)")
                    break
                logger.error(f"{symbol}: fetch failed: {e}")
                summary["errors"] += 1
                if not dry_run:
                    _record_status(cur, symbol, "error", 0, str(e))
                continue

            if not bars:
                logger.info(f"{symbol}: no data at Tiingo")
                summary["no_data"] += 1
                if not dry_run:
                    _record_status(cur, symbol, "no_data_at_vendor", 0, "empty/404 response")
                continue

            if dry_run:
                logger.info(f"{symbol}: would insert up to {len(bars)} price rows (dry-run, not writing)")
                summary["backfilled"] += 1
                continue

            inserted = _upsert_price_rows(cur, symbol, bars)
            _record_status(cur, symbol, "backfilled", inserted, f"{len(bars)} bars from vendor")
            logger.info(f"{symbol}: inserted {inserted} new price_daily row(s) ({len(bars)} bars returned)")
            summary["backfilled"] += 1
            summary["rows_inserted"] += inserted

            if i < len(symbols) - 1:
                time.sleep(INTER_REQUEST_SLEEP_SEC)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget", type=int, default=DEFAULT_DAILY_BUDGET, help="Max Tiingo requests this run")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols to force-attempt")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write to the database")
    args = parser.parse_args()

    explicit_symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    summary = run(args.budget, explicit_symbols, args.dry_run)
    logger.info(f"Done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
