#!/usr/bin/env python3
"""Live realized-IC monitor for stock_scores - the missing feedback loop for this repo's
scoring methodology.

Added 2026-09-12 (goal session: "question everything about our scoring methodology"). Every
existing validation of the composite/pillar scores (fama_macbeth_*.py, the backtest scripts
under algo/research/) is a one-off OFFLINE test against historical data. None of them answer
the question that actually matters once a score is live: is it still predicting anything, on an
ongoing basis, in the real, currently-scored universe? Nothing in this repo tracked that before
this script - confirmed via repo-wide grep for realized_ic/walk_forward/live_ic/
out_of_sample_monitor/score_performance_monitor, zero hits.

`stock_scores_history` (migration/loader already exists, daily snapshot since 2026-08-24) has
exactly the raw material needed and was simply never queried for this. For each historical
score_date old enough that `horizon_trading_days` have since elapsed, this script computes the
Spearman rank correlation ("Information Coefficient") between each score column as of that date
and each symbol's actual subsequent return - the same statistic institutional multi-factor shops
track continuously to catch a factor's real-world decay before it compounds into losses. Results
accumulate in `score_realized_ic_log` (migration 1280) so a trend becomes visible over many runs,
the same accumulates-over-time posture as xbrl_yfinance_crosscheck.py's rotating sample.

Known limitation, disclosed not hidden: `stock_scores_history` only goes back to 2026-08-24 as of
this script's creation - there are not yet enough elapsed trading days for the longer horizons to
produce any rows, and even the horizons that do produce rows rest on a small number of score_dates
so far. This script's value is in existing and accumulating from today forward, not in producing a
verdict on day one. Treat early runs as instrumentation coming online, not evidence of anything.

Usage:
    python scripts/score_realized_ic_monitor.py                  # compute + log all new IC points
    python scripts/score_realized_ic_monitor.py --horizons 5,10   # only these horizons (trading days)
    python scripts/score_realized_ic_monitor.py --dry-run         # print, don't write anywhere
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

SCORE_COLUMNS = ["composite_score", "momentum_score", "quality_score", "growth_score", "value_score", "risk_score"]
DEFAULT_HORIZONS = [5, 10, 20]
_MIN_SYMBOLS_FOR_IC = 30


def _fetch_score_dates(cur: Any) -> list[Any]:
    cur.execute("SELECT DISTINCT score_date FROM stock_scores_history ORDER BY score_date")
    return [row[0] for row in cur.fetchall()]


def _fetch_trading_days(cur: Any, start_date: Any, end_date: Any) -> list[Any]:
    """Distinct trading days actually present in price_daily, used to step forward by
    `horizon` TRADING days (not calendar days - weekends/holidays would otherwise silently
    shrink the realized horizon)."""
    cur.execute(
        "SELECT DISTINCT date FROM price_daily WHERE date >= %s AND date <= %s ORDER BY date",
        (start_date, end_date),
    )
    return [row[0] for row in cur.fetchall()]


def _fetch_prices(cur: Any, symbols: list[str], dates: list[Any]) -> dict[tuple[str, Any], float]:
    if not symbols or not dates:
        return {}
    cur.execute(
        """
        SELECT symbol, date, COALESCE(adj_close, close) AS px
        FROM price_daily
        WHERE symbol = ANY(%s) AND date = ANY(%s) AND COALESCE(adj_close, close) > 0
          AND COALESCE(data_unavailable, false) = false
        """,
        (symbols, dates),
    )
    return {(row[0], row[1]): float(row[2]) for row in cur.fetchall()}


def _fetch_already_logged(cur: Any) -> set[tuple[Any, int]]:
    """(score_date, horizon) pairs that already have a log row for every score column - skip
    recomputing these on subsequent runs so cost stays O(new score_dates), not O(all history).
    A pair with a PARTIAL set of columns (e.g. a prior run crashed mid-horizon) is intentionally
    NOT considered done, so it gets picked back up and completed."""
    cur.execute("SELECT score_date, horizon_trading_days, count(*) FROM score_realized_ic_log GROUP BY 1, 2")
    return {(row[0], row[1]) for row in cur.fetchall() if row[2] >= len(SCORE_COLUMNS)}


def _fetch_scores(cur: Any, score_date: Any) -> dict[str, dict[str, float]]:
    cur.execute(
        f"SELECT symbol, {', '.join(SCORE_COLUMNS)} FROM stock_scores_history WHERE score_date = %s",
        (score_date,),
    )
    out: dict[str, dict[str, float]] = {}
    for row in cur.fetchall():
        symbol = row[0]
        out[symbol] = {col: float(row[i + 1]) for i, col in enumerate(SCORE_COLUMNS) if row[i + 1] is not None}
    return out


def run(horizons: list[int], dry_run: bool) -> dict[str, Any]:
    from scipy import stats as scipy_stats

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor()

    score_dates = _fetch_score_dates(cur)
    if not score_dates:
        logger.warning("[SCORE_IC_MONITOR] stock_scores_history is empty - nothing to compute")
        return {"points_computed": 0, "points_skipped_insufficient_data": 0}

    trading_days = _fetch_trading_days(cur, score_dates[0], score_dates[-1])
    trading_day_index = {d: i for i, d in enumerate(trading_days)}
    already_logged = _fetch_already_logged(cur)

    computed = 0
    skipped = 0
    logged_points: list[dict[str, Any]] = []

    for score_date in score_dates:
        start_idx = trading_day_index.get(score_date)
        if start_idx is None:
            skipped += 1
            continue
        scores: dict[str, dict[str, float]] | None = None  # lazily fetched, only if a horizon needs it

        for horizon in horizons:
            if (score_date, horizon) in already_logged:
                continue
            end_idx = start_idx + horizon
            if end_idx >= len(trading_days):
                skipped += 1
                continue
            if scores is None:
                scores = _fetch_scores(cur, score_date)
                if not scores:
                    break
            symbols = list(scores.keys())
            future_date = trading_days[end_idx]

            prices = _fetch_prices(cur, symbols, [score_date, future_date])
            fwd_ret: dict[str, float] = {}
            for symbol in symbols:
                p0 = prices.get((symbol, score_date))
                p1 = prices.get((symbol, future_date))
                if p0 and p1:
                    fwd_ret[symbol] = p1 / p0 - 1.0

            for score_name in SCORE_COLUMNS:
                paired = [
                    (scores[s][score_name], fwd_ret[s]) for s in symbols if s in fwd_ret and score_name in scores[s]
                ]
                if len(paired) < _MIN_SYMBOLS_FOR_IC:
                    skipped += 1
                    continue
                score_vals, ret_vals = zip(*paired, strict=True)
                ic, _p = scipy_stats.spearmanr(score_vals, ret_vals)
                logged_points.append(
                    {
                        "score_date": score_date,
                        "horizon_trading_days": horizon,
                        "score_name": score_name,
                        "ic": None if ic != ic else round(float(ic), 5),  # NaN guard (ic != ic iff NaN)
                        "n_symbols": len(paired),
                    }
                )
                computed += 1

    if dry_run:
        for pt in logged_points:
            logger.info(f"[DRY-RUN] {pt}")
    else:
        for pt in logged_points:
            cur.execute(
                """
                INSERT INTO score_realized_ic_log (score_date, horizon_trading_days, score_name, ic, n_symbols)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (score_date, horizon_trading_days, score_name)
                DO UPDATE SET ic = EXCLUDED.ic, n_symbols = EXCLUDED.n_symbols, computed_at = CURRENT_TIMESTAMP
                """,
                (pt["score_date"], pt["horizon_trading_days"], pt["score_name"], pt["ic"], pt["n_symbols"]),
            )

        # Trailing-average summary per (score_name, horizon) as an info/warn note in the same
        # data_patrol_review triage workflow every other DataPatrol check uses - not a pass/fail
        # gate (too little history yet for that), just visibility that this is running and what
        # it currently shows.
        results: list[CheckResult] = []
        for score_name in SCORE_COLUMNS:
            for horizon in horizons:
                cur.execute(
                    """
                    SELECT avg(ic), count(*), min(score_date), max(score_date)
                    FROM score_realized_ic_log WHERE score_name = %s AND horizon_trading_days = %s
                    """,
                    (score_name, horizon),
                )
                avg_ic, n_points, min_date, max_date = cur.fetchone()
                if n_points == 0 or avg_ic is None:
                    continue
                severity = "warn" if n_points >= 10 and avg_ic < 0 else "info"
                results.append(
                    CheckResult(
                        f"realized_ic_{score_name}_{horizon}d",
                        severity,
                        "stock_scores_history",
                        f"{score_name} {horizon}-trading-day realized IC trailing avg={avg_ic:.4f} "
                        f"over {n_points} date(s) ({min_date} to {max_date})"
                        + (" - persistently negative, review" if severity == "warn" else " - accumulating history"),
                        {"avg_ic": float(avg_ic), "n_points": n_points},
                    )
                )
        if results:
            run_id = uuid.uuid4().hex
            PatrolLogger(run_id).log_results(cur, results)
        conn.commit()
        logger.info(f"[SCORE_IC_MONITOR] Logged {len(results)} summary result(s) to data_patrol_log")

    cur.close()
    conn.close()
    return {"points_computed": computed, "points_skipped_insufficient_data": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--horizons", default="5,10,20", help="Comma-separated forward horizons in trading days")
    parser.add_argument("--dry-run", action="store_true", help="Print computed IC points, don't write anywhere")
    args = parser.parse_args()

    horizons = [int(h.strip()) for h in args.horizons.split(",")]

    started = time.monotonic()
    summary = run(horizons=horizons, dry_run=args.dry_run)
    elapsed = time.monotonic() - started
    logger.info(
        f"[SCORE_IC_MONITOR] Done in {elapsed:.1f}s - {summary['points_computed']} IC point(s) computed, "
        f"{summary['points_skipped_insufficient_data']} skipped (insufficient data)"
    )


if __name__ == "__main__":
    main()
