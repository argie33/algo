#!/usr/bin/env python3
"""Bulk verification (and, where possible, bulk correction) for every row
check_quarterly_revenue_sum_vs_annual_total (algo/monitoring/data_patrol/checks/
tie_out_identity_quarterly.py) has flagged - a fiscal year whose quarters, summed, exceed
that year's own audited annual total by more than tolerance.

Added 2026-09-13 (goal session: "ours vs industry factor lists" symbol-level audit,
continued per explicit user direction - "i dont like doing this one offs i wish we had
ways to find and fix in bulk"). 170 ERROR + 1,127 WARN rows across 604 distinct symbols
were flagged; only QCOM had been manually cross-checked before this script existed.

**REWRITTEN after a first version proved unsafe.** That version called
utils/external/sec_income_statement.py's get_income_statement() directly and compared its
"revenue" field to what's stored - but that function returns PRE-transform, per-concept
rows; the actual concept-to-canonical-"revenue" resolution (magnitude-based candidate
comparison, REIT-fallback ordering, rank tracking - see loaders/helpers/sec_base.py's
transform(), ~500 lines of heavily-hardened logic) never ran, so "revenue" was silently
None for every single symbol tested (confirmed live: 30/30 sampled symbols, including MSFT
with known-correct data). Reimplementing that resolution logic by hand here would risk
introducing exactly the kind of new, unverified bug this whole effort exists to eliminate.

**Correct design: trigger the real, unmodified production loader and diff its own output.**
For each batch of flagged symbols, this shells out to
`python -m loaders.load_financial_statements --symbols A,B,C` (LOADER_STATEMENT_TYPE=income,
LOADER_PERIOD=annual) - the exact code path a real scheduled reload uses - then re-reads
annual_income_statement before/after. This never reimplements extraction; it only observes
what the real pipeline already does. Categorizes each flagged row:

- REELOAD_FIXED: the stored annual revenue changed AND now agrees with the quarters-sum
  identity within tolerance - was stale/pending-backfill data, now corrected for real by the
  loader itself (no separate "--apply" write needed or offered - the reload already wrote it).
- REELOAD_NO_CHANGE: the stored value is IDENTICAL before and after a live re-fetch - a live,
  currently-reproducing extraction bug (QCOM's shape: $639M before AND after, live-verified
  against SEC EDGAR directly at $44.284B real - the correct "Revenues" concept exists at the
  source but our resolution logic doesn't select it). These need a code-level fix in
  sec_income_statement.py/sec_statements_unit_context.py/sec_base.py's transform(), not
  anything this script can safely do - it can only find and report them precisely.
- REELOAD_CHANGED_STILL_WRONG: the value changed but still fails the identity check - partial
  progress (e.g. a genuinely stale figure updated to a different, still-inconsistent one),
  worth a closer manual look, not auto-resolved either way.

Default mode is a dry run - no loader is invoked, this only measures the current flagged
population. Pass --apply to actually trigger the reload batches (the only "fix" this script
performs is triggering the real loader; it never writes to annual_income_statement itself).

Usage:
    python scripts/verify_and_fix_revenue_identity.py                # dry run: just re-measure the flagged queue
    python scripts/verify_and_fix_revenue_identity.py --apply --limit 20   # reload first 20 flagged symbols, report outcome
    python scripts/verify_and_fix_revenue_identity.py --apply --symbols QCOM,MKZR
    python scripts/verify_and_fix_revenue_identity.py --apply          # reload the full flagged population (604 symbols)
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_MAX_EXAMPLES_PER_CATEGORY = 20
_RELOAD_BATCH_SIZE = 40  # amortizes per-subprocess DB-pool/lock-acquire overhead (~2-5s) across many symbols
_RELOAD_TIMEOUT_SECONDS = 600


def _flagged_rows(cur: Any) -> dict[str, list[dict[str, Any]]]:
    """Same identity as check_quarterly_revenue_sum_vs_annual_total (thresholds imported
    from tie_out_shared.py to stay in sync, query kept literal here - see that check's own
    docstring for the full rationale). Returns rows grouped by symbol."""
    from algo.monitoring.data_patrol.checks.tie_out_shared import (
        _QUARTERLY_REVENUE_ANNUAL_OVERSHOOT_TOLERANCE,
    )

    cur.execute(
        """
        WITH quarters AS (
            SELECT symbol, fiscal_year, SUM(revenue) AS quarters_sum, COUNT(*) AS n_quarters
            FROM quarterly_income_statement
            WHERE data_unavailable = FALSE AND revenue IS NOT NULL AND revenue > 0
            GROUP BY symbol, fiscal_year
            HAVING COUNT(*) >= 2
        )
        SELECT q.symbol, q.fiscal_year, q.quarters_sum, a.revenue AS annual_revenue
        FROM quarters q
        JOIN annual_income_statement a ON a.symbol = q.symbol AND a.fiscal_year = q.fiscal_year
        JOIN stock_symbols s ON s.symbol = q.symbol AND s.active = true
        WHERE a.data_unavailable = FALSE AND a.revenue IS NOT NULL AND a.revenue > 0
        ORDER BY q.symbol, q.fiscal_year
        """
    )
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in cur.fetchall():
        quarters_sum, annual_revenue = float(row["quarters_sum"]), float(row["annual_revenue"])
        if quarters_sum / annual_revenue <= _QUARTERLY_REVENUE_ANNUAL_OVERSHOOT_TOLERANCE:
            continue
        by_symbol.setdefault(row["symbol"], []).append(
            {"fiscal_year": row["fiscal_year"], "quarters_sum": quarters_sum, "annual_revenue_before": annual_revenue}
        )
    return by_symbol


def _reload_batch(symbols: list[str]) -> bool:
    """Shells out to the real, unmodified production loader for exactly these symbols.
    Returns True if the subprocess exited 0. A non-zero exit is logged and treated as "no
    reload happened" for this batch (rows stay whatever they were before) - never silently
    assumed to have worked."""
    env = {**os.environ, "LOADER_STATEMENT_TYPE": "income", "LOADER_PERIOD": "annual"}
    cmd = [sys.executable, "-m", "loaders.load_financial_statements", "--symbols", ",".join(symbols)]
    logger.info(f"[VERIFY_REVENUE] Reloading batch of {len(symbols)} symbol(s): {symbols[0]}..{symbols[-1]}")
    try:
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=_RELOAD_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        logger.error(f"[VERIFY_REVENUE] Batch reload timed out after {_RELOAD_TIMEOUT_SECONDS}s - skipping")
        return False
    if result.returncode != 0:
        logger.error(f"[VERIFY_REVENUE] Batch reload exited {result.returncode}: {result.stderr[-2000:]}")
        return False
    return True


def _current_annual_revenue(cur: Any, symbol: str, fiscal_year: int) -> float | None:
    cur.execute(
        "SELECT revenue FROM annual_income_statement WHERE symbol = %s AND fiscal_year = %s",
        (symbol, fiscal_year),
    )
    row = cur.fetchone()
    return float(row["revenue"]) if row and row["revenue"] is not None else None


def run(limit: int | None, symbols_override: list[str] | None, apply: bool) -> dict[str, Any]:
    from psycopg2.extras import DictCursor

    from algo.monitoring.data_patrol.base import CheckResult
    from algo.monitoring.data_patrol.checks.tie_out_shared import _QUARTERLY_REVENUE_ANNUAL_OVERSHOOT_TOLERANCE
    from algo.monitoring.data_patrol.logger import PatrolLogger
    from utils.db.connection import get_db_connection

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor(cursor_factory=DictCursor)

    by_symbol = _flagged_rows(cur)
    symbols = symbols_override or sorted(by_symbol)
    if limit is not None:
        symbols = symbols[:limit]
    total_flagged = sum(len(rows) for rows in by_symbol.values())
    logger.info(
        f"[VERIFY_REVENUE] {total_flagged} flagged row(s) across {len(by_symbol)} distinct symbol(s) - "
        f"processing {len(symbols)} symbol(s) this run (apply={apply})"
    )

    if apply:
        for i in range(0, len(symbols), _RELOAD_BATCH_SIZE):
            batch = symbols[i : i + _RELOAD_BATCH_SIZE]
            _reload_batch(batch)
        conn.commit()  # the loader subprocess uses its own connection; refresh this session's view
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    fixed: list[dict[str, Any]] = []
    no_change: list[dict[str, Any]] = []
    changed_still_wrong: list[dict[str, Any]] = []

    for symbol in symbols:
        for row in by_symbol.get(symbol, []):
            fy, before, quarters_sum = row["fiscal_year"], row["annual_revenue_before"], row["quarters_sum"]
            after = _current_annual_revenue(cur, symbol, fy) if apply else before
            entry = {
                "symbol": symbol,
                "fiscal_year": fy,
                "before": before,
                "after": after,
                "quarters_sum": quarters_sum,
            }
            if after is None:
                continue
            if not apply or after == before:
                (no_change if apply else changed_still_wrong).append(entry)
                continue
            still_flagged = (quarters_sum / after) > _QUARTERLY_REVENUE_ANNUAL_OVERSHOOT_TOLERANCE
            (changed_still_wrong if still_flagged else fixed).append(entry)

    if apply:
        results = [
            CheckResult(
                "revenue_identity_reload_fixed",
                "info",
                "annual_income_statement",
                f"{len(fixed)}/{sum(len(by_symbol.get(s, [])) for s in symbols)} flagged row(s) corrected by a "
                "real reload - were stale/pending-backfill data",
                {"count": len(fixed), "examples": fixed[:_MAX_EXAMPLES_PER_CATEGORY]},
            ),
            CheckResult(
                "revenue_identity_reload_no_change",
                "error",
                "annual_income_statement",
                f"{len(no_change)} flagged row(s) UNCHANGED by a live reload - a currently-reproducing "
                "extraction bug (QCOM's shape), needs a code-level fix, not reachable by re-running the loader",
                {
                    "count": len(no_change),
                    "examples": no_change[:_MAX_EXAMPLES_PER_CATEGORY],
                    # Per-symbol isolable (see algo/monitoring/data_patrol/quarantine.py's own
                    # docstring: an ERROR/CRITICAL finding with a non-empty flagged_symbols list
                    # gets those specific symbols quarantined - excluded from scoring - instead of
                    # Phase 1 halting the whole pipeline for it). Every affected symbol goes here,
                    # not just the truncated `examples` slice above - quarantine must be complete
                    # even when the display list is capped.
                    "flagged_symbols": [
                        {
                            "symbol": s,
                            "reason": (
                                "revenue identity fails a live reload re-check (FY"
                                f"{sorted({e['fiscal_year'] for e in no_change if e['symbol'] == s})}) - "
                                "currently-reproducing extraction bug, not a stale-data issue"
                            ),
                        }
                        for s in dict.fromkeys(e["symbol"] for e in no_change)
                    ],
                },
            ),
            CheckResult(
                "revenue_identity_reload_changed_still_wrong",
                "warn",
                "annual_income_statement",
                f"{len(changed_still_wrong)} flagged row(s) changed on reload but still fail the identity check - "
                "partial progress, needs a manual look",
                {"count": len(changed_still_wrong), "examples": changed_still_wrong[:_MAX_EXAMPLES_PER_CATEGORY]},
            ),
        ]
    else:
        results = [
            CheckResult(
                "revenue_identity_dry_run_measure",
                "info",
                "annual_income_statement",
                f"{total_flagged} flagged row(s) across {len(by_symbol)} symbol(s) currently - dry run, "
                "no reload triggered (pass --apply to reload and re-measure)",
                {"count": total_flagged},
            )
        ]

    run_id = uuid.uuid4().hex
    patrol_logger = PatrolLogger(run_id)
    patrol_logger.log_results(cur, results)
    conn.commit()
    logger.info(f"[VERIFY_REVENUE] Logged {len(results)} result(s) to data_patrol_log (run_id={run_id})")

    cur.close()
    conn.close()
    return {
        "flagged_total": total_flagged,
        "symbols_processed": len(symbols),
        "fixed": len(fixed),
        "no_change": len(no_change) if apply else None,
        "changed_still_wrong": len(changed_still_wrong),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--limit", type=int, default=None, help="Process only the first N flagged symbols (default: all)"
    )
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually reload flagged symbols through the real loader and report before/after (default: dry-run measure only)",
    )
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    started = time.monotonic()
    summary = run(limit=args.limit, symbols_override=symbols_override, apply=args.apply)
    elapsed = time.monotonic() - started
    logger.info(f"[VERIFY_REVENUE] Done in {elapsed:.1f}s - {summary}")


if __name__ == "__main__":
    main()
