from __future__ import annotations

import math
from datetime import date as _date
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

# See circuit_breaker_portfolio_risk.py's top-of-file comment for why this qualified
# `import ... as _cb` (not `from ... import _float, logger`) is used instead of a plain
# module-level import.
import algo.risk.circuit_breaker as _cb
from utils.trading import TradeStatus


class CircuitBreakerTradeSectorMixin:
    """Trade-history and sector-level risk circuit breakers: consecutive losses, rolling
    win-rate floor, sector position-count concentration (advisory), and cost-basis-weighted
    sector drawdown - split out of circuit_breaker.py's CircuitBreaker God-class (bloater
    decomposition, mechanical/no-behavior-change split, see git log 2026-09-05).

    Not usable standalone - relies on the `config` instance attribute and
    `_get_required_config` method defined on CircuitBreaker itself (same `config: Any`
    convention as algo/monitoring/position_order_management.py's PositionOrderManagementMixin;
    `_get_required_config` declared under TYPE_CHECKING only, see circuit_breaker_portfolio_risk.py).
    """

    config: Any

    if TYPE_CHECKING:

        def _get_required_config(self, key: str, context: str = ...) -> Any: ...

    def _check_consecutive_losses(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        # CRITICAL FIX: tiebreak was `id DESC` - id is the row's insertion order, which tracks
        # when the trade was ENTERED, not when it EXITED. Confirmed live against this DB that
        # this genuinely reorders same-exit_date trades differently from an exit_time-based
        # ordering (the convention _check_win_rate_floor already uses below for the identical
        # "most recent N closed trades" query). A day with 2+ exits could evaluate the
        # consecutive-loss streak against the wrong subset/order of trades. `id DESC` kept as a
        # final tiebreak (not the primary one) since exit_time is frequently NULL on this table
        # (several close paths didn't set it until this same fix round) and ORDER BY must stay
        # fully deterministic even when it is.
        # CRITICAL FIX: this query had no exclusion for non-representative closes, unlike
        # _check_win_rate_floor's identical "most recent N closed trades" query just below
        # (which already excludes reconciliation/force-close/delisted exit reasons as not
        # reflecting real strategy performance). Confirmed live 2026-07-27: a since-fixed
        # exit_engine bug (check_distribution() raising the stop to breakeven even when
        # price hadn't reached breakeven yet, then immediately reading the same price as
        # "below the new stop") force-closed 9 positions in one pass at prices nowhere near
        # their real, much-wider stop_loss_price - a code-bug artifact, not a real losing
        # streak - yet this check counted all 9 toward the halt with no way to exclude them.
        # DATA-QC is the short marker this session appended to those 9 trades'
        # exit_reason after verifying the root-cause fix (commits c6d399ba4, 5f1e8f8e1).
        # CRITICAL FIX: same gap for POSITION_SIZE_CONCENTRATION/SECTOR_CONCENTRATION
        # force-exits (phase6_exit_execution.py) - these are portfolio-construction/
        # risk-limit rebalancing, not a strategy call gone wrong, exactly like the
        # force-close/reconciliation/delisted exits already excluded above. Confirmed
        # live 2026-08-03: the position-size-concentration denominator bug (fixed in
        # b22e66d3b) force-exited 6 real positions within 7 minutes citing 17-42%
        # concentration (impossible for a diversified portfolio), 3 of them losses,
        # which this check counted as 3 real consecutive losses and halted trading via
        # circuit_breaker_halt at 09:20:30 - a structural/denominator bug pretending to
        # be a losing streak. Even with that bug now fixed, concentration force-exits
        # remain structurally not a strategy decision and should never count here.
        # FIX (2026-08-05): Also check algo_positions for recent closes (last 90s).
        # Phase 2 runs before Phase 9 (exit recording), so exits that closed on broker
        # but haven't been recorded in algo_trades yet don't affect the streak check.
        # If most recent position close was a win in the last 90s, it breaks the streak.
        cur.execute(
            """
            SELECT unrealized_pnl_pct as profit_loss_pct, closed_at as exit_date
            FROM algo_positions
            WHERE status = 'closed' AND closed_at > NOW() - INTERVAL '90 seconds'
            ORDER BY closed_at DESC
            LIMIT 1
            """
        )
        recent_close = cur.fetchone()
        if recent_close and recent_close[0] is not None:
            recent_pnl = _cb._float(recent_close[0], None, context="recent_position_pnl")
            if recent_pnl >= 0:
                _cb.logger.debug(
                    f"[CIRCUIT BREAKER] Recent position close ({recent_pnl:+.2f}%) "
                    f"in last 90s breaks loss streak - skipping algo_trades check"
                )
                return {"halted": False, "reason": "0 losses (recent win resets streak)"}

        cur.execute(
            """
            SELECT profit_loss_pct, exit_date FROM algo_trades
            WHERE status = %s AND exit_date IS NOT NULL
              AND trade_id NOT ILIKE 'EXT-%%'
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
            ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
            LIMIT 10
            """,
            (
                TradeStatus.CLOSED.value,
                "%reconciliation%",
                "%force%close%",
                "%delisted%",
                "%DATA-QC%",
                "%CONCENTRATION%",
            ),
        )
        rows = cur.fetchall()
        if not rows:
            return {"halted": False, "reason": "No closed trades"}
        # Count consecutive losses from most recent. Skip trades with NULL P&L (incomplete data).
        # Do not default NULL to 0 (would mask incomplete records), but do skip rather than fail.
        streak = 0
        for r in rows:
            if r[0] is None:
                # Skip trades with incomplete exit data; do not count as losses
                _cb.logger.debug("Skipping trade with NULL P&L in consecutive loss check")
                continue
            pnl = _cb._float(r[0], None, context="trade_pnl")
            if pnl < 0:
                streak += 1
            else:
                break
        # CRITICAL FIX: Use paper_mode_max_consecutive_losses when in paper trading mode
        # Paper mode allows higher threshold (5 vs 3) for thorough testing without interruption.
        # This prevents false halts during normal market volatility testing.
        #
        # BUG FOUND 2026-08-10: this used to silently default missing config to True (paper
        # mode), which is backwards for a capital-protection check - if alpaca_paper_trading
        # were ever missing while actually live, it would silently apply the LENIENT
        # threshold (5) instead of the strict live threshold (3), under-protecting real
        # capital. Every other consumer of this same config key in the codebase (phase6/8,
        # alpaca_broker_adapter.py, execution_config.py, alpaca_sync_manager.py,
        # infrastructure/reconciliation.py) already fails fast with "NO FALLBACK TO LIVE
        # TRADING" - and this file's own _get_required_config() docstring says the same
        # thing: "missing thresholds must ALWAYS cause failure. There are no safe defaults
        # for risk control parameters." This call site was the one place that didn't follow
        # its own file's rule.
        is_paper_trading = self._get_required_config("alpaca_paper_trading", "in consecutive losses check")
        if is_paper_trading:
            config_key = "paper_mode_max_consecutive_losses"
            # Fallback to regular threshold if paper mode not configured yet
            max_consec_val = self.config.get(config_key)
            if max_consec_val is None:
                max_consec_val = self._get_required_config("max_consecutive_losses", "in consecutive losses check")
        else:
            max_consec_val = self._get_required_config("max_consecutive_losses", "in consecutive losses check")

        threshold = int(max_consec_val)
        return {
            "halted": streak >= threshold,
            "reason": (f"{streak} consecutive losses >= {threshold}" if streak >= threshold else f"{streak} losses"),
            "value": streak,
            "threshold": threshold,
        }

    def _check_win_rate_floor(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Halt if recent win rate drops below floor on closed trades only.

        CRITICAL FIX 2026-08-06: Only count CLOSED trades with confirmed exits, not open positions.
        Including open positions caused false halts when positions had small unrealized losses
        that would recover. Win rate floor should measure proven performance on closed trades,
        not in-flight unrealized P&L which is transient and misleading.

        Example: 11 closed wins, 18 closed losses = 37.9% → halt
        But 4 open positions with negative P&L were artificially counted as losses in the old
        calculation, making the sample look worse than it was. This fix uses only closed trades
        (the decided outcome) for circuit breaker gating, while exit_engine monitors open positions
        separately via stop-loss/exit conditions.

        Rolling 30-trade window (per solution-blueprint.html's CB11 spec and the same convention
        _check_consecutive_losses uses via its own LIMIT 10) - NOT all-time history. An earlier
        version of this query aggregated every closed trade ever with no ORDER BY/LIMIT, so a
        cluster of old losses could permanently anchor the win rate below floor and halt trading
        forever regardless of how well it was performing recently; loaders/compute_circuit_breakers.py's
        _compute_win_rate already implemented the correct rolling-30 window (for a metrics/display
        table only, never wired into this actual gating check) - mirrored here.
        """
        # CRITICAL FIX: Use only closed trades for win rate. Open positions are managed separately
        # by exit_engine's stop-loss/target checks. Including unrealized P&L here caused false
        # halts due to temporary unrealized losses that would recover or be managed by exit logic.
        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                   COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
                   COUNT(*) FILTER (WHERE pnl_pct = 0) as breakeven,
                   COUNT(*) as total
            FROM (
                -- Most recent 30 closed trades with confirmed exits (rolling window, not all-time)
                -- Do NOT include open positions - they're transient and managed separately by exit_engine
                SELECT profit_loss_pct as pnl_pct
                FROM (
                    SELECT profit_loss_pct, id
                    FROM algo_trades
                    WHERE status = %s AND exit_date IS NOT NULL
                      AND exit_r_multiple IS NOT NULL
                      AND trade_id NOT ILIKE 'EXT-%%'
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                    -- CRITICAL FIX: exit_time is frequently NULL on this table (several close
                    -- paths didn't set it until this same fix round - see
                    -- _check_consecutive_losses's comment above), so NULLS LAST alone left ties
                    -- among NULL-exit_time rows in a non-deterministic order (no further ORDER BY
                    -- key) - this "most recent 30" window could silently vary between runs on the
                    -- same underlying data. id DESC is a final deterministic tiebreak.
                    ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
                    LIMIT 30
                ) recent_closed
            ) all_trades
            """,
            (
                TradeStatus.CLOSED.value,
                "%reconciliation%",
                "%force%close%",
                "%delisted%",
                "%DATA-QC%",
                "%CONCENTRATION%",
            ),
        )
        row = cur.fetchone()
        if row is None:
            return {"halted": False, "reason": "No trade data available - insufficient trades (< 10)"}

        total = row[3]
        if total is None:
            return {"halted": False, "reason": "Insufficient closed trades (< 10)"}
        total = int(total)

        # CRITICAL FIX: Do NOT default wins/losses to 0 if missing.
        # Missing data indicates query failure or data integrity issue.
        # Fail-fast to prevent incorrect win rate calculations.
        if row[0] is None or row[1] is None:
            raise RuntimeError(
                f"[CIRCUIT_BREAKER CRITICAL] Win/loss counts missing from query result. "
                f"Cannot calculate win rate without actual trade outcomes. "
                f"Row[0]={row[0]}, Row[1]={row[1]}. "
                f"Data integrity issue or insufficient closed trades. Check database state."
            )
        wins = int(row[0])
        losses = int(row[1])

        # Win rate based on wins vs (wins + losses), excluding break-even trades
        # This avoids dilution where many break-even trades inflate the denominator
        decisive_trades = wins + losses

        # CRITICAL FIX: Check if this is a NEW account (no closed trades yet).
        # Applying win_rate_floor to open positions before ANY closed trades were
        # executed halts trading indefinitely if those positions are underwater.
        # Grace period: don't apply win_rate_floor until at least 10 STRATEGIC CLOSED trades exist.
        # Exclude reconciliation and force-close exits as these are not strategic outcomes.
        cur.execute(
            """
            SELECT COUNT(*) FROM algo_trades
            WHERE status = %s AND exit_date IS NOT NULL
              AND exit_r_multiple IS NOT NULL
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
        """,
            (TradeStatus.CLOSED.value, "%reconciliation%", "%force%close%", "%delisted%", "%CONCENTRATION%"),
        )
        closed_row = cur.fetchone()
        # CRITICAL FIX: Do NOT default closed_count to 0 if query fails.
        # Missing count indicates data integrity issue or failed query.
        if closed_row is None or closed_row[0] is None:
            raise RuntimeError(
                "[CIRCUIT_BREAKER CRITICAL] Could not fetch closed trade count. "
                "Cannot determine if account is in bootstrap period. "
                "Database query failed or no trades found. Check database state."
            )
        closed_count = int(closed_row[0])

        if closed_count < 10:
            return {
                "halted": False,
                "reason": f"New account bootstrap period - insufficient closed trades ({closed_count} < 10 required)",
                "trades_sampled": total,
            }

        # The sample-size guard must gate on decisive_trades (the actual win_rate
        # denominator below), not on total (which also counts breakeven placeholder
        # rows - e.g. Phase 9 "pending fill price confirmation" reconciliation exits
        # recorded at exactly 0.00% before their real fill price is known). Gating on
        # total let it through with total=26 but decisive_trades=8 in a live run -
        # a below-threshold sample size computing a real halt off effectively 8 trades.
        if decisive_trades < 10:
            return {
                "halted": False,
                "reason": f"Insufficient decisive trades in window ({decisive_trades} < 10)",
                "trades_sampled": total,
            }
        win_rate = wins / decisive_trades * 100.0
        win_rate_val = self._get_required_config("min_win_rate_pct", "in win rate check")
        threshold = float(win_rate_val)
        if (
            not isinstance(threshold, float)
            or (threshold != threshold)
            or threshold == float("inf")
            or threshold == float("-inf")
        ):  # NaN/Inf check
            _cb.logger.critical("CRITICAL: min_win_rate_pct is invalid (NaN/Inf) - circuit breaker cannot function")
            return {"halted": True, "reason": "CRITICAL: min_win_rate_pct invalid (NaN/Inf)"}
        return {
            "halted": win_rate < threshold,
            "reason": (
                f"Win rate {win_rate:.1f}% < {threshold:.0f}%" if win_rate < threshold else f"Win rate {win_rate:.1f}%"
            ),
            "value": round(win_rate, 1),
            "threshold": threshold,
            "trades_sampled": total,
        }

    def _check_sector_concentration(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Log warning if any sector exceeds max position cap - advisory only, no halt.

        Sector concentration is a soft limit; the circuit breaker warns but does not block.
        """
        try:
            max_sector_val = self._get_required_config("max_positions_per_sector", "in sector concentration check")
            max_sector_positions = int(max_sector_val)

            cur.execute("""
                -- CRITICAL FIX: Return NULL for missing sector (don't hide with 'Unknown')
                SELECT ap.symbol, cp.sector
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
                WHERE ap.status = 'open'
                """)
            rows = cur.fetchall()
            if not rows:
                return {"halted": False, "reason": "No open positions"}

            sector_counts: dict[str, int] = {}
            for row in rows:
                if not row or len(row) < 2:
                    raise RuntimeError(f"Sector concentration check: invalid row structure {row}")
                _, sector = row[0], row[1]
                if not sector:
                    raise RuntimeError("Sector concentration check: row has None/empty sector")
                if sector not in sector_counts:
                    sector_counts[sector] = 0
                sector_counts[sector] += 1

            concentrated = {s: n for s, n in sector_counts.items() if n >= max_sector_positions and s != "Unknown"}
            if concentrated:
                sector_details = ", ".join(f"{s}({n})" for s, n in concentrated.items())
                _cb.logger.warning(
                    f"Sector at/near cap: {sector_details} (max {max_sector_positions}) - Phase 6 will block same-sector entries"
                )
                return {
                    "halted": False,
                    "reason": f"At-cap sectors (per-trade enforcement in Phase 6): {sector_details}",
                    "at_cap_sectors": concentrated,
                }

            return {
                "halted": False,
                "reason": f"All sectors within limits (max {max_sector_positions} per sector)",
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Sector concentration check failed: {e}") from e

    def _check_sector_drawdown(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Halt if any sector's cost-basis-weighted unrealized P&L drops to/below
        sector_drawdown_halt_pct.

        CRITICAL: sector_drawdown_halt_pct has been a seeded, validated, admin-editable
        config value since migration 005 - documented in
        algo/infrastructure/config/circuit_breaker_config.py's own module docstring as one
        of this codebase's 8 core circuit-breaker categories, alongside daily_loss,
        weekly_loss, consecutive_losses, win_rate, total_risk, profit_cap, and
        data_staleness (all of which DO have real _check_* methods here) - but unlike
        those 7 siblings, nothing ever read this value to actually halt trading. It looked
        like active protection and wasn't. This check closes that gap.

        Distinct from _check_sector_concentration (position-COUNT cap, advisory only,
        enforced per-trade in Phase 6): this is a P&L-based portfolio-wide halt, same
        severity tier as _check_drawdown/_check_daily_loss/_check_weekly_loss.

        Weighted by cost basis (SUM(unrealized_pnl) / SUM(entry_price * quantity) per
        sector), not a simple average of each position's unrealized_pnl_pct - an
        unweighted average would let a $500 position and a $50,000 position in the same
        sector count equally, masking the actual dollar-weighted sector exposure.

        sector_drawdown_halt_pct is stored negative (e.g. -12.0 = halt at 12% down),
        same convention as halt_drawdown_pct/max_daily_loss_pct/max_weekly_loss_pct -
        compared directly with <=, no abs() needed (see _check_daily_loss for the same
        pattern).
        """
        cur.execute("""
            -- Same NULL-sector fail-closed handling as _check_sector_concentration.
            SELECT cp.sector, ap.unrealized_pnl, ap.entry_price, ap.quantity
            FROM algo_positions ap
            LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
            WHERE ap.status = 'open'
            """)
        rows = cur.fetchall()
        if not rows:
            return {"halted": False, "reason": "No open positions"}

        sector_pnl: dict[str, float] = {}
        sector_basis: dict[str, float] = {}
        skipped_positions = 0
        for row in rows:
            if not row or len(row) < 4:
                _cb.logger.warning(f"Sector drawdown check: skipping malformed row {row}")
                skipped_positions += 1
                continue
            sector, unrealized_pnl, entry_price, quantity = row[0], row[1], row[2], row[3]
            # Skip positions with missing sector (from LEFT JOIN) - they'll be synced in next run
            if not sector:
                skipped_positions += 1
                continue
            # Skip positions with missing P&L data - they'll be resync'd in Phase 3
            # Don't halt orchestrator for incomplete position data
            if unrealized_pnl is None or entry_price is None or quantity is None:
                _cb.logger.warning(
                    f"Sector drawdown check: skipping position with missing P&L/cost-basis data (sector={sector}, "
                    f"pnl={unrealized_pnl}, price={entry_price}, qty={quantity})"
                )
                skipped_positions += 1
                continue
            try:
                cost_basis = float(entry_price) * float(quantity)
                unrealized_pnl_f = float(unrealized_pnl)
                # BUG FOUND 2026-08-10: `cost_basis <= 0` never catches NaN/Inf (always False
                # in Python), and unrealized_pnl_f had no finiteness check at all - either one
                # would silently corrupt this sector's summed cost basis/P&L with NaN, which
                # then feeds a real portfolio-wide P&L halt decision below.
                if (
                    math.isnan(cost_basis)
                    or math.isinf(cost_basis)
                    or math.isnan(unrealized_pnl_f)
                    or math.isinf(unrealized_pnl_f)
                    or cost_basis <= 0
                ):
                    _cb.logger.warning(
                        f"Sector drawdown check: skipping position with invalid cost basis/P&L (sector={sector}, basis={cost_basis}, pnl={unrealized_pnl_f})"
                    )
                    skipped_positions += 1
                    continue
            except (ValueError, TypeError) as e:
                _cb.logger.warning(f"Sector drawdown check: skipping position - cost basis conversion error: {e}")
                skipped_positions += 1
                continue
            sector_pnl[sector] = sector_pnl.get(sector, 0.0) + unrealized_pnl_f
            sector_basis[sector] = sector_basis.get(sector, 0.0) + cost_basis

        # If we skipped all positions, insufficient data to calculate sector drawdown
        if not sector_pnl:
            _cb.logger.info(
                f"Sector drawdown check: all {skipped_positions} positions skipped due to missing data - insufficient data for sector drawdown calculation"
            )
            return {
                "halted": False,
                "reason": "Insufficient data for sector drawdown check (positions missing P&L data)",
            }

        sector_returns = {s: sector_pnl[s] / sector_basis[s] * 100 for s in sector_pnl}
        worst_sector = min(sector_returns, key=lambda s: sector_returns[s])
        worst_pct = sector_returns[worst_sector]

        halt_val = self._get_required_config("sector_drawdown_halt_pct", "in sector drawdown check")
        threshold = _cb._float(halt_val, None, context="sector_drawdown_halt_pct")
        if threshold >= 0:
            _cb.logger.critical(f"CRITICAL: sector_drawdown_halt_pct must be negative, got {threshold}")
            return {
                "halted": True,
                "reason": f"CRITICAL: sector_drawdown_halt_pct misconfigured (must be negative, got {threshold})",
            }

        halted = worst_pct <= threshold
        return {
            "halted": halted,
            "reason": (
                f"{worst_sector} sector at {worst_pct:.2f}% <= {threshold:.1f}%"
                if halted
                else f"Worst sector ({worst_sector}) at {worst_pct:.2f}%"
            ),
            "value": round(worst_pct, 2),
            "threshold": threshold,
            "sector": worst_sector,
        }
