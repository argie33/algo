#!/usr/bin/env python3

import logging
import traceback
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
        execution_mode_check = config.get("execution_mode", "paper")
        # CRITICAL FIX: Require explicit config - fail-fast if missing
        # No silent fallback to False (which would attempt live trading)
        if "alpaca_paper_trading" not in config:
            raise ValueError(
                "[PHASE 6] Config missing 'alpaca_paper_trading'. "
                "Trading mode must be explicit (paper vs live). "
                "Check algo_config table has this key."
            )
        alpaca_paper_trading = config["alpaca_paper_trading"]
        is_paper_mode = execution_mode_check in ("paper", "auto") or alpaca_paper_trading

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
            log_phase_result_fn(6, "exit_execution", "success", "DRY-RUN: execution skipped")
            return PhaseResult(6, "exit_execution", "ok", {}, False, None)

        # ISSUE #4 FIX: Check if paper mode is active before initializing TradeExecutor
        if is_paper_mode:
            logger.info(
                f"[PHASE 6] Paper trading mode active (execution_mode={execution_mode_check}, "
                f"alpaca_paper_trading={alpaca_paper_trading}). Exit orders will execute against paper account."
            )

        # Initialize TradeExecutor, gracefully handle missing credentials in paper mode
        try:
            executor = TradeExecutor(config)
        except ValueError as e:
            if "credentials not found" in str(e).lower() or "credentials" in str(e).lower():
                # In paper trading mode, gracefully skip execution if credentials missing
                execution_mode = config.get("execution_mode", "paper")
                if execution_mode in ("paper", "auto"):
                    logger.warning(
                        f"[PHASE 6] Alpaca credentials missing - skipping exit execution in {execution_mode} mode. "
                        "Open positions will remain unchanged; only database updates (stop raises, etc.) will proceed."
                    )
                    log_phase_result_fn(6, "exit_execution", "success", f"Broker unavailable - {execution_mode} mode")
                    return PhaseResult(6, "exit_execution", "ok", {}, False, None)
                else:
                    # Live trading mode requires credentials
                    raise RuntimeError(f"[PHASE 6 CRITICAL] Live trading mode requires Alpaca credentials: {e}") from e
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

                elif action["action"] == "tighten_stop":
                    try:
                        with DatabaseContext("write") as cur:
                            acquire_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                            try:
                                cur.execute(
                                    "UPDATE algo_positions SET current_stop_price = %s WHERE position_id = %s",
                                    (action["new_stop"], action["position_id"]),
                                )
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
                symbol = action.get("symbol", "UNKNOWN")
                logger.error(f"  Error on exposure action {symbol}: {e}")

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
                symbol = rec.get("symbol", "UNKNOWN")
                logger.error(f"  Error on {symbol}: {e}")

        # 4b. Exit engine - tiered targets, stops, time, Minervini break
        if not dry_run:
            engine = ExitEngine(config)
            engine_exits = engine.check_and_execute_exits(run_date)
            exit_count += engine_exits

        log_phase_result_fn(
            4,
            "exit_execution",
            "success",
            f"{exit_count} exits, {stop_raises} stop-raises, {errors} errors",
        )
        return PhaseResult(
            4,
            "exit_execution",
            "ok",
            {"exits": exit_count, "stop_raises": stop_raises, "errors": errors},
            False,
            None,
        )

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        traceback.print_exc()
        log_phase_result_fn(6, "exit_execution", "error", str(e))
        return PhaseResult(6, "exit_execution", "halted", {}, True, str(e))
