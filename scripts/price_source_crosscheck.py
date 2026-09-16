#!/usr/bin/env python3
"""Periodic independent cross-check: our stored OHLCV price data vs an independently-fetched
yfinance read of the same trading day, for a rotating sample of the active universe.

Added 2026-09-16 (goal session: "make sure we're doing all we need with the xbrl.org stuff
... apply it across the landscape" - a follow-up audit of the XBRL data-quality stack found
that price data, unlike XBRL fundamentals, had zero cross-provider validation despite feeding
every scoring/trading decision directly). This is the price-data sibling of
xbrl_yfinance_crosscheck.py - same "second opinion, not ground truth" posture, same
data_patrol_log/data_patrol_review triage workflow, same rate-limit discipline (small daily
rotating sample, NOT full-universe, to avoid the shared-IP yfinance ban risk memory documents
under yfinance_validation_calls_self_triggered_ban_during_reload_20260903).

A prior one-time evaluation of this exact question (scripts/compare_price_sources.py, deleted
2026-07-27 per commit f6d061869, see steering/DATA_LOADERS.md ~line 528) found 99.4% coverage
and a close-diff median of 0.0000% between Alpaca and yfinance at the time PRICE_DATA_SOURCE
was switched to Alpaca - but that was a single one-off snapshot, not ongoing coverage, and
that script no longer exists. This script rebuilds that capability as a permanent, scheduled,
low-cost check instead of a one-off.

Comparison uses price_daily_split_adjusted (migration 1298), not raw price_daily: yfinance's
`close` is unconditionally split-adjusted for a symbol's entire history regardless of fetch
time (see migration 1298's docstring - Yahoo retroactively restates on every fetch), while our
raw price_daily is deliberately NOT retroactively mutated for splits (industry/CRSP-style
raw-store pattern). Comparing raw-vs-adjusted would produce a `close-to-1.0-factor` false
divergence for every symbol with any split in its history, not a real data error. The view's
close_adjusted already reconciles this the same way yfinance's own restatement does, so a
real remaining divergence after this comparison means something else is actually wrong
(vendor data error, symbol mapping bug, wrong trading day, etc.) rather than a split artifact.

Volume is intentionally NOT used as a divergence trigger here (only carried in the finding
detail for context) - unlike close price, whether a vendor's reported daily volume is itself
split-adjusted for historical rows is not verified for yfinance in this codebase, so a
volume-based threshold would risk the same kind of false-positive this script exists to avoid
for price. A future pass that verifies yfinance's volume convention could safely add this.

Also flags (INFO severity, not WARN) any sampled symbol whose current price_daily row has a
NULL data_source - steering/DATA_LOADERS.md notes this per-row source-attribution question was
deliberately left open ("without an ask for that tradeoff") rather than silently dropping
those rows from consideration; this surfaces them into the same review queue instead.

Usage:
    python scripts/price_source_crosscheck.py                  # sample 25 symbols, write findings
    python scripts/price_source_crosscheck.py --limit 50
    python scripts/price_source_crosscheck.py --symbols AAPL,MSFT,KO
    python scripts/price_source_crosscheck.py --dry-run          # print, don't write to data_patrol_log
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Close prices from two independently-parsed, split-adjusted sources for the same trading day
# should typically match almost exactly (prior one-off evaluation found a 0.0000% median diff)
# - a gap this wide most plausibly means a real vendor data error, wrong-day mismatch, or a
# split/dividend handling bug that survived the split-adjusted-view reconciliation above, not
# routine cross-vendor noise. Wide enough to tolerate normal end-of-day snapshot timing/rounding
# differences between vendors.
_DIVERGENCE_PCT = 1.0
_MAX_EXAMPLES = 15
_MAX_CONSECUTIVE_BAN_ERRORS = 3


def _select_symbols(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of active symbols with a recent stored price row."""
    cur.execute(
        """
        SELECT symbol FROM (
            SELECT DISTINCT pd.symbol
            FROM price_daily pd
            JOIN stock_symbols s ON s.symbol = pd.symbol AND s.active = true
            WHERE pd.date >= CURRENT_DATE - INTERVAL '7 days'
        ) candidates
        ORDER BY md5(symbol || CURRENT_DATE::text)
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _our_latest_value(cur: Any, symbol: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT date, close_adjusted, volume_adjusted, data_source
        FROM price_daily_split_adjusted
        WHERE symbol = %s
        ORDER BY date DESC
        LIMIT 1
        """,
        (symbol,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "date": row[0],
        "close_adjusted": float(row[1]) if row[1] is not None else None,
        "volume_adjusted": float(row[2]) if row[2] is not None else None,
        "data_source": row[3],
    }


def run(limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.data.source_router import DataSourceRouter
    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)
    router = DataSourceRouter()

    symbols = symbols_override or _select_symbols(cur, limit)
    logger.info(f"[PRICE_CROSSCHECK] Sampling {len(symbols)} symbol(s): {symbols}")

    flagged: list[dict[str, Any]] = []
    missing_source: list[dict[str, Any]] = []
    n_sampled = 0
    consecutive_ban_errors = 0

    for symbol in symbols:
        if consecutive_ban_errors >= _MAX_CONSECUTIVE_BAN_ERRORS:
            logger.warning(
                f"[PRICE_CROSSCHECK] {_MAX_CONSECUTIVE_BAN_ERRORS} consecutive shared-IP-ban "
                "errors - aborting the rest of this batch rather than spinning through it uselessly."
            )
            break

        ours = _our_latest_value(cur, symbol)
        if ours is None or ours["close_adjusted"] is None:
            continue

        if ours["data_source"] is None:
            missing_source.append({"symbol": symbol, "date": ours["date"].isoformat()})

        our_date = ours["date"]
        try:
            yf_rows = router.fetch_ohlcv(symbol, our_date, our_date)
            consecutive_ban_errors = 0
        except Exception as e:
            if "shared IP ban" in str(e) or "rate limited" in str(e).lower():
                consecutive_ban_errors += 1
            logger.debug(f"[PRICE_CROSSCHECK] {symbol} yfinance fetch failed (non-fatal): {e}")
            continue

        if not yf_rows or (isinstance(yf_rows, dict) and yf_rows.get("data_unavailable")):
            continue
        yf_row = yf_rows[0] if isinstance(yf_rows, list) else yf_rows
        if not isinstance(yf_row, dict) or yf_row.get("date") != our_date.isoformat():
            continue

        n_sampled += 1
        yf_close = float(yf_row["close"])
        our_close = ours["close_adjusted"]
        if yf_close == 0:
            continue
        pct_diff = abs(our_close - yf_close) / abs(yf_close) * 100.0
        if pct_diff <= _DIVERGENCE_PCT:
            continue
        flagged.append(
            {
                "symbol": symbol,
                "date": our_date.isoformat(),
                "our_close_adjusted": round(our_close, 4),
                "yfinance_close": round(yf_close, 4),
                "pct_diff": round(pct_diff, 4),
                "our_volume_adjusted": ours["volume_adjusted"],
                "yfinance_volume": yf_row.get("volume"),
            }
        )

    results: list[CheckResult] = []
    check_name = "price_source_independent_crosscheck"
    if flagged:
        results.append(
            CheckResult(
                check_name,
                "warn",
                "price_daily",
                f"{len(flagged)}/{n_sampled} symbol(s) with a comparable yfinance close diverge "
                f">{_DIVERGENCE_PCT:.1f}% from our split-adjusted stored close - review queue, "
                "not a confirmed bug: vendor snapshot timing, late corporate-action data, or a "
                "genuine data error can all produce this.",
                {"sampled": n_sampled, "flagged": len(flagged), "examples": flagged[:_MAX_EXAMPLES]},
            )
        )
    else:
        results.append(
            CheckResult(
                check_name,
                "info",
                "price_daily",
                f"no >{_DIVERGENCE_PCT:.1f}% yfinance close divergence found "
                f"({n_sampled} symbol(s) had a comparable yfinance value this run)",
            )
        )

    if missing_source:
        results.append(
            CheckResult(
                "price_source_missing_attribution",
                "info",
                "price_daily",
                f"{len(missing_source)} sampled symbol(s) have a NULL data_source on their latest "
                "price_daily row (pre-migration-1135 load, source unknown) - not itself an error, "
                "surfaced per steering/DATA_LOADERS.md's open question rather than silently dropped.",
                {"count": len(missing_source), "examples": missing_source[:_MAX_EXAMPLES]},
            )
        )

    if dry_run:
        for r in results:
            logger.info(f"[DRY-RUN] [{r.severity.upper()}] {r.check_name}: {r.message}")
    else:
        run_id = uuid.uuid4().hex
        patrol_logger = PatrolLogger(run_id)
        patrol_logger.log_results(cur, results)
        conn.commit()
        logger.info(f"[PRICE_CROSSCHECK] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {"sampled_symbols": len(symbols), "results": [r.to_dict() for r in results]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=25, help="How many symbols to sample this run (default 25)")
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument("--dry-run", action="store_true", help="Print findings, don't write to data_patrol_log")
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(limit=args.limit, symbols_override=symbols_override, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(f"[PRICE_CROSSCHECK] Done in {elapsed:.1f}s - {summary['sampled_symbols']} symbol(s) sampled")


if __name__ == "__main__":
    main()
