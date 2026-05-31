#!/usr/bin/env python3

"""Filter Tier 3 implementation — trend template and structural analysis."""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class FilterTier3Mixin:
    """Tier 3 (trend template) filtering logic."""

    def _tier3_trend_template(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """Trend template (Minervini) + Weinstein stage + compute stop from MA/ATR/swing.

        Pulls every swing-trading-canon factor we have for the stock:
          - Minervini trend_template_score (8-point system)
          - Weinstein stage (must be 2 = uptrend)
          - 52-week range distances
          - Stage-aligned moving averages
          - Consolidation flag (Darvas/Bassal favor breakout-from-consolidation)
        """
        # Reset state variables to prevent carryover from previous signals
        self._last_stop_method = None
        self._last_stop_reasoning = None
        try:
            cur.execute(
                """
                SELECT
                    tt.minervini_trend_score,
                    tt.percent_from_52w_low,
                    tt.percent_from_52w_high,
                    tt.weinstein_stage,
                    tt.consolidation_flag,
                    tt.trend_direction,
                    td.sma_50,
                    td.atr
                FROM trend_template_data tt
                LEFT JOIN technical_data_daily td
                    ON td.symbol = tt.symbol AND td.date = tt.date
                WHERE tt.symbol = %s AND tt.date <= %s
                ORDER BY tt.date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            row = cur.fetchone()
            if not row:
                return {'pass': False, 'reason': 'No trend data'}

            trend_score = row[0] or 0
            pct_from_low = float(row[1]) if row[1] is not None else 0.0
            pct_from_high = float(row[2]) if row[2] is not None else 0.0
            stock_stage = int(row[3]) if row[3] is not None else 0
            in_consolidation = bool(row[4]) if row[4] is not None else False
            trend_direction = (row[5] or '').lower()
            sma_50 = float(row[6]) if row[6] is not None else None
            atr = float(row[7]) if row[7] is not None else None

            # Weinstein per-stock stage: only Stage 2 stocks
            require_stock_stage_2 = bool(self.config.get('require_stock_stage_2', True))
            if require_stock_stage_2 and stock_stage != 2:
                return {
                    'pass': False,
                    'reason': f'Stock stage {stock_stage} != 2 ({trend_direction or "unknown"})',
                    'trend_score': trend_score,
                }

            min_score = int(self.config.get('min_trend_template_score', 7))
            if trend_score < min_score:
                return {
                    'pass': False,
                    'reason': f'Trend score {trend_score} < {min_score}',
                    'trend_score': trend_score,
                }

            min_from_low = float(self.config.get('min_percent_from_52w_low', 30.0))
            if pct_from_low < min_from_low:
                return {
                    'pass': False,
                    'reason': f'Only {pct_from_low:.0f}% from 52w low (need {min_from_low:.0f})',
                    'trend_score': trend_score,
                }

            max_from_high = float(self.config.get('max_percent_from_52w_high', 25.0))
            # pct_from_high is stored as (close - high52w) / high52w * 100, always ≤ 0.
            # A stock 30% below its 52w high has pct_from_high = -30.
            # Reject if stock is more than max_from_high% BELOW its 52w high.
            if pct_from_high < -max_from_high:
                return {
                    'pass': False,
                    'reason': f'{abs(pct_from_high):.0f}% below 52w high (max {max_from_high:.0f}% allowed)',
                    'trend_score': trend_score,
                }

            # Minervini rule: RS-line (stock vs SPY) must be making new highs or near new highs
            # Don't exit on Minervini break if RS line is strong
            rs_check = self._check_rs_line_strength(symbol, signal_date, cur)
            if rs_check and not rs_check.get('pass', True):
                return {
                    'pass': False,
                    'reason': rs_check.get('reason', 'RS line weak'),
                    'trend_score': trend_score,
                }

            # A4: Weekly Chart Hard Gate — require weekly chart Stage 2 (currently only scored)
            require_weekly_stage_2 = bool(self.config.get('require_weekly_stage_2', True))
            if require_weekly_stage_2:
                weekly_check = self._check_weekly_stage_2(symbol, signal_date, cur)
                if not weekly_check.get('pass', True):
                    return {
                        'pass': False,
                        'reason': weekly_check.get('reason', 'Weekly chart not Stage 2'),
                        'trend_score': trend_score,
                    }

            # A5: RS Line Trending Up — RS line must have positive slope (not just "near high")
            rs_slope_check = self._check_rs_line_slope(symbol, signal_date, cur)
            if not rs_slope_check.get('pass', True):
                return {
                    'pass': False,
                    'reason': rs_slope_check.get('reason', 'RS line not trending up'),
                    'trend_score': trend_score,
                }

            # Volume decay check: declining volume into breakout = false breakout (Minervini warning)
            vol_check = self._check_volume_decay(symbol, signal_date, cur)
            if vol_check and not vol_check.get('pass', True):
                return {
                    'pass': False,
                    'reason': vol_check.get('reason', 'Volume declining'),
                    'trend_score': trend_score,
                }

            # Compute stop loss: best of (50-DMA, swing low, 2x ATR). Cap at 8% below entry.
            stop_info = self._compute_stop_loss(symbol, signal_date, sma_50, atr, cur)
            stop_loss_price = stop_info.get('stop_price') if isinstance(stop_info, dict) else stop_info
            stop_method = stop_info.get('method', self._last_stop_method) if isinstance(stop_info, dict) else self._last_stop_method
            stop_reasoning = stop_info.get('reasoning', self._last_stop_reasoning) if isinstance(stop_info, dict) else self._last_stop_reasoning

            # Fail if no valid stop can be computed (insufficient structural levels)
            if stop_loss_price is None:
                return {
                    'pass': False,
                    'reason': 'No valid stop loss available (insufficient technical indicators)',
                    'trend_score': trend_score,
                }

            # Log stop loss calculation for audit trail
            if isinstance(stop_info, dict):
                try:
                    from algo.algo_trade_audit_logger import TradeAuditLogger
                    audit = TradeAuditLogger()
                    audit.log_stop_loss_calculation(
                        symbol, signal_date, None,
                        stop_loss_price,
                        stop_info.get('method', 'unknown'),
                        stop_info.get('reasoning', ''),
                        stop_info.get('candidates', {}),
                    )
                except Exception as e:
                    logger.debug(f"Stop loss audit logging failed: {e}")

            return {
                'pass': True,
                'reason': f'Trend {trend_score}/8, {pct_from_low:.0f}% from low',
                'trend_score': trend_score,
                'stop_loss_price': stop_loss_price,
                'stop_method': stop_method,
                'stop_reasoning': stop_reasoning,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'trend_score': 0}

    def _check_volume_decay(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """Minervini warning: declining volume into breakout signals false breakout.

        Checks if 10-day average volume is declining relative to 50-day average.
        A breakout with declining volume = weak accumulation = false setup.
        """
        try:
            cur.execute(
                """
                SELECT volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, signal_date),
            )
            rows = cur.fetchall()
            if len(rows) < 50:
                return {'pass': True, 'reason': 'Insufficient volume history'}

            volumes = [float(r[0]) for r in rows if r[0]]
            if len(volumes) < 50:
                return {'pass': True, 'reason': 'No volume data'}

            # 10-day vs 50-day average volume (use exactly 50 bars for the baseline)
            vol_10d_avg = sum(volumes[:10]) / 10.0
            vol_50d_avg = sum(volumes[:50]) / 50.0

            if vol_10d_avg > 0 and vol_50d_avg > 0:
                vol_decline_pct = ((vol_50d_avg - vol_10d_avg) / vol_50d_avg) * 100.0

                # If 10-day avg is >15% below 50-day avg, volume is declining (red flag)
                if vol_decline_pct > 15.0:
                    return {
                        'pass': False,
                        'reason': f'Volume declining: 10d avg {vol_decline_pct:.1f}% below 50d (sign of weak setup)',
                    }

            return {'pass': True, 'reason': 'Volume OK'}
        except Exception as e:
            logger.debug(f'Volume decay check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'Volume check error (continuing)'}

    def _check_rs_line_strength(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """Minervini rule: RS-line (stock vs SPY) should be strong (at/near new highs).

        Checks if the 60-day RS-line (stock close / SPY close) is within 5% of its
        52-week high. If RS-line is weak/broken, it's a warning even if price looks good.
        """
        try:
            cur.execute(
                """
                SELECT s.close, spy.close
                FROM price_daily s
                JOIN price_daily spy ON s.date = spy.date
                WHERE s.symbol = %s AND spy.symbol = 'SPY'
                  AND s.date <= %s
                ORDER BY s.date DESC LIMIT 250
                """,
                (symbol, signal_date),
            )
            rows = cur.fetchall()
            if len(rows) < 60:
                return {'pass': True, 'reason': 'Insufficient data for RS check'}

            # Compute RS-line (stock/SPY ratio) for last 60 and all available
            rs_line = [float(r[0]) / float(r[1]) for r in rows if r[0] and r[1]]
            if len(rs_line) < 60:
                return {'pass': True, 'reason': 'Insufficient RS history'}

            current_rs = rs_line[0]  # Most recent
            rs_60day_high = max(rs_line[:60])  # 60-day high (recent peak)

            # RS should be within threshold of 60-day high (use recent peak, not stale 52-week peak)
            rs_pct_from_high = ((rs_60day_high - current_rs) / rs_60day_high * 100.0) if rs_60day_high > 0 else 0
            max_rs_pct = float(self.config.get('max_rs_pct_from_60d_high', 15.0))

            if rs_pct_from_high > max_rs_pct:
                return {
                    'pass': False,
                    'reason': f'RS-line {rs_pct_from_high:.1f}% below 60d high (need <{max_rs_pct:.0f}% to trade)',
                }

            return {'pass': True, 'reason': f'RS-line strong: {rs_pct_from_high:.1f}% from high'}
        except Exception as e:
            logger.debug(f'RS-line check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'RS check error (continuing)'}

    def _check_weekly_stage_2(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """A4: Weekly Chart Hard Gate — Require weekly chart Stage 2.

        Even if daily is Stage 2, entering when weekly is Stage 3/4 is dangerous.
        Weekly chart shows the longer-term trend.
        """
        try:
            cur.execute(
                """
                SELECT signal FROM buy_sell_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            weekly_signal_row = cur.fetchone()
            if weekly_signal_row:
                weekly_signal = weekly_signal_row[0]
                if weekly_signal == 'SELL':
                    return {
                        'pass': False,
                        'reason': 'Weekly chart in SELL mode (avoid entries in Stage 3/4)',
                    }

            cur.execute(
                """
                SELECT pw.close,
                       AVG(pw.close) OVER (ORDER BY pw.date ASC ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as sma_30w
                FROM price_weekly pw
                WHERE pw.symbol = %s AND pw.date <= %s
                ORDER BY pw.date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            row = cur.fetchone()
            if row and row[0] and row[1]:
                close = float(row[0])
                sma_30w = float(row[1])
                if close < sma_30w:
                    return {
                        'pass': False,
                        'reason': f'Weekly price below 30-week MA (Stage 3/4, not Stage 2)',
                    }

            return {'pass': True, 'reason': 'Weekly chart Stage 2 OK'}
        except Exception as e:
            logger.debug(f'Weekly Stage 2 check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'Weekly check error (continuing)'}

    def _check_rs_line_slope(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """A5: RS Line Trending Up — RS line must have positive slope over last N days.

        Currently the system checks if RS line is within 5% of its 52-week high.
        This adds a direction check: is the RS line trending UP, not just consolidating near the high?
        """
        try:
            slope_days = int(self.config.get('min_rs_line_slope_days', 10))

            cur.execute(
                """
                SELECT s.close, spy.close, s.date
                FROM price_daily s
                JOIN price_daily spy ON s.date = spy.date
                WHERE s.symbol = %s AND spy.symbol = 'SPY'
                  AND s.date <= %s
                ORDER BY s.date DESC LIMIT %s
                """,
                (symbol, signal_date, slope_days + 5),
            )
            rows = cur.fetchall()
            if len(rows) < slope_days:
                return {'pass': True, 'reason': f'Insufficient data for {slope_days}d slope'}

            # Compute RS-line (stock/SPY ratio) for the period
            rs_line_with_dates = []
            for r in rows:
                if r[0] and r[1]:
                    rs = float(r[0]) / float(r[1])
                    rs_line_with_dates.append((r[2], rs))

            if len(rs_line_with_dates) < slope_days:
                return {'pass': True, 'reason': 'Insufficient RS data'}

            rs_line_values = [x[1] for x in rs_line_with_dates[:slope_days]]
            rs_line_values.reverse()  # Fix: make oldest first so slope calculation is correct
            x_values = list(range(slope_days))

            # Simple linear regression: slope = sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean)^2)
            x_mean = sum(x_values) / len(x_values)
            y_mean = sum(rs_line_values) / len(rs_line_values)

            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, rs_line_values))
            denominator = sum((x - x_mean) ** 2 for x in x_values)

            slope = numerator / denominator if denominator != 0 else 0

            if slope <= 0:
                return {
                    'pass': False,
                    'reason': f'RS line slope {slope:.4f} not trending up (need positive slope)',
                }

            return {'pass': True, 'reason': f'RS line trending up: slope {slope:.4f}'}
        except Exception as e:
            logger.debug(f'RS-line slope check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'RS slope check error (continuing)'}

    def _compute_stop_loss(self, symbol, signal_date, sma_50, atr, cur) -> Dict[str, Any]:
        """Compute stop loss — base-type-specific when possible, falls back to MA/ATR.

        First tries the base-type-specific stop (cup-handle uses handle low,
        VCP uses last contraction, etc — research-backed per pattern). If
        that's not available, uses best of (50-DMA, swing low, 2x ATR)
        capped at 8% below entry.

        Returns dict with keys: stop_price, method, reasoning, candidates
        """
        cur.execute(
            "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = cur.fetchone()
        if not row:
            return {'stop_price': None, 'method': 'none', 'reasoning': 'No price data', 'candidates': {}}
        entry = float(row[0])

        # Try base-type-specific stop first (most accurate per the canon)
        try:
            from algo.algo_signals import SignalComputer
            sc = SignalComputer()
            base_stop_info = sc.base_type_stop(symbol, signal_date, entry, atr)
            if base_stop_info and base_stop_info['stop_price'] > 0:
                # Stash the metadata so the pipeline can show WHY this stop was chosen
                self._last_stop_method = base_stop_info['method']
                self._last_stop_reasoning = base_stop_info['reasoning']
                self._last_stop_base_type = base_stop_info['base_type']
                # Only use base-type stop if it's NOT the fallback (real base detected)
                if 'fallback' not in base_stop_info['method'] and 'sanity' not in base_stop_info['method']:
                    return {
                        'stop_price': base_stop_info['stop_price'],
                        'method': base_stop_info['method'],
                        'reasoning': base_stop_info['reasoning'],
                        'candidates': {'base_type': base_stop_info['stop_price']},
                    }
        except Exception as e:
            logger.error(f"  (base_type_stop failed for {symbol}: {e})")

        # Fallback: structural stops (MA / swing / ATR)
        cur.execute(
            """
            SELECT MIN(low) FROM price_daily
            WHERE symbol = %s AND date <= %s
              AND date >= %s::date - INTERVAL '10 days'
            """,
            (symbol, signal_date, signal_date),
        )
        swing_row = cur.fetchone()
        swing_low = float(swing_row[0]) if swing_row and swing_row[0] is not None else None

        atr_stop = (entry - (2.0 * atr)) if atr else None
        max_stop_pct = float(self.config.get('max_stop_distance_pct', 8.0)) / 100.0
        floor_stop = entry * (1.0 - max_stop_pct)

        candidates_dict = {
            'sma_50': sma_50,
            'swing_low_10d': swing_low,
            'atr_2x': atr_stop,
            'floor_stop_8pct': floor_stop,
        }

        candidates = [c for c in (sma_50, swing_low, atr_stop) if c is not None and 0 < c < entry]
        if not candidates:
            # FAIL-CLOSED: No structural stops available (data quality issue)
            self._last_stop_method = 'none'
            self._last_stop_reasoning = 'No structural levels available (SMA-50, swing low, ATR all missing)'
            logger.error(f'[Stop] No structural levels for {symbol} on {signal_date} (sma_50={sma_50}, swing={swing_low}, atr_stop={atr_stop})')
            return {
                'stop_price': None,
                'method': 'none',
                'reasoning': self._last_stop_reasoning,
                'candidates': candidates_dict,
            }

        viable = [c for c in candidates if c >= floor_stop]
        stop = max(viable) if viable else floor_stop
        self._last_stop_method = 'best_of_ma_swing_atr'
        self._last_stop_reasoning = f'Best of (50-DMA, swing low, 2×ATR), capped at 8%'
        return {
            'stop_price': round(stop, 2),
            'method': self._last_stop_method,
            'reasoning': self._last_stop_reasoning,
            'candidates': candidates_dict,
        }
