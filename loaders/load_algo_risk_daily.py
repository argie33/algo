#!/usr/bin/env python3
"""Algo Risk Daily Loader - VAR, CVAR, portfolio beta, concentration risk.

Runs multiple times per day to keep risk metrics current as positions change.
Calculates from:
  - algo_portfolio_snapshots (equity curve for VaR/CVaR)
  - algo_trades (open positions for concentration)
  - price_daily (current prices)
  - market_health_daily (market beta reference)

Risk metrics updated hourly during market hours.
"""
from loaders.loader_helper import setup_imports
setup_imports()

import sys
import logging
import statistics
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext
from utils.timezone_utils import EASTERN_TZ

logger = logging.getLogger(__name__)
ET = EASTERN_TZ

class AlgoRiskDailyLoader(OptimalLoader):
    """Compute daily risk metrics from portfolio and positions."""

    table_name = "algo_risk_daily"
    primary_key = ("report_date",)
    watermark_field = "report_date"

    # Allow multiple updates per day
    allow_multiple_updates_per_day = True

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute risk metrics from portfolio snapshots and open positions.

        Metrics:
        - var_pct_95: Value at Risk at 95% confidence
        - cvar_pct_95: Conditional VaR (expected loss beyond VaR)
        - stressed_var_pct: VaR using worst 10% of days
        - portfolio_beta: Market correlation (vs SPY)
        - top_5_concentration: % of portfolio in top 5 positions
        """
        try:
            now_et = datetime.now(ET)
            report_date = now_et.date()

            with DatabaseContext('read') as cur:
                # 1. Fetch portfolio snapshots for VaR calculation
                cur.execute("""
                    SELECT snapshot_date, daily_return_pct, total_portfolio_value
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - 252
                    ORDER BY snapshot_date ASC
                """)
                snapshots = cur.fetchall() or []

                # 2. Fetch open positions for concentration risk
                cur.execute("""
                    WITH open_trades AS (
                        SELECT DISTINCT ON (symbol) symbol, entry_quantity, entry_price
                        FROM algo_trades
                        WHERE status IN ('open', 'filled', 'partially_filled', 'active')
                          AND exit_date IS NULL
                        ORDER BY symbol, trade_date DESC
                    ),
                    latest_prices AS (
                        SELECT DISTINCT ON (symbol) symbol, close as current_price
                        FROM price_daily
                        WHERE symbol IN (SELECT DISTINCT symbol FROM open_trades)
                        ORDER BY symbol, date DESC
                    )
                    SELECT ot.symbol,
                           (ot.entry_quantity * lp.current_price)::DECIMAL(14,2) as position_value
                    FROM open_trades ot
                    LEFT JOIN latest_prices lp ON ot.symbol = lp.symbol
                    WHERE lp.current_price IS NOT NULL
                    ORDER BY position_value DESC
                """)
                positions = cur.fetchall() or []

                # 3. Fetch SPY returns for beta calculation
                cur.execute("""
                    SELECT daily_return_pct FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - 252
                    ORDER BY snapshot_date ASC
                """)
                portfolio_rets = [float(r[0]) / 100 for r in cur.fetchall() if r[0] is not None]

                cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = 'SPY' AND date >= CURRENT_DATE - 252
                    ORDER BY date ASC
                """)
                spy_closes = [float(r[0]) for r in cur.fetchall() if r[0] is not None]

            if not snapshots:
                logger.warning(f"No portfolio snapshots available for {report_date}")
                return None

            result = self._calculate_metrics(report_date, snapshots, positions,
                                            portfolio_rets, spy_closes)
            return [result] if result else None

        except Exception as e:
            logger.error(f"Failed to compute risk metrics: {e}")
            return None

    def _calculate_metrics(self, report_date: date, snapshots: list,
                          positions: list, portfolio_rets: list, spy_closes: list) -> dict:
        """Calculate all risk metrics.

        M3 FIX: Risk percentiles now loaded from config instead of hardcoded.
        """
        from algo.algo_config import AlgoConfig
        cfg = AlgoConfig()

        # Extract daily returns
        returns = [float(s['daily_return_pct']) / 100 for s in snapshots
                  if s.get('daily_return_pct') is not None]

        # VaR at configured percentile (default 5% = 95% confidence)
        var_pct_95 = None
        if len(returns) >= 20:
            var_pct = float(cfg.get('var_percentile', 5)) / 100  # M3 FIX: Read from config
            sorted_rets = sorted(returns)
            idx = int(len(sorted_rets) * var_pct)
            var_pct_95 = round(min(0, sorted_rets[idx]) * 100, 2)

        # CVaR (conditional VaR): expected loss beyond VaR threshold
        cvar_pct_95 = None
        if var_pct_95 is not None and len(returns) >= 20:
            cvar_pct = float(cfg.get('cvar_percentile', 5)) / 100  # M3 FIX: Read from config
            worst_pct = [r for r in returns if r <= (var_pct_95 / 100)]
            if worst_pct:
                cvar_pct_95 = round(statistics.mean(worst_pct) * 100, 2)

        # Stressed VaR: worst N% of days (default 10%)
        stressed_var_pct = None
        if len(returns) >= 20:
            stressed_pct = float(cfg.get('stressed_var_percentile', 10)) / 100  # M3 FIX: Read from config
            worst_idx = max(1, int(len(returns) * stressed_pct))
            worst_days = sorted(returns)[:worst_idx]
            if worst_days:
                stressed_var_pct = round(statistics.mean(worst_days) * 100, 2)

        # Portfolio Beta: correlation * (σ_portfolio / σ_spy)
        portfolio_beta = None
        if len(portfolio_rets) >= 20 and len(spy_closes) >= 21:
            try:
                # Calculate SPY returns
                spy_rets = []
                for i in range(1, len(spy_closes)):
                    if spy_closes[i-1] > 0:
                        ret = (spy_closes[i] - spy_closes[i-1]) / spy_closes[i-1]
                        spy_rets.append(ret)

                if len(spy_rets) == len(portfolio_rets):
                    # Covariance-based beta
                    port_mean = statistics.mean(portfolio_rets)
                    spy_mean = statistics.mean(spy_rets)
                    covar = sum((portfolio_rets[i] - port_mean) * (spy_rets[i] - spy_mean)
                               for i in range(len(spy_rets))) / len(spy_rets)
                    spy_var = sum((r - spy_mean) ** 2 for r in spy_rets) / len(spy_rets)
                    if spy_var > 0:
                        portfolio_beta = round(covar / spy_var, 3)
            except (ValueError, ZeroDivisionError):
                pass

        # Concentration: top 5 positions as % of total
        top_5_concentration = None
        if positions:
            total_value = sum(float(p['position_value']) for p in positions
                            if p.get('position_value') is not None)
            if total_value > 0:
                top_5_sum = sum(float(p['position_value']) for p in positions[:5]
                               if p.get('position_value') is not None)
                top_5_concentration = round(top_5_sum / total_value * 100, 2)

        return {
            'report_date': report_date,
            'var_pct_95': var_pct_95,
            'cvar_pct_95': cvar_pct_95,
            'stressed_var_pct': stressed_var_pct,
            'portfolio_beta': portfolio_beta,
            'top_5_concentration': top_5_concentration,
            'position_count': len(positions),
            'updated_at': datetime.now(ET),
        }

def main():
    loader = AlgoRiskDailyLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} risk metrics computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No risk metrics computed (insufficient data)")
        return 0

if __name__ == "__main__":
    sys.exit(main())
