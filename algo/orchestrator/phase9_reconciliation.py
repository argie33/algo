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


def run(
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable,
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
        from algo.orchestration import WeightOptimizer
        from algo.reporting import DailyFinanceReport
        from algo.signals.attribution import SignalAttributionEngine
        from algo.signals.trade_performance import SignalTradePerformancePopulator

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

        # CRITICAL: Detect and warn if mock data is being returned (indicates dry run mode)
        if result.get("_is_mock_data", False):
            logger.critical(
                "[PHASE 7 SAFETY] Mock data detected in reconciliation result. "
                "This indicates dry_run mode is active. Portfolio value and cash are SYNTHETIC. "
                "Verify this is intentional and ORCHESTRATOR_DRY_RUN is set in the environment."
            )

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
            summary = result.get("error", "unknown")
        log_phase_result_fn(9, "reconciliation", status, summary)

        # CRITICAL: Validate that local P&L matches Broker P&L
        pnl_validation_status = "warn"
        pnl_validation_summary = "N/A"
        try:
            account_data = recon.broker.fetch_account()
            if account_data and reconciliation_succeeded:
                broker_equity = account_data.get("equity")
                if broker_equity is None:
                    broker_equity = account_data.get("portfolio_value")
                    if broker_equity is None:
                        logger.error(
                            "[PHASE 7 P&L VALIDATION] Broker data missing both 'equity' and "
                            "'portfolio_value'. Available keys: " + str(list(account_data.keys()))
                        )
                        raise ValueError("Broker data missing equity and portfolio_value — cannot validate P&L")

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

        # CRITICAL: Audit for stale estimated exit prices (reconciliation issues)
        try:
            with DatabaseContext("read") as audit_cur:
                stale_audit = recon.audit_stale_estimated_prices(audit_cur)
                if stale_audit.get("status", "OK") != "OK":
                    msg = stale_audit.get("message", str(stale_audit))
                    logger.warning(f"[PHASE 7 AUDIT] Stale estimated prices detected: {msg}")
                    log_phase_result_fn(9, "exit_reconciliation_audit", "warn", msg)
                else:
                    logger.info("[PHASE 7 AUDIT] All exit prices reconciled properly")
        except (psycopg2.DatabaseError, psycopg2.OperationalError, KeyError) as e:
            logger.error(f"[PHASE 7] Exit price audit failed: {e}")

        # Record exits for recently closed positions (batch operation to avoid N+1 queries)
        try:
            # FIX: Fetch all data in single read context, then perform writes in separate context
            # Prevents nested transaction deadlocks and maintains ACID isolation
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
                # Single write context for all updates (no nested contexts)
                with DatabaseContext("write") as write_cursor:
                    # Acquire locks for both tables to prevent concurrent writes
                    acquire_advisory_lock(write_cursor, ALGO_TRADES_LOCK_ID, "algo_trades")
                    acquire_advisory_lock(write_cursor, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                    try:
                        for symbol, entry_price, exit_price, quantity in closed_positions:
                            if not exit_price:
                                logger.critical(
                                    f"[CRITICAL] Exit price missing for {symbol}: cannot use entry price "
                                    f"(${entry_price}) as fallback. This corrupts P&L. Skipping exit record."
                                )
                                continue

                            pnl = (exit_price - entry_price) * quantity
                            pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

                            try:
                                write_cursor.execute(
                                    """
                                    UPDATE algo_trades
                                    SET exit_date = %s, exit_price = %s, profit_loss_dollars = %s,
                                        profit_loss_pct = %s, exit_reason = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE symbol = %s AND exit_date IS NULL
                                    ORDER BY entry_date DESC LIMIT 1
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
                                logger.info(
                                    f"Recorded exit: {symbol} {quantity}sh @ ${exit_price:.2f} on {run_date} "
                                    f"(P&L: ${pnl:.2f} / {pnl_pct:.1f}%)"
                                )
                            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
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

        # Step 1: Populate signal_trade_performance from closed trades
        stpp_result = {"success": False, "trades_processed": 0}
        try:
            stpp = SignalTradePerformancePopulator()
            stpp_result = stpp.populate_closed_trades(lookback_days=7)
            trades_processed = stpp_result.get("trades_processed", 0)
            logger.info(f"Signal trade performance: {stpp_result.get('message', 'N/A')}")
            if stpp_result.get("ic_values"):
                logger.info(f"  IC values computed: {stpp_result['ic_values']}")
        except Exception as e:
            logger.warning(f"Signal trade performance failed (numpy/scipy not available): {e}")
        trades_processed = stpp_result.get("trades_processed", 0)
        log_phase_result_fn(
            7,
            "signal_attribution",
            "success" if stpp_result.get("success") else "warn",
            f"{trades_processed} trades processed",
        )

        # Step 2: Compute IC via attribution engine
        attr_result = {}
        try:
            attribution = SignalAttributionEngine()
            attr_result = attribution.compute_ic(run_date, lookback_trades=40)
            # compute_ic returns {component_name: {ic_value, ic_pvalue, sample_size, ...}}
            logger.info(f"Signal attribution: IC computed for {len(attr_result)} components")
            for comp, ic_data in attr_result.items():
                logger.info(f"  {comp}: IC={ic_data.get('ic_value', 0):.3f}, pval={ic_data.get('ic_pvalue', 1):.3f}")
            if attr_result:
                attribution.persist(run_date, attr_result)
        except ImportError as e:
            logger.warning(f"Signal attribution skipped (scipy/numpy not available): {e}")
        except ValueError as e:
            logger.warning(f"Signal attribution skipped (insufficient trades or invalid data): {e}")
        except Exception as e:
            logger.error(f"Signal attribution failed unexpectedly: {e}", exc_info=True)
        log_phase_result_fn(
            7,
            "ic_computation",
            "success" if attr_result else "warn",
            f"{len(attr_result)} components analyzed",
        )

        # Step 3: Run weight optimization (if enough trades)
        opt_result: dict[str, Any] = {"changes": []}
        try:
            from algo.orchestration import RegimeManager as _RegimeManager

            _current_regime = _RegimeManager().get_current_regime(run_date)
            optimizer = WeightOptimizer(config)
            opt_result = optimizer.apply(run_date, regime=_current_regime, dry_run=False)
            if opt_result.get("changes"):
                logger.info(f"Weight optimization: {len(opt_result['changes'])} changes applied")
                for change in opt_result["changes"]:
                    logger.info(f"  {change['component']}: {change['old_weight']}% → {change['new_weight']}%")
            else:
                logger.info("Weight optimization: no changes (insufficient trades or weights stable)")
        except ValueError as e:
            logger.warning(f"Weight optimization skipped (insufficient trades): {e}")
        except ImportError as e:
            logger.warning(f"Weight optimization skipped (scipy/numpy not available): {e}")
        except Exception as e:
            logger.error(f"Weight optimization failed unexpectedly: {e}", exc_info=True)
        changes = opt_result.get("changes") if opt_result else []
        log_phase_result_fn(
            7,
            "weight_optimization",
            "success" if opt_result and opt_result.get("success") else "warn",
            f"{len(changes) if changes else 0} weight changes",
        )

        # Step 4: Generate institutional daily report
        try:
            daily_report = DailyFinanceReport()
            report = daily_report.generate(run_date)
            report_text = daily_report.format_text(report)
            logger.info(f"\n{report_text}")
        except Exception as e:
            logger.error(f"Daily report generation failed (could not generate): {e}", exc_info=True)
            log_phase_result_fn(9, "daily_report", "warn", f"generation error: {str(e)[:60]}")
        else:
            # Validate critical report data before use
            try:
                if not report or "portfolio" not in report:
                    raise ValueError("Daily report generated but missing portfolio data")
                portfolio_data = report.get("portfolio")
                if (
                    not portfolio_data
                    or "current_value" not in portfolio_data
                    or portfolio_data.get("current_value") is None
                ):
                    raise ValueError("Portfolio data missing current_value")
                if (
                    not portfolio_data
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
                                ("daily_report", run_date, "PORTFOLIO", json.dumps(report)),
                            )
                        finally:
                            release_advisory_lock(cur, ALGO_AUDIT_LOG_LOCK_ID, "algo_audit_log")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.critical(f"[AUDIT_FAILURE] Could not log daily report to audit log: {e}")
                    raise

                current_val = portfolio_data.get("current_value", "N/A") if portfolio_data else "N/A"
                pnl_pct = portfolio_data.get("daily_pnl_pct", "N/A") if portfolio_data else "N/A"
                log_phase_result_fn(
                    7,
                    "daily_report",
                    "success",
                    f"Portfolio ${current_val if isinstance(current_val, str) else f'{current_val:,.0f}'}, P&L {pnl_pct if isinstance(pnl_pct, str) else f'{pnl_pct:+.2f}%'}",
                )
            except ValueError as e:
                logger.error(f"Daily report validation failed (generated but data incomplete): {e}")
                log_phase_result_fn(9, "daily_report", "warn", f"validation error: {str(e)[:60]}")

        # Step 5: Compute and log live performance metrics
        perf_status = "warn"
        perf_summary = "N/A"
        try:
            from algo.reporting import LivePerformance

            perf = LivePerformance(config)
            perf_report = perf.generate_daily_report(run_date)
            if perf_report and perf_report.get("status") == "ok":
                perf_status = "success"
                perf_summary = (
                    f"Sharpe {perf_report.get('rolling_sharpe_252d', 'N/A')}, "
                    f"Win rate {perf_report.get('win_rate_50t', 'N/A')}%, "
                    f"Expectancy {perf_report.get('expectancy', 'N/A')}"
                )
            elif perf_report:
                perf_summary = perf_report.get("message", "insufficient data")
            else:
                perf_summary = "failed to generate report"
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            perf_summary = f"error: {str(e)[:60]}"
        finally:
            log_phase_result_fn(9, "performance", perf_status, perf_summary)

        # Compute and log risk metrics
        risk_status = "warn"
        risk_summary = "N/A"
        try:
            from algo.risk import ValueAtRisk

            risk = ValueAtRisk(config)
            risk_report = risk.generate_daily_risk_report(run_date)
            if risk_report and risk_report.get("status") == "ok":
                risk_status = "success"
                var_metrics = risk_report.get("var_metrics") if risk_report else None
                var_pct = var_metrics.get("var_pct", "N/A") if var_metrics else "N/A"
                concentration = risk_report.get("concentration") if risk_report else None
                conc_pct = concentration.get("top_5_concentration_pct", "N/A") if concentration else "N/A"
                alerts = risk_report.get("alerts") if risk_report else []
                alerts_count = len(alerts) if alerts else 0
                risk_summary = f"VaR {var_pct}%, Concentration {conc_pct}%" + (
                    f", {alerts_count} alerts" if alerts_count else ""
                )
            elif risk_report:
                risk_summary = risk_report.get("message", "insufficient data")
            else:
                risk_summary = "failed to generate report"
        except Exception as e:
            risk_summary = f"error: {str(e)[:60]}"
        finally:
            log_phase_result_fn(9, "risk_metrics", risk_status, risk_summary)

        # Step 6: Update algo_metrics_daily with actual trade results from this run
        metrics_status = "warn"
        metrics_summary = "N/A"
        try:
            # FIX: Read data first, close context, then perform write in separate transaction
            # Prevents nested transaction deadlocks and maintains ACID isolation
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
                # Explicitly handle None values from aggregate functions (when no matching rows exist)
                # Using None -> 0 conversion is valid only for COUNT aggregates with no matching rows
                total_actions = total_actions if total_actions is not None else 0
                entries = entries if entries is not None else 0
                exits = exits if exits is not None else 0

                # Single write context for UPSERT (no nested contexts)
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
        finally:
            log_phase_result_fn(9, "metrics_update", metrics_status, metrics_summary)

        # Refresh materialized view so positions dashboard reflects current state.
        # This runs after reconciliation updates algo_positions from Broker.
        try:
            with DatabaseContext("write") as cur:
                cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
            logger.info("[PHASE 7] Refreshed algo_positions_with_risk materialized view")
            log_phase_result_fn(9, "positions_view_refresh", "success", "algo_positions_with_risk refreshed")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[PHASE 7] Could not refresh algo_positions_with_risk: {e}")
            log_phase_result_fn(9, "positions_view_refresh", "warn", f"refresh failed: {str(e)[:60]}")

        # Fail-fast: if reconciliation failed, don't include partial data with 0 defaults
        # Downstream code should check phase_status and error message instead
        if reconciliation_succeeded:
            data = {
                "portfolio_value": result.get("portfolio_value"),
                "positions": result.get("positions"),
                "unrealized_pnl": result.get("unrealized_pnl"),
                "reconciliation": result,
            }
            phase_status = "ok"
        else:
            data = {
                "reconciliation": result,
            }
            phase_status = "error"

        return PhaseResult(9, "reconciliation", phase_status, data, False, None)

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        traceback.print_exc()
        log_phase_result_fn(9, "reconciliation", "error", str(e))
        return PhaseResult(9, "reconciliation", "error", {}, False, str(e))
