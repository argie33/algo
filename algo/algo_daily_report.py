#!/usr/bin/env python3

"""
Daily Finance Report — Institutional-style daily metrics and IC attribution.

Reads: algo_performance_daily, algo_risk_daily, algo_component_attribution,
       algo_trades, algo_positions, market_exposure_daily

Outputs: Text report + JSON to algo_audit_log

Called at end of Phase 7 daily orchestration.
"""

import logging
import json
from datetime import date as _date
from typing import Dict, Any, List, Optional

from utils.db_connection import get_db_connection
from config.credential_helper import get_db_config, get_db_password
from algo.algo_regime_manager import RegimeManager

logger = logging.getLogger(__name__)


class DailyFinanceReport:
    """Generate institutional daily finance report."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.regime_mgr = RegimeManager()

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = get_db_connection()
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Close connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def generate(self, report_date: _date = None) -> Dict[str, Any]:
        """
        Generate comprehensive daily report.

        Returns:
            {
                'date': str,
                'portfolio': {...},
                'risk': {...},
                'strategy': {...},
                'components': {...},
                'regime': {...},
                'signals': {...},
                'warnings': [...],
            }
        """
        self.connect()
        if report_date is None:
            report_date = _date.today()

        try:
            report = {
                'date': str(report_date),
                'portfolio': self._fetch_portfolio(report_date),
                'risk': self._fetch_risk(report_date),
                'strategy': self._fetch_strategy(report_date),
                'components': self._fetch_components(report_date),
                'regime': self._fetch_regime(report_date),
                'signals': self._fetch_signals(report_date),
                'warnings': [],
            }

            # Check thresholds
            report['warnings'] = self._check_thresholds(report)

            logger.info(f"Daily report generated for {report_date}")
            return report

        finally:
            self.disconnect()

    def _fetch_portfolio(self, report_date: _date) -> Dict[str, Any]:
        """Portfolio value, P&L, drawdown."""
        try:
            self.cur.execute(
                """
                SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots
                WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 2
                """,
                (report_date,),
            )
            rows = self.cur.fetchall()

            if not rows:
                return {}

            current_value = float(rows[0][0]) if rows[0][0] else 0
            prior_value = float(rows[1][0]) if len(rows) > 1 and rows[1][0] else current_value

            daily_pnl_pct = ((current_value - prior_value) / prior_value * 100) if prior_value > 0 else 0

            # YTD P&L (simplified)
            self.cur.execute(
                """SELECT total_portfolio_value FROM algo_portfolio_snapshots
                   WHERE EXTRACT(YEAR FROM snapshot_date) = EXTRACT(YEAR FROM %s)
                   ORDER BY snapshot_date ASC LIMIT 1""",
                (report_date,),
            )
            ytd_row = self.cur.fetchone()
            ytd_start = float(ytd_row[0]) if ytd_row and ytd_row[0] else current_value
            ytd_pnl_pct = ((current_value - ytd_start) / ytd_start * 100) if ytd_start > 0 else 0

            return {
                'current_value': round(current_value, 2),
                'daily_pnl_pct': round(daily_pnl_pct, 2),
                'ytd_pnl_pct': round(ytd_pnl_pct, 2),
                'open_positions': self._count_open_positions(report_date),
            }
        except Exception as e:
            logger.debug(f"Portfolio fetch failed: {e}")
            return {}

    def _fetch_risk(self, report_date: _date) -> Dict[str, Any]:
        """VaR, beta, Sharpe, Sortino."""
        try:
            self.cur.execute(
                """SELECT var_95_pct, cvar_95_pct, portfolio_beta, sharpe_252d, sortino_252d
                   FROM algo_risk_daily
                   WHERE report_date <= %s
                   ORDER BY report_date DESC LIMIT 1""",
                (report_date,),
            )
            row = self.cur.fetchone()

            if not row:
                return {}

            return {
                'var_95_pct': round(float(row[0]), 2) if row[0] else None,
                'cvar_95_pct': round(float(row[1]), 2) if row[1] else None,
                'beta': round(float(row[2]), 2) if row[2] else None,
                'sharpe_ytd': round(float(row[3]), 2) if row[3] else None,
                'sortino_ytd': round(float(row[4]), 2) if row[4] else None,
            }
        except Exception as e:
            logger.debug(f"Risk fetch failed: {e}")
            return {}

    def _fetch_strategy(self, report_date: _date) -> Dict[str, Any]:
        """Win rate, profit factor, expectancy, best setup."""
        try:
            self.cur.execute(
                """SELECT win_rate_50t, avg_win_r_50t, avg_loss_r_50t, expectancy
                   FROM algo_performance_daily
                   WHERE report_date <= %s
                   ORDER BY report_date DESC LIMIT 1""",
                (report_date,),
            )
            row = self.cur.fetchone()

            if not row:
                return {}

            win_rate = float(row[0]) if row[0] else 0
            avg_win = float(row[1]) if row[1] else 0
            avg_loss = abs(float(row[2])) if row[2] else 1
            profit_factor = avg_win / max(0.01, avg_loss)

            # Get average hold days from recent closed trades
            avg_hold_days = 0
            self.cur.execute(
                """
                SELECT AVG(trade_duration_days)
                FROM (
                    SELECT trade_duration_days FROM algo_trades
                    WHERE exit_date IS NOT NULL AND exit_date <= %s
                    ORDER BY exit_date DESC LIMIT 100
                ) AS last_100
                """,
                (report_date,),
            )
            hold_row = self.cur.fetchone()
            if hold_row and hold_row[0]:
                avg_hold_days = round(float(hold_row[0]), 1)

            return {
                'win_rate_pct': round(win_rate * 100, 1),
                'profit_factor': round(profit_factor, 2),
                'avg_hold_days': avg_hold_days,
                'expectancy_r': round(float(row[3]), 3) if row[3] else None,
            }
        except Exception as e:
            logger.debug(f"Strategy fetch failed: {e}")
            return {}

    def _fetch_components(self, report_date: _date) -> Dict[str, Any]:
        """IC and weight for each component."""
        try:
            self.cur.execute(
                """
                SELECT component, ic_value, ic_pvalue FROM algo_component_attribution
                WHERE report_date = %s
                ORDER BY component
                """,
                (report_date,),
            )
            rows = self.cur.fetchall()

            components = {}
            for comp, ic, pval in rows:
                components[comp] = {
                    'ic': round(float(ic), 3) if ic else 0,
                    'pvalue': round(float(pval), 3) if pval else 1.0,
                    'status': self._ic_interpretation(ic) if ic else 'unknown',
                }

            return components
        except Exception as e:
            logger.debug(f"Components fetch failed: {e}")
            return {}

    def _fetch_regime(self, report_date: _date) -> Dict[str, Any]:
        """Current regime and parameter multipliers."""
        try:
            regime = self.regime_mgr.get_current_regime(report_date)
            params = self.regime_mgr.get_regime_params(report_date)

            history = self.regime_mgr.regime_history(days=30)
            days_in_regime = history[0]['days_in_regime'] if history else 0

            return {
                'current': regime,
                'days_in_regime': days_in_regime,
                'position_size_mult': params['position_size_mult'],
                'weight_update_alpha': params['weight_update_alpha'],
                'description': params['description'],
            }
        except Exception as e:
            logger.debug(f"Regime fetch failed: {e}")
            return {}

    def _fetch_signals(self, report_date: _date) -> Dict[str, Any]:
        """Signal counts for today."""
        try:
            self.cur.execute(
                """SELECT COUNT(*) FROM buy_sell_daily
                   WHERE date = %s AND signal_type = 'BUY'""",
                (report_date,),
            )
            candidates = self.cur.fetchone()[0]

            self.cur.execute(
                """SELECT COUNT(*) FROM algo_signals_evaluated
                   WHERE signal_date = %s AND filter_tier_5_pass = TRUE""",
                (report_date,),
            )
            tier_passed = self.cur.fetchone()[0]

            self.cur.execute(
                """SELECT COUNT(*) FROM algo_trades
                   WHERE trade_date = %s""",
                (report_date,),
            )
            entries = self.cur.fetchone()[0]

            return {
                'candidates_today': candidates,
                'passed_tiers': tier_passed,
                'entries_today': entries,
            }
        except Exception as e:
            logger.debug(f"Signals fetch failed: {e}")
            return {}

    def format_text(self, report: Dict[str, Any]) -> str:
        """Format report as text for logs."""
        regime = report.get('regime', {})
        components = report.get('components', {})
        portfolio = report.get('portfolio', {})
        risk = report.get('risk', {})
        strategy = report.get('strategy', {})

        lines = [
            f"{'='*70}",
            f"DAILY FINANCE REPORT — {report['date']} | Regime: {regime.get('current', 'unknown')}",
            f"{'='*70}",
            f"Portfolio: ${portfolio.get('current_value') or 0:,.0f} | "
            f"Daily P&L: {portfolio.get('daily_pnl_pct') or 0:+.2f}% | "
            f"YTD: {portfolio.get('ytd_pnl_pct') or 0:+.2f}%",
            f"Risk: VaR {risk.get('var_95_pct') or 0:.1f}% | "
            f"Beta {risk.get('beta') or 0:.2f} | "
            f"Sharpe {risk.get('sharpe_ytd') or 0:.1f}",
            f"",
            f"Strategy (last 50 trades):",
            f"  Win rate: {strategy.get('win_rate_pct', 0):.0f}% | "
            f"Profit factor: {strategy.get('profit_factor', 0):.1f}x | "
            f"Expectancy: {strategy.get('expectancy_r') or 0:+.2f}R",
            f"",
            f"Component IC (alpha contribution):",
        ]

        for comp in ['setup_quality', 'trend_quality', 'momentum_rs', 'volume',
                     'fundamentals', 'sector_industry', 'multi_timeframe']:
            comp_data = components.get(comp, {})
            ic = comp_data.get('ic', 0)
            status = comp_data.get('status', '?')
            status_marker = '★' if status == 'strong' else '◇' if status == 'moderate' else ' '
            lines.append(f"  {comp:20s} r={ic:+.3f} {status_marker:2s} {status.upper():10s}")

        signals = report.get('signals', {})
        lines.extend([
            f"",
            f"Today: {signals.get('candidates_today', 0)} BUY signals → "
            f"{signals.get('passed_tiers', 0)} tier-passed → "
            f"{signals.get('entries_today', 0)} entries",
            f"{'='*70}",
        ])

        return '\n'.join(lines)

    def _check_thresholds(self, report: Dict[str, Any]) -> List[str]:
        """Check metric thresholds and return warnings."""
        warnings = []

        risk = report.get('risk', {})
        if risk.get('var_95_pct', 0) > 2.0:
            warnings.append(f"⚠️  VaR > 2% ({risk.get('var_95_pct'):.1f}%) - High daily risk")

        if risk.get('sharpe_ytd', 1) < 0.5:
            warnings.append(f"⚠️  Sharpe < 0.5 ({risk.get('sharpe_ytd'):.2f}) - Strategy struggling")

        portfolio = report.get('portfolio', {})
        if portfolio.get('daily_pnl_pct', 0) < -2.0:
            warnings.append(f"⚠️  Daily loss > 2% ({portfolio.get('daily_pnl_pct'):.1f}%) - Halt entries?")

        return warnings

    def _ic_interpretation(self, ic_value: float) -> str:
        """Interpret IC value."""
        if ic_value >= 0.40:
            return 'strong'
        elif ic_value >= 0.25:
            return 'moderate'
        elif ic_value >= 0.10:
            return 'weak'
        else:
            return 'noise'

    def _count_open_positions(self, report_date: _date) -> int:
        """Count open positions."""
        try:
            self.cur.execute(
                """SELECT COUNT(*) FROM algo_positions
                   WHERE status = 'open' AND created_at <= %s""",
                (report_date,),
            )
            return self.cur.fetchone()[0]
        except Exception:
            return 0


if __name__ == "__main__":
    report_gen = DailyFinanceReport()
    report = report_gen.generate(_date.today())
    print(report_gen.format_text(report))
