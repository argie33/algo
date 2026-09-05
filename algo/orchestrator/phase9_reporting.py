"""Phase 9 daily-report/performance/risk-metrics generation, extracted from
phase9_reconciliation.py (2026-09-05, file-size ratchet: that file is a Tier-2 bloater
flagged for decomposition). Bodies are verbatim, no logic changed - only moved file.

`DatabaseContext`/`acquire_advisory_lock`/`release_advisory_lock` are accessed via the
phase9_reconciliation module object at call time (not imported by name here) because several
existing tests patch `algo.orchestrator.phase9_reconciliation.DatabaseContext` (and the two
advisory-lock functions) expecting that to affect these functions - a plain import here would
silently stop seeing those patches.
"""

import json
import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

import algo.orchestrator.phase9_reconciliation as _p9r
from utils.db.advisory_locks import ALGO_AUDIT_LOG_LOCK_ID, ALGO_METRICS_DAILY_LOCK_ID

logger = logging.getLogger(__name__)


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
    if "success" not in stpp_result:
        raise RuntimeError(
            "[PHASE 9] CRITICAL: signal trade performance result missing 'success' field. "
            "Cannot determine if signal attribution computation succeeded. "
            "Check SignalTradePerformancePopulator.populate_closed_trades() return value."
        )
    log_phase_result_fn(
        9,
        "signal_attribution",
        "success" if stpp_result["success"] else "warn",
        f"{trades_processed} trades processed",
    )
    return trades_processed


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
            with _p9r.DatabaseContext("write") as cur:  # type: ignore[attr-defined]
                _p9r.acquire_advisory_lock(cur, ALGO_AUDIT_LOG_LOCK_ID, "algo_audit_log")  # type: ignore[attr-defined]
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
                            # BUG FOUND 2026-08-10 (live-reproduced): several of DailyFinanceReport's
                            # sub-fetchers (_fetch_risk/_fetch_strategy/_fetch_components/etc) return
                            # raw date/datetime values pulled straight from DB rows without str()
                            # conversion. json.dumps() raised TypeError on every run - not caught by
                            # this block's except (only catches DatabaseError/OperationalError/
                            # RuntimeError) - so it propagated uncaught out of Phase 9 as
                            # "TypeError: Object of type date is not JSON serializable", marking the
                            # entire orchestrator run FAILED and skipping the audit log INSERT
                            # entirely, even though reconciliation itself succeeded and no other phase
                            # had any problem. default=str is the standard safe fallback for an
                            # archival JSON text column - it doesn't matter which nested sub-fetcher
                            # the date came from, and there's no reason to chase every possible one.
                            json.dumps(report, default=str),
                        ),
                    )
                finally:
                    _p9r.release_advisory_lock(cur, ALGO_AUDIT_LOG_LOCK_ID, "algo_audit_log")  # type: ignore[attr-defined]
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
                else f"{float(current_val):,.0f}"
                if current_val is not None
                else "N/A"
            )
            pnl_pct_str = (
                str(pnl_pct)
                if isinstance(pnl_pct, str)
                else f"{float(pnl_pct):+.2f}%"
                if pnl_pct is not None
                else "N/A"
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
                # CRITICAL: Only halt if ACTUALLY in live trading (execution_mode="auto" AND alpaca_paper_trading=False)
                # If alpaca_paper_trading=True, we're using Alpaca's PAPER endpoint, not real money
                #
                # BUG FOUND 2026-08-10: this used to silently default a missing config key to
                # True (paper), which fails OPEN for this specific gate - if alpaca_paper_trading
                # were ever missing while actually live, `is_live_trading` below would silently
                # compute False, and the live-Sharpe circuit breaker just below (the check that
                # halts real-money trading when performance craters) would never fire at all, not
                # just apply a looser threshold. Every other consumer of this config key in the
                # codebase (phase6/8, alpaca_broker_adapter.py, execution_config.py,
                # alpaca_sync_manager.py, infrastructure/reconciliation.py, and now
                # circuit_breaker.py's consecutive-losses check) already fails fast instead of
                # guessing. Matching that here.
                execution_mode = config.get("execution_mode")
                if "alpaca_paper_trading" not in config:
                    raise ValueError(
                        "[PHASE 9] Config missing 'alpaca_paper_trading'. "
                        "Trading mode must be explicit (paper vs live) before the live-Sharpe "
                        "circuit breaker can be evaluated. Check algo_config table has this key."
                    )
                alpaca_paper_trading = config["alpaca_paper_trading"]
                min_sharpe_val = config.get("min_live_sharpe_ratio")
                min_sharpe = float(min_sharpe_val) if min_sharpe_val is not None else 0.0

                is_live_trading = execution_mode == "auto" and not alpaca_paper_trading
                if is_live_trading and sharpe is not None and sharpe < min_sharpe:
                    error_msg = (
                        f"[PHASE 9 CRITICAL] Live Sharpe ratio ({sharpe:.2f}) is below minimum threshold ({min_sharpe:.2f}) "
                        f"in LIVE TRADING MODE (execution_mode=auto, alpaca_paper_trading=False). Cannot proceed with real money trading. "
                        f"Fix: (1) Review backtest for overfitting, (2) Verify signal quality, "
                        f"(3) Wait for larger sample size (need 100+ trades), "
                        f"(4) Check if market regime changed. "
                        f"Options: Set execution_mode to 'paper' to continue testing, or adjust min_live_sharpe_ratio in config."
                    )
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg)
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
    except (RuntimeError, ValueError) as rv_e:
        # CRITICAL: RuntimeError/ValueError indicate data quality issues (insufficient history, etc).
        # These MUST propagate to halt Phase 9 per GOVERNANCE (fail-fast).
        # Never silently degrade on data quality failures.
        raise RuntimeError(f"[PHASE 9] Data quality error in performance metrics: {rv_e}") from rv_e
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
                # BUG FOUND 2026-09-01 (/goal session, risk-mgmt review pass): this `alerts`
                # list (VaR>2%, concentration>30%, beta>2.0x) was only ever folded into the
                # "N alerts" phase-result log line above - never surfaced via notify() like
                # every other portfolio-level risk breach in this codebase (this same file's
                # own P&L-divergence call site above, phase2_circuit_breakers.py's halt
                # alerts, notify_signal_staleness()). A real VaR/beta/concentration breach
                # was invisible unless someone read algo_risk_daily or this log by hand.
                try:
                    from algo.reporting import notify

                    notify(
                        severity="warning",
                        title="Portfolio Risk Report Alert",
                        message=f"{run_date}: " + "; ".join(alerts),
                        details={"alerts": alerts, "run_date": str(run_date)},
                    )
                except (ValueError, TypeError, RuntimeError) as notify_err:
                    logger.error(f"[PHASE 9] Failed to send risk alert notification: {notify_err}")
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
    # CRITICAL FIX: unlike its three sibling functions above (_validate_pnl_step,
    # _compute_performance_metrics, _compute_risk_metrics), metrics_status/metrics_summary were
    # only ever assigned inside the try body's success/no-trades branches, not pre-initialized
    # before the try. A psycopg2.DatabaseError/OperationalError raised before either branch runs
    # (e.g. during the SELECTs or the INSERT) hits the except clause, which raises a RuntimeError
    # with the intended "[PHASE 9 CRITICAL] Failed to persist metrics..." message - but the
    # finally block below then references the still-unassigned locals, raising UnboundLocalError
    # from inside finally, which replaces that RuntimeError as the exception actually propagated.
    # A real DB failure here reported as a confusing Python internals crash instead of the
    # intended diagnostic message.
    metrics_status = "warn"
    metrics_summary = "N/A"
    try:
        row_data = None
        with _p9r.DatabaseContext("read") as cur:  # type: ignore[attr-defined]
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

            with _p9r.DatabaseContext("write") as write_cur:  # type: ignore[attr-defined]
                _p9r.acquire_advisory_lock(write_cur, ALGO_METRICS_DAILY_LOCK_ID, "algo_metrics_daily")  # type: ignore[attr-defined]
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
                    _p9r.release_advisory_lock(write_cur, ALGO_METRICS_DAILY_LOCK_ID, "algo_metrics_daily")  # type: ignore[attr-defined]
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
