#!/usr/bin/env python3

"""
Trend signal methods — Minervini trend template, Weinstein stage, Mansfield RS.

These methods read from pre-computed trend_template_data (populated by loaders)
and compute Mansfield RS on-demand using price returns. Falls back to on-the-fly
computation if trend_template_data is stale.
"""

from typing import Dict, Any, Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class SignalTrendMixin:
    """Trend signal methods reading from pre-computed data and real-time calculations."""

    def _compute_minervini_from_prices(self, cur, symbol: str, eval_date) -> Dict[str, Any]:
        """Compute Minervini 8-point trend score on-the-fly from price_daily."""
        cur.execute(
            """SELECT date, close, volume FROM price_daily
               WHERE symbol = %s AND date >= %s::date - INTERVAL '300 days'
               AND date <= %s
               ORDER BY date ASC""",
            (symbol, eval_date, eval_date)
        )
        rows = cur.fetchall()
        if not rows or len(rows) < 50:
            return {'score': 0, 'pass': False, 'criteria': {}, 'reason': 'Insufficient price history'}

        df = pd.DataFrame(rows, columns=['date', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close']).sort_values('date').reset_index(drop=True)

        if len(df) < 50:
            return {'score': 0, 'pass': False, 'criteria': {}, 'reason': 'Insufficient price history'}

        close = df['close']
        df['sma_50'] = close.rolling(50, min_periods=50).mean()
        df['sma_150'] = close.rolling(150, min_periods=150).mean()
        df['sma_200'] = close.rolling(200, min_periods=200).mean()
        df['sma_200_slope'] = df['sma_200'].diff(5) / df['sma_200'].shift(5)
        df['high_52w'] = close.rolling(252, min_periods=252).max()
        df['low_52w'] = close.rolling(252, min_periods=252).min()

        row = df.iloc[-1]
        c = row['close']
        sma50 = row['sma_50'] if pd.notna(row['sma_50']) else None
        sma150 = row['sma_150'] if pd.notna(row['sma_150']) else None
        sma200 = row['sma_200'] if pd.notna(row['sma_200']) else None
        high52 = row['high_52w'] if pd.notna(row['high_52w']) else None
        low52 = row['low_52w'] if pd.notna(row['low_52w']) else None

        score = 0
        if sma50 and c > sma50:
            score += 1
        if sma150 and c > sma150:
            score += 1
        if sma200 and c > sma200:
            score += 1
        if sma50 and sma150 and sma50 > sma150:
            score += 1
        if sma150 and sma200 and sma150 > sma200:
            score += 1
        sma200_slope = row['sma_200_slope']
        if sma200_slope and pd.notna(sma200_slope) and sma200_slope > 0:
            score += 1
        if high52 and c >= high52 * 0.75:
            score += 1
        if low52 and c >= low52 * 1.30:
            score += 1

        pct_from_low = ((c - low52) / low52 * 100) if low52 else None
        pct_from_high = ((c - high52) / high52 * 100) if high52 else None

        sma200_slope = row['sma_200_slope']
        if sma200 and c > sma200:
            if pd.notna(sma200_slope) and sma200_slope > 0:
                weinstein_stage = 2
            else:
                weinstein_stage = 3
        else:
            if pd.notna(sma200_slope) and sma200_slope < 0:
                weinstein_stage = 4
            else:
                weinstein_stage = 1

        return {
            'score': score,
            'pass': score >= 5,
            'criteria': {
                'percent_from_52w_high': float(pct_from_high) if pct_from_high is not None else None,
                'percent_from_52w_low': float(pct_from_low) if pct_from_low is not None else None,
                'weinstein_stage': weinstein_stage,
                'trend_direction': 'uptrend' if score >= 6 else ('downtrend' if score <= 2 else 'sideways'),
            }
        }

    def minervini_trend_template(self, symbol: str, eval_date) -> Dict[str, Any]:
        def _fetch_trend(cur):
            cur.execute(
                """SELECT minervini_trend_score, percent_from_52w_high, percent_from_52w_low,
                          weinstein_stage, trend_direction, date
                   FROM trend_template_data
                   WHERE symbol = %s AND date <= %s
                   ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date)
            )
            row = cur.fetchone()
            if row and row[5] and (eval_date - row[5]).days <= 1:
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

            logger.debug(f"[MINERVINI] trend_template_data stale for {symbol}; computing on-the-fly")
            return self._compute_minervini_from_prices(cur, symbol, eval_date)

        try:
            return self._with_cursor(_fetch_trend) or {'score': 0, 'pass': False, 'criteria': {}, 'reason': 'Database error'}  # type: ignore[attr-defined]
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
            return self._with_cursor(_fetch_stage) or {'stage': 1, 'confidence': 0, 'price_vs_ma_pct': None, 'slope_pct': None}  # type: ignore[attr-defined]
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
            return self._with_cursor(_compute_rs) or {'mansfield_rs': 0, 'positive': False, 'stock_return_pct': None, 'spy_return_pct': None}  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(f"mansfield_rs({symbol}) failed: {e}")
            return {'mansfield_rs': 0, 'positive': False, 'stock_return_pct': None, 'spy_return_pct': None}

    def stage2_phase(self, symbol: str, eval_date) -> Dict[str, Any]:
        """Alias for weinstein_stage() for backwards compatibility."""
        return self.weinstein_stage(symbol, eval_date)
