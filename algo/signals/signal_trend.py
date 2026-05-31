#!/usr/bin/env python3

"""
Trend signal methods — Minervini trend template, Weinstein stage, Mansfield RS.

These methods read from pre-computed trend_template_data (populated by loaders)
and compute Mansfield RS on-demand using price returns.
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class SignalTrendMixin:
    """Trend signal methods reading from pre-computed data and real-time calculations."""

    def minervini_trend_template(self, symbol: str, eval_date) -> Dict[str, Any]:
        def _fetch_trend(cur):
            cur.execute(
                """SELECT minervini_trend_score, percent_from_52w_high, percent_from_52w_low,
                          weinstein_stage, trend_direction
                   FROM trend_template_data
                   WHERE symbol = %s AND date <= %s
                   ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date)
            )
            row = cur.fetchone()
            if not row:
                return {'score': 0, 'pass': False, 'criteria': {}, 'reason': 'No trend data'}

            score = int(row[0] or 0)
            return {
                'score': score,
                'pass': score >= 5,
                'criteria': {
                    'percent_from_52w_high': float(row[1]) if row[1] else None,
                    'percent_from_52w_low': float(row[2]) if row[2] else None,
                    'weinstein_stage': int(row[3]) if row[3] else None,
                    'trend_direction': str(row[4]) if row[4] else None,
                }
            }

        try:
            return self._with_cursor(_fetch_trend) or {'score': 0, 'pass': False, 'criteria': {}, 'reason': 'Database error'}
        except Exception as e:
            logger.warning(f"minervini_trend_template({symbol}) failed: {e}")
            return {'score': 0, 'pass': False, 'criteria': {}, 'reason': str(e)[:50]}

    def weinstein_stage(self, symbol: str, eval_date) -> Dict[str, Any]:
        """
        Read pre-computed Weinstein 4-stage classification from trend_template_data.

        Stages: 1 (downtrend), 2 (uptrend), 3 (peak/top), 4 (recovery)

        Returns: {
            'stage': int (1-4),
            'confidence': float,
            'price_vs_ma_pct': float,
            'slope_pct': float,
        }
        """
        def _fetch_stage(cur):
            cur.execute(
                """SELECT weinstein_stage, consolidation_flag
                   FROM trend_template_data
                   WHERE symbol = %s AND date <= %s
                   ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date)
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return {'stage': 1, 'confidence': 0, 'price_vs_ma_pct': None, 'slope_pct': None}

            stage = int(row[0])
            # consolidation_flag=True means stock is building a base (early phase, higher confidence)
            confidence = 1.0 if row[1] else 0.5

            return {
                'stage': stage,
                'confidence': confidence,
                'price_vs_ma_pct': None,
                'slope_pct': None,
            }

        try:
            return self._with_cursor(_fetch_stage) or {'stage': 1, 'confidence': 0, 'price_vs_ma_pct': None, 'slope_pct': None}
        except Exception as e:
            logger.warning(f"weinstein_stage({symbol}) failed: {e}")
            return {'stage': 1, 'confidence': 0, 'price_vs_ma_pct': None, 'slope_pct': None}

    def mansfield_rs(self, symbol: str, eval_date, lookback: int = 252) -> Dict[str, Any]:
        """
        Compute Mansfield Relative Strength: (stock_return / spy_return) - 1.

        Measures how much better/worse the stock performed vs SPY over lookback period.
        Positive RS = outperforming market
        Negative RS = underperforming market

        Returns: {
            'mansfield_rs': float,
            'positive': bool,
            'stock_return_pct': float,
            'spy_return_pct': float,
        }
        """
        def _compute_rs(cur):
            stock_ret = self._period_return(cur, symbol, eval_date, lookback)
            spy_ret = self._period_return(cur, 'SPY', eval_date, lookback)

            if stock_ret is None or spy_ret is None or spy_ret == 0:
                return {
                    'mansfield_rs': 0,
                    'positive': False,
                    'stock_return_pct': stock_ret,
                    'spy_return_pct': spy_ret,
                }

            mrs = (stock_ret / spy_ret) - 1
            return {
                'mansfield_rs': round(mrs, 4),
                'positive': mrs > 0,
                'stock_return_pct': round(stock_ret * 100, 2),
                'spy_return_pct': round(spy_ret * 100, 2),
            }

        try:
            return self._with_cursor(_compute_rs) or {'mansfield_rs': 0, 'positive': False, 'stock_return_pct': None, 'spy_return_pct': None}
        except Exception as e:
            logger.warning(f"mansfield_rs({symbol}) failed: {e}")
            return {'mansfield_rs': 0, 'positive': False, 'stock_return_pct': None, 'spy_return_pct': None}

    def stage2_phase(self, symbol: str, eval_date) -> Dict[str, Any]:
        """Alias for weinstein_stage() for backwards compatibility."""
        return self.weinstein_stage(symbol, eval_date)
