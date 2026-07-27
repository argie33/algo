#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.exceptions import ValidationError
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
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

        # In paper mode, skip all position_recs validation - Phase 3 intentionally returns empty
        if is_paper_mode:
            logger.info("[PHASE 6] Paper trading mode active - skipping position monitor validation")
            # Continue to exit engine execution (positions still need monitoring for circuit breakers)
        else:
            # Live mode: Detect Phase 3 crash - if position monitor errored, position_recs is []
            # but we may have real open positions. This is a critical data integrity error.
            if position_recs is None:
                msg = (
                    "[PHASE 6 CRITICAL] position_recs not set - Phase 3 did not execute properly. "
                    "Cannot proceed with exit execution without position monitor recommendations."
                )
                logger.critical(msg)
                raise RuntimeError(msg)
            elif len(position_recs) == 0:
                # Check if open positions exist but phase 3 returned empty
                try:
                    with DatabaseContext("read") as cur_chk:
                        cur_chk.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                        row = cur_chk.fetchone()
                        if row is None or row[0] is None:
                            raise RuntimeError("Open position count query failed")
                        open_count = row[0]
                    if open_count > 0:
                        msg = (
                            f"[PHASE 6 CRITICAL] position_recs is empty but {open_count} open positions exist. "
                            f"Phase 3 likely crashed without recommendations. "
                            f"Cannot execute safety exits without position monitor evaluation. "
                            f"Open positions remain unevaluated for exit conditions."
                        )
                        logger.critical(msg)
                        raise RuntimeError(msg)
                except RuntimeError:
                    raise
                except Exception as e:
                    msg = (
                        f"[PHASE 6 CRITICAL] Position count check failed: {e}. "
                        f"Cannot verify if open positions need exit evaluation."
                    )
                    logger.critical(msg)
                    raise RuntimeError(msg) from e

        # In dry-run mode, skip TradeExecutor initialization (no Alpaca credentials needed)
        if dry_run:
            logger.info("[DRY-RUN] Phase 6: Skipping trade execution (dry-run mode)")
            log_phase_result_fn(6, "exit_execution", "degraded", "DRY-RUN: execution skipped (no real trades)")
            return PhaseResult(
                6,
                "exit_execution",
                "degraded",
                {},
                False,
                "DRY-RUN: exit execution skipped (no real trades placed)",
            )

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
                raise
        exit_count = 0
        stop_raises = 0
        errors = 0

        # 4a-prime. Apply exposure-policy actions FIRST (highest priority)
        for action in exposure_actions:
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
                    continue

                if action["action"] == "force_exit":
                    # CRITICAL: Current price is mandatory for force exits
                    # Cannot execute exit without price - would corrupt P&L reporting
                    try:
                        with DatabaseContext("read") as cur_tmp:
                            cur_tmp.execute(
                                "SELECT current_price FROM algo_positions WHERE position_id = %s",
                                (action["position_id"],),
                            )
                            row_tmp = cur_tmp.fetchone()
                            if row_tmp is None or row_tmp[0] is None:
                                raise RuntimeError(
                                    f"[FORCE-EXIT] Current price unavailable for position {action['position_id']}. "
                                    "Cannot execute force exit without price."
                                )
                            cur_price = float(row_tmp[0])
                            if cur_price <= 0:
                                raise RuntimeError(
                                    f"[FORCE-EXIT] Invalid current price {cur_price} for position {action['position_id']}. "
                                    "Cannot execute exit with non-positive price."
                                )
                    except (RuntimeError, TypeError, ValueError) as e:
                        logger.critical(f"  CRITICAL: force_exit cannot proceed: {e}")
                        errors += 1
                        continue

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
                        raise
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

                elif action["action"] == "tighten_stop":
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
                if dry_run:
                    if verbose:
                        logger.info(f"  [DRY-RUN] {rec['symbol']}: {rec['action']} ({rec['action_reason']})")
                    continue

                if rec["action"] == "EARLY_EXIT":
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
        if not dry_run:
            engine = ExitEngine(config)
            engine_exits, engine_stop_raises, engine_errors = engine.check_and_execute_exits(run_date)
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

        # CRITICAL FIX: status was hardcoded "success"/"ok" below regardless of `errors`,
        # so a run where every open position failed its exit/stop check still reported
        # a clean success - operators had no signal to go look. Positions that error here
        # get no exit/stop coverage for this run (see check_and_execute_exits errors above).
        phase_status = "degraded" if errors > 0 else "success"
        log_phase_result_fn(
            6,
            "exit_execution",
            phase_status,
            f"{exit_count} exits, {stop_raises} stop-raises, {errors} errors",
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
        return PhaseResult(
            6,
            "exit_execution",
            "degraded" if errors > 0 else "ok",
            result_data,
            False,
            f"{errors} position(s) failed exit/stop evaluation this run" if errors > 0 else None,
        )

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        log_phase_result_fn(6, "exit_execution", "error", str(e))
        return PhaseResult(
            6,
            "exit_execution",
            "halted",
            {"status": "halted", "reason": f"Database error in exit execution: {str(e)[:100]}", "exits_executed": 0},
            True,
            str(e),
        )
