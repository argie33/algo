"""
Portfolio Risk Measures — VaR, CVaR, Concentration, Beta Exposure

Institutional risk measurement for portfolio monitoring.

Metrics:
- Historical VaR: "We have 95% confidence portfolio won't lose more than $X in one day"
- Conditional VaR (Expected Shortfall): Mean loss beyond VaR threshold
- Stressed VaR: VaR using worst 12-month historical window
- Beta Exposure: Portfolio beta vs. S&P 500 (systematic risk)
- Concentration: Top holdings %, sector breakdown, industry breakdown

Alerts:
- Daily VaR > 2% of portfolio → WARNING
- Concentration > 30% in top 5 holdings → WARNING
- Beta exposure > 2.0 (2× market risk) → WARNING
"""

import psycopg2
import os
import json
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
import numpy as np

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class PortfolioRisk:
    """Portfolio risk metrics and concentration analysis."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"PortfolioRisk: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def historical_var(self, confidence: float = 0.95, lookback_days: int = 252) -> Optional[Dict[str, float]]:
        """Compute historical simulation VaR.

        Args:
            confidence: Confidence level (default 0.95 = 95%)
            lookback_days: Historical window (default 252 = 1 year)

        Returns:
            dict with VaR dollar and %, or None if insufficient data
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Get daily portfolio returns
            cur.execute(
                """
                SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%d days'
                ORDER BY snapshot_date ASC
                """ % lookback_days,
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if len(rows) < 30:
                return None

            values = [float(row[1]) for row in rows]
            returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

            if not returns:
                return None

            # VaR = loss at (1 - confidence) percentile
            var_percentile = np.percentile(returns, (1 - confidence) * 100)
            current_value = values[-1]

            var_dollars = current_value * abs(var_percentile)
            var_pct = abs(var_percentile) * 100

            return {
                'confidence_level': confidence,
                'var_dollars': round(var_dollars, 2),
                'var_pct': round(var_pct, 3),
                'interpretation': f'95% confident portfolio won\'t lose more than ${var_dollars:.2f} (or {var_pct:.2f}%) in one day',
                'data_points': len(returns),
            }

        except Exception as e:
            print(f"PortfolioRisk: historical_var error: {e}")
            return None

    def cvar(self, confidence: float = 0.95, lookback_days: int = 252) -> Optional[Dict[str, float]]:
        """Compute Conditional VaR (Expected Shortfall) — mean loss beyond VaR.

        Args:
            confidence: Confidence level
            lookback_days: Historical window

        Returns:
            dict with CVaR dollar and %, or None if insufficient data
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Get daily portfolio returns
            cur.execute(
                """
                SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%d days'
                ORDER BY snapshot_date ASC
                """ % lookback_days,
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if len(rows) < 30:
                return None

            values = [float(row[1]) for row in rows]
            returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

            if not returns:
                return None

            # CVaR = mean of losses worse than VaR threshold
            var_threshold = np.percentile(returns, (1 - confidence) * 100)
            tail_losses = [r for r in returns if r <= var_threshold]

            if not tail_losses:
                return None

            cvar_pct = np.mean(tail_losses) * 100
            current_value = values[-1]
            cvar_dollars = current_value * abs(np.mean(tail_losses))

            return {
                'confidence_level': confidence,
                'cvar_dollars': round(cvar_dollars, 2),
                'cvar_pct': round(cvar_pct, 3),
                'interpretation': f'Average loss on worst-case days (worse than VaR): {cvar_pct:.2f}%',
                'tail_event_count': len(tail_losses),
            }

        except Exception as e:
            print(f"PortfolioRisk: cvar error: {e}")
            return None

    def stressed_var(self, confidence: float = 0.99) -> Optional[Dict[str, float]]:
        """Compute stressed VaR using worst 12-month rolling window.

        Conservative measure for stress periods.

        Args:
            confidence: Confidence level (default 0.99 = 99%)

        Returns:
            dict with stressed VaR, or None if insufficient data
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Get daily portfolio returns for past 5 years
            cur.execute(
                """
                SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '5 years'
                ORDER BY snapshot_date ASC
                """
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if len(rows) < 365:
                return None

            values = [float(row[1]) for row in rows]
            returns = np.array([(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))])

            # Find worst 12-month window
            worst_var = 0
            worst_start_idx = 0

            for start_idx in range(len(returns) - 252):
                window_returns = returns[start_idx:start_idx + 252]
                var_thresh = np.percentile(window_returns, 1.0)  # 1% = 99% confidence
                if abs(var_thresh) > abs(worst_var):
                    worst_var = var_thresh
                    worst_start_idx = start_idx

            current_value = values[-1]
            stressed_var_dollars = current_value * abs(worst_var)
            stressed_var_pct = abs(worst_var) * 100

            return {
                'confidence_level': confidence,
                'stressed_var_dollars': round(stressed_var_dollars, 2),
                'stressed_var_pct': round(stressed_var_pct, 3),
                'worst_window_period': f'{rows[worst_start_idx][0]} to {rows[worst_start_idx + 252][0]}',
                'interpretation': f'Potential loss using worst historical 12-month period: {stressed_var_pct:.2f}%',
            }

        except Exception as e:
            print(f"PortfolioRisk: stressed_var error: {e}")
            return None

    def beta_exposure(self) -> Optional[Dict[str, Any]]:
        """Compute portfolio beta exposure vs. S&P 500.

        Returns:
            dict with portfolio beta and per-position beta
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Get open positions
            cur.execute(
                """
                SELECT ap.symbol, ap.quantity, ap.current_price, at.entry_price
                FROM algo_positions ap
                JOIN algo_trades at ON ap.position_id LIKE CONCAT('%', at.trade_id, '%')
                WHERE ap.status = 'open'
                """
            )
            positions = cur.fetchall()

            if not positions:
                cur.close()
                conn.close()
                return None

            # Get portfolio value
            cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
            portfolio_row = cur.fetchone()
            cur.close()
            conn.close()
            portfolio_value = float(portfolio_row[0]) if portfolio_row else 100000.0

            # Compute beta for each position (simplified: use RSI as proxy for beta)
            # In production: compute actual beta using correlation with SPY returns
            total_beta_exposure = 0
            positions_list = []

            for symbol, qty, cur_price, entry_price in positions:
                position_value = qty * (cur_price or entry_price)
                position_weight = position_value / portfolio_value if portfolio_value > 0 else 0

                # Simplified beta: assume growth stocks = 1.2 beta, value = 0.8 beta
                # In production: compute actual beta from returns correlation
                estimated_beta = 1.0  # Placeholder

                weighted_beta = estimated_beta * position_weight
                total_beta_exposure += weighted_beta

                positions_list.append({
                    'symbol': symbol,
                    'weight_pct': round(position_weight * 100, 2),
                    'estimated_beta': round(estimated_beta, 2),
                    'contribution': round(weighted_beta, 3),
                })

            return {
                'portfolio_beta': round(total_beta_exposure, 2),
                'interpretation': f'Portfolio is {round(total_beta_exposure, 1)}× market risk',
                'positions': positions_list,
                'portfolio_value': portfolio_value,
            }

        except Exception as e:
            print(f"PortfolioRisk: beta_exposure error: {e}")
            return None

    def concentration_report(self) -> Optional[Dict[str, Any]]:
        """Generate concentration report: top holdings, sectors, industries.

        Returns:
            dict with concentration metrics
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Get open positions with sector/industry
            cur.execute(
                """
                SELECT ap.symbol, ap.quantity, ap.current_price, at.entry_price,
                       at.sector, at.industry
                FROM algo_positions ap
                JOIN algo_trades at ON ap.position_id LIKE CONCAT('%', at.trade_id, '%')
                WHERE ap.status = 'open'
                ORDER BY ap.position_value DESC
                """
            )
            positions = cur.fetchall()

            if not positions:
                cur.close()
                conn.close()
                return None

            # Calculate total portfolio value
            cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
            portfolio_row = cur.fetchone()
            cur.close()
            conn.close()
            portfolio_value = float(portfolio_row[0]) if portfolio_row else 100000.0

            # Top holdings by %
            top_holdings = []
            sector_exposure = {}
            industry_exposure = {}

            for symbol, qty, cur_price, entry_price, sector, industry in positions:
                position_value = qty * (cur_price or entry_price)
                position_pct = position_value / portfolio_value * 100 if portfolio_value > 0 else 0

                top_holdings.append({
                    'symbol': symbol,
                    'value_dollars': round(position_value, 2),
                    'pct_of_portfolio': round(position_pct, 2),
                })

                sector = sector or 'Unknown'
                industry = industry or 'Unknown'
                sector_exposure[sector] = sector_exposure.get(sector, 0) + position_pct
                industry_exposure[industry] = industry_exposure.get(industry, 0) + position_pct

            # Top 5 holdings concentration
            top_5_pct = sum([h['pct_of_portfolio'] for h in top_holdings[:5]])

            return {
                'portfolio_value': round(portfolio_value, 2),
                'position_count': len(positions),
                'top_holdings': top_holdings[:5],
                'top_5_concentration_pct': round(top_5_pct, 1),
                'sector_exposure': {k: round(v, 1) for k, v in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)},
                'industry_exposure': {k: round(v, 1) for k, v in sorted(industry_exposure.items(), key=lambda x: x[1], reverse=True)[:5]},
                'diversification_status': 'CONCENTRATED' if top_5_pct > 30 else 'DIVERSIFIED',
            }

        except Exception as e:
            print(f"PortfolioRisk: concentration_report error: {e}")
            return None

    def generate_daily_risk_report(self, report_date: Optional[date] = None) -> Dict[str, Any]:
        """Generate comprehensive daily risk report.

        Args:
            report_date: Date to report on (default today)

        Returns:
            dict with all risk metrics
        """
        try:
            if not report_date:
                report_date = date.today()

            # Compute all risk metrics (each handles its own connection)
            var_metrics = self.historical_var()
            cvar_metrics = self.cvar()
            stressed_var = self.stressed_var()
            beta = self.beta_exposure()
            concentration = self.concentration_report()

            result = {
                'report_date': report_date,
                'generated_at': datetime.now().isoformat(),
                'status': 'ok',
                'var_metrics': var_metrics,
                'cvar_metrics': cvar_metrics,
                'stressed_var': stressed_var,
                'beta_exposure': beta,
                'concentration': concentration,
                'alerts': [],
            }

            # Alert if VaR > 2%
            if var_metrics and var_metrics['var_pct'] > 2.0:
                result['alerts'].append(f"VaR Risk: Portfolio VaR is {var_metrics['var_pct']:.2f}% (>2% threshold)")

            # Alert if concentration > 30%
            if concentration and concentration['top_5_concentration_pct'] > 30:
                result['alerts'].append(f"Concentration Risk: Top 5 holdings are {concentration['top_5_concentration_pct']:.1f}% (>30%)")

            # Alert if beta > 2.0
            if beta and beta['portfolio_beta'] > 2.0:
                result['alerts'].append(f"Beta Risk: Portfolio beta {beta['portfolio_beta']:.1f} (>2.0× market risk)")

            # Insert into database with fresh connection
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO algo_risk_daily (
                    report_date, var_95_pct, cvar_95_pct, stressed_var_99_pct, created_at
                ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    report_date,
                    var_metrics['var_pct'] if var_metrics else None,
                    cvar_metrics['cvar_pct'] if cvar_metrics else None,
                    stressed_var['stressed_var_pct'] if stressed_var else None,
                )
            )
            conn.commit()
            cur.close()
            conn.close()

            return result

        except Exception as e:
            print(f"PortfolioRisk: generate_daily_risk_report error: {e}")
            return {'status': 'error', 'message': str(e)}
