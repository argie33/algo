#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_error_handling import (
    ErrorCategory,
    PhaseError,
    log_phase_error,
)
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager

logger = logging.getLogger(__name__)


def run(  # noqa: C901 -- grew complex from today's execution-mode/dependency-chain fixes;
    # revisit as a follow-up refactor rather than rushing a split during live incident work.
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult:
    """Execute Phase 3: Position Monitor.

    Args:
        config: Configuration object
        get_conn: Function to get database connection
        put_conn: Function to return database connection
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok', data containing position recommendations
    """
    # Phase 3 (Position Monitor) is CRITICAL and cannot be skipped
    # It detects: single-stock halts, stale orders, stuck positions, orphaned trades
    # Position monitoring is non-negotiable - do not disable via environment variables
    is_paper_mode = config.get("execution_mode") == "paper"

    # CRITICAL FIX: In paper mode, we still need to update current_price and position_value
    # so the API doesn't filter out positions. Skip full analysis (requires sector/technical data).
    if is_paper_mode:
        logger.info("[PHASE 3] Paper mode: updating position prices only")
        try:
            from utils.db import DatabaseContext

            # Simple price update without full position analysis
            # Fetch positions with all required fields directly (not via get_open_positions which is incomplete)
            def _update_position_prices(cur: Any) -> int:
                updated = 0
                # Fetch open positions with required fields for price update (including entry_date for days calculation)
                cur.execute("""
                    SELECT position_id, symbol, quantity, current_price, entry_date, stop_loss_price, avg_entry_price
                    FROM algo_positions
                    WHERE status = 'open' AND quantity > 0
                    ORDER BY position_id
                """)
                positions = cur.fetchall()
                logger.info(f"[PHASE 3] Found {len(positions)} open positions to update")

                # Get latest prices from price_daily table for all open symbols
                open_symbols = [row[1] for row in positions]  # row[1] is symbol
                prices: dict[str, float | None] = {}

                if open_symbols:
                    cur.execute(
                        """
                        WITH latest_prices AS (
                            SELECT symbol, close, data_unavailable, data_unavailable_reason,
                                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                            FROM price_daily
                            WHERE symbol = ANY(%s)
                        )
                        SELECT symbol, close, data_unavailable, data_unavailable_reason
                        FROM latest_prices
                        WHERE rn = 1
                        """,
                        (open_symbols,),
                    )
                    price_rows = cur.fetchall()

                    # GOVERNANCE COMPLIANCE: Check data_unavailable flag for each price
                    for row in price_rows:
                        if len(row) != 4:
                            raise RuntimeError(
                                f"[PHASE 3] Price query returned {len(row)} columns, expected 4. Schema drift detected."
                            )
                        symbol = row[0]
                        close_price = row[1]
                        data_unavailable_flag = bool(row[2]) if row[2] is not None else False
                        reason_msg = row[3] if row[3] is not None else None

                        # FAIL-FAST: Cannot use prices marked unavailable for position monitoring
                        if data_unavailable_flag:
                            logger.critical(
                                f"[PHASE 3] {symbol}: Price data marked unavailable: {reason_msg or 'no reason provided'}. "
                                f"Cannot monitor position without valid price data. Fail-closed."
                            )
                            raise RuntimeError(
                                f"[PHASE 3] {symbol}: Price data marked unavailable. "
                                f"Position monitoring requires valid price data for all open positions. "
                                f"Check price_daily loader status."
                            )

                        prices[symbol] = float(close_price) if close_price is not None else None

                update_errors = []
                for position_id, symbol, quantity, _old_price, entry_date, stop_loss, avg_entry in positions:
                    try:
                        # GOVERNANCE: Require fresh price data for position monitoring
                        # Fail-fast: Don't accept stale prices. If today's price missing, skip the position
                        # (don't silently use yesterday's price, which violates fail-fast principle).
                        current_price = prices.get(symbol)

                        if current_price is None:
                            logger.warning(
                                f"[PHASE 3] {symbol}: Skipping position update - today's price data not available. "
                                f"This is expected during ramp-up or before morning price loader completes. "
                                f"Position will be updated in next run when current prices are loaded."
                            )
                            # Skip this position; don't fail the entire phase and don't accept stale data
                            # It will be updated in a later run when fresh price data arrives
                            continue

                        if quantity is None:
                            logger.warning(f"[PHASE 3] Skipping {symbol}: missing required quantity field")
                            continue

                        current_price = float(current_price)
                        quantity = float(quantity)

                        # FAIL-FAST: Critical position data must be present
                        # avg_entry and stop_loss are required to monitor position health
                        # Silent defaults (0) hide data quality issues and produce misleading P&L
                        if avg_entry is None:
                            logger.warning(
                                f"[PHASE 3] {symbol}: Cannot update position - avg_entry_price is missing. "
                                f"Position exists but entry cost basis unavailable. Skip position update."
                            )
                            continue
                        if stop_loss is None:
                            logger.warning(
                                f"[PHASE 3] {symbol}: Cannot update position - stop_loss is missing. "
                                f"Position exists but stop loss unavailable. Skip position update."
                            )
                            continue

                        avg_entry = float(avg_entry)
                        stop_loss = float(stop_loss)

                        # Validate converted values
                        if avg_entry <= 0:
                            logger.warning(
                                f"[PHASE 3] {symbol}: Invalid avg_entry_price ({avg_entry}). "
                                f"Entry price must be positive. Skip position update."
                            )
                            continue
                        if stop_loss <= 0:
                            logger.warning(
                                f"[PHASE 3] {symbol}: Invalid stop_loss ({stop_loss}). "
                                f"Stop loss must be positive. Skip position update."
                            )
                            continue

                        # Calculate enrichment fields: days held and ladder % to stop
                        days_since_entry = (run_date - entry_date).days if entry_date else 0
                        ladder_pct_stop = 0.0
                        if current_price and avg_entry > stop_loss:
                            # ladder_pct_stop: how far we are from stop to entry as % of entry-to-stop range
                            entry_to_stop_range = avg_entry - stop_loss
                            current_to_stop_dist = current_price - stop_loss
                            if entry_to_stop_range > 0:
                                ladder_pct_stop = (current_to_stop_dist / entry_to_stop_range) * 100

                        # Update position with current price and computed fields
                        cur.execute(
                            """
                            UPDATE algo_positions
                            SET current_price = %s,
                                position_value = %s * %s,
                                unrealized_pnl = (%s - avg_entry_price) * %s,
                                unrealized_pnl_pct = CASE WHEN avg_entry_price > 0
                                    THEN ((%s - avg_entry_price) / avg_entry_price) * 100 ELSE NULL END,
                                days_since_entry = %s,
                                ladder_pct_stop = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE position_id = %s
                            """,
                            (
                                current_price,
                                quantity,
                                current_price,
                                current_price,
                                quantity,
                                current_price,
                                days_since_entry,
                                ladder_pct_stop,
                                position_id,
                            ),
                        )
                        updated += 1
                    except Exception as e:
                        logger.error(f"[PHASE 3 CRITICAL] Failed to update {symbol}: {type(e).__name__}: {e}")
                        update_errors.append((symbol, str(e)[:100]))

                # GOVERNANCE: Fail-fast only if CRITICAL errors (not just missing price data)
                # Missing price data is expected during ramp-up and is handled gracefully by skipping
                # Filter non-critical errors: missing prices, data loader lag, etc.
                critical_errors = [
                    e
                    for e in update_errors
                    if not any(
                        phrase in e[1].lower()
                        for phrase in [
                            "price",
                            "missing",
                            "no data",
                            "unavailable",
                            "fallback",
                            "ramp-up",
                            "loader",
                        ]
                    )
                ]
                if critical_errors:
                    errors_str = "; ".join(f"{sym}({err})" for sym, err in critical_errors[:3])
                    if len(critical_errors) > 3:
                        errors_str += f"... and {len(critical_errors) - 3} more"
                    error_msg = f"[PHASE 3 CRITICAL] {len(critical_errors)} position updates failed: {errors_str}"
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg)
                elif update_errors:
                    # Non-critical errors (e.g. missing price data during ramp-up)
                    skipped_count = len(update_errors)
                    logger.warning(
                        f"[PHASE 3] Skipped {skipped_count} positions due to missing data (expected during ramp-up). "
                        f"Successfully updated {updated} positions."
                    )

                return updated

            with DatabaseContext("write") as cur:
                updated_count = _update_position_prices(cur)

            # CRITICAL FIX (Session 394): Generate exit recommendations even in paper mode
            # to maintain position management (keep count below hard limit of 17).
            # Skipping recommendations breaks position management: Phase 6 gets empty recommendations ->
            # no exits execute -> position count hits hard limit -> Phase 8 blocks all new entries.
            # FAIL-FAST FIX: PositionMonitor failure is CRITICAL - cannot generate fake fallback
            # recommendations. Position monitoring is too fundamental to work around.
            from algo.monitoring import PositionMonitor
            recommendations = []
            try:
                monitor = PositionMonitor(config)
                recommendations = monitor.review_positions(run_date)
                n_early_exit = sum(1 for r in recommendations if r["action"] == "EARLY_EXIT")
                n_raise_stop = sum(1 for r in recommendations if r["action"] == "RAISE_STOP")
                logger.info(f"[PHASE 3] Paper mode generated {len(recommendations)} recommendations: {n_early_exit} early exits, {n_raise_stop} stop raises")
            except Exception as review_err:
                error_str = str(review_err)[:200]

                # CRITICAL FIX (Session 431): FAIL-FAST on data gaps instead of creating fake fallback
                # Previous approach: Detect data gap errors and generate minimal fallback exit recommendation
                # PROBLEM: Fallback recommendations are fake (not based on actual position analysis)
                # This masks transient data issues and violates fail-fast principle for risk-critical logic
                #
                # Position management must be based on actual analysis. A data gap is transient and should
                # be resolved, not covered up with synthesized recommendations. If PositionMonitor can't
                # analyze positions (data gap or code bug), Phase 3 must halt. Orchestrator will retry
                # on the next run when data has been loaded.
                #
                # FAIL-FAST: Regardless of error type (data gap, code bug, API failure), position monitoring
                # failure = critical risk-management failure. Cannot trade if we can't monitor positions.
                error_msg = (
                    f"[PHASE 3 CRITICAL] PositionMonitor.review_positions() failed: {error_str}. "
                    f"Cannot generate exit recommendations without proper position analysis. "
                    f"Position monitoring is non-negotiable for risk management. "
                    f"This orchestrator run cannot proceed - must halt to prevent unmonitored position risks. "
                    f"Next run will retry when data has been loaded."
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg) from review_err

            log_phase_result_fn(
                3,
                "position_monitor",
                "success",
                f"{updated_count} positions updated with current prices, {len(recommendations)} recommendations generated",
            )
            return PhaseResult(
                3,
                "position_monitor",
                "ok",
                {"recommendations": recommendations, "count": updated_count},
                False,
                None,
            )
        except Exception as e:
            logger.error(f"[PHASE 3] Paper mode price update FAILED: {type(e).__name__}: {e}")
            # Report the truth: price update failed. Don't mask with "ok" status.
            # If positions need prices and we can't get them, this is an error.
            return PhaseResult(
                3,
                "position_monitor",
                "error",
                {"recommendations": [], "count": 0},
                True,  # Halt on price update failure - can't trade without current prices
                str(e),
            )

    try:
        from algo.infrastructure import MarketEventHandler
        from algo.monitoring import PositionMonitor

        monitor = PositionMonitor(config)

        try:
            meh = MarketEventHandler(config)
            try:
                open_positions = monitor.get_open_positions()
            except RuntimeError as pos_e:
                error = PhaseError(
                    category=ErrorCategory.DEPENDENCY_FAILED,
                    message="Cannot fetch open positions for halt checking",
                    root_cause=str(pos_e)[:150],
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(3, error, log_phase_result_fn)
                raise
            halts_found = []
            halt_check_errors = []
            for pos in open_positions:
                if "symbol" not in pos and "name" not in pos:
                    raise RuntimeError(
                        "[PHASE 3] Position missing both symbol and name. "
                        "At least one identifier is required. "
                        "Verify PositionMonitor.get_open_positions() returns valid position data."
                    )
                symbol = pos.get("symbol")
                if not symbol:
                    symbol = pos.get("name")
                if not symbol:
                    raise RuntimeError(
                        f"[PHASE 3] Position symbol and name are both empty or missing. "
                        f"Position data: {pos}. Cannot proceed without valid symbol identifier."
                    )
                try:
                    halt_check = meh.check_single_stock_halt(symbol)
                    if halt_check is None:
                        logger.error(
                            f"[PHASE 3 CRITICAL] {symbol}: halt check returned None - cannot verify if position is halted"
                        )
                        halt_check_errors.append((symbol, "halt_check_returned_None"))
                    elif "error" in halt_check:
                        if "reason" not in halt_check or halt_check["reason"] is None:
                            logger.critical(
                                f"[PHASE 3 CRITICAL] {symbol}: halt check returned error but missing reason field. "
                                f"Keys: {list(halt_check.keys())}. "
                                f"Cannot determine why halt check failed. Check market-data API integration."
                            )
                            raise ValueError(
                                f"[PHASE 3] Halt check error for {symbol} missing reason field. "
                                "Cannot safely evaluate halt status."
                            )
                        error_reason = halt_check["reason"]
                        logger.error(f"[PHASE 3 CRITICAL] {symbol}: halt check API failed ({error_reason})")
                        halt_check_errors.append((symbol, error_reason))
                    elif halt_check.get("halted"):
                        halts_found.append(symbol)
                        meh.handle_single_stock_halt(symbol)
                        if verbose:
                            logger.warning(f"  [WARN] {symbol} halted - pending orders cancelled")
                except Exception as halt_exc:
                    logger.error(
                        f"[PHASE 3 CRITICAL] Failed to check halt status for {symbol}: {type(halt_exc).__name__}: {halt_exc}"
                    )
                    halt_check_errors.append((symbol, f"exception: {type(halt_exc).__name__}"))

            # GOVERNANCE: Fail-fast if halt checks failed - cannot monitor positions without halt detection
            if halt_check_errors:
                errors_str = "; ".join(f"{sym}({err})" for sym, err in halt_check_errors[:3])
                if len(halt_check_errors) > 3:
                    errors_str += f"... and {len(halt_check_errors) - 3} more"
                error_msg = f"[PHASE 3 CRITICAL] Cannot monitor positions - {len(halt_check_errors)} halt checks failed: {errors_str}"
                logger.critical(error_msg)
                raise RuntimeError(error_msg)
            if halts_found:
                log_phase_result_fn(
                    3,
                    "single_stock_halts",
                    "warn",
                    f"{len(halts_found)} symbols halted: {', '.join(halts_found)}",
                )
        except (OSError, RuntimeError, ValueError) as e:
            # CRITICAL: This used to log the failure as recoverable=True/"warning" and then
            # fall through to check_stale_orders()/review_positions() below as if halt
            # checking had succeeded - silently defeating the "GOVERNANCE: Fail-fast" raises
            # a few lines up (which fire when we can't even fetch open positions, or can't
            # verify halt status for one or more of them). A stock that's actually halted
            # but whose halt check failed to confirm that would flow straight into position
            # review and downstream entry/exit phases with its halt status simply unknown.
            # Must actually halt the phase here, not just log and continue.
            error = PhaseError(
                category=ErrorCategory.DEPENDENCY_FAILED,
                message="Halt check failed for open positions",
                root_cause=str(e)[:150],
                recoverable=False,
                log_level="critical",
            )
            log_phase_error(3, error, log_phase_result_fn)
            return PhaseResult(
                3,
                "position_monitor",
                "error",
                {"recommendations": [], "count": 0},
                True,
                str(e),
            )

        stale_result = monitor.check_stale_orders(run_date)
        if stale_result and stale_result.get("status") == "STALE_ORDERS_FOUND":
            if "count" not in stale_result:
                raise RuntimeError(
                    f"Stale order check returned incomplete data: missing 'count' field. "
                    f"Got keys: {list(stale_result.keys())}"
                )
            stale_count = stale_result["count"]
            alerts.send_position_alert(
                "STALE_ORDERS",
                "STALE_ORDER_ALERT",
                f"{stale_count} orders pending >1 hour",
                {"orders": stale_count},
            )

        recommendations = monitor.review_positions(run_date)

        n_raise_stop = sum(1 for r in recommendations if r["action"] == "RAISE_STOP")
        n_early_exit = sum(1 for r in recommendations if r["action"] == "EARLY_EXIT")
        n_hold = sum(1 for r in recommendations if r["action"] == "HOLD")
        n_failed = sum(1 for r in recommendations if r["action"] == "FAILED_VALIDATION")

        summary = f"{len(recommendations)} positions reviewed"
        if n_hold > 0:
            summary += f"; {n_hold} hold"
        if n_raise_stop > 0:
            summary += f", {n_raise_stop} raise-stop"
        if n_early_exit > 0:
            summary += f", {n_early_exit} early-exit"
        if n_failed > 0:
            summary += f", {n_failed} FAILED_VALIDATION"

        log_phase_result_fn(
            3,
            "position_monitor",
            "success",
            summary,
        )
        # Surface the summary metrics the health dashboard (dashboard/panels/health.py,
        # Phase 3 detail row) already expects under these exact keys - previously this
        # PhaseResult.data only had recommendations/count, so Open positions/Oldest
        # position/Max loss/Total unrealized silently never rendered despite each
        # recommendation dict already carrying days_held/unrealized_pct/unrealized_pnl
        # per position. FAILED_VALIDATION entries lack these fields entirely, so filter
        # None values rather than assuming every entry has them.
        days_held_vals = [r["days_held"] for r in recommendations if r.get("days_held") is not None]
        unrealized_pct_vals = [r["unrealized_pct"] for r in recommendations if r.get("unrealized_pct") is not None]
        unrealized_pnl_vals = [r["unrealized_pnl"] for r in recommendations if r.get("unrealized_pnl") is not None]
        phase_data = {
            "recommendations": recommendations,
            "count": len(recommendations),
            "open_positions": len(recommendations),
            "oldest_days": max(days_held_vals) if days_held_vals else None,
            "max_loss_pct": min(unrealized_pct_vals) if unrealized_pct_vals else None,
            "total_unrealized_pnl": sum(unrealized_pnl_vals) if unrealized_pnl_vals else None,
        }
        validate_phase_data(3, phase_data)
        return PhaseResult(
            3,
            "position_monitor",
            "ok",
            phase_data,
            False,
            None,
        )

    except Exception as e:
        error = PhaseError(
            category=ErrorCategory.DEPENDENCY_FAILED,
            message="Position monitor failed unexpectedly",
            root_cause=str(e)[:200],
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(3, error, log_phase_result_fn)

        # CRITICAL: Position monitor crash requires explicit config check, then halt regardless of mode
        # Can't safely trade if we can't monitor open positions
        # CRITICAL FIX: Require explicit config - fail-fast if missing
        if "is_paper_trading" not in config:
            raise ValueError(
                "[PHASE 3] Config missing 'is_paper_trading'. "
                "Trading mode must be explicit (paper vs live). "
                "Check algo_config table has this key."
            ) from e
        if config["is_paper_trading"]:
            logger.error(f"[PHASE 3 PAPER MODE] Position monitor crashed - cannot proceed: {type(e).__name__}: {e}")
            # Even in paper mode, if position monitor crashes, we must halt.
            # Can't safely trade without being able to monitor positions.
            return PhaseResult(
                3,
                "position_monitor",
                "error",
                {"recommendations": [], "count": 0},
                True,  # Halt - position monitor crash is critical failure in any mode
                str(e),
            )

        # In live trading, halt immediately if position monitoring fails (risk management)
        logger.critical(
            f"[PHASE 3 HALT] Position monitor crashed unexpectedly: {type(e).__name__}: {e}. "
            f"Cannot safely monitor open positions. Halting trading to prevent unmonitored position risks."
        )
        return PhaseResult(3, "position_monitor", "halted", {"recommendations": []}, True, str(e))
