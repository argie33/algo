#!/usr/bin/env python3
"""
Phase 7: RECONCILIATION & SNAPSHOT

Pull live Alpaca account data, sync positions, calculate P&L,
create daily portfolio snapshot.

Also computes:
- Live performance metrics (Sharpe, win rate, expectancy)
- Risk metrics (VaR, concentration, alerts)

FAIL-OPEN: log if Alpaca down.
"""

import json
import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, Dict

from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager

logger = logging.getLogger(__name__)


def run(
    config: Any,
    get_conn: Callable,
    put_conn: Callable,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 7: Reconciliation & Snapshot.

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
        PhaseResult with status 'ok' (fail-open), data containing reconciliation results
    """
    try:
        from algo.algo_daily_reconciliation import DailyReconciliation
        from algo.algo_signal_trade_performance import SignalTradePerformancePopulator
        from algo.algo_signal_attribution import SignalAttributionEngine
        from algo.algo_weight_optimizer import WeightOptimizer
        from algo.algo_daily_report import DailyFinanceReport

        recon = DailyReconciliation(config)
        result = recon.run_daily_reconciliation(run_date)
        status = 'success' if result.get('success') else 'error'
        summary = (
            f'Portfolio ${result.get("portfolio_value", 0):,.2f}, '
            f'{result.get("positions", 0)} positions, '
            f'unrealized P&L ${result.get("unrealized_pnl", 0):+,.2f}'
        ) if result.get('success') else result.get('error', 'unknown')
        log_phase_result_fn(7, 'reconciliation', status, summary)

        # Step 1: Populate signal_trade_performance from closed trades
        stpp = SignalTradePerformancePopulator()
        stpp_result = stpp.populate_closed_trades(lookback_days=7)
        trades_processed = stpp_result.get('trades_processed', 0)
        logger.info(f"Signal trade performance: {stpp_result.get('message', 'N/A')}")
        if stpp_result.get('ic_values'):
            logger.info(f"  IC values computed: {stpp_result['ic_values']}")
        log_phase_result_fn(7, 'signal_attribution', 'success' if stpp_result.get('success') else 'warn',
                          f"{trades_processed} trades processed")

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
        except Exception as e:
            logger.warning(f"Signal attribution failed: {e}")
        log_phase_result_fn(7, 'ic_computation', 'success' if attr_result else 'warn',
                          f"{len(attr_result)} components analyzed")

        # Step 3: Run weight optimization (if enough trades)
        opt_result = {'changes': []}
        try:
            from algo.algo_regime_manager import RegimeManager as _RegimeManager
            _current_regime = _RegimeManager().get_current_regime(run_date) or 'confirmed_uptrend'
            optimizer = WeightOptimizer(config)
            opt_result = optimizer.apply(run_date, regime=_current_regime, dry_run=False)
            if opt_result.get('changes'):
                logger.info(f"Weight optimization: {len(opt_result['changes'])} changes applied")
                for change in opt_result['changes']:
                    logger.info(f"  {change['component']}: {change['old_weight']}% → {change['new_weight']}%")
            else:
                logger.info("Weight optimization: no changes (insufficient trades or weights stable)")
        except Exception as e:
            logger.warning(f"Weight optimization failed: {e}")
        log_phase_result_fn(7, 'weight_optimization', 'success' if opt_result.get('success') else 'warn',
                          f"{len(opt_result.get('changes', []))} weight changes")

        # Step 4: Generate institutional daily report
        try:
            daily_report = DailyFinanceReport()
            report = daily_report.generate(run_date)
            report_text = daily_report.format_text(report)
            logger.info(f"\n{report_text}")

            # Log to algo_audit_log for historical tracking
            if get_conn and put_conn:
                conn = None
                cur = None
                try:
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO algo_audit_log (
                            action_type, action_date, symbol, details, created_at
                        ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        ('daily_report', run_date, 'PORTFOLIO', json.dumps(report)),
                    )
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to log daily report to audit log: {e}")
                finally:
                    if cur:
                        try:
                            cur.close()
                        except Exception:
                            pass
                    if conn:
                        put_conn(conn)

            log_phase_result_fn(7, 'daily_report', 'success',
                              f"Portfolio ${report.get('portfolio', {}).get('current_value', 0):,.0f}, "
                              f"P&L {report.get('portfolio', {}).get('daily_pnl_pct', 0):+.2f}%")
        except Exception as e:
            logger.warning(f"Daily report generation failed: {e}")
            log_phase_result_fn(7, 'daily_report', 'warn', f"error: {str(e)[:60]}")

        # Compute and log live performance metrics (legacy, kept for compatibility)
        perf_status = 'warn'
        perf_summary = 'N/A'
        try:
            from algo.algo_performance import LivePerformance
            perf = LivePerformance(config)
            perf_report = perf.generate_daily_report(run_date)
            if perf_report and perf_report.get('status') == 'ok':
                perf_status = 'success'
                perf_summary = (
                    f"Sharpe {perf_report.get('rolling_sharpe_252d', 'N/A')}, "
                    f"Win rate {perf_report.get('win_rate_50t', 'N/A')}%, "
                    f"Expectancy {perf_report.get('expectancy', 'N/A')}"
                )
            elif perf_report:
                perf_summary = perf_report.get('message', 'insufficient data')
            else:
                perf_summary = 'failed to generate report'
        except Exception as e:
            perf_summary = f'error: {str(e)[:60]}'
        finally:
            log_phase_result_fn(7, 'performance', perf_status, perf_summary)

        # Compute and log risk metrics
        risk_status = 'warn'
        risk_summary = 'N/A'
        try:
            from algo.algo_var import PortfolioRisk
            risk = PortfolioRisk(config)
            risk_report = risk.generate_daily_risk_report(run_date)
            if risk_report and risk_report.get('status') == 'ok':
                risk_status = 'success'
                var_pct = risk_report.get('var_metrics', {}).get('var_pct', 'N/A') if risk_report.get('var_metrics') else 'N/A'
                conc_pct = risk_report.get('concentration', {}).get('top_5_concentration_pct', 'N/A') if risk_report.get('concentration') else 'N/A'
                alerts_count = len(risk_report.get('alerts', []))
                risk_summary = (
                    f"VaR {var_pct}%, Concentration {conc_pct}%"
                    + (f", {alerts_count} alerts" if alerts_count else "")
                )
            elif risk_report:
                risk_summary = risk_report.get('message', 'insufficient data')
            else:
                risk_summary = 'failed to generate report'
        except Exception as e:
            risk_summary = f'error: {str(e)[:60]}'
        finally:
            log_phase_result_fn(7, 'risk_metrics', risk_status, risk_summary)

        data = {
            'portfolio_value': result.get('portfolio_value', 0),
            'positions': result.get('positions', 0),
            'unrealized_pnl': result.get('unrealized_pnl', 0),
            'reconciliation': result,
        }

        return PhaseResult(7, 'reconciliation', 'ok', data, False, None)

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(7, 'reconciliation', 'error', str(e))
        return PhaseResult(7, 'reconciliation', 'ok', {}, False, str(e))
