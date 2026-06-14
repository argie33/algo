
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

import os
import logging
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)

class ValueAtRisk:
    """Portfolio risk metrics and concentration analysis."""

    def __init__(self, config):
        self.config = config

    def historical_var(self, confidence: float = 0.95, lookback_days: int = 252) -> Optional[Dict[str, Any]]:
        """Compute historical simulation VaR.

        Args:
            confidence: Confidence level (default 0.95 = 95%)
            lookback_days: Historical window (default 252 = 1 year)

        Returns:
            dict with VaR dollar and %, or None if insufficient data
        """
        import numpy as np
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    f"""
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '{int(lookback_days)} days'
                    ORDER BY snapshot_date ASC
                    """
                )
                rows = cur.fetchall()

                if len(rows) < 5:
                    return None
                if len(rows) < 30:
                    logger.warning(f"Risk metrics using limited historical data: {len(rows)} snapshots (recommend 30+)")

                values = [float(row[1]) for row in rows]
                returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

                if not returns:
                    return None

                var_percentile = np.percentile(returns, (1 - confidence) * 100)
                current_value = values[-1]

                var_dollars = current_value * abs(var_percentile)
                var_pct = abs(var_percentile) * 100

                return {
                    'confidence_level': confidence,
                    'var_dollars': float(round(var_dollars, 2)),
                    'var_pct': float(round(var_pct, 3)),
                    'interpretation': f'95% confident portfolio won\'t lose more than ${var_dollars:.2f} (or {var_pct:.2f}%) in one day',
                    'data_points': len(returns),
                }

        except Exception as e:
            logger.error(f"historical_var error: {e}", exc_info=True)
            return None

    def cvar(self, confidence: float = 0.95, lookback_days: int = 252) -> Optional[Dict[str, Any]]:
        """Compute Conditional VaR (Expected Shortfall) — mean loss beyond VaR.

        Args:
            confidence: Confidence level
            lookback_days: Historical window

        Returns:
            dict with CVaR dollar and %, or None if insufficient data
        """
        import numpy as np
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    f"""
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '{int(lookback_days)} days'
                    ORDER BY snapshot_date ASC
                    """
                )
                rows = cur.fetchall()

                if len(rows) < 5:
                    return None
                if len(rows) < 30:
                    logger.warning(f"Risk metrics using limited historical data: {len(rows)} snapshots (recommend 30+)")

                values = [float(row[1]) for row in rows]
                returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

                if not returns:
                    return None

                var_threshold = np.percentile(returns, (1 - confidence) * 100)
                tail_losses = [r for r in returns if r <= var_threshold]

                if not tail_losses:
                    return None

                cvar_pct = abs(np.mean(tail_losses)) * 100
                current_value = values[-1]
                cvar_dollars = current_value * abs(np.mean(tail_losses))

                return {
                    'confidence_level': confidence,
                    'cvar_dollars': float(round(cvar_dollars, 2)),
                    'cvar_pct': float(round(cvar_pct, 3)),
                    'interpretation': f'Average loss on worst-case days (worse than VaR): {cvar_pct:.2f}%',
                    'tail_event_count': len(tail_losses),
                }

        except Exception as e:
            logger.error(f"CVaR calculation error: {e}", exc_info=True)
            return None

    def stressed_var(self, confidence: float = 0.99) -> Optional[Dict[str, Any]]:
        """Compute stressed VaR using worst 12-month rolling window.

        Conservative measure for stress periods.

        Args:
            confidence: Confidence level (default 0.99 = 99%)

        Returns:
            dict with stressed VaR, or None if insufficient data
        """
        import numpy as np
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    """
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '5 years'
                    ORDER BY snapshot_date ASC
                    """
                )
                rows = cur.fetchall()

                if len(rows) < 365:
                    return None

                values = [float(row[1]) for row in rows]
                returns = np.array([(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))])

                worst_var = 0
                worst_start_idx = 0

                for start_idx in range(len(returns) - 252):
                    window_returns = returns[start_idx:start_idx + 252]
                    var_thresh = np.percentile(window_returns, 1.0)
                    if abs(var_thresh) > abs(worst_var):
                        worst_var = var_thresh
                        worst_start_idx = start_idx

                current_value = values[-1]
                stressed_var_dollars = current_value * abs(worst_var)
                stressed_var_pct = abs(worst_var) * 100

                return {
                    'confidence_level': confidence,
                    'stressed_var_dollars': float(round(stressed_var_dollars, 2)),
                    'stressed_var_pct': float(round(stressed_var_pct, 3)),
                    'worst_window_period': f'{rows[worst_start_idx][0]} to {rows[worst_start_idx + 252][0]}',
                    'interpretation': f'Potential loss using worst historical 12-month period: {stressed_var_pct:.2f}%',
                }

        except Exception as e:
            logger.error(f"Stressed VaR calculation error: {e}", exc_info=True)
            return None

    def beta_exposure(self) -> Optional[Dict[str, Any]]:
        """Compute portfolio beta exposure vs. S&P 500.

        Returns:
            dict with portfolio beta and per-position beta
        """
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    """
                    SELECT ap.symbol, ap.quantity, ap.current_price, ap.avg_entry_price AS entry_price
                    FROM algo_positions ap
                    WHERE ap.status = 'open'
                    """
                )
                positions = cur.fetchall()

                if not positions:
                    return None

                cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
                portfolio_row = cur.fetchone()
                if not portfolio_row:
                    logger.error("No portfolio snapshot available - cannot compute risk metrics with real portfolio value")
                    return None
                portfolio_value = float(portfolio_row[0])

                # Fetch SPY returns for the last 60 trading days (beta denominator)
                cur.execute(
                    """
                    SELECT date, close FROM price_daily
                    WHERE symbol = 'SPY'
                    ORDER BY date DESC LIMIT 61
                    """
                )
                spy_rows = cur.fetchall()
                spy_returns = []
                if len(spy_rows) >= 2:
                    spy_prices = list(reversed([float(r[1]) for r in spy_rows]))
                    spy_returns = [(spy_prices[i] - spy_prices[i-1]) / spy_prices[i-1]
                                   for i in range(1, len(spy_prices))]

                spy_var = 0.0
                if spy_returns:
                    spy_mean = sum(spy_returns) / len(spy_returns)
                    spy_var = sum((r - spy_mean) ** 2 for r in spy_returns) / len(spy_returns)

                total_beta_exposure = 0.0
                positions_list = []

                for symbol, qty, cur_price, entry_price in positions:
                    # CRITICAL: Do NOT use entry_price as fallback for current_price
                    if cur_price is None or float(cur_price) <= 0:
                        logger.warning(f"[VAR] {symbol}: missing or invalid current_price, skipping from VAR calculation")
                        continue
                    position_value = float(qty) * float(cur_price)
                    position_weight = position_value / portfolio_value if portfolio_value > 0 else 0

                    # Compute 60-day beta via covariance with SPY
                    estimated_beta = 1.0
                    if spy_returns and spy_var > 0:
                        try:
                            cur.execute(
                                """
                                SELECT close FROM price_daily
                                WHERE symbol = %s
                                ORDER BY date DESC LIMIT 61
                                """,
                                (symbol,)
                            )
                            stock_rows = cur.fetchall()
                            if len(stock_rows) >= 2:
                                stock_prices = list(reversed([float(r[0]) for r in stock_rows]))
                                stock_returns = [(stock_prices[i] - stock_prices[i-1]) / stock_prices[i-1]
                                                for i in range(1, len(stock_prices))]
                                n = min(len(stock_returns), len(spy_returns))
                                if n >= 20:
                                    s_rets = stock_returns[-n:]
                                    m_rets = spy_returns[-n:]
                                    s_mean = sum(s_rets) / n
                                    m_mean = sum(m_rets) / n
                                    cov = sum((s_rets[i] - s_mean) * (m_rets[i] - m_mean)
                                             for i in range(n)) / n
                                    var = sum((r - m_mean) ** 2 for r in m_rets) / n
                                    if var > 0:
                                        estimated_beta = round(cov / var, 2)
                        except Exception as e:
                            logger.warning(f"Exception: {e}")
                            estimated_beta = 1.0

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
            logger.error(f"Beta exposure calculation error: {e}", exc_info=True)
            return None

    def concentration_report(self) -> Optional[Dict[str, Any]]:
        """Generate concentration report: top holdings, sectors, industries.

        Returns:
            dict with concentration metrics
        """
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    """
                    SELECT ap.symbol, ap.quantity, ap.current_price, ap.avg_entry_price AS entry_price,
                           cp.sector, cp.industry
                    FROM algo_positions ap
                    LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                    WHERE ap.status = 'open'
                    ORDER BY ap.position_value DESC
                    """
                )
                positions = cur.fetchall()

                if not positions:
                    return None

                cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
                portfolio_row = cur.fetchone()
                if not portfolio_row:
                    logger.error("No portfolio snapshot available - cannot compute risk metrics with real portfolio value")
                    return None
                portfolio_value = float(portfolio_row[0])

                top_holdings = []
                sector_exposure: Dict[str, float] = {}
                industry_exposure: Dict[str, float] = {}

                for symbol, qty, cur_price, entry_price, sector, industry in positions:
                    # CRITICAL: Do NOT use entry_price as fallback for current_price
                    if cur_price is None or float(cur_price) <= 0:
                        logger.warning(f"[VAR exposure] {symbol}: missing or invalid current_price, excluding from exposure")
                        continue
                    position_value = float(qty) * float(cur_price)
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
            logger.error(f"Concentration report error: {e}", exc_info=True)
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

            logger.info(f"Generating daily risk report for {report_date}")

            # Compute all risk metrics (each handles its own connection)
            var_metrics = self.historical_var()
            cvar_metrics = self.cvar()
            stressed_var = self.stressed_var()
            beta = self.beta_exposure()
            concentration = self.concentration_report()

            logger.debug(f"  VaR: {var_metrics['var_pct']:.3f}%" if var_metrics else "  VaR: <unavailable>")
            logger.debug(f"  CVaR: {cvar_metrics['cvar_pct']:.3f}%" if cvar_metrics else "  CVaR: <unavailable>")
            logger.debug(f"  Stressed VaR: {stressed_var['stressed_var_pct']:.3f}%" if stressed_var else "  Stressed VaR: <unavailable>")
            logger.debug(f"  Beta: {beta['portfolio_beta']:.3f}" if beta else "  Beta: <unavailable>")
            logger.debug(f"  Top 5 Concentration: {concentration['top_5_concentration_pct']:.1f}%" if concentration else "  Top 5 Concentration: <unavailable>")

            result: Dict[str, Any] = {
                'report_date': report_date,
                'generated_at': datetime.now(timezone.utc).isoformat(),
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
                msg = f"VaR Risk: Portfolio VaR is {var_metrics['var_pct']:.2f}% (>2% threshold)"
                result['alerts'].append(msg)  # type: ignore[union-attr]
                logger.warning(msg)

            # Alert if concentration > 30%
            if concentration and concentration['top_5_concentration_pct'] > 30:
                msg = f"Concentration Risk: Top 5 holdings are {concentration['top_5_concentration_pct']:.1f}% (>30%)"
                result['alerts'].append(msg)  # type: ignore[union-attr]
                logger.warning(msg)

            # Alert if beta > 2.0
            if beta and beta['portfolio_beta'] > 2.0:
                msg = f"Beta Risk: Portfolio beta {beta['portfolio_beta']:.1f} (>2.0× market risk)"
                result['alerts'].append(msg)  # type: ignore[union-attr]
                logger.warning(msg)

            try:
                with DatabaseContext('write') as cur:
                    var_pct_val = float(var_metrics['var_pct']) if var_metrics else None
                    cvar_pct_val = float(cvar_metrics['cvar_pct']) if cvar_metrics else None
                    stressed_var_pct_val = float(stressed_var['stressed_var_pct']) if stressed_var else None
                    portfolio_beta_val = float(beta['portfolio_beta']) if beta else None
                    top_5_conc_val = float(concentration['top_5_concentration_pct']) if concentration else None

                    cur.execute(
                        """
                        INSERT INTO algo_risk_daily (
                            report_date, var_pct_95, cvar_pct_95, stressed_var_pct, portfolio_beta, top_5_concentration
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (report_date) DO UPDATE SET
                            var_pct_95 = EXCLUDED.var_pct_95,
                            cvar_pct_95 = EXCLUDED.cvar_pct_95,
                            stressed_var_pct = EXCLUDED.stressed_var_pct,
                            portfolio_beta = EXCLUDED.portfolio_beta,
                            top_5_concentration = EXCLUDED.top_5_concentration
                        """,
                        (
                            report_date,
                            var_pct_val,
                            cvar_pct_val,
                            stressed_var_pct_val,
                            portfolio_beta_val,
                            top_5_conc_val,
                        )
                    )
                    logger.info(f"[OK] Risk report persisted: var={var_pct_val}%, cvar={cvar_pct_val}%, beta={portfolio_beta_val}, concentration={top_5_conc_val}%")
            except Exception as e:
                logger.error(f"Failed to persist risk report: {e}", exc_info=True)

            return result

        except Exception as e:
            logger.error(f"Daily risk report generation error: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

