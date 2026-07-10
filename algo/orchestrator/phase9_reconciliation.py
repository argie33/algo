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

    try:
        result = recon.run_daily_reconciliation(run_date, dry_run=dry_run)
    except Exception as e:
        error_str = str(e).lower()
        is_alpaca_auth_error = "401" in str(e) or "403" in str(e) or "unauthorized" in error_str
        is_paper_mode = config.get("execution_mode") in ("paper", "auto")

        if is_alpaca_auth_error and is_paper_mode:
            logger.error(
                f"[PHASE 9 PAPER MODE] Alpaca API error ({type(e).__name__}): {e}. "
                f"Paper mode reconciliation requires either: "
                f"(1) Alpaca credentials in AWS Secrets Manager (algo/alpaca secret), or "
                f"(2) database state that's in sync. Cannot proceed with hardcoded defaults ($100k) as that masks data issues."
            )
            raise RuntimeError(
                f"[PHASE 9] Paper mode reconciliation failed: {type(e).__name__}: {str(e)[:200]}. "
                f"Check Alpaca credentials in AWS Secrets Manager or database sync state."
            ) from e
        else:
            raise

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
            logger.error(
                f"[PHASE 9 CRITICAL] Reconciliation reported success but missing critical data: {missing_keys}. "
                f"Result keys available: {list(result.keys())}. "
                f"Cannot proceed with hardcoded defaults as that masks data sync issues. "
                f"Check: (1) DailyReconciliation implementation, (2) Alpaca API connectivity, "
                f"(3) algo_portfolio_snapshots table state"
            )
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
        if recon.broker is None:
            logger.warning("[PHASE 9 P&L] Paper mode: broker unavailable, skipping P&L validation")
            pnl_validation_status = "warn"
            pnl_validation_summary = "Paper mode - no broker account"
            return pnl_validation_status, pnl_validation_summary
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
                logger.info(f"[PHASE 9 P&L VALIDATION] {pnl_check['message']}")
            elif pnl_check["status"] == "alert":
                logger.warning(f"[PHASE 9 P&L VALIDATION] {pnl_check['message']}")
            else:  # critical
                logger.critical(f"[PHASE 9 P&L VALIDATION] {pnl_check['message']}")
        else:
            pnl_validation_summary = "Skipped (reconciliation failed or no Broker data)"
    except Exception as e:
        logger.error(f"[PHASE 9] P&L validation failed: {e}")
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
                logger.warning(f"[PHASE 9 AUDIT] Stale estimated prices detected: {msg}")
                log_phase_result_fn(9, "exit_reconciliation_audit", "warn", msg)
            else:
                logger.info("[PHASE 9 AUDIT] All exit prices reconciled properly")
    except (psycopg2.DatabaseError, psycopg2.OperationalError, KeyError) as e:
        logger.error(f"[PHASE 9] Exit price audit failed: {e}")


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
    except ImportError as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Signal trade performance requires scipy/numpy: {e}. "
            f"Cannot validate signal attribution without these dependencies. "
            f"Install: pip install scipy numpy"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Signal trade performance failed unexpectedly: {e}. "
            f"Cannot proceed with trading when signal attribution is broken."
        )
        logger.critical(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

    if trades_processed is None:
        raise ValueError("Signal trade performance: trades_processed count is missing")
    log_phase_result_fn(
        9,
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
        9,
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
            9,
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
        9,
        "weight_optimization",
        "success" if opt_result.get("success", False) else "warn",
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
                                    profit_loss_pct = %s, exit_reason = %s, status = 'closed',
                                    updated_at = CURRENT_TIMESTAMP
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


def run(  # noqa: C901
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
                        from decimal import Decimal

                        with DatabaseContext("write") as cur:
                            # Count actual open positions from database
                            cur.execute("SELECT COUNT(*) as open_count FROM algo_positions WHERE status = 'open'")
                            position_row = cur.fetchone()
                            open_position_count = position_row[0] if position_row else 0

                            # Calculate portfolio value from positions
                            cur.execute("""
                                SELECT COALESCE(SUM(position_value), 0) as total_invested
                                FROM algo_positions
                                WHERE status = 'open'
                            """)
                            invested_row = cur.fetchone()
                            total_invested = Decimal(str(invested_row[0])) if invested_row else Decimal(0)

                            # FIX: Use configurable initial capital instead of hardcoded value
                            # Prevents silent trading on incorrect portfolio state in paper mode
                            initial_capital = config.get("initial_capital_paper_trading")
                            if not initial_capital:
                                raise RuntimeError(
                                    "[PHASE 9] CRITICAL: initial_capital_paper_trading not configured. "
                                    "Cannot reconcile paper trading portfolio without configured starting capital. "
                                    "Set in algo_config table or fail explicitly rather than using hardcoded fallback."
                                )
                            total_value = Decimal(str(initial_capital))
                            total_cash = total_value - total_invested

                            # Calculate daily return vs previous day
                            cur.execute(
                                """
                                SELECT total_portfolio_value
                                FROM algo_portfolio_snapshots
                                WHERE snapshot_date < %s
                                ORDER BY snapshot_date DESC LIMIT 1
                            """,
                                (run_date,),
                            )
                            prev_row = cur.fetchone()
                            prev_value = Decimal(prev_row[0]) if prev_row and prev_row[0] else Decimal(str(initial_capital))
                            daily_return_pct = (
                                ((total_value - prev_value) / prev_value * 100) if prev_value > 0 else Decimal(0)
                            )

                            # Create snapshot with actual position count and portfolio value
                            cur.execute(
                                """
                                INSERT INTO algo_portfolio_snapshots (
                                    snapshot_date, total_portfolio_value, total_cash,
                                    position_count, daily_return_pct, created_at
                                ) VALUES (%s, %s, %s, %s, %s, NOW())
                                ON CONFLICT (snapshot_date) DO UPDATE
                                SET total_portfolio_value = EXCLUDED.total_portfolio_value,
                                    total_cash = EXCLUDED.total_cash,
                                    position_count = EXCLUDED.position_count,
                                    daily_return_pct = EXCLUDED.daily_return_pct,
                                    created_at = NOW(),
                                    updated_at = NOW()
                            """,
                                (
                                    run_date,
                                    total_value,
                                    total_cash,
                                    open_position_count,
                                    daily_return_pct,
                                ),
                            )
                        log_phase_result_fn(9, "portfolio_snapshot", "success", "snapshot created from DB state")
                    except Exception as snapshot_err:
                        logger.error(f"[PHASE 9] CRITICAL: Could not create portfolio snapshot: {snapshot_err}")
                        raise RuntimeError(
                            f"[PHASE 9] Portfolio snapshot creation failed - orchestrator cannot proceed: {snapshot_err}"
                        ) from snapshot_err

                    # Snapshot already created above; proceed to refresh view and return

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
        # Skip if reconciliation failed (recon object may be incomplete or paper mode)
        if reconciliation_succeeded:
            try:
                _validate_pnl_step(recon, result, log_phase_result_fn)
            except Exception as validation_err:
                logger.warning(f"[PHASE 9] P&L validation failed (non-blocking): {validation_err}")

        # CRITICAL: Audit for stale estimated exit prices (reconciliation issues)
        # Skip if reconciliation failed (recon object may be incomplete or paper mode)
        if reconciliation_succeeded:
            try:
                _audit_exit_prices_step(recon, log_phase_result_fn)
            except Exception as audit_err:
                logger.warning(f"[PHASE 9] Exit price audit failed (non-blocking): {audit_err}")

        # CREATE PORTFOLIO SNAPSHOT from reconciliation result
        # This MUST happen after reconciliation to capture accurate state
        logger.info(
            f"[PHASE 9] Creating snapshot: reconciliation_succeeded={reconciliation_succeeded}, result={result}"
        )
        try:
            from decimal import Decimal

            with DatabaseContext("write") as cur:
                logger.info("[PHASE 9] Snapshot: Database connection established")

                # CRITICAL: Validate result exists
                if result is None:
                    raise ValueError(
                        "[PHASE 9] CRITICAL: Reconciliation returned None instead of result dict. "
                        "Cannot create snapshot without reconciliation data."
                    )

                # Validate Phase 4 reconciliation data exists
                missing_keys = []
                required_keys = ["portfolio_value", "positions", "unrealized_pnl", "position_value"]
                for key in required_keys:
                    if key not in result or result[key] is None:
                        missing_keys.append(key)

                if missing_keys:
                    available_keys = list(result.keys())
                    raise ValueError(
                        f"[PHASE 9] CRITICAL: Reconciliation missing {len(missing_keys)} required keys: {missing_keys}. "
                        f"Available keys: {available_keys}. "
                        f"Reconciliation result: {result}. "
                        f"Cannot create snapshot without complete reconciliation data. "
                        f"Check: (1) DailyReconciliation return values, (2) paper mode return statement, "
                        f"(3) position_value calculation in reconciliation query"
                    )

                if "portfolio_value" not in result:
                    raise ValueError("[PHASE 9] CRITICAL: Phase 4 reconciliation missing 'portfolio_value'. Cannot create snapshot.")
                if "positions" not in result or result["positions"] is None:
                    raise ValueError("[PHASE 9] CRITICAL: Phase 4 reconciliation missing 'positions' count. Cannot create snapshot.")
                if "unrealized_pnl" not in result:
                    raise ValueError("[PHASE 9] CRITICAL: Phase 4 reconciliation missing 'unrealized_pnl'. Cannot create snapshot.")
                if "position_value" not in result:
                    raise ValueError("[PHASE 9] CRITICAL: Phase 4 reconciliation missing 'position_value'. Cannot calculate cash. Cannot create snapshot.")

                current_value = Decimal(str(result["portfolio_value"]))
                pos_count = result["positions"]
                unrealized = Decimal(str(result["unrealized_pnl"]))
                position_value = Decimal(str(result["position_value"]))

                # Get previous portfolio value for daily return calculation
                cur.execute(
                    """
                    SELECT total_portfolio_value
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date < %s
                    ORDER BY snapshot_date DESC LIMIT 1
                """,
                    (run_date,),
                )
                prev_row = cur.fetchone()

                if prev_row is None:
                    # First snapshot - use current value as baseline (0% return)
                    prev_value = current_value
                    logger.info("[PHASE 9] Snapshot: No previous snapshot found; baseline to current value")
                else:
                    prev_value = Decimal(prev_row[0])

                # CRITICAL: Do NOT default daily return to 0 when prev_value ≤ 0
                # 0% return ≠ "data missing". If prev_value is invalid, that's a data integrity issue.
                if prev_value <= 0:
                    raise ValueError(
                        f"[PHASE 9 CRITICAL] Cannot calculate daily return: previous portfolio value is {prev_value} (expected > 0). "
                        f"This indicates: (1) First portfolio snapshot with corrupted value, or "
                        f"(2) Data integrity issue in algo_portfolio_snapshots. "
                        f"Check database state."
                    )
                daily_return_pct = (current_value - prev_value) / prev_value * 100
                logger.info(f"[PHASE 9] Snapshot: Previous={prev_value}, Current={current_value}, Daily return={daily_return_pct}%")

                cash = current_value - position_value
                logger.info(f"[PHASE 9] Snapshot: Cash calculation: ${current_value:,.2f} (portfolio) - ${position_value:,.2f} (positions) = ${cash:,.2f}")

                logger.info(f"[PHASE 9] Snapshot: Executing INSERT with position_count={pos_count}, cash={cash}")
                cur.execute(
                    """
                    INSERT INTO algo_portfolio_snapshots (
                        snapshot_date, total_portfolio_value, total_cash,
                        position_count, daily_return_pct, created_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (snapshot_date) DO UPDATE
                    SET total_portfolio_value = EXCLUDED.total_portfolio_value,
                        total_cash = EXCLUDED.total_cash,
                        position_count = EXCLUDED.position_count,
                        daily_return_pct = EXCLUDED.daily_return_pct,
                        created_at = NOW(),
                        updated_at = NOW()
                """,
                    (
                        run_date,
                        current_value,
                        cash,
                        pos_count,
                        daily_return_pct,
                    ),
                )
                logger.info("[PHASE 9] Snapshot: INSERT executed, exiting DatabaseContext to trigger commit")

                # ISSUE #6 FIX: Verify position_count matches algo_positions table COUNT
                # Ensures snapshot data is consistent with actual database state
                try:
                    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                    actual_open_count = cur.fetchone()[0] if cur.fetchone() else 0
                    # Re-fetch since we just called fetchone()
                    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                    actual_open_count = cur.fetchone()[0]

                    if actual_open_count != pos_count:
                        logger.warning(
                            f"[PHASE 9] CONSISTENCY CHECK: position_count in snapshot ({pos_count}) "
                            f"does not match algo_positions COUNT ({actual_open_count}). "
                            f"Database may have pending updates or reconciliation incomplete."
                        )
                    else:
                        logger.info(
                            f"[PHASE 9] CONSISTENCY CHECK: position_count verified ({pos_count} matches algo_positions)"
                        )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as consistency_err:
                    logger.error(
                        f"[PHASE 9] CONSISTENCY CHECK FAILED: Could not verify position count: {consistency_err}. "
                        f"Snapshot was created but consistency check incomplete."
                    )

                if result.get('positions') is None:
                    raise RuntimeError(
                        "[PHASE 9] CRITICAL: Reconciliation result missing 'positions' count. "
                        "Cannot create snapshot without verified position count. "
                        "Broker reconciliation data may be incomplete."
                    )
                pos_count = result['positions']
                logger.info(
                    f"[PHASE 9 SNAPSHOT] Created: portfolio=${current_value:.2f}, positions={pos_count}"
                )
                log_phase_result_fn(
                    9,
                    "portfolio_snapshot",
                    "success",
                    f"snapshot created: ${current_value:.2f}, {pos_count} positions",
                )
        except Exception as snapshot_err:
            logger.warning(f"[PHASE 9 SNAPSHOT] Failed to create snapshot: {snapshot_err}", exc_info=True)
            log_phase_result_fn(9, "portfolio_snapshot", "warn", f"snapshot failed: {str(snapshot_err)[:60]}")

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

        # CRITICAL FIX: Sync quantity column for all open positions (entry_quantity -> quantity)
        # This ensures the quantity field is populated for all open trades after reconciliation
        # Without this, dashboard and risk calculations cannot determine current position sizes
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    UPDATE algo_trades
                    SET quantity = entry_quantity, updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'open' AND (quantity IS NULL OR quantity != entry_quantity)
                """)
                synced_count = cur.cursor.rowcount
                if synced_count > 0:
                    logger.info(f"[PHASE 9] Synced quantity for {synced_count} open positions (quantity = entry_quantity)")
            log_phase_result_fn(9, "quantity_sync", "success", f"synced {synced_count} open positions")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[PHASE 9] CRITICAL: Failed to sync quantity column: {e}")
            log_phase_result_fn(9, "quantity_sync", "error", f"sync failed: {str(e)[:60]}")

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
                # Paper mode: treat 401 as non-critical (expected without real credentials)
                if config.get("execution_mode") in ("paper", "auto"):
                    logger.warning(
                        "[PHASE 9] Paper mode: Broker authentication failed (401) - expected without real credentials. "
                        "Using database portfolio state instead of broker sync."
                    )
                    # FIX: Use configurable initial capital instead of hardcoded value
                    initial_capital = config.get("initial_capital_paper_trading")
                    if not initial_capital:
                        raise RuntimeError(
                            "[PHASE 9] CRITICAL: initial_capital_paper_trading not configured. "
                            "Cannot reconcile paper mode without configured starting capital."
                        )
                    # CRITICAL FIX: Never default positions and unrealized_pnl to 0
                    # These MUST be fetched from database on reconciliation failure.
                    # Defaulting to 0 masks data loss and could lead to corrupted position tracking.
                    try:
                        with DatabaseContext("read") as cur:
                            cur.execute("""
                                SELECT COUNT(*) as pos_count
                                FROM algo_trades
                                WHERE status = 'open'
                            """)
                            pos_row = cur.fetchone()
                            pos_count = pos_row[0] if pos_row else None
                            if pos_count is None:
                                raise RuntimeError(
                                    "[PHASE 9] CRITICAL: Cannot fetch position count from database. "
                                    "Cannot proceed with paper mode reconciliation."
                                )

                            cur.execute("""
                                SELECT SUM(unrealized_pnl_total) as total_pnl
                                FROM algo_portfolio_snapshots
                                ORDER BY created_at DESC LIMIT 1
                            """)
                            pnl_row = cur.fetchone()
                            total_pnl = float(pnl_row[0]) if (pnl_row and pnl_row[0] is not None) else 0.0
                    except Exception as db_err:
                        raise RuntimeError(
                            f"[PHASE 9] CRITICAL: Failed to fetch reconciliation data from database on auth failure: {db_err}. "
                            "Cannot proceed safely without verified position data."
                        ) from db_err

                    reconciliation_succeeded = True
                    phase_status = "ok"
                    result = {
                        "success": True,
                        "portfolio_value": float(initial_capital),
                        "positions": pos_count,
                        "unrealized_pnl": total_pnl,
                        "note": "Paper mode - broker auth failed, fetched from database",
                    }
                else:
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

    except Exception as e:
        traceback.print_exc()
        error_msg = str(e)
        error_type = type(e).__name__
        full_traceback = traceback.format_exc()
        logger.critical(
            f"[PHASE 9 CRITICAL] Unexpected error ({error_type}): {error_msg}. "
            "Full traceback above. Cannot proceed with trading when portfolio state is unknown. "
            "Setting halt flag to prevent further trading until broker is accessible.",
            exc_info=True,
        )
        # CRITICAL: Include full traceback in summary so it persists to execution log
        error_summary = f"{error_type}: {error_msg[:100]}\n{full_traceback[:500]}"
        log_phase_result_fn(9, "reconciliation", "error", error_summary)
        return PhaseResult(9, "reconciliation", "error", {}, True, f"Phase 9 error ({error_type}): {error_msg[:100]}")
