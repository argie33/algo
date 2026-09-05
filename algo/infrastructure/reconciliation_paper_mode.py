#!/usr/bin/env python3
"""PAPER-MODE (self.broker is None) RECONCILIATION HELPERS

Pure extract-method split of `DailyReconciliation.run_daily_reconciliation()` (see that
module's docstring/class docstring for the overall contract). This file holds the tail of
the `if self.broker is None:` branch - everything after the LOCAL_MODE guard and the
resolve_local_pending_exits()/backfill_all_trade_metrics() calls, which stay inline in
run_daily_reconciliation() itself (several regression tests do whitebox source-text
scanning of that exact branch - see test_reconciliation_mfe_mae_backfill_wired_paper_mode_20260824.py
and test_reconciliation_auto_mode_reason_key.py - so this split preserves those literal
call sites in the owner module and only extracts the remaining computation/write/verify
steps here).

NO BEHAVIOR CHANGE: every method here is a verbatim relocation of code that used to live
inline in run_daily_reconciliation()'s `if self.broker is None:` branch - control flow,
thresholds, log messages, SQL, and return values are unchanged. Comments documenting
non-obvious business logic (fix-history notes, migration references) moved verbatim with
the code they describe.

Mixed into DailyReconciliation via multiple inheritance - `self.config` resolves normally
through the instance regardless of which file defines the method.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date_type
from datetime import datetime, timezone
from typing import Any

from algo.config.credential_manager import get_algo_owner_cognito_sub
from algo.infrastructure.reconciliation_shared import compute_adjusted_drawdown
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


@dataclass
class PaperModeState:
    """Everything computed while gathering paper-mode (broker=None) reconciliation inputs,
    threaded from `_paper_mode_compute_state` into `_paper_mode_write_snapshot` and
    `_paper_mode_final_verification`. One field per named local variable the original
    inline code carried across this same span - see the methods below for the rationale
    behind each.
    """

    reconcile_date: _date_type
    open_position_count: int
    total_unrealized_pnl: float
    total_invested: float
    total_cost_basis: float
    realized_pnl_today: float
    initial_capital: float
    baseline_equity: float
    prev_unrealized_pnl: float
    unrealized_pnl_change: float
    portfolio_value: float


@dataclass
class PaperModeSnapshotWrite:
    """Values computed inside `_paper_mode_write_snapshot` that the caller needs afterward
    (for the final result dict) beyond what's already in `PaperModeState`."""

    cash_remaining: float
    cumulative_return_pct: float


