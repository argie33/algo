#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from decimal import Decimal
from typing import Any

import psycopg2

from algo.exceptions import ValidationError
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
from algo.trading.exceptions import DatabaseError
from utils.db.advisory_locks import (
    ALGO_POSITIONS_LOCK_ID,
    acquire_advisory_lock,
    release_advisory_lock,
)
from utils.db.context import DatabaseContext
from utils.trading.status import PositionStatus

logger = logging.getLogger(__name__)


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
    position_recs: list[dict[str, Any]],
    exposure_actions: list[dict[str, Any]],
    check_halt_flag: Callable[..., Any] | None = None,
) -> PhaseResult:
    """Execute Phase 6: Exit Execution.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        position_recs: Recommendations from phase_3_position_monitor
        exposure_actions: Actions from phase_5_exposure_policy
        check_halt_flag: Unused (kept for API compatibility). Exits always run.

    Returns:
        PhaseResult with status 'ok'
    """
    # No halt flag check here: exits MUST run regardless of halt state.
    # When circuit breaker fires, we still need to exit stressed positions
    # to reduce risk. Blocking exits compounds losses.
    # New entries are blocked by Phase 2/8 - exits are always executed.
    try:
        from algo.trading import ExitEngine
        from algo.trading.executor import TradeExecutor

        # ISSUE #4 FIX: Check if paper mode is active FIRST before validating position_recs
        # In paper mode, Phase 3 intentionally skips position monitoring (it's a live-trading risk feature)
        # so position_recs will be empty. This is expected behavior, not an error.
        execution_mode_check = config.get("execution_mode")
        if execution_mode_check is None:
            raise ValueError(
                "[PHASE 6 CRITICAL] execution_mode config missing. "
                "Cannot determine trading mode (live vs paper). "
                "Set explicit execution_mode in algo_config table."
            )
        # Validate execution_mode is one of the allowed values (fail-fast on invalid config)
        allowed_modes = ("paper", "auto", "dry", "review")
        if execution_mode_check not in allowed_modes:
            raise ValueError(
                f"[PHASE 6 CRITICAL] execution_mode '{execution_mode_check}' is invalid. "
                f"Must be one of: {', '.join(allowed_modes)}. "
                f"Check algo_config table for typos or invalid values."
            )
        # CRITICAL FIX: Require explicit config - fail-fast if missing
        # No silent fallback to False (which would attempt live trading)
        if "alpaca_paper_trading" not in config:
            raise ValueError(
                "[PHASE 6] Config missing 'alpaca_paper_trading'. "
                "Trading mode must be explicit (paper vs live). "
                "Check algo_config table has this key."
            )
        alpaca_paper_trading = config["alpaca_paper_trading"]
        # CRITICAL: "auto" is this system's real live-trading mode. Phase 3
        # (phase3_position_monitor.py) itself only skips position monitoring for
        # execution_mode == "paper" (confirmed by reading its own check), so it DOES
        # populate real position_recs in "auto" mode - the premise of "position_recs will
        # be empty, this is expected" above does not hold for "auto". Including "auto" here
        # meant a genuine safety check below (detect Phase 3 crashing and returning [] while
        # real open positions exist) was silently skipped for every live orchestrator run,
        # logged with a misleading "[PHASE 6] Paper trading mode active" message. Same bug
        # class as this session's other execution_mode fixes (position_sizer.py, executor.py,
        # executor_entry_handler.py) - scope to paper only; alpaca_paper_trading is a
        # separate, legitimate flag (the configured Alpaca account itself being a paper
        # account) left untouched.
        # CRITICAL FIX Session 345: Only check execution_mode_check, not alpaca_paper_trading
        # The Alpaca account paper flag should not override orchestrator execution mode setting
        is_paper_mode = execution_mode_check == "paper"

        # CRITICAL FIX 2026-07-30: ALWAYS validate Phase 3 data regardless of mode
        # Phase 3 DOES generate recommendations in paper mode (verified: recent runs show 14 recommendations)
        # Paper mode safety checks are NOT optional - still need to detect Phase 3 crashes
        # Previously: paper mode skipped this validation, allowing Phase 3 crashes to go undetected
        logger.info("[PHASE 6] Validating Phase 3 position monitor data (mode=%s)", execution_mode_check)

        # Detect Phase 3 crash - if position monitor errored, position_recs is []
        # but we may have real open positions. This is a critical data integrity error.
        if position_recs is None:
            msg = (
                "[PHASE 6 CRITICAL] position_recs not set - Phase 3 did not execute properly. "
                "Cannot proceed with exit execution without position monitor recommendations."
            )
            logger.critical(msg)
            raise RuntimeError(msg)
        elif len(position_recs) == 0:
            # In dry-run mode, empty position_recs is OK - no actual exits will execute
            if dry_run:
                logger.info("[PHASE 6] Dry-run mode with no position recommendations - returning degraded status")
                result_data = {
                    "exits_executed": 0,
                    "stops_raised": 0,
                    "errors": 0,
                    "detail": "DRY-RUN: No position monitor recommendations received"
                }
                log_phase_result_fn(
                    6,
                    "exit_execution",
                    "degraded",
                    "DRY-RUN: No position monitor recommendations",
                )
                return PhaseResult(
                    6,
                    "exit_execution",
                    "degraded",
                    result_data,
                    False,
                    "DRY-RUN: No position monitor recommendations",
                )

            # CRITICAL: Check if we have open positions but no recommendations
            # Phase 3 MUST generate recommendations for all open positions (or halt if it can't)
            # Empty recommendations + open positions = Phase 3 silently skipped position monitoring
            with DatabaseContext("read") as cur:
                cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
                result = cur.fetchone()
                if result is None or result[0] is None:
                    raise RuntimeError("[PHASE 6] Query to count open positions returned NULL")
                open_position_count = result[0]

            if open_position_count > 0:
                msg = (
                    f"[PHASE 6 CRITICAL] Phase 3 generated no recommendations but {open_position_count} positions are open. "
                    f"This violates fail-fast position monitoring: Phase 3 must either generate recommendations or halt. "
                    f"Cannot proceed with unmonitored positions - cannot determine exit conditions or P&L. "
                    f"This indicates Phase 3 silently skipped position analysis (data integrity violation)."
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            # Empty recommendations + no open positions = normal case
            # All positions are closed or healthy
            logger.info("[PHASE 6] Position monitor returned no exit recommendations (normal case - no open positions). Proceeding with zero exits.")

        # Check for sector concentration and add force-exit recommendations for over-concentrated sectors
        # Sector concentration limit: configured via max_positions_per_sector (default 10)
        # CRITICAL FIX: Previously hardcoded limit=3, now uses config value to prevent exits when config != 3
        def _check_sector_concentration():
            """Identify over-concentrated sectors and add force-exit recommendations."""
            try:
                max_sector_val = config.get("max_positions_per_sector")
                if max_sector_val is None:
                    raise ValueError(
                        "CRITICAL: max_positions_per_sector config missing. "
                        "Cannot enforce sector concentration limits. Check algo_config table."
                    )
                # CRITICAL: ensure max_per_sector is native Python int, not Decimal from psycopg2
                max_per_sector = int(max_sector_val)

                with DatabaseContext("read") as cur:
                    cur.execute(
                        f"""
                        SELECT cs.sector, COUNT(*) as position_count
                        FROM algo_positions ap
                        JOIN company_profile cs ON ap.symbol = cs.symbol
                        WHERE ap.status = 'open'
                        GROUP BY cs.sector
                        HAVING COUNT(*) > %s
                        ORDER BY COUNT(*) DESC
                        """,
                        (max_per_sector,),
                    )

                    concentrated_sectors = cur.fetchall()
                    rebalance_actions = []

                    for sector, count in concentrated_sectors:
                        count_int = int(count) if count is not None else 0
                        # CRITICAL: re-ensure max_per_sector is int for subtraction
                        max_per_sector_int = int(max_per_sector)
                        over_limit = count_int - max_per_sector_int
                        logger.warning(f"[PHASE 6 CONCENTRATION] Sector {sector}: {count_int} positions (limit {max_per_sector_int}, need to exit {over_limit})")

                        # Get the weakest positions in this sector (lowest unrealized P&L first to cut losses)
                        # Ensure over_limit is an int for the LIMIT clause
                        cur.execute("""
                            SELECT ap.position_id, ap.symbol
                            FROM algo_positions ap
                            JOIN company_profile cs ON ap.symbol = cs.symbol
                            WHERE ap.status = 'open' AND cs.sector = %s
                            ORDER BY ap.unrealized_pnl ASC
                            LIMIT %s
                        """, (sector, int(over_limit)))

                        weak_positions = cur.fetchall()
                        for pos_id, symbol in weak_positions:
                            action = {
                                "symbol": symbol,
                                "position_id": pos_id,
                                "action": "force_exit",
                                "reason": f"SECTOR_CONCENTRATION: {sector} has {count_int} positions (limit {max_per_sector})",
                                "trade_id": None,  # Will be fetched during execution
                            }
                            rebalance_actions.append(action)
                            logger.warning(f"[PHASE 6 REBALANCE] Force-exit {symbol} (sector concentration rebalance)")

                    return rebalance_actions
            except Exception as e:
                logger.error(f"[PHASE 6] Sector concentration check failed: {e}")
                raise RuntimeError(
                    f"[PHASE 6] Cannot proceed with exit execution: sector concentration check failed. {e}"
                ) from e

        # Check for position size concentration and add force-exit recommendations for oversized positions
        # Position size limit: configured via max_position_size_pct (default 6%)
        # CRITICAL: Oversized positions violate risk management rules and must be force-exited
        def _check_position_size_concentration():
            """Identify oversized positions and add force-exit recommendations."""
            try:
                max_size_pct_val = config.get("max_position_size_pct")
                if max_size_pct_val is None:
                    raise ValueError(
                        "CRITICAL: max_position_size_pct config missing. "
                        "Cannot enforce position size limits. Check algo_config table."
                    )
                # Explicitly convert to float to handle Decimal types from config (psycopg2 returns Decimal)
                try:
                    max_size_pct_float = float(max_size_pct_val)
                except (TypeError, ValueError) as te:
                    raise ValueError(f"max_position_size_pct must be numeric, got {type(max_size_pct_val).__name__}: {max_size_pct_val}") from te

                with DatabaseContext("read") as cur:
                    # Get total portfolio value
                    cur.execute("SELECT SUM(position_value) FROM algo_positions WHERE status='open'")
                    result = cur.fetchone()
                    if result is None:
                        raise RuntimeError("[PHASE 6] Query for total position value returned NULL")
                    total_value = result[0]
                    if total_value is None:
                        total_value_float = 0.0
                    else:
                        total_value_float = float(total_value)

                    if total_value_float <= 0:
                        logger.info("[PHASE 6] No open positions or zero portfolio value - skipping size concentration check")
                        return []

                    # Find positions exceeding size limit
                    cur.execute("""
                        SELECT ap.position_id, ap.symbol, ap.position_value
                        FROM algo_positions ap
                        WHERE ap.status = 'open'
                        ORDER BY ap.position_value DESC
                    """)

                    oversized_positions = []
                    for pos_id, symbol, value in cur.fetchall():
                        # Compute percentage in Python with explicit float conversion to avoid Decimal/float type mixing
                        try:
                            # CRITICAL: Convert to float BEFORE any arithmetic to handle psycopg2 Decimal types
                            # Division of float by Decimal returns Decimal, so we must ensure total_value_float is native float
                            value_float = float(value) if value is not None else 0.0
                            # Ensure division uses native floats, not Decimals
                            total_value_for_division = float(total_value_float)
                            pct_float = (value_float / total_value_for_division * 100) if total_value_for_division > 0 else 0.0
                            # Force to native float in case division returned Decimal
                            pct_float = float(pct_float)
                        except (TypeError, ValueError, ZeroDivisionError) as te:
                            logger.error(f"[PHASE 6 SIZE_CONCENTRATION] {symbol}: Failed to compute percentage {value} / {total_value_float}: {te}")
                            continue

                        # CRITICAL: Ensure both operands are Python native float before arithmetic
                        limit_for_comparison = float(max_size_pct_float)

                        if pct_float > limit_for_comparison:
                            # Both operands guaranteed to be native Python float after explicit conversion above
                            exceed_amount = pct_float - limit_for_comparison
                            oversized_positions.append((pos_id, symbol, pct_float, limit_for_comparison))
                            logger.warning(f"[PHASE 6 SIZE_CONCENTRATION] {symbol}: {pct_float:.1f}% (limit {limit_for_comparison:.0f}%, exceeds by {exceed_amount:.1f}%)")

                    rebalance_actions = []
                    for pos_id, symbol, pct, limit in oversized_positions:
                        action = {
                            "symbol": symbol,
                            "position_id": pos_id,
                            "action": "force_exit",
                            "reason": f"POSITION_SIZE_CONCENTRATION: {pct:.1f}% > {limit:.0f}% limit",
                            "trade_id": None,  # Will be fetched during execution
                        }
                        rebalance_actions.append(action)
                        logger.warning(f"[PHASE 6 REBALANCE] Force-exit {symbol} (position size {pct:.1f}% exceeds {limit:.0f}% limit)")

                    return rebalance_actions
            except Exception as e:
                logger.error(f"[PHASE 6] Position size concentration check failed: {e}")
                raise RuntimeError(
                    f"[PHASE 6] Cannot proceed with exit execution: position size concentration check failed. {e}"
                ) from e

        # Add concentration rebalance actions to the exposure_actions queue
        # CRITICAL FIX: Concentration violations must halt execution, not silently continue
        # Oversized positions create uncontrolled risk exposure that can trigger margin calls
        # If concentration checks fail, this is a data integrity or policy failure - halt immediately
        sector_concentration_actions = []
        size_concentration_actions = []
        try:
            sector_concentration_actions = _check_sector_concentration()
        except Exception as e:
            raise RuntimeError(
                f"[PHASE 6 CRITICAL] Sector concentration check failed - cannot proceed with exits. {type(e).__name__}: {e}"
            ) from e
        try:
            size_concentration_actions = _check_position_size_concentration()
        except Exception as e:
            raise RuntimeError(
                f"[PHASE 6 CRITICAL] Position size concentration check failed - cannot proceed with exits. {type(e).__name__}: {e}"
            ) from e
        # Guard against None values - ensure lists are always valid
        sector_concentration_actions = sector_concentration_actions or []
        size_concentration_actions = size_concentration_actions or []
        all_actions = sector_concentration_actions + size_concentration_actions + exposure_actions

        # DRY-RUN: Process counts of what WOULD happen, then skip actual execution
        # (Don't return early - we still need to count exits for logging/dashboard visibility)

        # Initialize TradeExecutor only in non-dry-run mode
        executor = None
        if not dry_run:
            # ISSUE #4 FIX: Check if paper mode is active before initializing TradeExecutor
            if is_paper_mode:
                logger.info(
                    f"[PHASE 6] Paper trading mode active (execution_mode={execution_mode_check}, "
                    f"alpaca_paper_trading={alpaca_paper_trading}). Exit orders will execute against paper account."
                )

            # Initialize TradeExecutor, FAIL-FAST if credentials missing
            try:
                executor = TradeExecutor(config)
            except ValueError as e:
                if "credentials not found" in str(e).lower() or "credentials" in str(e).lower():
                    # FAIL-FAST: Credentials required for exit execution in ALL modes.
                    # No graceful degradation - if we have open positions to manage,
                    # we MUST be able to execute exit orders. Missing credentials is a hard error.
                    raise RuntimeError(f"[PHASE 6 CRITICAL] Alpaca credentials required: {e}") from e
                else:
                    raise RuntimeError(f"[PHASE 6] TradeExecutor initialization failed: {e}") from e

        exit_count = 0
        stop_raises = 0
        errors = 0

        # 4a-prime. Apply sector concentration rebalancing FIRST, then exposure-policy actions
        for action in all_actions:
            try:
                if "symbol" not in action or "action" not in action or "reason" not in action:
                    raise RuntimeError(
                        "[PHASE 6] Exposure action missing required fields (symbol, action, reason). "
                        "Cannot execute without all three identifiers. "
                        "Verify exposure_policy phase produced valid action data."
                    )
                if dry_run:
                    if verbose:
                        logger.info(f"  [DRY-RUN] {action['symbol']}: {action['action'].upper()} ({action['reason']})")
                    # Still count the action for reporting, even in dry-run mode
                    if action["action"] == "force_exit":
                        exit_count += 1
                    elif action["action"] == "partial_exit":
                        exit_count += 1
                    continue

                if action["action"] == "force_exit":
                    # CRITICAL: Current price is mandatory for force exits
                    # Cannot execute exit without price - would corrupt P&L reporting
                    # Also fetch trade_id if not provided (for concentration rebalancing actions)
                    try:
                        with DatabaseContext("read") as cur_tmp:
                            cur_tmp.execute(
                                "SELECT current_price, trade_ids_arr FROM algo_positions WHERE position_id = %s",
                                (action["position_id"],),
                            )
                            row_tmp = cur_tmp.fetchone()
                            if row_tmp is None or row_tmp[0] is None:
                                raise RuntimeError(
                                    f"[FORCE-EXIT] Current price unavailable for position {action['position_id']}. "
                                    "Cannot execute force exit without price."
                                )
                            cur_price = float(row_tmp[0])
                            # If trade_id not in action, use the first trade from position
                            if not action.get("trade_id"):
                                if row_tmp[1]:
                                    trades = row_tmp[1] if isinstance(row_tmp[1], list) else [row_tmp[1]]
                                    if trades:
                                        action["trade_id"] = trades[0]
                                # CRITICAL: Ensure trade_id was found
                                if not action.get("trade_id"):
                                    raise RuntimeError(
                                        f"[FORCE-EXIT] Cannot find trade_id for position {action['position_id']}. "
                                        "Position has no associated trades. Cannot execute force exit."
                                    )
                            if cur_price <= 0:
                                raise RuntimeError(
                                    f"[FORCE-EXIT] Invalid current price {cur_price} for position {action['position_id']}. "
                                    "Cannot execute exit with non-positive price."
                                )
                    except (RuntimeError, TypeError, ValueError) as e:
                        # FAIL-FAST: Force-exit is a safety mechanism - if it fails, halt immediately
                        # Continuing here silently leaves the position unexited, violating exposure policy
                        error_msg = (
                            f"[PHASE 6 FAIL-FAST] Force-exit failed for {action['symbol']}: {e}. "
                            f"Cannot proceed with unexited position. Position remains in portfolio with stale risk controls. "
                            f"This indicates a critical data or database issue. Check: (1) current price availability, "
                            f"(2) broker connection, (3) position state in database."
                        )
                        logger.critical(error_msg)
                        raise RuntimeError(error_msg) from e

                    # In dry-run mode, just count (don't execute)
                    if dry_run:
                        exit_count += 1
                        if verbose:
                            logger.info(f"  [DRY-RUN] EXPOSURE FORCE-EXIT: {action['symbol']}")
                    else:
                        result = executor.exit_trade(
                            trade_id=action["trade_id"],
                            exit_price=cur_price,
                            exit_reason=action["reason"],
                            exit_fraction=1.0,
                            exit_stage="exposure_force_exit",
                        )
                        if "success" not in result or result["success"] is None:
                            raise RuntimeError(
                                f"Force exit result missing 'success' field. Got keys: {list(result.keys())}"
                            )
                        if result["success"]:
                            exit_count += 1
                            logger.info(f"  EXPOSURE FORCE-EXIT: {result.get('message', action['symbol'])}")
                        else:
                            errors += 1
                            logger.error(
                                f"  FORCE-EXIT FAILED: {action['symbol']} (reason: {action['reason']}). "
                                f"Error: {result.get('message', 'Unknown error')}. "
                                f"Trade ID: {action.get('trade_id', 'UNKNOWN')}"
                            )

                elif action["action"] == "partial_exit":
                    # Need current price - fetch
                    try:
                        with DatabaseContext("read") as cur:
                            cur.execute(
                                "SELECT current_price FROM algo_positions WHERE position_id = %s",
                                (action["position_id"],),
                            )
                            row = cur.fetchone()
                            if row is None or row[0] is None:
                                raise RuntimeError(f"No current price available for position {action['position_id']}")
                            cur_price = float(row[0])
                    except (RuntimeError, TypeError, ValueError) as e:
                        logger.critical(
                            f"  CRITICAL: Cannot execute exit without current price for {action['position_id']}: {e}"
                        )
                        raise RuntimeError(
                            f"[PHASE 6] Cannot fetch current price for exit execution: {e}"
                        ) from e
                    if cur_price is not None and cur_price > 0:
                        if "exit_fraction" not in action:
                            raise ValidationError(
                                field="exit_fraction",
                                value=None,
                                expected="float between 0.0 and 1.0",
                                context={
                                    "position_id": action.get("position_id"),
                                    "action_type": "exposure_partial",
                                },
                            )
                        # In dry-run mode, just count (don't execute)
                        if dry_run:
                            exit_count += 1
                            if verbose:
                                logger.info(f"  [DRY-RUN] EXPOSURE PARTIAL: {action['symbol']}")
                        else:
                            result = executor.exit_trade(
                                trade_id=action["trade_id"],
                                exit_price=cur_price,
                                exit_reason=action["reason"],
                                exit_fraction=float(action["exit_fraction"]),
                                exit_stage="exposure_partial",
                                new_stop_price=action.get("new_stop"),
                            )
                            if "success" not in result or result["success"] is None:
                                raise RuntimeError(
                                    f"Partial exit result missing 'success' field. Got keys: {list(result.keys())}"
                                )
                            if result["success"]:
                                exit_count += 1
                                logger.info(f"  EXPOSURE PARTIAL: {result['message']}")
                            else:
                                errors += 1
                                logger.error(
                                    f"  PARTIAL-EXIT FAILED: {action['symbol']} (fraction: {action.get('exit_fraction', '?')}). "
                                    f"Reason: {action['reason']}. "
                                    f"Error: {result.get('message', 'Unknown error')}. "
                                    f"Trade ID: {action.get('trade_id', 'UNKNOWN')}"
                                )

                elif action["action"] == "tighten_stop":
                    if dry_run:
                        # In dry-run, just log what would happen (don't write to DB)
                        stop_raises += 1
                        if verbose:
                            logger.info(
                                f"  [DRY-RUN] EXPOSURE TIGHTEN {action['symbol']}: stop -> ${action['new_stop']:.2f}"
                            )
                    else:
                        try:
                            with DatabaseContext("write") as cur:
                                acquire_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                                try:
                                    cur.execute(
                                        "UPDATE algo_positions SET current_stop_price = %s WHERE position_id = %s",
                                        (action["new_stop"], action["position_id"]),
                                    )
                                    # rowcount guards against silently counting a no-op as a success -
                                    # e.g. the position closed (a race with a concurrent exit) between
                                    # Phase 5 computing this action and Phase 6 executing it, in which
                                    # case the WHERE clause matches nothing but execute() itself doesn't
                                    # raise, so without this check stop_raises would be incremented and
                                    # "EXPOSURE TIGHTEN" logged as if the stop had actually moved.
                                    if cur.rowcount == 0:
                                        errors += 1
                                        logger.warning(
                                            f"  Tighten no-op for {action['symbol']}: position "
                                            f"{action['position_id']} not found (likely already closed)"
                                        )
                                    else:
                                        stop_raises += 1
                                        if verbose:
                                            logger.info(
                                                f"  EXPOSURE TIGHTEN {action['symbol']}: stop -> ${action['new_stop']:.2f}"
                                            )
                                finally:
                                    release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                        except (RuntimeError, ValueError, TypeError) as e:
                            errors += 1
                            logger.error(f"  Tighten failed for {action['symbol']}: {e}")
            except (RuntimeError, ValueError, TypeError, AttributeError) as e:
                errors += 1
                if "symbol" not in action:
                    logger.critical(
                        f"[PHASE 6 CRITICAL] Exposure action missing 'symbol' field. "
                        f"Cannot log which action failed. Action keys: {list(action.keys())}. "
                        f"Phase 5 produced invalid action record. Cannot proceed with partial error logging. "
                        f"Error was: {e}"
                    )
                    raise RuntimeError(
                        "Exposure action missing 'symbol' field - phase data contract violated. "
                        "Cannot safely log or recover from errors."
                    ) from e
                logger.error(f"  Error on exposure action {action['symbol']}: {e}")

        # 4a. Apply position monitor recommendations (early exits + stop raises)
        for rec in position_recs:
            try:
                if "symbol" not in rec or "action" not in rec:
                    raise RuntimeError(
                        "[PHASE 6] Position recommendation missing required fields (symbol, action). "
                        "Cannot execute without both identifiers. "
                        "Verify position_monitor phase produced valid recommendation data."
                    )
                # CRITICAL FIX: position_monitor.py appends a {action: "FAILED_VALIDATION", error: ...}
                # rec (no action_reason/current_price/new_stop_recommended) whenever
                # PositionValidationError is raised for a position - e.g. bad quantity, bad entry
                # price, corrupted stop/target data. Confirmed live 2026-07-27: neither the
                # EARLY_EXIT nor RAISE_STOP branch below matches "FAILED_VALIDATION", so the rec
                # fell through the loop with no error counted and no log - a position whose data was
                # too corrupt to even evaluate for exit/stop got silently zero exit coverage this
                # run, with `errors` and phase_status staying clean. This is exactly the failure mode
                # this file's exposure/stop-raise no-op checks elsewhere already guard against.
                if rec["action"] == "FAILED_VALIDATION":
                    errors += 1
                    logger.error(f"  [PHASE 6] {rec['symbol']}: validation failed, no exit/stop coverage this run - {rec.get('error')}")
                    continue

                if rec["action"] == "EARLY_EXIT":
                    if dry_run:
                        # In dry-run, just count (don't execute)
                        exit_count += 1
                        if verbose:
                            logger.info(f"  [DRY-RUN] {rec['symbol']}: {rec['action']} ({rec['action_reason']})")
                    else:
                        result = executor.exit_trade(
                            trade_id=rec["trade_id"],
                            exit_price=rec["current_price"],
                            exit_reason=rec["action_reason"],
                            exit_fraction=1.0,
                            exit_stage="early_exit",
                        )
                        if "success" not in result or result["success"] is None:
                            raise RuntimeError(
                                f"Early exit result missing 'success' field. Got keys: {list(result.keys())}"
                            )
                        if result["success"]:
                            exit_count += 1
                            if verbose:
                                logger.info(f"  EARLY EXIT: {result['message']}")
                        else:
                            errors += 1
                elif rec["action"] == "RAISE_STOP" and rec.get("new_stop_recommended") is not None:
                    if dry_run:
                        # In dry-run, just count (don't write to DB)
                        stop_raises += 1
                        if verbose:
                            logger.info(
                                f"  [DRY-RUN] RAISED STOP {rec['symbol']}: ${rec['active_stop']:.2f} -> ${rec['new_stop_recommended']:.2f}"
                            )
                    else:
                        try:
                            with DatabaseContext("write") as cur:
                                acquire_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                                try:
                                    cur.execute(
                                        "UPDATE algo_positions SET current_stop_price = %s "
                                        "WHERE position_id = %s AND status = %s",
                                        (
                                            rec["new_stop_recommended"],
                                            rec["position_id"],
                                            PositionStatus.OPEN.value,
                                        ),
                                    )
                                    # rowcount guards against silently counting a no-op as a success -
                                    # e.g. the position closed between Phase 3 computing this
                                    # recommendation and Phase 6 executing it (status != 'open' by
                                    # then), in which case the WHERE clause matches nothing but
                                    # execute() itself doesn't raise.
                                    if cur.rowcount == 0:
                                        errors += 1
                                        logger.warning(
                                            f"  Stop-raise no-op for {rec['symbol']}: position "
                                            f"{rec['position_id']} not found or no longer open"
                                        )
                                    else:
                                        stop_raises += 1
                                        if verbose:
                                            logger.info(
                                                f"  RAISED STOP {rec['symbol']}: ${rec['active_stop']:.2f} -> ${rec['new_stop_recommended']:.2f}"
                                            )
                                finally:
                                    release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                        except (RuntimeError, ValueError, TypeError) as e:
                            errors += 1
                            logger.error(f"  Stop-raise failed for {rec['symbol']}: {e}")
            except (RuntimeError, ValueError, TypeError, AttributeError) as e:
                errors += 1
                if "symbol" not in rec:
                    logger.critical(
                        f"[PHASE 6 CRITICAL] Position recommendation missing 'symbol' field. "
                        f"Cannot log which position failed. Recommendation keys: {list(rec.keys())}. "
                        f"Phase 3 produced invalid recommendation record. Cannot proceed with partial error logging. "
                        f"Error was: {e}"
                    )
                    raise RuntimeError(
                        "Position recommendation missing 'symbol' field - phase data contract violated. "
                        "Cannot safely log or recover from errors."
                    ) from e
                logger.error(f"  Error on {rec['symbol']}: {e}")

        # 4b. Exit engine - tiered targets, stops, time, Minervini break
        if not dry_run and executor is not None:
            engine = ExitEngine(config)
            engine_exits, engine_stop_raises, engine_errors, engine_forced_closes_no_price = engine.check_and_execute_exits(run_date)
            exit_count += engine_exits
            # CRITICAL FIX: engine_exits used to also include the engine's own internal
            # stop-raise-only outcomes (fraction=0, no shares sold), which got summed into
            # exit_count while this phase's separate `stop_raises` counter (from the
            # Phase-3-recommendation path above) stayed unrelated - so this summary line
            # could read "16 exits, 0 stop-raises" when 0 positions actually closed and
            # all 16 were stop-raises. Now added to the same counter its name promises.
            stop_raises += engine_stop_raises
            # CRITICAL FIX: check_and_execute_exits() catches per-trade exceptions
            # internally (logs "Exit check failed for X" and moves on to the next
            # position) so a real failure never raised past this call - it just
            # silently produced no exit/stop check for that position this run. This
            # count was previously discarded entirely, so the phase always reported
            # "0 errors" and status "ok" no matter how many positions failed their
            # exit evaluation (confirmed against a live run's log showing 8 logged
            # "Exit check failed" errors alongside a "0 errors" Phase 6 summary).
            errors += engine_errors
        elif dry_run:
            # In dry-run mode, log what the exit engine WOULD have checked
            logger.info("[DRY-RUN] Exit engine checks (tiered targets/stops/time) would run, but execution skipped")

        # CRITICAL FIX: status was hardcoded "success"/"ok" below regardless of `errors`,
        # so a run where every open position failed its exit/stop check still reported
        # a clean success - operators had no signal to go look. Positions that error here
        # get no exit/stop coverage for this run (see check_and_execute_exits errors above).

        # DRY-RUN: Always degraded (no real execution), but include counts of what would happen
        # LIVE: Degraded if errors, success otherwise
        if dry_run:
            phase_status = "degraded"
            detail_text = f"DRY-RUN: execution skipped (no real trades) - would have: {exit_count} exits, {stop_raises} stop-raises"
        else:
            phase_status = "degraded" if errors > 0 else "success"
            detail_text = f"{exit_count} exits, {stop_raises} stop-raises, {engine_forced_closes_no_price} forced_closes_no_price, {errors} errors"
            if errors > 0:
                # Exit-check failures mean open positions lost stop/target/time-exit coverage
                # for this run - unlike phase2 (circuit breakers) and phase3 (position monitor),
                # this phase previously never used the `alerts` param it's handed, so a degraded
                # exit-execution status was visible only to something polling
                # orchestrator_execution_log, never pushed to an operator. Per-trade detail is in
                # algo_exit_check_errors (see exit_engine.py's check_and_execute_exits).
                alerts.send_position_alert(
                    "PORTFOLIO",
                    "EXIT_CHECK_FAILURES",
                    f"{errors} position(s) failed exit/stop evaluation this run - "
                    f"see algo_exit_check_errors for detail",
                    {"errors": errors, "exits": exit_count, "stop_raises": stop_raises, "forced_closes_no_price": engine_forced_closes_no_price},
                )

        log_phase_result_fn(
            6,
            "exit_execution",
            phase_status,
            detail_text,
        )
        # exits_executed/success_rate: the health dashboard (dashboard/panels/health.py,
        # Phase 6 detail row) reads these exact keys, but this dict only ever had
        # exits/stop_raises/errors - "exits_executed" never matched "exits" so it always
        # rendered nothing. avg_profit/symbols_exited are deliberately NOT added here:
        # ExitEngine.check_and_execute_exits() (the tiered target/stop/time exit path,
        # likely most actual exits) returns only a bare int count with no per-exit
        # symbol/profit detail exposed to this phase, so computing those two fields only
        # from the exposure-action/position-rec exit loops above would silently exclude
        # the majority of real exits - a fabricated-looking number is worse than no number.
        total_exit_attempts = exit_count + errors
        success_rate = (exit_count / total_exit_attempts * 100) if total_exit_attempts > 0 else None
        result_data = {
            "exits": exit_count,
            "exits_executed": exit_count,
            "stop_raises": stop_raises,
            "errors": errors,
            "success_rate": success_rate,
        }
        # Validate schema contract before returning
        from algo.orchestrator.phase_data_contract import validate_phase_data

        validate_phase_data(6, result_data)

        # DRY-RUN: Return degraded status with what-would-happen counts
        # LIVE: Return ok/degraded based on errors
        if dry_run:
            return PhaseResult(
                6,
                "exit_execution",
                "degraded",
                result_data,
                False,
                f"DRY-RUN: {exit_count} exits and {stop_raises} stop-raises would execute",
            )
        else:
            return PhaseResult(
                6,
                "exit_execution",
                "degraded" if errors > 0 else "ok",
                result_data,
                False,
                f"{errors} position(s) failed exit/stop evaluation this run" if errors > 0 else None,
            )

    except (psycopg2.DatabaseError, psycopg2.OperationalError, DatabaseError) as e:
        log_phase_result_fn(6, "exit_execution", "error", str(e))
        return PhaseResult(
            6,
            "exit_execution",
            "halted",
            {"status": "halted", "reason": f"Exit execution error: {str(e)[:100]}", "exits_executed": 0},
            True,
            str(e),
        )
    except Exception as e:
        logger.critical(f"[PHASE 6] Unexpected error during exit execution: {type(e).__name__}: {str(e)[:200]}")
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        log_phase_result_fn(6, "exit_execution", "error", error_msg)
        return PhaseResult(
            6,
            "exit_execution",
            "halted",
            {"status": "halted", "reason": error_msg, "exits_executed": 0},
            True,
            error_msg,
        )
