#!/usr/bin/env python3
"""Mark algo_signals rows stuck in 'pending' past the system's own staleness window as 'expired'.

FOUND 2026-08-23 (goal session, "dig into the logs/data issues" audit): algo_signals.execution_status
has a clean historical gap - 'expired' rows only exist for signal_date 2026-07-10 through
2026-07-24, 'pending' rows only for 2026-07-28 onward (118 rows as of this writing, growing
daily). No current code path writes execution_status='expired' anywhere in this repo (confirmed
via full-repo grep and `git log -S` across history - it was never written by any commit, likely
set by a one-off manual/seed action on the local dev DB, not a removed feature). The transition
date aligns exactly with commit 9f13337c2 (2026-07-23, "Use only today's buy/sell signals, not
stale 7-day lookback"): before that fix, Phase 7 re-pulled a rolling 7-day window, so an
un-acted-on signal got re-considered on later days; after it, Phase 7 only looks at TODAY's
signals, so a signal that isn't executed/rejected the same day it's inserted is never revisited
by anything - it sits in 'pending' forever.

This is NOT a trading-safety bug: `algo/orchestrator/phase8_entry_execution.py`'s own
`_signal_age_trading_days()` + "stale_signal" rejection path already correctly rejects an old
signal if it's ever re-surfaced as a candidate - these rows are provably inert (Phase 7 never
re-surfaces them), just permanently stuck in a non-terminal status. It IS a real, ongoing
data-hygiene/reporting-accuracy gap: dashboards/audits reading algo_signals.execution_status
see a growing pile of signals that look "still open" but never will be.

Deliberately a standalone script, NOT wired into the live orchestrator phases - this is
housekeeping on already-inert rows, kept separate from trading-decision code so it carries zero
risk to Phase 7/8's live behavior. Reuses phase8_entry_execution.py's own
`_signal_age_trading_days()` and `max_signal_age_hours` config threshold (default 24h/1 trading
day if unset in algo_config) rather than inventing a new number, so "stale" means exactly what
Phase 8 itself already means by it.

Usage:
    python scripts/expire_stale_pending_signals.py --dry-run   # report only, no changes
    python scripts/expire_stale_pending_signals.py             # apply
"""

import argparse
import logging
import sys
from datetime import date, datetime
from typing import Any

from algo.orchestrator.phase8_entry_execution import _signal_age_trading_days
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _get_max_signal_age_hours() -> int:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT value FROM algo_config WHERE key = 'max_signal_age_hours'")
        row = cur.fetchone()
    return int(row[0]) if row else 24


def find_stale_pending_signals(run_date: date, max_age_hours: int) -> list[dict[str, Any]]:
    """Return pending algo_signals rows whose trading-day age exceeds max_age_hours."""
    with DatabaseContext("read") as cur:
        cur.execute(
            "SELECT id, symbol, signal_date, entry_price FROM algo_signals "
            "WHERE execution_status = 'pending' ORDER BY signal_date"
        )
        rows = cur.fetchall()

    max_age_trading_days = max_age_hours // 24
    stale = []
    for row_id, symbol, signal_date, entry_price in rows:
        age_trading_days = _signal_age_trading_days(signal_date, run_date)
        if age_trading_days > max_age_trading_days:
            stale.append(
                {
                    "id": row_id,
                    "symbol": symbol,
                    "signal_date": signal_date,
                    "entry_price": entry_price,
                    "age_trading_days": age_trading_days,
                }
            )
    return stale


def expire_stale_pending_signals(dry_run: bool = False) -> dict[str, Any]:
    run_date = datetime.now(EASTERN_TZ).date()
    max_age_hours = _get_max_signal_age_hours()
    stale = find_stale_pending_signals(run_date, max_age_hours)

    logger.info(
        f"[EXPIRE_SIGNALS] max_signal_age_hours={max_age_hours} "
        f"({max_age_hours // 24} trading day(s)) - found {len(stale)} stale pending signal(s)"
    )
    for s in stale:
        logger.info(f"  {s['symbol']} signal_date={s['signal_date']} age={s['age_trading_days']}td")

    if dry_run:
        logger.info("[DRY_RUN] No changes made")
        return {"expired": 0, "found": len(stale), "dry_run": True}

    if not stale:
        return {"expired": 0, "found": 0}

    with DatabaseContext("write") as cur:
        cur.execute(
            "UPDATE algo_signals SET execution_status = 'expired' WHERE id = ANY(%s)",
            ([s["id"] for s in stale],),
        )
        expired_count = cur.rowcount

    logger.info(f"[EXPIRE_SIGNALS] Marked {expired_count} signal(s) as expired")
    return {"expired": expired_count, "found": len(stale)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be expired, make no changes")
    args = parser.parse_args()

    result = expire_stale_pending_signals(dry_run=args.dry_run)
    logger.info(f"[EXPIRE_SIGNALS] Done: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