class PaperModeReconciliationMixin:
    """Mixin providing the broker=None (paper/local-mode) tail of run_daily_reconciliation().

    `_finish_paper_mode_reconciliation` is the entry point called by
    `run_daily_reconciliation()` right after the resolve_local_pending_exits()/
    backfill_all_trade_metrics() calls that must stay inline there.
    """

    config: dict[str, Any]

    def _finish_paper_mode_reconciliation(self, reconcile_date: _date_type | None) -> dict[str, Any]:
        state = self._paper_mode_compute_state(reconcile_date)
        write = self._paper_mode_write_snapshot(state)
        final_verification_failed, final_verification_detail = self._paper_mode_final_verification(state)

        result: dict[str, Any] = {
            "success": True,
            "positions": state.open_position_count,
            "portfolio_value": state.portfolio_value,
            "position_value": float(state.total_invested),
            "unrealized_pnl": state.total_unrealized_pnl,
            "cash_remaining": float(write.cash_remaining),
            "cumulative_return_pct": write.cumulative_return_pct,
            "reason": "Reconciliation skipped: using database state (broker credentials unavailable, paper trading mode)",
        }
        if final_verification_failed:
            result["final_verification_failed"] = True
            result["final_verification_detail"] = final_verification_detail
        return result

    def _paper_mode_compute_state(self, reconcile_date: _date_type | None) -> PaperModeState:
        # Query actual positions and portfolio value from database instead of hardcoding
        with DatabaseContext("read") as cur:
            # Count open positions
            cur.execute("SELECT COUNT(*) as open_count FROM algo_positions WHERE status = 'open'")
            position_row = cur.fetchone()
            if position_row is None:
                raise RuntimeError(
                    "[CRITICAL] Position count query returned no rows. "
                    "COUNT(*) should always return a result. This indicates database failure. "
                    "Check: (1) database connectivity, (2) algo_positions table exists"
                )
            open_position_count = position_row["open_count"]
            if open_position_count is None:
                raise RuntimeError(
                    "[CRITICAL] Position count is NULL. COUNT(*) should always return a numeric value. "
                    "Check database integrity."
                )

            # Calculate unrealized P&L from positions (both real and paper)
            cur.execute("""
                SELECT COUNT(*) as position_count,
                       SUM(unrealized_pnl) as total_pnl,
                       SUM(position_value) as total_invested,
                       SUM(quantity * avg_entry_price) as total_cost_basis
                FROM algo_positions
                WHERE status = 'open'
            """)
            pnl_row = cur.fetchone()
            if pnl_row is None:
                raise RuntimeError(
                    "[CRITICAL] Paper mode reconciliation query returned no rows. "
                    "Cannot calculate portfolio state without database access. "
                    "Check: (1) database connectivity, (2) algo_positions table exists"
                )

            position_count = pnl_row["position_count"]
            if position_count == 0:
                total_unrealized_pnl = 0.0
                total_invested = 0.0
                total_cost_basis = 0.0
                logger.debug("[RECONCILIATION] No open positions - unrealized P&L = 0")
            elif position_count > 0:
                # Positions exist - all three aggregates must return non-NULL (data integrity check)
                if (
                    pnl_row["total_pnl"] is None
                    or pnl_row["total_invested"] is None
                    or pnl_row["total_cost_basis"] is None
                ):
                    missing_fields = [
                        f for f in ["total_pnl", "total_invested", "total_cost_basis"] if pnl_row[f] is None
                    ]
                    raise RuntimeError(
                        f"[CRITICAL] {position_count} open positions exist but SUM aggregation failed on: {missing_fields}. "
                        "This indicates data corruption (NULL/invalid values in position fields). "
                        f"Check algo_positions records for data integrity issues: {missing_fields}"
                    )
                total_unrealized_pnl = float(pnl_row["total_pnl"])
                total_invested = float(pnl_row["total_invested"])
                total_cost_basis = float(pnl_row["total_cost_basis"])
            else:
                # Impossible case (negative position count), but catch it explicitly
                raise RuntimeError(
                    f"[CRITICAL] Position count query returned impossible result: {position_count}. "
                    "Database query error or corruption."
                )

            # Write portfolio snapshot even in paper mode for position monitor and dashboard
            if not reconcile_date:
                reconcile_date = datetime.now(timezone.utc).date()

            # CRITICAL: Realized P&L must be scoped to trades closed TODAY, not summed over all
            # of algo_trades history (see baseline roll-forward comment below for why an all-time
            # SUM() is the wrong quantity to add to a baseline that itself already reflects all
            # prior realized P&L). Closed trades with NULL profit_loss_dollars (pending broker
            # fill reconciliation - see phase9_reconciliation.py, which deliberately leaves this
            # NULL rather than fabricate a $0 P&L) are excluded by SUM() the same way the
            # roll-forward baseline comment below describes: that day's nudge is zero, not an error.
            #
            # BUG FOUND 2026-07-28: when EVERY closed trade that day was still pending (all NULL),
            # SUM() returns NULL for the whole aggregate (not "0 from N excluded rows" - Postgres
            # SUM() over an all-NULL group is NULL), and this used to be treated as indistinguishable
            # from real corruption, hard-erroring Phase 9 - live-reproduced: 9 closed trades on
            # 2026-07-27, all pending broker-fill confirmation, correctly excluded individually but
            # the all-NULL aggregate wrongly raised. Now distinguish "pending" (estimated_exit_price
            # IS NOT NULL - the documented marker for this exact state) from genuine corruption
            # (profit_loss_dollars NULL with no pending marker at all, which is still unexplained
            # and still raises).
            cur.execute(
                """
                SELECT COUNT(*) as closed_count,
                       SUM(profit_loss_dollars) as realized_pnl_today,
                       COUNT(*) FILTER (
                           WHERE profit_loss_dollars IS NULL AND estimated_exit_price IS NOT NULL
                       ) as pending_count,
                       COUNT(*) FILTER (
                           WHERE profit_loss_dollars IS NULL AND estimated_exit_price IS NULL
                       ) as corrupt_count
                FROM algo_trades
                WHERE status = 'closed' AND exit_date = %s
                """,
                (reconcile_date,),
            )
            realized_row = cur.fetchone()
            if realized_row is None:
                raise RuntimeError(
                    "[RECONCILIATION CRITICAL] Realized P&L query returned no rows. "
                    "Database query failed or table unavailable."
                )

            closed_count = realized_row["closed_count"]
            pending_count = realized_row["pending_count"]
            corrupt_count = realized_row["corrupt_count"]
            if closed_count == 0:
                realized_pnl_today = 0.0
                logger.debug(f"[RECONCILIATION] No closed trades on {reconcile_date} - realized P&L = 0")
            elif corrupt_count > 0:
                raise RuntimeError(
                    f"[RECONCILIATION CRITICAL] {corrupt_count}/{closed_count} closed trades on "
                    f"{reconcile_date} have NULL profit_loss_dollars with no estimated_exit_price "
                    "pending-reconciliation marker either. This indicates data corruption "
                    "(NULL/invalid values in profit_loss_dollars column). "
                    "Check algo_trades records for incomplete exit P&L reconciliation."
                )
            elif realized_row["realized_pnl_today"] is None:
                # All closed trades today are still pending broker-fill confirmation - not
                # corruption. Same zero-nudge treatment as the partial-pending case below.
                realized_pnl_today = 0.0
                logger.warning(
                    f"[RECONCILIATION] All {closed_count} closed trades on {reconcile_date} are "
                    "pending broker-fill confirmation (estimated_exit_price set, profit_loss_dollars "
                    "not yet known) - realized P&L for today recorded as $0 until "
                    "reconcile_exit_fills() resolves them."
                )
            else:
                realized_pnl_today = float(realized_row["realized_pnl_today"])
                if pending_count > 0:
                    logger.warning(
                        f"[RECONCILIATION] {pending_count}/{closed_count} closed trades on "
                        f"{reconcile_date} still pending broker-fill confirmation - realized P&L "
                        f"(${realized_pnl_today:.2f}) excludes them until reconcile_exit_fills() resolves them."
                    )

            # FIX: Provide default fallback for initial_capital_paper_trading in case config doesn't have it
            initial_capital = self.config.get("initial_capital_paper_trading")
            if initial_capital is None:
                raise RuntimeError(
                    "[RECONCILIATION] CRITICAL: initial_capital_paper_trading not configured. "
                    "Never assume default portfolio value ($100k). Set explicit value in algo_config table."
                )

            if not isinstance(initial_capital, (int, float)) or initial_capital <= 0:
                raise ValueError(
                    f"[CRITICAL] initial_capital_paper_trading must be positive number, got {initial_capital}. "
                    "Configuration must be valid. Check config values."
                )

            # CRITICAL: Roll FORWARD from the previously recorded snapshot instead of recomputing
            # an absolute value from initial_capital + all-time trade history. This account can
            # carry real equity history that predates (or falls outside) algo_trades' own P&L
            # tracking - e.g. migration 1112 found broker-confirmed equity of $72,029.10 that
            # SUM(algo_trades.profit_loss_dollars) has no way to reproduce, since it happened
            # before that ledger existed. Reconstructing "initial_capital + SUM(all closed
            # trades)" throws that real history away and snaps back to initial_capital the instant
            # algo_trades' own P&L data is incomplete (NULL, pending broker-fill reconciliation)
            # or simply doesn't cover the account's full history - this is the exact corruption
            # class of migration 1112 recurring in a new form (see migration 1127). Rolling
            # forward from the prior snapshot can never regress to a stale constant: each run only
            # nudges the last confirmed value by what changed since, so it is self-healing even if
            # a gap in algo_trades' knowledge (a NULL P&L trade) means that day's nudge is zero.
            cur.execute(
                """
                SELECT total_portfolio_value, unrealized_pnl_total FROM algo_portfolio_snapshots
                WHERE snapshot_date < %s
                ORDER BY snapshot_date DESC LIMIT 1
                """,
                (reconcile_date,),
            )
            prev_snapshot_row = cur.fetchone()
            if prev_snapshot_row and prev_snapshot_row["total_portfolio_value"] is not None:
                baseline_equity = float(prev_snapshot_row["total_portfolio_value"])
                prev_unrealized_pnl = (
                    float(prev_snapshot_row["unrealized_pnl_total"])
                    if prev_snapshot_row["unrealized_pnl_total"] is not None
                    else 0.0
                )
            else:
                # Bootstrap: no prior snapshot exists at all - initial_capital is the only
                # reference point available.
                baseline_equity = float(initial_capital)
                prev_unrealized_pnl = 0.0

            unrealized_pnl_change = total_unrealized_pnl - prev_unrealized_pnl
            portfolio_value = baseline_equity + realized_pnl_today + unrealized_pnl_change

            logger.info(
                f"[RECONCILIATION PAPER MODE] Found {open_position_count} open positions, "
                f"baseline: ${baseline_equity:.2f}, realized P&L today: ${realized_pnl_today:.2f}, "
                f"unrealized P&L change: ${unrealized_pnl_change:+.2f} (now ${total_unrealized_pnl:.2f}), "
                f"portfolio value: ${portfolio_value:.2f}"
            )

        return PaperModeState(
            reconcile_date=reconcile_date,
            open_position_count=open_position_count,
            total_unrealized_pnl=total_unrealized_pnl,
            total_invested=total_invested,
            total_cost_basis=total_cost_basis,
            realized_pnl_today=realized_pnl_today,
            initial_capital=float(initial_capital),
            baseline_equity=baseline_equity,
            prev_unrealized_pnl=prev_unrealized_pnl,
            unrealized_pnl_change=unrealized_pnl_change,
            portfolio_value=portfolio_value,
        )

    def _paper_mode_write_snapshot(self, state: PaperModeState) -> PaperModeSnapshotWrite:
        reconcile_date = state.reconcile_date
        open_position_count = state.open_position_count
        total_unrealized_pnl = state.total_unrealized_pnl
        total_invested = state.total_invested
        portfolio_value = state.portfolio_value
        baseline_equity = state.baseline_equity
        initial_capital = state.initial_capital

        try:
            logger.info(
                f"[RECONCILIATION] Paper mode: About to write snapshot for {reconcile_date} with {open_position_count} positions"
            )
            with DatabaseContext("write") as cur:
                logger.info("[RECONCILIATION] Paper mode: DatabaseContext opened, role=write")
                # Cash = total account value minus what's tied up in the cost basis of currently
                # open positions. Derived from the rolled-forward portfolio_value (never hardcoded
                # or recomputed from initial_capital) so it stays consistent with it by construction.
                cash_remaining = portfolio_value - total_invested

                # CRITICAL: Portfolio value must be positive for valid reconciliation
                if portfolio_value <= 0:
                    raise ValueError(
                        f"[CRITICAL] Portfolio value is ${portfolio_value:.2f}. "
                        f"Cannot create snapshot with zero or negative portfolio. "
                        f"Check: (1) initial_capital_paper_trading is positive, "
                        f"(2) position values in database are correct"
                    )

                # Unrealized P&L % against the cost basis of open positions, NOT
                # initial_capital - matches the broker-available path below and the
                # per-position convention in algo_positions.unrealized_pnl_pct (see
                # position_analyzer.py). Dividing by initial_capital instead makes this
                # number drift from what "% unrealized on my open positions" should mean
                # any time initial_capital differs from what's actually invested right now.
                unrealized_pnl_pct = (
                    (total_unrealized_pnl / state.total_cost_basis * 100) if state.total_cost_basis > 0 else 0.0
                )

                # Calculate running peak and drawdown percentage
                # running_peak = maximum portfolio value seen up to this date
                # drawdown_pct = how far below peak the current portfolio is
                cur.execute(
                    """
                    SELECT MAX(total_portfolio_value)
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s
                """,
                    (reconcile_date,),
                )
                peak_result = cur.fetchone()
                # MAX(total_portfolio_value) returns a Decimal (NUMERIC column); portfolio_value
                # is a plain float computed above from baseline_equity/realized_pnl_today/
                # unrealized_pnl_change - subtracting Decimal - float below raises TypeError,
                # which the broad except a few lines down swallowed and logged, then fell
                # through to a return statement that crashed on cumulative_return_pct (assigned
                # further down, never reached) instead of surfacing this real error.
                running_peak = float(peak_result["max"]) if peak_result and peak_result["max"] else portfolio_value
                running_peak = max(running_peak, portfolio_value)  # Today's value is the new peak if higher

                drawdown_pct = 0.0
                if running_peak > 0:
                    drawdown_pct = ((running_peak - portfolio_value) / running_peak) * 100

                # Calculate position win/loss/breakeven counts from actual positions
                winning_count = 0
                losing_count = 0
                breakeven_count = 0
                if open_position_count > 0:
                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM algo_positions
                        WHERE status = 'open'
                        AND unrealized_pnl > 0
                    """)
                    winning_row = cur.fetchone()
                    winning_count = winning_row["count"] if winning_row else 0

                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM algo_positions
                        WHERE status = 'open'
                        AND unrealized_pnl < 0
                    """)
                    losing_row = cur.fetchone()
                    losing_count = losing_row["count"] if losing_row else 0

                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM algo_positions
                        WHERE status = 'open'
                        AND unrealized_pnl = 0
                    """)
                    breakeven_row = cur.fetchone()
                    breakeven_count = breakeven_row["count"] if breakeven_row else 0

                # CRITICAL: circuit_breaker.py::_check_daily_loss() reads daily_return_pct directly
                # from this table - it does not recompute it. Hardcoding this to 0.0 (as before)
                # silently disabled the Daily Loss Limit circuit breaker for every reconciliation
                # that goes through this LOCAL_MODE fallback path, since a fabricated 0.0% daily
                # return can never breach a negative threshold. Reuse baseline_equity (the same
                # prior-snapshot value portfolio_value was rolled forward from above) rather than
                # re-querying it - they are the same "previous total_portfolio_value" quantity.
                daily_return_pct = (
                    (portfolio_value - baseline_equity) / baseline_equity * 100 if baseline_equity > 0 else 0.0
                )

                # Cash-flow-adjusted equity/peak/drawdown (migration 1134): this LOCAL_MODE/paper
                # branch computed its own raw running_peak/drawdown_pct above but never called this
                # helper, so the four params below were referenced undefined (NameError on every
                # LOCAL_MODE reconciliation write). The non-LOCAL_MODE path further down (~line 1052)
                # already does this correctly - mirror it here.
                net_capital_flow_cum, adjusted_running_peak, adjusted_drawdown_pct = compute_adjusted_drawdown(
                    cur, reconcile_date, portfolio_value
                )
                adjusted_equity = portfolio_value - net_capital_flow_cum

                # Cumulative return against adjusted_equity (cash-flow-adjusted), NOT raw
                # portfolio_value: "total return since inception" should reflect trading
                # performance (realized + unrealized) relative to starting capital, not be
                # inflated/deflated by deposits and withdrawals along the way - the same
                # migration 1134 rationale already applied to drawdown/daily-loss elsewhere
                # in this codebase (circuit_breaker.py, position_sizer.py). Also fixes a
                # second divergence: the non-LOCAL_MODE path below computed this from
                # realized-trades-only cumulative_pnl, excluding unrealized gains entirely -
                # "total return" should include both.
                cumulative_return_pct = (adjusted_equity - float(initial_capital)) / float(initial_capital) * 100

                # Calculate concentration metrics for paper mode
                # CRITICAL FIX: Use actual position data, not approximation
                # Previous: avg_position_size_pct = total_invested / portfolio_value was mathematically wrong
                # (this ratio represents cash allocation, not position concentration)
                largest_position_pct_paper = 0.0
                avg_position_size_pct_paper = 0.0

                if portfolio_value > 0 and open_position_count > 0:
                    # Query actual largest position as percentage of portfolio
                    # Use portfolio_value for consistency with cash/equity calculations
                    cur.execute(
                        """
                        SELECT MAX(position_value / %s * 100) as largest_pct,
                               AVG(position_value / %s * 100) as avg_pct
                        FROM algo_positions
                        WHERE status = 'open' AND quantity != 0
                    """,
                        (portfolio_value, portfolio_value),
                    )
                    conc_row = cur.fetchone()
                    if conc_row and conc_row[0] is not None:
                        largest_position_pct_paper = float(conc_row[0])
                        avg_position_size_pct_paper = (
                            float(conc_row[1]) if conc_row[1] else (100.0 / open_position_count)
                        )
                        logger.debug(
                            f"[RECONCILIATION] Paper mode concentration metrics: "
                            f"portfolio_value=${portfolio_value:.2f}, "
                            f"largest_pct={largest_position_pct_paper:.2f}%, "
                            f"avg_pct={avg_position_size_pct_paper:.2f}%"
                        )
                    else:
                        # Fallback: if query fails, use theoretical average (100% / position_count)
                        avg_position_size_pct_paper = 100.0 / open_position_count if open_position_count > 0 else 0.0
                        largest_position_pct_paper = (
                            100.0 / open_position_count
                        )  # Theoretical minimum for n equal positions, NOT average

                # Calculate Herfindahl index for concentration_risk_pct
                # This is the sum of squared position percentages (0-10000, where 10000 = single position)
                herfindahl_paper = 0.0
                if portfolio_value > 0:
                    cur.execute(
                        """
                        SELECT position_value / %s * 100
                        FROM algo_positions
                        WHERE status = 'open' AND quantity != 0
                    """,
                        (portfolio_value,),
                    )
                    for pos_row in cur.fetchall():
                        pct = float(pos_row[0])
                        herfindahl_paper += pct * pct

                snapshot_params = (
                    reconcile_date,
                    portfolio_value,
                    cash_remaining,  # THIS IS THE CORRECTED CASH VALUE
                    portfolio_value,
                    open_position_count,
                    largest_position_pct_paper,
                    avg_position_size_pct_paper,
                    herfindahl_paper,  # concentration_risk_pct (Herfindahl index)
                    state.realized_pnl_today,  # was hardcoded 0.0 - dashboard/reporting always showed $0 realized
                    total_unrealized_pnl,
                    unrealized_pnl_pct,
                    winning_count,
                    losing_count,
                    breakeven_count,
                    "open_positions_only",
                    0,
                    0,
                    daily_return_pct,
                    cumulative_return_pct,
                    0.0,
                    0.0,
                    "paper_mode",
                    drawdown_pct,
                    running_peak,
                    net_capital_flow_cum,
                    adjusted_equity,
                    adjusted_running_peak,
                    adjusted_drawdown_pct,
                    get_algo_owner_cognito_sub(),
                )
                logger.info(
                    f"[RECONCILIATION] Paper mode: INSERT params - date={reconcile_date}, positions={open_position_count}, portfolio_value={portfolio_value}, cash={cash_remaining}"
                )

                cur.execute(
                    """
                    INSERT INTO algo_portfolio_snapshots (
                        snapshot_date, total_portfolio_value, total_cash, total_equity,
                        position_count, largest_position_pct, average_position_size_pct,
                        concentration_risk_pct,
                        realized_pnl_today, unrealized_pnl_total, unrealized_pnl_pct,
                        unrealized_pnl_winning_count, unrealized_pnl_losing_count, unrealized_pnl_breakeven_count,
                        unrealized_pnl_source,
                        win_count_today, loss_count_today,
                        daily_return_pct, cumulative_return_pct, max_drawdown_pct,
                        sharpe_ratio, market_health_status, drawdown_pct, running_peak,
                        net_capital_flow_cum, adjusted_equity, adjusted_running_peak, adjusted_drawdown_pct,
                        cognito_sub, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (snapshot_date) DO UPDATE SET
                    total_portfolio_value = EXCLUDED.total_portfolio_value,
                    total_cash = EXCLUDED.total_cash,
                    total_equity = EXCLUDED.total_equity,
                    position_count = EXCLUDED.position_count,
                    realized_pnl_today = EXCLUDED.realized_pnl_today,
                    unrealized_pnl_total = EXCLUDED.unrealized_pnl_total,
                    unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                    unrealized_pnl_winning_count = EXCLUDED.unrealized_pnl_winning_count,
                    unrealized_pnl_losing_count = EXCLUDED.unrealized_pnl_losing_count,
                    unrealized_pnl_breakeven_count = EXCLUDED.unrealized_pnl_breakeven_count,
                    unrealized_pnl_source = EXCLUDED.unrealized_pnl_source,
                    daily_return_pct = EXCLUDED.daily_return_pct,
                    cumulative_return_pct = EXCLUDED.cumulative_return_pct,
                    max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                    drawdown_pct = EXCLUDED.drawdown_pct,
                    running_peak = EXCLUDED.running_peak,
                    net_capital_flow_cum = EXCLUDED.net_capital_flow_cum,
                    adjusted_equity = EXCLUDED.adjusted_equity,
                    adjusted_running_peak = EXCLUDED.adjusted_running_peak,
                    adjusted_drawdown_pct = EXCLUDED.adjusted_drawdown_pct,
                    updated_at = NOW()
                    """,
                    snapshot_params,
                )
                logger.info("[RECONCILIATION] Paper mode: INSERT executed successfully")

                # VERIFY the insert worked BEFORE exiting the transaction
                try:
                    cur.execute(
                        "SELECT position_count FROM algo_portfolio_snapshots WHERE snapshot_date = %s ORDER BY created_at DESC LIMIT 1",
                        (reconcile_date,),
                    )
                    verify_result = cur.fetchone()
                    if verify_result:
                        actual_count = verify_result["position_count"]
                        logger.info(
                            f"[RECONCILIATION] VERIFICATION: position_count={actual_count} (expected={open_position_count}) - MATCH={actual_count == open_position_count}"
                        )
                    else:
                        logger.error("[RECONCILIATION] VERIFICATION: No snapshot row found!")
                except Exception as verify_err:
                    logger.error(f"[RECONCILIATION] VERIFICATION QUERY FAILED: {verify_err}")

                logger.info("[RECONCILIATION] Exiting DatabaseContext to trigger COMMIT")
        except Exception as e:
            # Re-raise (don't swallow): this used to log-and-continue, falling through to the
            # `return {"success": True, ...}` below - which references cumulative_return_pct/
            # adjusted_equity/drawdown_pct etc. computed inside this same try block. Any
            # exception before those assignments turned a real, diagnosable error (e.g. a
            # Decimal/float TypeError) into a confusing UnboundLocalError, and even when the
            # exception happened late enough that every variable WAS defined, silently
            # continuing here means reporting "success": True for a reconciliation whose
            # portfolio-snapshot write had actually failed and rolled back.
            logger.error(f"[RECONCILIATION] Failed to write portfolio snapshot: {e}", exc_info=True)
            raise RuntimeError(f"[RECONCILIATION] Failed to write portfolio snapshot: {e}") from e

        return PaperModeSnapshotWrite(cash_remaining=cash_remaining, cumulative_return_pct=cumulative_return_pct)

    def _paper_mode_final_verification(self, state: PaperModeState) -> tuple[bool, str | None]:
        # FINAL VERIFICATION: Query immediately after context exit (after commit) to verify data persisted
        # CRITICAL: this can genuinely detect and log a real persistence failure (mismatch or
        # query error) - the return below used to ignore that outcome entirely and always
        # report "success": True, the exact same "log a real failure, report success anyway"
        # anti-pattern already fixed above (see the comment on the outer except at the top of
        # this write path) for the write itself. Post-commit, we can't roll back, but we can -
        # and must - stop silently claiming the snapshot is verified when it isn't.
        reconcile_date = state.reconcile_date
        open_position_count = state.open_position_count
        final_verification_failed = False
        final_verification_detail = None
        try:
            with DatabaseContext("read") as verify_ctx:
                verify_ctx.execute(
                    "SELECT position_count FROM algo_portfolio_snapshots WHERE snapshot_date = %s ORDER BY created_at DESC LIMIT 1",
                    (reconcile_date,),
                )
                verify_final = verify_ctx.fetchone()
                if verify_final and verify_final["position_count"] == open_position_count:
                    logger.info(
                        f"[RECONCILIATION] FINAL VERIFICATION SUCCESS: Snapshot persisted with position_count={verify_final['position_count']}"
                    )
                else:
                    actual = verify_final["position_count"] if verify_final else "NULL"
                    final_verification_failed = True
                    final_verification_detail = f"expected position_count={open_position_count}, got {actual}"
                    logger.error(
                        f"[RECONCILIATION] FINAL VERIFICATION FAILED: Expected position_count={open_position_count}, got {actual}"
                    )
        except Exception as final_verify_err:
            final_verification_failed = True
            final_verification_detail = f"verification query error: {final_verify_err}"
            logger.error(f"[RECONCILIATION] FINAL VERIFICATION ERROR: {final_verify_err}")

        return final_verification_failed, final_verification_detail
