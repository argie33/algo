#!/usr/bin/env python3

import json
import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, Dict

from algo.orchestrator.phase_result import PhaseResult
from utils.db.context import DatabaseContext
from utils.trading.recorder import TradeRecorder


logger = logging.getLogger(__name__)


def run(
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable,
    dry_run: bool = False,
) -> PhaseResult:
    """Execute Phase 7: Reconciliation & Snapshot.

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
        reconciliation_succeeded = result.get("success", False)
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
                f'Portfolio ${result["portfolio_value"]:,.2f}, '
                f'{result["positions"]} positions, '
                f'unrealized P&L ${result["unrealized_pnl"]:+,.2f}'
            )
        else:
            summary = result.get("error", "unknown")
        log_phase_result_fn(7, "reconciliation", status, summary)

        # CRITICAL: Validate that local P&L matches Alpaca P&L
        pnl_validation_status = "warn"
        pnl_validation_summary = "N/A"
        try:
            alpaca_data = recon._fetch_alpaca_account()
            if alpaca_data and reconciliation_succeeded:
                alpaca_equity = alpaca_data.get("equity")
                if alpaca_equity is None:
                    alpaca_equity = alpaca_data.get("portfolio_value")
                    if alpaca_equity is None:
                        logger.error(
                            "[PHASE 7 P&L VALIDATION] Alpaca data missing both 'equity' and "
                            "'portfolio_value'. Available keys: " + str(list(alpaca_data.keys()))
                        )
                        raise ValueError(
                            "Alpaca data missing equity and portfolio_value — cannot validate P&L"
                        )
                local_equity = result.get("portfolio_value", 0)

                pnl_check = recon.validate_pnl(alpaca_equity, local_equity)
                pnl_validation_status = pnl_check["status"]
                pnl_validation_summary = pnl_check["message"]

                if pnl_check["status"] == "ok":
                    logger.info(f"[PHASE 7 P&L VALIDATION] {pnl_check['message']}")
                elif pnl_check["status"] == "alert":
                    logger.warning(f"[PHASE 7 P&L VALIDATION] {pnl_check['message']}")
                else:  # critical
                    logger.critical(f"[PHASE 7 P&L VALIDATION] {pnl_check['message']}")
            else:
                pnl_validation_summary = "Skipped (reconciliation failed or no Alpaca data)"
        except Exception as e:
            logger.error(f"[PHASE 7] P&L validation failed: {e}")
            pnl_validation_summary = f"error: {str(e)[:60]}"
        finally:
            log_phase_result_fn(7, "pnl_validation", pnl_validation_status, pnl_validation_summary)

        # CRITICAL: Audit for stale estimated exit prices (reconciliation issues)
        try:
            with DatabaseContext("read") as audit_cur:
                stale_audit = recon.audit_stale_estimated_prices(audit_cur)
                if stale_audit["status"] != "OK":
                    logger.warning(
                        f"[PHASE 7 AUDIT] Stale estimated prices detected: {stale_audit['message']}"
                    )
                    log_phase_result_fn(
                        7, "exit_reconciliation_audit", "warn", stale_audit["message"]
                    )
                else:
                    logger.info("[PHASE 7 AUDIT] All exit prices reconciled properly")
        except Exception as e:
            logger.error(f"[PHASE 7] Exit price audit failed: {e}")

        # Record exits for recently closed positions
        try:
            recorder = TradeRecorder()

            with DatabaseContext("read") as cursor:
                # Find positions that were closed today
                cursor.execute(
                    """
                    SELECT symbol, avg_entry_price, current_price, quantity
                    FROM algo_positions
                    WHERE status = 'closed' AND closed_at::date = %s
                """,
                    (run_date,),
                )

                closed_positions = cursor.fetchall()
                exits_recorded = 0

                for symbol, entry_price, exit_price, quantity in closed_positions:
                    if not exit_price:
                        logger.critical(
                            f"[CRITICAL] Exit price missing for {symbol}: cannot use entry price "
                            f"(${entry_price}) as fallback. This corrupts P&L. Skipping exit record."
                        )
                        continue
                    if recorder.record_exit(
                        symbol=symbol,
                        exit_date=run_date,
                        exit_price=float(exit_price),
                        quantity=int(quantity),
                        reason="Closed position recorded during reconciliation",
                    ):
                        exits_recorded += 1

                if exits_recorded > 0:
                    logger.info(f"Recorded {exits_recorded} exits in trade history")
        except Exception as e:
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
            logger.info(
                f"Signal trade performance: {stpp_result.get('message', 'N/A')}"
            )
            if stpp_result.get("ic_values"):
                logger.info(f"  IC values computed: {stpp_result['ic_values']}")
        except Exception as e:
            logger.warning(
                f"Signal trade performance failed (numpy/scipy not available): {e}"
            )
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
            logger.info(
                f"Signal attribution: IC computed for {len(attr_result)} components"
            )
            for comp, ic_data in attr_result.items():
                logger.info(
                    f"  {comp}: IC={ic_data.get('ic_value', 0):.3f}, pval={ic_data.get('ic_pvalue', 1):.3f}"
                )
            if attr_result:
                attribution.persist(run_date, attr_result)
        except ImportError as e:
            logger.warning(
                f"Signal attribution skipped (scipy/numpy not available): {e}"
            )
        except ValueError as e:
            logger.warning(
                f"Signal attribution skipped (insufficient trades or invalid data): {e}"
            )
        except Exception as e:
            logger.error(
                f"Signal attribution failed unexpectedly: {e}",
                exc_info=True
            )
        log_phase_result_fn(
            7,
            "ic_computation",
            "success" if attr_result else "warn",
            f"{len(attr_result)} components analyzed",
        )

        # Step 3: Run weight optimization (if enough trades)
        opt_result: Dict[str, Any] = {"changes": []}
        try:
            from algo.orchestration import RegimeManager as _RegimeManager

            _current_regime = _RegimeManager().get_current_regime(run_date)
            optimizer = WeightOptimizer(config)
            opt_result = optimizer.apply(
                run_date, regime=_current_regime, dry_run=False
            )
            if opt_result.get("changes"):
                logger.info(
                    f"Weight optimization: {len(opt_result['changes'])} changes applied"
                )
                for change in opt_result["changes"]:
                    logger.info(
                        f"  {change['component']}: {change['old_weight']}% → {change['new_weight']}%"
                    )
            else:
                logger.info(
                    "Weight optimization: no changes (insufficient trades or weights stable)"
                )
        except ValueError as e:
            logger.warning(
                f"Weight optimization skipped (insufficient trades): {e}"
            )
        except ImportError as e:
            logger.warning(
                f"Weight optimization skipped (scipy/numpy not available): {e}"
            )
        except Exception as e:
            logger.error(
                f"Weight optimization failed unexpectedly: {e}",
                exc_info=True
            )
        log_phase_result_fn(
            7,
            "weight_optimization",
            "success" if opt_result.get("success") else "warn",
            f"{len(opt_result.get('changes', []))} weight changes",
        )

        # Step 4: Generate institutional daily report
        try:
            daily_report = DailyFinanceReport()
            report = daily_report.generate(run_date)
            report_text = daily_report.format_text(report)
            logger.info(f"\n{report_text}")
        except Exception as e:
            logger.error(
                f"Daily report generation failed (could not generate): {e}",
                exc_info=True
            )
            log_phase_result_fn(7, "daily_report", "warn", f"generation error: {str(e)[:60]}")
        else:
            # Validate critical report data before use
            try:
                if not report or "portfolio" not in report:
                    raise ValueError("Daily report generated but missing portfolio data")
                portfolio_data = report.get("portfolio", {})
                if "current_value" not in portfolio_data or portfolio_data.get("current_value") is None:
                    raise ValueError("Portfolio data missing current_value")
                if "daily_pnl_pct" not in portfolio_data or portfolio_data.get("daily_pnl_pct") is None:
                    raise ValueError("Portfolio data missing daily_pnl_pct")

                # Log to algo_audit_log for historical tracking
                try:
                    with DatabaseContext("write") as cur:
                        cur.execute(
                            """
                            INSERT INTO algo_audit_log (
                                action_type, action_date, symbol, details, created_at
                            ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                            """,
                            ("daily_report", run_date, "PORTFOLIO", json.dumps(report)),
                        )
                except Exception as e:
                    logger.critical(
                        f"[AUDIT_FAILURE] Could not log daily report to audit log: {e}"
                    )
                    raise

                log_phase_result_fn(
                    7,
                    "daily_report",
                    "success",
                    f"Portfolio ${portfolio_data['current_value']:,.0f}, "
                    f"P&L {portfolio_data['daily_pnl_pct']:+.2f}%",
                )
            except ValueError as e:
                logger.error(
                    f"Daily report validation failed (generated but data incomplete): {e}"
                )
                log_phase_result_fn(7, "daily_report", "warn", f"validation error: {str(e)[:60]}")

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
        except Exception as e:
            perf_summary = f"error: {str(e)[:60]}"
        finally:
            log_phase_result_fn(7, "performance", perf_status, perf_summary)

        # Compute and log risk metrics
        risk_status = "warn"
        risk_summary = "N/A"
        try:
            from algo.risk import ValueAtRisk

            risk = ValueAtRisk(config)
            risk_report = risk.generate_daily_risk_report(run_date)
            if risk_report and risk_report.get("status") == "ok":
                risk_status = "success"
                var_pct = (
                    risk_report.get("var_metrics", {}).get("var_pct", "N/A")
                    if risk_report.get("var_metrics")
                    else "N/A"
                )
                conc_pct = (
                    risk_report.get("concentration", {}).get(
                        "top_5_concentration_pct", "N/A"
                    )
                    if risk_report.get("concentration")
                    else "N/A"
                )
                alerts_count = len(risk_report.get("alerts", []))
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
            log_phase_result_fn(7, "risk_metrics", risk_status, risk_summary)

        # Step 6: Update algo_metrics_daily with actual trade results from this run
        metrics_status = "warn"
        metrics_summary = "N/A"
        try:
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
                row = cur.fetchone()
                if row:
                    total_actions, entries, exits, avg_score = row
                    # UPSERTable into algo_metrics_daily
                    with DatabaseContext("write") as write_cur:
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
                                total_actions or 0,
                                entries or 0,
                                exits or 0,
                                avg_score,
                            ),
                        )
                    metrics_status = "success"
                    metrics_summary = f"{total_actions or 0} actions, {entries or 0} entries, {exits or 0} exits"
                    logger.info(f"Updated algo_metrics_daily: {metrics_summary}")
                else:
                    logger.info("No trades recorded today (metrics not updated)")
                    metrics_status = "warn"
                    metrics_summary = "No trades recorded"
        except Exception as e:
            logger.warning(f"Failed to update algo_metrics_daily: {e}")
            metrics_summary = f"error: {str(e)[:60]}"
        finally:
            log_phase_result_fn(7, "metrics_update", metrics_status, metrics_summary)

        # Refresh materialized view so positions dashboard reflects current state.
        # This runs after reconciliation updates algo_positions from Alpaca.
        try:
            with DatabaseContext("write") as cur:
                cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
            logger.info("[PHASE 7] Refreshed algo_positions_with_risk materialized view")
            log_phase_result_fn(7, "positions_view_refresh", "success", "algo_positions_with_risk refreshed")
        except Exception as e:
            logger.warning(f"[PHASE 7] Could not refresh algo_positions_with_risk: {e}")
            log_phase_result_fn(7, "positions_view_refresh", "warn", f"refresh failed: {str(e)[:60]}")

        data = {
            "portfolio_value": result.get("portfolio_value") if reconciliation_succeeded else 0,
            "positions": result.get("positions") if reconciliation_succeeded else 0,
            "unrealized_pnl": result.get("unrealized_pnl") if reconciliation_succeeded else 0,
            "reconciliation": result,
        }

        # Return status reflecting whether the core reconciliation succeeded
        phase_status = "ok" if reconciliation_succeeded else "error"
        return PhaseResult(7, "reconciliation", phase_status, data, False, None)

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(7, "reconciliation", "error", str(e))
        return PhaseResult(7, "reconciliation", "error", {}, False, str(e))
