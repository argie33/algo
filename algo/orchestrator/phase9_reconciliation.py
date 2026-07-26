#!/usr/bin/env python3

import json
import logging
import traceback
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime, timezone
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
        # "auto" is this system's real live-trading mode (see this session's other
        # execution_mode fixes) - both branches below ultimately raise regardless, so this
        # doesn't change control flow, only which error message an "auto" mode auth failure
        # gets logged/raised under (previously always the misleading "[PHASE 9 PAPER MODE]"
        # one, obscuring that a live deployment's Alpaca credentials are the real problem).
        is_paper_mode = config.get("execution_mode") == "paper"

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

        # Defensive formatting for reconciliation summary - handle None values gracefully
        try:
            pf_val = result["portfolio_value"]
            pos_count = result["positions"]
            pnl = result["unrealized_pnl"]

            pf_str = f"{float(pf_val):,.2f}" if pf_val is not None else "N/A"
            pos_str = f"{int(pos_count)}" if pos_count is not None else "N/A"
            pnl_str = f"{float(pnl):+,.2f}" if pnl is not None else "N/A"

            summary = f"Portfolio ${pf_str}, {pos_str} positions, unrealized P&L ${pnl_str}"
        except (ValueError, TypeError) as fmt_err:
            logger.error(f"[PHASE 9] Failed to format reconciliation summary: {fmt_err}")
            summary = "Portfolio: data formatting error"
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
                # GOVERNANCE: a critical P&L divergence is, per validate_pnl()'s own
                # docstring, real data corruption between broker and local state. Every
                # other critical branch in this file surfaces via notify(); this one only
                # logged, so a >1% divergence could go unnoticed unless someone was
                # watching logs at the moment it happened.
                try:
                    from algo.reporting import notify

                    notify(
                        severity="critical",
                        title="Phase 9 P&L Divergence",
                        message=pnl_check["message"],
                        details={"broker_equity": broker_equity, "local_equity": local_equity},
                    )
                except (ValueError, TypeError, RuntimeError) as notify_err:
                    logger.error(f"Failed to send P&L divergence notification: {notify_err}")
        else:
            pnl_validation_summary = "Skipped (reconciliation failed or no Broker data)"
    except (ValueError, RuntimeError, KeyError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] P&L validation failed: {e}. "
            f"Cannot proceed with reconciliation when P&L validation unavailable. "
            f"Check broker connectivity, account sync, and local portfolio state."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
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
                raise ValueError(f"Exit price audit result missing 'status' field. Keys: {list(stale_audit.keys())}")

            if status != "OK":
                msg = stale_audit.get("message")
                if msg is None:
                    raise ValueError(
                        f"Exit price audit status '{status}' but message missing. Keys: {list(stale_audit.keys())}"
                    )
                if status == "CRITICAL":
                    logger.critical(f"[PHASE 9 AUDIT] Stale estimated prices detected: {msg}")
                else:
                    logger.warning(f"[PHASE 9 AUDIT] Stale estimated prices detected: {msg}")
                log_phase_result_fn(9, "exit_reconciliation_audit", "warn", msg)
            else:
                logger.info("[PHASE 9 AUDIT] All exit prices reconciled properly")
    except (psycopg2.DatabaseError, psycopg2.OperationalError, KeyError, ValueError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Exit price audit failed: {e}. "
            f"Cannot proceed when exit prices cannot be verified. "
            f"Check database connectivity and reconciliation state."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e


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
    from algo.signals.attribution import SignalAttributionEngine

    attr_result: dict[str, Any] = {}
    available_components = 0

    # SignalAttributionEngine is fully deprecated (see algo/signals/attribution.py's own
    # module docstring: "swing scores have been removed; this module ... returns
    # unavailable data") - compute_ic() always returns every component marked
    # data_unavailable=True, never a real ic_value. Even though the feature is deprecated,
    # we still run the computation and properly guard persist() to avoid writing all-NULL
    # rows on every Phase 9 run when all components are unavailable.
    try:
        attribution = SignalAttributionEngine()
        attr_result = attribution.compute_ic(run_date, lookback_trades=40)
        total_components = len(attr_result)
        logger.info(f"Signal attribution: IC computed for {total_components} components (deprecated feature)")
        for comp, ic_data in attr_result.items():
            ic_value = ic_data.get("ic_value")
            ic_pvalue = ic_data.get("ic_pvalue")
            if ic_value is None or ic_pvalue is None:
                if ic_data.get("data_unavailable"):
                    if "reason" not in ic_data or ic_data["reason"] is None:
                        logger.critical(
                            f"[PHASE 9 CRITICAL] IC data marked unavailable but missing 'reason' field. "
                            f"Component: {comp}. Data keys: {list(ic_data.keys())}. "
                            f"Cannot determine why IC is unavailable. Check upstream IC calculation."
                        )
                        raise ValueError(
                            f"[PHASE 9] IC data for {comp} marked unavailable but missing 'reason' field. "
                            "Cannot proceed with incomplete data_unavailable marker."
                        )
                    reason = ic_data["reason"]
                    logger.warning(f"[ATTRIBUTION] {comp} IC unavailable: {reason} - skipping")
                    continue
                logger.critical(f"CRITICAL: IC value missing for component {comp}. Cannot validate signal quality.")
                raise ValueError(f"IC calculation failed for {comp}: missing 'ic_value'. Signal validation incomplete.")
            available_components += 1
            logger.info(f"  {comp}: IC={ic_value:.3f}, pval={ic_pvalue:.3f}")

        # Guard: only persist if at least one component has real data (not all unavailable)
        if available_components > 0:
            attribution.persist(run_date, attr_result)
            status = "success"
            summary = f"{available_components}/{total_components} components analyzed"
        else:
            # All components deprecated/unavailable - don't persist null rows
            status = "warn"
            summary = f"0/{total_components} components available (feature deprecated)"
    except Exception as e:
        logger.error(f"[ATTRIBUTION] Signal attribution computation failed: {e}")
        status = "warn"
        summary = f"Signal attribution failed: {e}"

    log_phase_result_fn(9, "ic_computation", status, summary)
    return attr_result


def _generate_daily_report(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    from algo.reporting import DailyFinanceReport

    try:
        daily_report = DailyFinanceReport()
        report = daily_report.generate(run_date)
        report_text = daily_report.format_text(report)
        logger.info(f"\n{report_text}")
    except (ValueError, RuntimeError, KeyError, TypeError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Daily report generation failed: {e}. "
            f"Cannot proceed when portfolio reporting unavailable. "
            f"Check DailyFinanceReport implementation and portfolio state."
        )
        logger.critical(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Daily report generation failed unexpectedly: {e}. "
            f"Cannot proceed when portfolio reporting unavailable."
        )
        logger.critical(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

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
            # CRITICAL: Audit log persistence is non-negotiable. Cannot continue without persisting
            # portfolio snapshots to audit trail per GOVERNANCE (data integrity).
            error_msg = (
                f"[PHASE 9 CRITICAL] Failed to persist portfolio snapshot to audit log: {e}. "
                f"Cannot proceed with reconciliation when audit trail is unavailable. "
                f"Database may be corrupted or inaccessible. Check database connectivity and disk space."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from e

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

        # Safely format portfolio metrics, handling edge cases where values might still be None
        try:
            current_val_str = (
                str(current_val)
                if isinstance(current_val, str)
                else f"{float(current_val):,.0f}" if current_val is not None else "N/A"
            )
            pnl_pct_str = (
                str(pnl_pct)
                if isinstance(pnl_pct, str)
                else f"{float(pnl_pct):+.2f}%" if pnl_pct is not None else "N/A"
            )
            report_summary = f"Portfolio ${current_val_str}, P&L {pnl_pct_str}"
        except (ValueError, TypeError) as fmt_err:
            logger.error(f"[PHASE 9 REPORT] Failed to format portfolio metrics: {fmt_err}. Using defaults.")
            report_summary = "Portfolio $? P&L ?"

        log_phase_result_fn(
            9,
            "daily_report",
            "success",
            report_summary,
        )
    except ValueError as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Daily report validation failed: {e}. "
            f"Report was generated but contains incomplete or invalid data. "
            f"Cannot proceed with incomplete portfolio reporting per GOVERNANCE (data integrity)."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e


def _compute_performance_metrics(config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    from algo.reporting import LivePerformance

    perf_status = "warn"
    perf_summary = "N/A"
    try:
        perf = LivePerformance(config)
        perf_report = perf.generate_daily_report(run_date)
        # generate_daily_report() returns status "ok" (clean) or "warning" (report succeeded
        # and was persisted, but live Sharpe fell below 70% of backtest - see
        # performance.py::generate_daily_report). Both are a successful report generation;
        # only "error" means generation actually failed. Treating "warning" as failure here
        # previously logged "generation failed" for a report that succeeded and was already
        # written to algo_performance_daily - a misleading status with no bearing on reality.
        if perf_report and perf_report.get("status") in ("ok", "warning"):
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
            elif perf_report.get("status") == "warning":
                perf_summary = f"Sharpe {sharpe}, Win rate {win_rate}%, Expectancy {expectancy} - {perf_report.get('warning', 'see logs')}"
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
            # CRITICAL FIX: Performance report returning None is not "insufficient history" - it's a failure.
            # Fail-fast when performance metrics cannot be computed. Do NOT silently degrade to "warn".
            msg = (
                "[PHASE 9 CRITICAL] Performance report generation returned None. "
                "Cannot determine portfolio performance. Possible causes: "
                "(1) Portfolio has no trade history (new account), "
                "(2) Performance calculation failed (data unavailable), "
                "(3) Bug in performance metrics module. "
                "Must verify performance metrics computation before proceeding."
            )
            logger.critical(msg)
            raise RuntimeError(msg)
    except (RuntimeError, ValueError):
        # CRITICAL: RuntimeError/ValueError indicate data quality issues (insufficient history, etc).
        # These MUST propagate to halt Phase 9 per GOVERNANCE (fail-fast).
        # Never silently degrade on data quality failures.
        raise
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Performance metrics database error: {e}. "
            f"Cannot proceed when performance data unavailable. "
            f"Check database connectivity and portfolio state."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Performance metrics computation failed unexpectedly: {e}. "
            f"Cannot proceed when performance data unavailable."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    finally:
        log_phase_result_fn(9, "performance", perf_status, perf_summary)


def _compute_risk_metrics(config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
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
                # VaR unavailable due to insufficient historical data - row was still inserted with NULLs
                logger.warning(
                    "Risk report status=ok but var_metrics unavailable (insufficient historical data). "
                    "Row inserted with NULL VaR values - will populate as data accumulates."
                )
            if concentration is not None:
                conc_pct = concentration.get("top_5_concentration_pct")
                if conc_pct is not None:
                    summary_parts.append(f"Conc {conc_pct:.1f}%")
            # ValueAtRisk.beta_exposure() explicitly returns None when there are no open
            # positions (see algo/risk/var.py) - the same "may legitimately be None" case
            # already handled for var_metrics/concentration above, but this line called
            # .get() on it unconditionally, crashing Phase 9 with an AttributeError (masked
            # by the broad except below into a confusing "failed unexpectedly" RuntimeError)
            # any time the portfolio had zero positions when the risk report was generated.
            if beta_exposure is not None:
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
    except (ValueError, RuntimeError, KeyError, TypeError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Risk metrics computation failed: {e}. "
            f"Cannot proceed when risk assessment unavailable. "
            f"Check portfolio state and risk calculation logic."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Risk metrics computation failed unexpectedly: {e}. "
            f"Cannot proceed when risk assessment unavailable."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    finally:
        log_phase_result_fn(9, "risk_metrics", risk_status, risk_summary)


def _update_daily_metrics(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> None:
    try:
        row_data = None
        with DatabaseContext("read") as cur:
            # CRITICAL: entries/exits used to be counted via algo_audit_log.action_type =
            # 'BUY'/'SELL' - those literal values are never written anywhere in this codebase
            # (confirmed live: 0 rows, ever, out of the whole table's history; real trade
            # actions log under names like 'phase_8_entry_execution'/'exit_stop'), so this
            # column pair has been silently 0 since the table's inception regardless of real
            # trading activity - the health panel has displayed "0 entries, 0 exits" every
            # day even on days with dozens of real trades. Count from algo_trades directly
            # instead (same source dashboard/panels/health.py's phase 6/8 rows already use).
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_actions,
                    AVG(CAST(details->>'score' AS FLOAT)) as avg_signal_score
                FROM algo_audit_log
                WHERE DATE(created_at) = %s
            """,
                (run_date,),
            )
            audit_row = cur.fetchone()

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE entry_date = %s) as entries,
                    COUNT(*) FILTER (WHERE exit_date = %s) as exits
                FROM algo_trades
            """,
                (run_date, run_date),
            )
            trade_row = cur.fetchone()
            row_data = (audit_row[0], trade_row[0], trade_row[1], audit_row[1]) if audit_row and trade_row else None

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
        error_msg = (
            f"[PHASE 9 CRITICAL] Failed to persist metrics to algo_metrics_daily: {e}. "
            f"Cannot proceed when metrics persistence unavailable. "
            f"Check database connectivity and disk space."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    finally:
        log_phase_result_fn(9, "metrics_update", metrics_status, metrics_summary)


def _optimize_weights(config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]) -> dict[str, Any]:
    """Run weight optimization. Gracefully skip if regime data unavailable (data quality issue, not code bug)."""
    from algo.orchestration import RegimeManager as _RegimeManager
    from algo.orchestration import WeightOptimizer

    opt_result: dict[str, Any] = {"changes": []}
    try:
        try:
            _current_regime = _RegimeManager().get_current_regime(run_date)
        except RuntimeError as regime_e:
            # Regime data unavailable - log warning and skip weight optimization
            # This is a data quality issue (market_exposure_daily stale/missing), not a code bug
            # Weight optimization is important but not critical for Phase 9; Phase 9 must continue
            # for reconciliation/metrics/risk calculations per governance feedback
            logger.warning(
                f"[PHASE 9] Skipping weight optimization: regime unavailable ({regime_e}). "
                f"Market exposure analysis (Phase 5) must complete to enable weight optimization. "
                f"Portfolio weights remain unchanged. Phase 9 continues for reconciliation/metrics/risk."
            )
            log_phase_result_fn(9, "weight_optimization", "warn", f"regime unavailable: {str(regime_e)[:60]}")
            return opt_result

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

    # CRITICAL: Explicit validation - no silent empty list defaults
    changes = opt_result.get("changes")
    if changes is None:
        raise ValueError(
            "[PHASE 9] Weight optimization result missing 'changes' field. "
            "Optimization failed or returned malformed data. Cannot proceed with reconciliation."
        )
    if not isinstance(changes, list):
        raise ValueError(
            f"[PHASE 9] Weight optimization 'changes' is not a list: {type(changes)}. "
            "Data structure corrupted or optimization returned invalid type."
        )
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
                            raise RuntimeError(
                                f"[PHASE 9 CRITICAL] Exit price missing for {symbol} closed position. "
                                f"Cannot record P&L without exit price. "
                                f"This indicates a reconciliation failure or data corruption. "
                                f"Halting Phase 9 to prevent audit trail gaps."
                            )

                        if entry_price is None or entry_price <= 0:
                            error_msg = (
                                f"[PHASE 9 CRITICAL] Trade {symbol} has invalid entry_price ({entry_price}). "
                                f"Cannot record trade P&L without valid entry price. "
                                f"This indicates a position tracking or database corruption issue. "
                                f"Halting Phase 9 to prevent audit trail corruption."
                            )
                            logger.critical(error_msg)
                            raise RuntimeError(error_msg)

                        # CRITICAL: `exit_price` here is algo_positions.current_price at the moment this
                        # position was detected closed (e.g. no longer present at the broker per
                        # alpaca_sync_manager.py's reconciliation). That is NOT a confirmed broker fill -
                        # if current_price was never refreshed after entry (position closed at the broker
                        # before the next price sync ran), it silently equals entry_price, fabricating a
                        # $0.00 P&L that hides the real gain/loss. Record it the same way
                        # executor_exit_handler.py already does for its own estimated exits: leave
                        # profit_loss_dollars/pct NULL (unknown, not zero) and mark estimated_exit_price
                        # so the existing reconcile_exit_fills() pass on a subsequent run - and
                        # audit_stale_estimated_prices() if it stays unreconciled too long - can replace
                        # this guess with the broker's actual fill price.
                        sp = f"sp_exit_{symbol.replace('-', '_').replace('.', '_')}"
                        try:
                            write_cursor.execute(f"SAVEPOINT {sp}")
                            write_cursor.execute(
                                """
                                UPDATE algo_trades
                                SET exit_date = %s, exit_price = %s, estimated_exit_price = %s,
                                    profit_loss_dollars = NULL, profit_loss_pct = NULL, exit_r_multiple = NULL,
                                    exit_reason = %s, status = 'closed',
                                    trade_duration_days = %s::date - entry_date,
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
                                    exit_price,
                                    "Closed position recorded during reconciliation - pending fill price confirmation",
                                    run_date,
                                    symbol,
                                ),
                            )
                            write_cursor.execute(
                                """
                                UPDATE algo_positions
                                SET status = 'closed', closed_at = CURRENT_TIMESTAMP, current_price = %s, unrealized_pnl = NULL,
                                    exit_reason = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE symbol = %s
                            """,
                                (exit_price, "Closed position recorded during reconciliation - pending fill price confirmation", symbol),
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
                                f"Recorded exit: {symbol} {quantity}sh @ ~${exit_price:.2f} (estimated) on {run_date} "
                                f"- P&L pending broker fill reconciliation"
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
        PhaseResult with status 'ok' if all reconciliation steps succeed. Raises RuntimeError
        (fail-closed, per GOVERNANCE) on any critical step failure rather than returning a
        degraded PhaseResult - this stale docstring previously said "fail-open", which does
        not match the raise-heavy implementation below.
    """
    try:
        from algo.infrastructure.reconciliation import DailyReconciliation

        try:
            recon = DailyReconciliation(config)
        except ValueError as e:
            # GOVERNANCE: Fail-fast on missing Alpaca credentials - no fallback to database state
            # Attempting to reconcile with cached/estimated portfolio values (instead of broker source-of-truth)
            # masks data sync issues and leads to incorrect position sizing on next entry.
            # Better to halt and require explicit credential remediation than to silently degrade.
            if "credentials not found" in str(e).lower() or "credentials" in str(e).lower():
                raise RuntimeError(
                    f"[PHASE 9 CRITICAL] Alpaca credentials not available. "
                    f"Reconciliation requires live broker data. "
                    f"Cannot proceed with trading using stale or estimated portfolio state. "
                    f"Fix: Ensure Alpaca API keys are configured in AWS Secrets Manager (algo/alpaca secret) or environment. "
                    f"Error: {e}"
                ) from e
            else:
                raise
        reconciliation_succeeded, result = _run_reconciliation_step(config, run_date, log_phase_result_fn, dry_run)

        # CRITICAL: Validate that local P&L matches Broker P&L
        # Skip if reconciliation failed (recon object may be incomplete or paper mode)
        if reconciliation_succeeded:
            _validate_pnl_step(recon, result, log_phase_result_fn)

        # CRITICAL: Audit for stale estimated exit prices (reconciliation issues)
        # Skip if reconciliation failed (recon object may be incomplete or paper mode)
        if reconciliation_succeeded:
            _audit_exit_prices_step(recon, log_phase_result_fn)

        # Portfolio snapshot is created by DailyReconciliation in reconciliation.py with full metrics
        # Do NOT create a second snapshot here as it would overwrite the proper one with incomplete data
        logger.info(
            f"[PHASE 9] Portfolio snapshot created by DailyReconciliation (reconciliation_succeeded={reconciliation_succeeded})"
        )
        try:
            log_phase_result_fn(9, "portfolio_snapshot", "success", "snapshot created by reconciliation")
        except Exception as snapshot_err:
            logger.warning(f"[PHASE 9 SNAPSHOT] Failed to log snapshot status: {snapshot_err}", exc_info=True)
            log_phase_result_fn(9, "portfolio_snapshot", "warn", f"logging failed: {str(snapshot_err)[:60]}")

        # Record exits for recently closed positions (batch operation to avoid N+1 queries)
        _record_closed_positions_exits(run_date, log_phase_result_fn)

        # Step 1: Populate signal_trade_performance from closed trades
        _populate_signal_trade_performance(log_phase_result_fn)

        # Step 2: Compute IC via attribution engine
        _compute_signal_attribution(run_date, log_phase_result_fn)

        # Step 3: Run weight optimization (if enough trades)
        # Weight optimization raises explicit RuntimeError/ValueError on critical failures.
        # These must propagate to halt Phase 9 per GOVERNANCE (fail-fast on missing data).
        # Only catch ImportError (optional scipy/numpy dependency).
        try:
            _optimize_weights(config, run_date, log_phase_result_fn)
        except ImportError as e:
            error_msg = (
                f"[PHASE 9] Weight optimization requires scipy/numpy (not available): {e}. "
                f"This is a setup issue, not a data quality issue. "
                f"Install: pip install scipy numpy"
            )
            logger.error(error_msg)
            log_phase_result_fn(9, "weight_optimization", "warn", "dependency missing: scipy/numpy")
            # Don't raise - scipy is optional for setup, but if weight optimization fails
            # for data reasons, that WILL be caught and raised above

        # Step 4: Generate institutional daily report
        _generate_daily_report(run_date, log_phase_result_fn)

        # Step 5: Compute and log live performance metrics (always run, even on non-trading days)
        # Performance metrics raises explicit RuntimeError/ValueError on critical failures.
        # These must propagate to halt Phase 9 per GOVERNANCE (fail-fast on missing data).
        # Only catch ImportError (optional scipy/numpy dependency).
        try:
            _compute_performance_metrics(config, run_date, log_phase_result_fn)
        except ImportError as e:
            error_msg = (
                f"[PHASE 9] Performance metrics requires scipy/numpy (not available): {e}. "
                f"This is a setup issue, not a data quality issue. "
                f"Install: pip install scipy numpy"
            )
            logger.error(error_msg)
            log_phase_result_fn(9, "performance", "warn", "dependency missing: scipy/numpy")
            # Don't raise - scipy is optional for setup, but if perf metrics fails
            # for data reasons, that WILL be caught and raised above

        # Step 6: Compute and log risk metrics (always run, even on non-trading days)
        # Risk metrics computation MUST succeed - it feeds position sizing and risk limits.
        # Fail-fast per GOVERNANCE if risk data unavailable.
        _compute_risk_metrics(config, run_date, log_phase_result_fn)

        # Step 7: Update algo_metrics_daily with actual trade results from this run
        # Metrics update must persist trade results to audit trail.
        # Fail-fast per GOVERNANCE - audit trail integrity is non-negotiable.
        _update_daily_metrics(run_date, log_phase_result_fn)

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
                synced_count = cur.rowcount
                if synced_count > 0:
                    logger.info(
                        f"[PHASE 9] Synced quantity for {synced_count} open positions (quantity = entry_quantity)"
                    )
                else:
                    logger.debug("[PHASE 9] No quantity sync needed - all open positions have quantity set")
            log_phase_result_fn(
                9,
                "quantity_sync",
                "success",
                f"synced {synced_count} open positions" if synced_count > 0 else "no sync needed",
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[PHASE 9] CRITICAL: Failed to sync quantity column: {e}")
            log_phase_result_fn(9, "quantity_sync", "error", f"sync failed: {str(e)[:60]}")

        # Refresh materialized view so positions dashboard reflects current state.
        # This runs after reconciliation updates algo_positions from Broker.
        # CRITICAL FIX: Permission errors in LOCAL_MODE are expected (non-superuser), skip view refresh gracefully
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
        except psycopg2.errors.InsufficientPrivilege:
            # Permission denied is expected in LOCAL_MODE (non-superuser cannot refresh materialized views)
            # This is not a critical failure - just log warning and continue
            logger.warning(
                "[PHASE 9] Cannot refresh algo_positions_with_risk (permission denied - expected in LOCAL_MODE). "
                "View will use cached data; next proper execution with elevated privileges will refresh it."
            )
            log_phase_result_fn(
                9,
                "positions_view_refresh",
                "warning",
                "skipped (permission denied - expected in LOCAL_MODE)",
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            # Other DB errors are critical (disk space, connection issues, view corruption)
            error_msg = (
                f"[PHASE 9 CRITICAL] Failed to refresh algo_positions_with_risk materialized view: {e}. "
                f"Dashboard position data will become stale. "
                f"Check: (1) materialized view definition, (2) database disk space"
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from e

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
                # CRITICAL: Circuit breaker metrics feed risk dashboards and position limits.
                # Cannot allow stale CB status on dashboard per GOVERNANCE (data integrity).
                error_msg = (
                    f"[PHASE 9 CRITICAL] Circuit breaker metrics computation failed: {e}. "
                    f"Cannot proceed without current risk assessment. "
                    f"Dashboard risk panel will become stale if this phase continues. "
                    f"Check: (1) compute_circuit_breaker_metrics() implementation, "
                    f"(2) circuit_breaker_status table state, (3) database connectivity"
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg) from e

        # Degrade gracefully if reconciliation failed (e.g., broker unavailable in dry-run)
        # Phase 9 is always_run, so it should not cause a halt even if broker is unavailable
        if reconciliation_succeeded:
            # cash_available/total_return_pct/latest_snapshot: the health dashboard
            # (dashboard/panels/health.py, Phase 9 detail row) already expects these
            # exact keys, but this dict never included them - only portfolio_value made
            # it through, so Cash available/Total return/Last snapshot silently never
            # rendered even though run_daily_reconciliation() now returns the first two
            # (cash_remaining/cumulative_return_pct) and this phase runs immediately
            # after the snapshot write, so "now" is an accurate last-snapshot timestamp.
            data = {
                "portfolio_value": result.get("portfolio_value"),
                "positions": result.get("positions"),
                "unrealized_pnl": result.get("unrealized_pnl"),
                "cash_available": result.get("cash_remaining"),
                "total_return_pct": result.get("cumulative_return_pct"),
                "latest_snapshot": datetime.now(timezone.utc).isoformat(),
                "reconciliation": result,
            }
            phase_status = "ok"
        else:
            # Reconciliation failed - fail-fast (no graceful degradation)
            # GOVERNANCE: Reconciliation is non-negotiable. Using estimated/cached portfolio state
            # instead of broker source-of-truth masks data sync issues and leads to position sizing errors.
            # Better to halt explicitly and require broker access than to silently degrade.
            error_msg = str(result["reason"])

            logger.critical(
                f"[PHASE 9] CRITICAL: Reconciliation failed: {error_msg}. "
                f"Cannot proceed with trading without broker verification of portfolio state. "
                f"Ensure Alpaca API is accessible and credentials are valid."
            )
            phase_status = "error"

            data = {
                "reconciliation": result,
            }

        # Validate schema contract before returning
        from algo.orchestrator.phase_data_contract import validate_phase_data

        validate_phase_data(9, data)

        # CRITICAL: Log final consolidated phase result (not a sub-step)
        # Phase 9 logs multiple sub-steps (reconciliation, portfolio_snapshot, weight_optimization, etc.)
        # but the orchestrator's phase_results[9] must contain the OVERALL phase status, not the last sub-step.
        # This ensures the halt_reason accurately reports Phase 9's overall outcome, not a specific sub-step.
        # Without this, when Phase 1 fails, the halt_reason incorrectly shows the last Phase 9 sub-step message
        # instead of the Phase 1 error - a governance violation (inaccurate error reporting).
        phase_summary = f"Portfolio state: {data.get('portfolio_value', 'N/A')} | Status: {phase_status}"
        log_phase_result_fn(9, "reconciliation", phase_status, phase_summary)

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
        return PhaseResult(
            9,
            "reconciliation",
            "error",
            {"status": "error", "reason": f"Phase 9 error ({error_type}): {error_msg[:100]}", "positions": 0},
            True,
            f"Phase 9 error ({error_type}): {error_msg[:100]}",
        )
