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

        recon = DailyReconciliation(config)
        result = recon.run_daily_reconciliation(run_date)
        status = 'success' if result.get('success') else 'error'
        summary = (
            f'Portfolio ${result.get("portfolio_value", 0):,.2f}, '
            f'{result.get("positions", 0)} positions, '
            f'unrealized P&L ${result.get("unrealized_pnl", 0):+,.2f}'
        ) if result.get('success') else result.get('error', 'unknown')
        log_phase_result_fn(7, 'reconciliation', status, summary)

        # Compute and log live performance metrics
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
