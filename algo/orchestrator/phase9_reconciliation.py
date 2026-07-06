#!/usr/bin/env python3

import json
import logging
import traceback
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.orchestrator.phase_result import PhaseResult
from utils.db.advisory_locks import (
    ALGO_AUDIT_LOG_LOCK_ID,
    ALGO_METRICS_DAILY_LOCK_ID,
    ALGO_POSITIONS_LOCK_ID,
    ALGO_TRADES_LOCK_ID,
    acquire_advisory_lock,
    release_advisory_lock,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def _run_reconciliation_step(
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable[..., Any],
    dry_run: bool,
) -> tuple[bool, dict[str, Any]]:
    """Run initial reconciliation step and validate results."""
    from algo.infrastructure.reconciliation import DailyReconciliation

    recon = DailyReconciliation(config)
    result = recon.run_daily_reconciliation(run_date, dry_run=dry_run)

    if "success" not in result:
        raise ValueError(
            "Reconciliation result missing 'success' field. "
            f"Available keys: {list(result.keys())}. "
            "Check DailyReconciliation.run_daily_reconciliation() implementation."
        )

    reconciliation_succeeded = result["success"]
    status = "success" if reconciliation_succeeded else "error"

    if reconciliation_succeeded:
        required_keys = ["portfolio_value", "positions", "unrealized_pnl"]
        missing_keys = [k for k in required_keys if k not in result or result[k] is None]
        if missing_keys:
            raise ValueError(f"Reconciliation succeeded but missing critical data: {missing_keys}")

        summary = (
            f"Portfolio ${result['portfolio_value']:,.2f}, "
            f"{result['positions']} positions, "
            f"unrealized P&L ${result['unrealized_pnl']:+,.2f}"
        )
    else:
        error_msg = result.get("error")
        if not error_msg:
            raise ValueError(
                f"CRITICAL: Reconciliation failed but error message missing. "
                f"Result keys: {list(result.keys())}. "
                f"Cannot proceed without understanding why reconciliation failed."
            )
        summary = error_msg
    log_phase_result_fn(9, "reconciliation", status, summary)
    return reconciliation_succeeded, result


def _validate_pnl_step(
    recon: Any,
    result: dict[str, Any],
    log_phase_result_fn: Callable[..., Any],
) -> tuple[str, str]:
    """Validate P&L and log results."""
    pnl_validation_status = "warn"
    pnl_validation_summary = "N/A"
    try:
        account_data = recon.broker.fetch_account()
        if account_data and result.get("success"):
            # FALLBACK SEQUENCE (explicit, fail-fast if all missing):
            # 1. Try 'equity' field (primary broker account equity)
            # 2. Try 'portfolio_value' field (fallback if equity missing)
            # 3. Raise if both missing
            broker_equity = account_data.get("equity")
            if broker_equity is None:
                broker_equity = account_data.get("portfolio_value")
            if broker_equity is None:
                logger.error(
                    "[PHASE 9 P&L VALIDATION] CRITICAL: Broker data missing both 'equity' and "
                    "'portfolio_value' fields. Available keys: " + str(list(account_data.keys()))
                )
                raise ValueError(
                    "Broker data missing required equity/portfolio_value fields. "
                    "Cannot validate P&L reconciliation without broker account balance."
                )

            if "portfolio_value" not in result:
                raise ValueError(
                    "Reconciliation succeeded but missing portfolio_value (required for P&L validation). "
                    f"Available keys: {list(result.keys())}"
                )
            local_equity = result["portfolio_value"]

            pnl_check = recon.validate_pnl(broker_equity, local_equity)
            pnl_validation_status = pnl_check["status"]
            pnl_validation_summary = pnl_check["message"]

            if pnl_check["status"] == "ok":
                logger.info(f"[PHASE 7 P&L VALIDATION] {pnl_check['message']}")
            elif pnl_check["status"] == "alert":
                logger.warning(f"[PHASE 7 P&L VALIDATION] {pnl_check['message']}")
            else:  # critical
                logger.critical(f"[PHASE 7 P&L VALIDATION] {pnl_check['message']}")
        else:
            pnl_validation_summary = "Skipped (reconciliation failed or no Broker data)"
    except Exception as e:
        logger.error(f"[PHASE 7] P&L validation failed: {e}")
        pnl_validation_summary = f"error: {str(e)[:60]}"
    finally:
        log_phase_result_fn(9, "pnl_validation", pnl_validation_status, pnl_validation_summary)
    return pnl_validation_status, pnl_validation_summary


def _audit_exit_prices_step(
    recon: Any,
    log_phase_result_fn: Callable[..., Any],
) -> None:
    """Audit stale estimated exit prices."""
    try:
        with DatabaseContext("read") as audit_cur:
            stale_audit = recon.audit_stale_estimated_prices(audit_cur)
            status = stale_audit.get("status")
            if status is None:
                if stale_audit.get("implementation_required"):
                    logger.warning("[PHASE 9] Exit price audit not yet implemented — skipping stale price check")
                    return
                raise ValueError(f"Exit price audit result missing 'status' field. Keys: {list(stale_audit.keys())}")

            if status != "OK":
                msg = stale_audit.get("message")
                if msg is None:
                    raise ValueError(
                        f"Exit price audit status '{status}' but message missing. Keys: {list(stale_audit.keys())}"
                    )
                logger.warning(f"[PHASE 7 AUDIT] Stale estimated prices detected: {msg}")
                log_phase_result_fn(9, "exit_reconciliation_audit", "warn", msg)
            else:
                logger.info("[PHASE 7 AUDIT] All exit prices reconciled properly")
    except (psycopg2.DatabaseError, psycopg2.OperationalError, KeyError) as e:
        logger.error(f"[PHASE 7] Exit price audit failed: {e}")


def _populate_signal_trade_performance(log_phase_result_fn: Callable[..., Any]) -> int:
    """Populate signal trade performance from closed trades."""
    from algo.signals.trade_performance import SignalTradePerformancePopulator

    stpp_result = {"success": False, "trades_processed": 0}
    try:
        stpp = SignalTradePerformancePopulator()
        stpp_result = stpp.populate_closed_trades(lookback_days=7)
        trades_processed = stpp_result.get("trades_processed")
        if trades_processed is None:
            raise ValueError("Signal trade performance populator returned None for trades_processed count")
        logger.info(f"Signal trade performance: {stpp_result.get('message', 'N/A')}")
        if stpp_result.get("ic_values"):
            logger.info(f"  IC values computed: {stpp_result['ic_values']}")
    except Exception as e:
        logger.warning(f"Signal trade performance failed (numpy/scipy not available): {e}")
        trades_processed = 0  # Fall back to 0 only if exception occurred

    if trades_processed is None:
        raise ValueError("Signal trade performance: trades_processed count is missing")
    log_phase_result_fn(
        7,
        "signal_attribution",
        "success" if stpp_result.get("success") else "warn",
        f"{trades_processed} trades processed",
    )
    return trades_processed


def _compute_signal_attribution(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> dict[str, Any]:
    """Compute signal attribution IC."""
    from algo.signals.attribution import SignalAttributionEngine

    attr_result = {}
    try:
        attribution = SignalAttributionEngine()
        attr_result = attribution.compute_ic(run_date, lookback_trades=40)
        logger.info(f"Signal attribution: IC computed for {len(attr_result)} components")
        for comp, ic_data in attr_result.items():
            ic_value = ic_data.get("ic_value")
            ic_pvalue = ic_data.get("ic_pvalue")
            if ic_value is None or ic_pvalue is None:
                if ic_data.get("data_unavailable"):
                    reason = ic_data.get("reason", "unknown")
                    logger.warning(f"[ATTRIBUTION] {comp} IC unavailable: {reason} — skipping")
                    continue
                logger.critical(f"CRITICAL: IC value missing for component {comp}. Cannot validate signal quality.")
                raise ValueError(f"IC calculation failed for {comp}: missing 'ic_value'. Signal validation incomplete.")
            logger.info(f"  {comp}: IC={ic_value:.3f}, pval={ic_pvalue:.3f}")
        if attr_result:
            attribution.persist(run_date, attr_result)
    except ImportError as e:
        error_msg = (
            f"CRITICAL: Signal attribution requires scipy/numpy (not available): {e}. "
            f"Cannot validate signal quality without these dependencies. "
            f"Install: pip install scipy numpy"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    except ValueError as e:
        error_msg = (
            f"CRITICAL: Signal attribution validation failed: {e}. "
            f"Cannot proceed with trading without signal quality validation. "
            f"Insufficient trades or invalid signal data indicates a system error."
        )
        logger.critical(error_msg)
        raise ValueError(error_msg) from e
    except Exception as e:
        error_msg = f"CRITICAL: Signal attribution failed unexpectedly: {e}"
        logger.critical(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

    log_phase_result_fn(
        7,
        "ic_computation",
        "success" if attr_result else "warn",
        f"{len(attr_result)} components analyzed",
    )
    return attr_result


def _generate_daily_report(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    """Generate and validate daily finance report."""
    from algo.reporting import DailyFinanceReport

    try:
        daily_report = DailyFinanceReport()
        report = daily_report.generate(run_date)
        report_text = daily_report.format_text(report)
        logger.info(f"\n{report_text}")
    except Exception as e:
        logger.error(
            f"Daily report generation failed (could not generate): {e}",
            exc_info=True,
        )
        log_phase_result_fn(9, "daily_report", "warn", f"generation error: {str(e)[:60]}")
        return

    # Validate critical report data before use
    try:
        if not report or "portfolio" not in report:
            raise ValueError("Daily report generated but missing portfolio data")
        portfolio_data = report.get("portfolio")
        if (
            portfolio_data is None
            or "current_value" not in portfolio_data
            or portfolio_data.get("current_value") is None
        ):
            raise ValueError("Portfolio data missing current_value")
        if (
            portfolio_data is None
            or "daily_pnl_pct" not in portfolio_data
            or portfolio_data.get("daily_pnl_pct") is None
        ):
            raise ValueError("Portfolio data missing daily_pnl_pct")

        # Log to algo_audit_log for historical tracking
        try:
            with DatabaseContext("write") as cur:
                acquire_advisory_lock(cur, ALGO_AUDIT_LOG_LOCK_ID, "algo_audit_log")
                try:
                    cur.execute(
                        """
                        INSERT INTO algo_audit_log (
                            action_type, action_date, symbol, details, created_at
                        ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        (
                            "daily_report",
                            run_date,
                            "PORTFOLIO",
                            json.dumps(report),
                        ),
                    )
                finally:
                    release_advisory_lock(cur, ALGO_AUDIT_LOG_LOCK_ID, "algo_audit_log")
        except (psycopg2.DatabaseError, psycopg2.OperationalError, RuntimeError) as e:
            logger.critical(f"[AUDIT_FAILURE] Could not log daily report to audit log: {e}")
            logger.warning(f"[PHASE 9] Audit log write failed but continuing: {str(e)[:100]}")
            # Don't raise - allow Phase 9 to continue to risk metrics and other critical steps

        # Portfolio data must be present for daily reporting
        if not portfolio_data:
            logger.critical("CRITICAL: Portfolio data missing from daily report. Cannot report account status.")
            raise ValueError("Daily report missing portfolio_data. Cannot calculate current value or P&L.")
        current_val = portfolio_data.get("current_value")
        pnl_pct = portfolio_data.get("daily_pnl_pct")
        if current_val is None:
            logger.critical("CRITICAL: Portfolio current_value missing from daily report.")
            raise ValueError("Daily report: current_value missing. Cannot report account status.")
        if pnl_pct is None:
            logger.critical("CRITICAL: Portfolio daily_pnl_pct missing from daily report.")
            raise ValueError("Daily report: daily_pnl_pct missing. Cannot report P&L.")
        log_phase_result_fn(
            7,
            "daily_report",
            "success",
            f"Portfolio ${current_val if isinstance(current_val, str) else f'{current_val:,.0f}'}, P&L {pnl_pct if isinstance(pnl_pct, str) else f'{pnl_pct:+.2f}%'}",
        )
    except ValueError as e:
        logger.error(f"Daily report validation failed (generated but data incomplete): {e}")
        log_phase_result_fn(9, "daily_report", "warn", f"validation error: {str(e)[:60]}")


def _compute_performance_metrics(config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    """Compute and log live performance metrics. Degrades gracefully if Sharpe ratio unavailable."""
    from algo.reporting import LivePerformance

    perf_status = "warn"
    perf_summary = "N/A"
    try:
        perf = LivePerformance(config)
        perf_report = perf.generate_daily_report(run_date)
        if perf_report and perf_report.get("status") == "ok":
            perf_status = "success"
            sharpe = perf_report.get("rolling_sharpe_252d")
            win_rate = perf_report.get("win_rate_50t")
            expectancy = perf_report.get("expectancy")
            if sharpe is None or win_rate is None or expectancy is None:
                missing = [
                    k for k in ["rolling_sharpe_252d", "win_rate_50t", "expectancy"] if perf_report.get(k) is None
                ]
                logger.warning(f"Performance metrics unavailable: {missing}. Portfolio history may be too short.")
                perf_status = "warn"
                perf_summary = f"incomplete: {', '.join(missing)}"
            else:
                perf_summary = f"Sharpe {sharpe}, Win rate {win_rate}%, Expectancy {expectancy}"
        elif perf_report:
            perf_message = perf_report.get("message")
            if not perf_message:
                logger.warning("Performance report failed without error message.")
                perf_status = "warn"
                perf_summary = "generation failed"
            else:
                perf_status = "warn"
                perf_summary = perf_message
        else:
            logger.warning("Performance report generation returned None. Portfolio history may be insufficient.")
            perf_status = "warn"
            perf_summary = "insufficient history"
    except (RuntimeError, ValueError) as e:
        logger.warning(f"Performance metrics computation failed (degrading gracefully): {e}")
        perf_status = "warn"
        perf_summary = f"computation failed: {str(e)[:50]}"
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"Performance metrics database error: {e}")
        perf_status = "warn"
        perf_summary = f"db error: {str(e)[:50]}"
    except Exception as e:
        logger.warning(f"Unexpected error in performance metrics: {e}")
        perf_status = "warn"
        perf_summary = f"error: {str(e)[:50]}"
    finally:
        log_phase_result_fn(9, "performance", perf_status, perf_summary)


def _compute_risk_metrics(config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    """Compute and log risk metrics."""
    from algo.risk import ValueAtRisk

    risk_status = "warn"
    risk_summary = "N/A"
    try:
        risk = ValueAtRisk(config)
        risk_report = risk.generate_daily_risk_report(run_date)
        if risk_report and risk_report.get("status") == "ok":
            risk_status = "success"
            var_metrics = risk_report.get("var_metrics")
            concentration = risk_report.get("concentration")

            if "beta_exposure" not in risk_report:
                raise ValueError(
                    "Risk report status=ok but missing required 'beta_exposure' field. "
                    "When risk calculation succeeds (status=ok), beta_exposure must be present. "
                    "This indicates incomplete risk analysis."
                )
            beta_exposure = risk_report["beta_exposure"]

            if "alerts" not in risk_report:
                raise ValueError(
                    "Risk report status=ok but missing required 'alerts' field. "
                    "When risk calculation succeeds (status=ok), alerts must be present. "
                    "This indicates incomplete risk analysis."
                )
            alerts = risk_report["alerts"]

            # Build summary from whatever metrics are available
            summary_parts: list[str] = []
            if var_metrics is not None:
                var_pct = var_metrics.get("var_pct")
                if var_pct is not None:
                    summary_parts.append(f"VaR {var_pct}%")
                else:
                    logger.warning(f"Risk metrics missing 'var_pct' field. Available keys: {list(var_metrics.keys())}")
            else:
                # VaR unavailable due to insufficient historical data — row was still inserted with NULLs
                logger.warning(
                    "Risk report status=ok but var_metrics unavailable (insufficient historical data). "
                    "Row inserted with NULL VaR values — will populate as data accumulates."
                )
            if concentration is not None:
                conc_pct = concentration.get("top_5_concentration_pct")
                if conc_pct is not None:
                    summary_parts.append(f"Conc {conc_pct:.1f}%")
            beta_val = beta_exposure.get("portfolio_beta")
            if beta_val is not None:
                summary_parts.append(f"beta={beta_val:.2f}")
            alerts_count = len(alerts)
            if alerts_count:
                summary_parts.append(f"{alerts_count} alerts")
            risk_summary = ", ".join(summary_parts) if summary_parts else "row inserted (no metrics available yet)"
        elif risk_report:
            risk_summary = risk_report.get("message", "insufficient data")
        else:
            risk_summary = "failed to generate report"
    except Exception as e:
        risk_summary = f"error: {str(e)[:60]}"
    finally:
        log_phase_result_fn(9, "risk_metrics", risk_status, risk_summary)


def _update_daily_metrics(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    """Update algo_metrics_daily with daily trade results."""
    try:
        row_data = None
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_actions,
                    SUM(CASE WHEN action_type = 'BUY' THEN 1 ELSE 0 END) as entries,
                    SUM(CASE WHEN action_type = 'SELL' THEN 1 ELSE 0 END) as exits,
                    AVG(CAST(details->>'score' AS FLOAT)) as avg_signal_score
                FROM algo_audit_log
                WHERE DATE(created_at) = %s
            """,
                (run_date,),
            )
            row_data = cur.fetchone()

        if row_data:
            total_actions, entries, exits, avg_score = row_data
            total_actions = total_actions if total_actions is not None else 0
            entries = entries if entries is not None else 0
            exits = exits if exits is not None else 0

            with DatabaseContext("write") as write_cur:
                acquire_advisory_lock(write_cur, ALGO_METRICS_DAILY_LOCK_ID, "algo_metrics_daily")
                try:
                    write_cur.execute(
                        """
                        INSERT INTO algo_metrics_daily (date, total_actions, entries, exits, avg_signal_score)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (date) DO UPDATE SET
                            total_actions = EXCLUDED.total_actions,
                            entries = EXCLUDED.entries,
                            exits = EXCLUDED.exits,
                            avg_signal_score = EXCLUDED.avg_signal_score
                    """,
                        (
                            run_date,
                            total_actions,
                            entries,
                            exits,
                            avg_score,
                        ),
                    )
                finally:
                    release_advisory_lock(write_cur, ALGO_METRICS_DAILY_LOCK_ID, "algo_metrics_daily")
            metrics_status = "success"
            metrics_summary = f"{total_actions} actions, {entries} entries, {exits} exits"
            logger.info(f"Updated algo_metrics_daily: {metrics_summary}")
        else:
            logger.info("No trades recorded today (metrics not updated)")
            metrics_status = "warn"
            metrics_summary = "No trades recorded"
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"Failed to update algo_metrics_daily: {e}")
        metrics_summary = f"error: {str(e)[:60]}"
        metrics_status = "warn"
    finally:
        log_phase_result_fn(9, "metrics_update", metrics_status, metrics_summary)


def _optimize_weights(config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]) -> dict[str, Any]:
    """Run weight optimization."""
    from algo.orchestration import RegimeManager as _RegimeManager
    from algo.orchestration import WeightOptimizer

    opt_result: dict[str, Any] = {"changes": []}
    try:
        _current_regime = _RegimeManager().get_current_regime(run_date)
        optimizer = WeightOptimizer(config)
        opt_result = optimizer.apply(run_date, regime=_current_regime, dry_run=False)
        if opt_result.get("changes"):
            logger.info(f"Weight optimization: {len(opt_result['changes'])} changes applied")
            for change in opt_result["changes"]:
                logger.info(f"  {change['component']}: {change['old_weight']}% -> {change['new_weight']}%")
        else:
            logger.info("Weight optimization: no changes (insufficient trades or weights stable)")
    except ValueError as e:
        error_msg = (
            f"CRITICAL: Weight optimization failed: {e}. "
            f"Cannot optimize portfolio weights without sufficient trade history. "
            f"Portfolio exposure remains unoptimized and unvalidated."
        )
        logger.critical(error_msg)
        raise ValueError(error_msg) from e
    except ImportError as e:
        error_msg = (
            f"CRITICAL: Weight optimization requires scipy/numpy (not available): {e}. "
            f"Cannot optimize portfolio without mathematical dependencies. "
            f"Install: pip install scipy numpy"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"CRITICAL: Weight optimization failed unexpectedly: {e}"
        logger.critical(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

    if opt_result is None:
        error_msg = (
            "Weight optimization failed or did not complete, reconciliation cannot proceed. "
            "WeightOptimizer.apply() returned None instead of a result dictionary. "
            "This indicates an internal failure in the optimization engine."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # CRITICAL FIX: Explicit check for changes field instead of empty list default
    changes = opt_result.get("changes")
    if changes is None:
        logger.warning("Weight optimization result missing 'changes' field — defaulting to empty list")
        changes = []
    elif not isinstance(changes, list):
        logger.error(f"Weight optimization 'changes' is not a list: {type(changes)}. Defaulting to empty list.")
        changes = []
    log_phase_result_fn(
        7,
        "weight_optimization",
        "success" if opt_result.get("success") else "warn",
        f"{len(changes) if changes else 0} weight changes",
    )
    return opt_result


def _record_closed_positions_exits(
    run_date: _date,
    log_phase_result_fn: Callable[..., Any],
) -> None:
    """Record exits for recently closed positions."""
    try:
        with DatabaseContext("read") as cursor:
            cursor.execute(
                """
                SELECT symbol, avg_entry_price, current_price, quantity
                FROM algo_positions
                WHERE status = 'closed' AND closed_at::date = %s
            """,
                (run_date,),
            )
            closed_positions = cursor.fetchall()

        if closed_positions:
            exits_recorded = 0
            with DatabaseContext("write") as write_cursor:
                acquire_advisory_lock(write_cursor, ALGO_TRADES_LOCK_ID, "algo_trades")
                acquire_advisory_lock(write_cursor, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                try:
                    for (
                        symbol,
                        entry_price,
                        exit_price,
                        quantity,
                    ) in closed_positions:
                        if not exit_price:
                            logger.critical(
                                f"[CRITICAL] Exit price missing for {symbol}: cannot use entry price "
                                f"(${entry_price}) as fallback. This corrupts P&L. Skipping exit record."
                            )
                            continue

                        if entry_price is None or entry_price <= 0:
                            logger.error(f"CRITICAL: Trade {symbol} has invalid entry_price ({entry_price}), skipping")
                            continue
                        pnl = (exit_price - entry_price) * quantity
                        pnl_pct = (exit_price - entry_price) / entry_price * 100

                        sp = f"sp_exit_{symbol.replace('-', '_').replace('.', '_')}"
                        try:
                            write_cursor.execute(f"SAVEPOINT {sp}")
                            write_cursor.execute(
                                """
                                UPDATE algo_trades
                                SET exit_date = %s, exit_price = %s, profit_loss_dollars = %s,
                                    profit_loss_pct = %s, exit_reason = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE trade_id = (
                                    SELECT trade_id FROM algo_trades
                                    WHERE symbol = %s AND exit_date IS NULL
                                    ORDER BY trade_date DESC LIMIT 1
                                )
                            """,
                                (
                                    run_date,
                                    exit_price,
                                    pnl,
                                    pnl_pct,
                                    "Closed position recorded during reconciliation",
                                    symbol,
                                ),
                            )
                            write_cursor.execute(
                                """
                                UPDATE algo_positions
                                SET status = 'CLOSED', current_price = %s, unrealized_pnl = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE symbol = %s
                            """,
                                (exit_price, pnl, symbol),
                            )
                            if write_cursor.rowcount == 0:
                                logger.warning(
                                    f"Position update returned 0 rows for {symbol}. "
                                    f"Position may already be closed or missing."
                                )
                            else:
                                exits_recorded += 1
                            write_cursor.execute(f"RELEASE SAVEPOINT {sp}")
                            logger.info(
                                f"Recorded exit: {symbol} {quantity}sh @ ${exit_price:.2f} on {run_date} "
                                f"(P&L: ${pnl:.2f} / {pnl_pct:.1f}%)"
                            )
                        except (
                            psycopg2.DatabaseError,
                            psycopg2.OperationalError,
                        ) as e:
                            write_cursor.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                            logger.error(f"Failed to record exit for {symbol}: {e}")

                    if exits_recorded > 0:
                        logger.info(f"Recorded {exits_recorded} exits in trade history")
                finally:
                    release_advisory_lock(write_cursor, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                    release_advisory_lock(write_cursor, ALGO_TRADES_LOCK_ID, "algo_trades")
        else:
            logger.info("No closed positions found for exit recording")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(
            f"Failed to record exits in trade history: {e}. "
            "Cannot complete reconciliation without persisting trade exit data."
        ) from e


def run(
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable[..., Any],
    dry_run: bool = False,
) -> PhaseResult:
    """Execute Phase 9: Reconciliation & Snapshot.

    Args:
        config: Configuration object
        run_date: Date for this run
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok' (fail-open), data containing reconciliation results
    """
    try:
        from algo.infrastructure.reconciliation import DailyReconciliation

        try:
            recon = DailyReconciliation(config)
        except ValueError as e:
            # In paper trading mode, gracefully handle missing Alpaca credentials
            if "credentials not found" in str(e).lower() or "credentials" in str(e).lower():
                execution_mode = config.get("execution_mode", "paper")
                if execution_mode in ("paper", "auto"):
                    logger.warning(
                        f"[PHASE 9] Alpaca credentials missing — reconciliation skipped in {execution_mode} mode. "
                        "Portfolio snapshot will be created from database state without broker sync."
                    )
                    # Create basic snapshot without broker reconciliation
                    try:
                        with DatabaseContext("write") as cur:
                            cur.execute("""
                                INSERT INTO algo_portfolio_snapshots (snapshot_date, total_value, cash, positions_count, created_at)
                                SELECT %s, COALESCE(SUM(position_value), 0) + (
                                    SELECT COALESCE(cash_balance, 0) FROM algo_account_balance ORDER BY date DESC LIMIT 1
                                ), COALESCE((SELECT cash_balance FROM algo_account_balance ORDER BY date DESC LIMIT 1), 0),
                                COUNT(*), NOW()
                                FROM algo_positions WHERE status = 'open'
                                ON CONFLICT (snapshot_date) DO UPDATE
                                SET total_value = EXCLUDED.total_value,
                                    cash = EXCLUDED.cash,
                                    positions_count = EXCLUDED.positions_count,
                                    created_at = NOW()
                            """, (run_date,))
                        log_phase_result_fn(9, "portfolio_snapshot", "success", "snapshot created from DB state")
                    except Exception as snapshot_err:
                        logger.warning(f"[PHASE 9] Could not create portfolio snapshot: {snapshot_err}")
                        log_phase_result_fn(9, "portfolio_snapshot", "warn", f"snapshot creation failed: {str(snapshot_err)[:60]}")

                    # Refresh materialized view
                    try:
                        with DatabaseContext("write") as cur:
                            cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
                        logger.info("[PHASE 9] Refreshed algo_positions_with_risk materialized view")
                    except Exception as view_err:
                        logger.warning(f"[PHASE 9] Could not refresh view: {view_err}")

                    # Return partial success
                    log_phase_result_fn(9, "reconciliation", "success", f"Broker unavailable - {execution_mode} mode")
                    return PhaseResult(9, "reconciliation", "ok", {}, False, None)
                else:
                    # Live trading requires credentials
                    raise RuntimeError(f"[PHASE 9 CRITICAL] Live trading requires Alpaca credentials: {e}") from e
            else:
                raise
        reconciliation_succeeded, result = _run_reconciliation_step(config, run_date, log_phase_result_fn, dry_run)

        # CRITICAL: Validate that local P&L matches Broker P&L
        _validate_pnl_step(recon, result, log_phase_result_fn)

        # CRITICAL: Audit for stale estimated exit prices (reconciliation issues)
        _audit_exit_prices_step(recon, log_phase_result_fn)

        # Record exits for recently closed positions (batch operation to avoid N+1 queries)
        _record_closed_positions_exits(run_date, log_phase_result_fn)

        # Step 1: Populate signal_trade_performance from closed trades
        _populate_signal_trade_performance(log_phase_result_fn)

        # Step 2: Compute IC via attribution engine
        _compute_signal_attribution(run_date, log_phase_result_fn)

        # Step 3: Run weight optimization (if enough trades)
        _optimize_weights(config, run_date, log_phase_result_fn)

        # Step 4: Generate institutional daily report
        _generate_daily_report(run_date, log_phase_result_fn)

        # Step 5: Compute and log live performance metrics (always run, even on non-trading days)
        try:
            _compute_performance_metrics(config, run_date, log_phase_result_fn)
        except Exception as e:
            logger.warning(f"[PHASE 9] Performance metrics computation failed: {e}")
            log_phase_result_fn(9, "performance", "warn", f"computation error: {str(e)[:60]}")

        # Step 6: Compute and log risk metrics (always run, even on non-trading days)
        try:
            _compute_risk_metrics(config, run_date, log_phase_result_fn)
        except Exception as e:
            logger.warning(f"[PHASE 9] Risk metrics computation failed: {e}")
            log_phase_result_fn(9, "risk_metrics", "warn", f"computation error: {str(e)[:60]}")

        # Step 7: Update algo_metrics_daily with actual trade results from this run
        try:
            _update_daily_metrics(run_date, log_phase_result_fn)
        except Exception as e:
            logger.warning(f"[PHASE 9] Metrics update failed: {e}")
            log_phase_result_fn(9, "metrics_update", "warn", f"update error: {str(e)[:60]}")

        # Refresh materialized view so positions dashboard reflects current state.
        # This runs after reconciliation updates algo_positions from Broker.
        try:
            with DatabaseContext("write") as cur:
                cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
            logger.info("[PHASE 9] Refreshed algo_positions_with_risk materialized view")
            log_phase_result_fn(
                9,
                "positions_view_refresh",
                "success",
                "algo_positions_with_risk refreshed",
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[PHASE 9] Could not refresh algo_positions_with_risk: {e}")
            log_phase_result_fn(9, "positions_view_refresh", "warn", f"refresh failed: {str(e)[:60]}")

        # Compute circuit breaker metrics and write to circuit_breaker_status table.
        # Runs after reconciliation so algo_portfolio_snapshots has today's data.
        # dashboard /api/algo/circuit-breakers reads from circuit_breaker_status.
        if reconciliation_succeeded:
            try:
                import psycopg2.extras as _extras

                from loaders.compute_circuit_breakers import compute_circuit_breaker_metrics

                with DatabaseContext("write", cursor_factory=_extras.RealDictCursor) as cb_cur:
                    cb_metrics = compute_circuit_breaker_metrics(cb_cur, today=run_date)
                if cb_metrics is None:
                    raise RuntimeError(
                        f"[PHASE 9 CRITICAL] Circuit breaker metrics computation returned None on {run_date}. "
                        "Cannot proceed with reconciliation without circuit breaker state."
                    )
                triggered = cb_metrics.get("triggered_count")
                any_triggered = cb_metrics.get("any_triggered")
                if triggered is None or any_triggered is None:
                    raise RuntimeError(
                        f"[PHASE 9 CRITICAL] Circuit breaker metrics incomplete on {run_date}: "
                        f"triggered_count={triggered}, any_triggered={any_triggered}. "
                        "Check compute_circuit_breaker_metrics() for data quality issues."
                    )
                logger.info(
                    f"[PHASE 9] Circuit breaker metrics written: {triggered} triggered, any_triggered={any_triggered}"
                )
                log_phase_result_fn(
                    9,
                    "circuit_breaker_metrics",
                    "success",
                    f"{triggered} circuit breakers triggered",
                )
            except Exception as e:
                logger.warning(
                    f"[PHASE 9] Circuit breaker metrics failed (non-blocking): {e}. "
                    "circuit_breaker_status table not updated — dashboard CB panel will show stale data."
                )
                log_phase_result_fn(
                    9,
                    "circuit_breaker_metrics",
                    "warn",
                    f"failed: {str(e)[:80]}",
                )

        # Degrade gracefully if reconciliation failed (e.g., broker unavailable in dry-run)
        # Phase 9 is always_run, so it should not cause a halt even if broker is unavailable
        if reconciliation_succeeded:
            data = {
                "portfolio_value": result.get("portfolio_value"),
                "positions": result.get("positions"),
                "unrealized_pnl": result.get("unrealized_pnl"),
                "reconciliation": result,
            }
            phase_status = "ok"
        else:
            # Reconciliation failed (broker unavailable, 401, etc) - degrade gracefully
            # Explicitly extract error message with audit trail for debugging
            error_msg = result.get("reason")
            if error_msg is None:
                error_msg = result.get("error")
            if error_msg is None:
                error_msg = "(reconciliation failed with no error details)"
            if "401" in str(error_msg) or "unauthorized" in str(error_msg).lower():
                logger.critical(
                    "[PHASE 9] CRITICAL: Broker authentication failed (401). "
                    "Reconciliation cannot proceed - cannot verify position alignment. "
                    "This is NOT EXPECTED in production. Check Alpaca credentials."
                )
                phase_status = "error"  # Fail explicitly - don't mask auth errors as "ok"
            else:
                logger.error(f"[PHASE 9] CRITICAL: Reconciliation failed: {error_msg}")
                phase_status = "error"  # Fail explicitly on reconciliation failure

            data = {
                "reconciliation": result,
            }

        return PhaseResult(9, "reconciliation", phase_status, data, False, None)

    except (psycopg2.DatabaseError, psycopg2.OperationalError, RuntimeError, ValueError) as e:
        traceback.print_exc()
        error_msg = str(e)
        logger.critical(
            f"[PHASE 9 CRITICAL] Reconciliation failed with error: {error_msg}. "
            "Cannot proceed with trading when portfolio state is unknown. "
            "Setting halt flag to prevent further trading until broker is accessible."
        )
        log_phase_result_fn(9, "reconciliation", "error", error_msg)
        return PhaseResult(9, "reconciliation", "error", {}, True, f"Reconciliation failed (halted): {error_msg}")
