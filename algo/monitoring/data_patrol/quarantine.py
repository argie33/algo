#!/usr/bin/env python3
"""Per-symbol data-quality quarantine.

Bridges a DataPatrol check's per-symbol findings (e.g. ohlc_sanity's negative-price/
bad-high-low corruption) to `symbol_quarantine`, so Phase 1 can exclude just the
affected symbols from scoring/trading instead of halting the entire pipeline. See
migration 1277 for the schema and rationale.

A check opts in by putting a `flagged_symbols` list in its CheckResult.details:
    details = {"flagged_symbols": [{"symbol": "XYZ", "reason": "negative close price"}]}
Any CRIT/ERROR finding without a non-empty `flagged_symbols` list is NOT quarantinable -
Phase 1 halts the whole run for it, same as before this module existed. This is a
deliberate fail-safe default: a check must explicitly prove it knows exactly which
symbols are responsible before the blast radius shrinks from "whole pipeline" to
"those symbols".
"""

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


def apply_symbol_quarantine(
    cur: Any,
    check_name: str,
    severity: str,
    patrol_run_id: str,
    flagged_symbols: list[dict[str, Any]],
) -> None:
    """Record quarantine flags for this run's flagged symbols, resolving ALL of this
    check_name's prior open rows before inserting the current run's fresh set (supersede-
    on-reinsert, same lifecycle as PatrolLogger.log_results for data_patrol_log).

    FIXED 2026-09-13 (goal: patrol/quarantine comprehensiveness audit): this used to only
    resolve symbols that had DROPPED OFF the flagged list (`symbol != ALL(%s)`) - a symbol
    that stayed flagged run after run never got its prior open row resolved, so every run
    inserted ANOTHER open row for it instead of superseding. Live-verified: 567 duplicate
    open rows for the same 81 symbols under quarterly_revenue_sum_vs_annual_extreme (7 open
    rows each, one per patrol run since it started firing) and 30 for ohlc_sanity's newly
    re-flagged batch after just 2 runs. Now unconditionally resolves every open row for
    this check_name first, then inserts one fresh row per currently-flagged symbol -
    exactly mirroring data_patrol_log's own resolve-then-insert pattern instead of the
    narrower "only resolve what's no longer flagged" logic that let persistent findings
    accumulate unboundedly.
    """
    symbols = [f["symbol"] for f in flagged_symbols if f.get("symbol")]
    try:
        cur.execute(
            """
            UPDATE symbol_quarantine
            SET resolved_at = CURRENT_TIMESTAMP
            WHERE resolved_at IS NULL AND check_name = %s
            """,
            (check_name,),
        )
        if symbols:
            cur.executemany(
                """
                INSERT INTO symbol_quarantine
                  (symbol, check_name, severity, reason, patrol_run_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (f["symbol"], check_name, severity, f.get("reason", check_name), patrol_run_id)
                    for f in flagged_symbols
                    if f.get("symbol")
                ],
            )
        _sync_stock_scores_exclusion(cur, check_name, symbols)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Failed to apply symbol quarantine for {check_name}: {e}") from e


def _sync_stock_scores_exclusion(cur: Any, check_name: str, currently_flagged: list[str]) -> None:
    """Mirror symbol_quarantine into stock_scores.data_unavailable, reusing the existing
    trading-exclusion convention (GOVERNANCE.md: data_unavailable symbols are excluded from
    scoring/trading) instead of adding a second, parallel exclusion mechanism.

    Only touches rows this module itself marked (`reason` prefixed 'quarantined:') so it can
    never clobber a data_unavailable reason set by the scoring loader itself for an unrelated
    cause (e.g. insufficient metric coverage).
    """
    if currently_flagged:
        cur.execute(
            """
            UPDATE stock_scores
            SET data_unavailable = TRUE, reason = %s
            WHERE symbol = ANY(%s)
            """,
            (f"quarantined: {check_name}", currently_flagged),
        )
    # Release symbols this check no longer flags, but only if no OTHER open flag (from this
    # or any other check) still applies to them.
    cur.execute(
        """
        UPDATE stock_scores
        SET data_unavailable = FALSE, reason = NULL
        WHERE reason = %s
          AND symbol != ALL(%s)
          AND NOT EXISTS (
              SELECT 1 FROM symbol_quarantine sq
              WHERE sq.symbol = stock_scores.symbol AND sq.resolved_at IS NULL
          )
        """,
        (f"quarantined: {check_name}", currently_flagged or [""]),
    )
