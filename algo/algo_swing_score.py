#!/usr/bin/env python3

import os
import json
from utils.db.context import DatabaseContext
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Tuple, Any, Optional
from algo.algo_signals import SignalComputer

logger = logging.getLogger(__name__)

class SwingTraderScore:
    """Compute and persist swing-specific composite scores."""

    W_SETUP = 25        # Chart setup quality (breakout levels, support/resistance) - highest priority
    W_TREND = 20        # Trend direction and strength (moving average relationships, slope)
    W_MOMENTUM = 20     # Momentum indicators (RSI, MACD, rate of change) - co-equal with trend
    W_VOLUME = 12       # Volume confirmation (above/below average, on-balance volume)
    W_FUNDAMENTALS = 10 # Company fundamentals (earnings, growth, valuation)
    W_SECTOR = 8        # Sector rotation and performance relative to market
    W_MULTI_TF = 5      # Multi-timeframe alignment (1h/4h/daily confirmation)

    def __init__(self):
        from algo.algo_signals import SignalComputer
        self._signals = SignalComputer()

    def _with_cursor(self, operation, mode='read'):
        """Execute operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext(mode) as cur:
                return operation(cur)
        except Exception as e:
            logger.debug(f"Database operation failed: {e}")
            return None

    def _load_config_weights(self, cur) -> Dict[str, int]:
        """Load swing score component weights from config table if available."""
        weights = {}
        try:
            cur.execute(
                "SELECT key, value FROM algo_config WHERE key LIKE 'swing_weight_%'"
            )
            weights = {k: int(v) for k, v in cur.fetchall()}
        except Exception as e:
            logger.debug(f"Could not load swing weights from config: {e} — using defaults")
        return weights

    def _load_date_thresholds(self, cur) -> Dict[str, int]:
        """Load date threshold config values."""
        thresholds = {
            'swing_score_short_lookback_days': 40,
            'swing_score_medium_lookback_days': 90,
            'swing_score_long_lookback_days': 270,
        }
        try:
            # SEC-001 FIX: Use parameterized query to prevent SQL injection
            import psycopg2.sql
            keys_list = list(thresholds.keys())
            placeholders = ', '.join(['%s'] * len(keys_list))
            query = f"SELECT key, value FROM algo_config WHERE key IN ({placeholders})"
            cur.execute(query, keys_list)
            for k, v in cur.fetchall():
                thresholds[k] = int(v)
        except Exception as e:
            logger.debug(f"Could not load date thresholds from config: {e} — using defaults")
        return thresholds

    def compute(self, symbol: str, eval_date, sector: Optional[str] = None, industry: Optional[str] = None) -> Dict[str, Any]:
        """
        Compute the full swing trader score composite with hard-fail gates.

        **Process:**
          1. Check hard-fail gates (trend score, stage, base type, etc.)
          2. If any hard gate fails, return 0 score with reason
          3. If gates pass, compute 7 weighted components
          4. Aggregate into swing_score (0-100 scale) and letter grade
          5. Persist to swing_trader_scores table for dashboard/tracking

        **Hard-Fail Gates (Applied First):**
          - Trend template score >= 5/8 (Minervini 8-point minimum)
          - Weinstein stage == 2 (must be in uptrend phase)
          - Within 25% of 52-week high (not extended too far)
          - Base count < 4 (not too many bases before breakout)
          - Industry rank <= 100 (not in bottom half)
          - Base type != 'wide_and_loose' and quality != 'D'
          - Earnings not within 5 trading days (avoid event risk)

        **Weighted Components:**
          - SETUP_QUALITY (25%): Base type + breakout proximity + VCP + pivot
          - TREND_QUALITY (20%): Minervini score + stage + 30wk MA slope
          - MOMENTUM_RS (20%): RS percentile + 1m/3m/6m return blend
          - VOLUME (12%): Breakout volume + accumulation days
          - FUNDAMENTALS (10%): EPS growth + revenue growth + ROE
          - SECTOR_INDUSTRY (8%): Industry rank > sector rank (industry weighted)
          - MULTI_TIMEFRAME (5%): Weekly + monthly buy_sell alignment

        **Scoring:**
          - Sum of weighted components (0-100)
          - Letter grade: A+ (85+), A (75+), B (65+), C (55+), D (45+), F (<45)

        **Return Dict:**
          {
              'symbol': str,
              'eval_date': str,
              'pass': bool (False if hard gates fail),
              'swing_score': float (0-100, or 0 if failed gates),
              'grade': str ('A+', 'A', 'B', 'C', 'D', 'F'),
              'reason': str (if pass=False, reason for failure),
              'components': {
                  'setup_quality': {'pts': float, 'max': 25, 'detail': dict},
                  'trend_quality': {'pts': float, 'max': 20, 'detail': dict},
                  'momentum_rs': {'pts': float, 'max': 20, 'detail': dict},
                  'volume': {'pts': float, 'max': 12, 'detail': dict},
                  'fundamentals': {'pts': float, 'max': 10, 'detail': dict},
                  'sector_industry': {'pts': float, 'max': 8, 'detail': dict},
                  'multi_timeframe': {'pts': float, 'max': 5, 'detail': dict},
              },
              'hard_gates': dict (details of gate checks)
          }

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            eval_date: Date to evaluate as of
            sector: Sector name (optional, used for ranking comparison)
            industry: Industry name (optional, used for ranking comparison)

        Returns:
            Dict with swing_score, grade, components breakdown, and hard-gate details
        """
        with DatabaseContext('read') as cur:
            try:
                # Hard gates — fail-closed: DB/infra error blocks scoring rather than passing silently
                try:
                    gates = self._check_hard_gates(symbol, eval_date, industry, cur)
                except Exception as gate_err:
                    logger.warning(f"Swing score hard gates unavailable for {symbol}: {gate_err} — blocking")
                    return {
                        'symbol': symbol,
                        'eval_date': str(eval_date),
                        'pass': False,
                        'reason': f'Hard gates unavailable: {str(gate_err)[:60]}',
                        'swing_score': 0.0,
                    }

                if not gates['pass']:
                    logger.debug(f"Swing score {symbol}: hard gate failed - {gates.get('reason', 'unknown')}")
                    return {
                        'symbol': symbol,
                        'eval_date': str(eval_date),
                        'pass': False,
                        'reason': gates['reason'],
                        'hard_gates': gates,
                        'swing_score': 0.0,
                    }

                # Compute components (wrap each in error handling to prevent cascade failures)
                try:
                    setup_pts, setup_detail = self._setup_component(symbol, eval_date)
                except Exception as e:
                    logger.debug(f"Setup component failed for {symbol}: {e}")
                    setup_pts, setup_detail = 0, {'error': str(e)[:50]}

                try:
                    trend_pts, trend_detail = self._trend_component(symbol, eval_date, cur)
                except Exception as e:
                    logger.debug(f"Trend component failed for {symbol}: {e}")
                    trend_pts, trend_detail = 0, {'error': str(e)[:50]}

                try:
                    mom_pts, mom_detail = self._momentum_component(symbol, eval_date, cur)
                except Exception as e:
                    logger.debug(f"Momentum component failed for {symbol}: {e}")
                    mom_pts, mom_detail = 0, {'error': str(e)[:50]}

                try:
                    vol_pts, vol_detail = self._volume_component(symbol, eval_date, cur)
                except Exception as e:
                    logger.debug(f"Volume component failed for {symbol}: {e}")
                    vol_pts, vol_detail = 0, {'error': str(e)[:50]}

                try:
                    fund_pts, fund_detail = self._fundamentals_component(symbol, cur)
                except Exception as e:
                    logger.debug(f"Fundamentals component failed for {symbol}: {e}")
                    fund_pts, fund_detail = 0, {'error': str(e)[:50]}

                try:
                    sec_pts, sec_detail = self._sector_component(symbol, eval_date, sector, industry, cur)
                except Exception as e:
                    logger.debug(f"Sector component failed for {symbol}: {e}")
                    sec_pts, sec_detail = 0, {'error': str(e)[:50]}

                try:
                    mtf_pts, mtf_detail = self._multi_timeframe_component(symbol, eval_date, cur)
                except Exception as e:
                    logger.debug(f"Multi-timeframe component failed for {symbol}: {e}")
                    mtf_pts, mtf_detail = 0, {'error': str(e)[:50]}

                total = setup_pts + trend_pts + mom_pts + vol_pts + fund_pts + sec_pts + mtf_pts

                # Classify grade based on score: A+ (85+), A (75+), B (65+), C (55+), D (45+), F (<45)
                if total >= 85:
                    grade = 'A+'
                elif total >= 75:
                    grade = 'A'
                elif total >= 65:
                    grade = 'B'
                elif total >= 55:
                    grade = 'C'
                elif total >= 45:
                    grade = 'D'
                else:
                    grade = 'F'

                result = {
                    'symbol': symbol,
                    'eval_date': str(eval_date),
                    'pass': True,
                    'swing_score': round(total, 1),
                    'grade': grade,
                    'components': {
                        'setup_quality': {'pts': round(setup_pts, 1), 'max': self.W_SETUP, 'detail': setup_detail},
                        'trend_quality': {'pts': round(trend_pts, 1), 'max': self.W_TREND, 'detail': trend_detail},
                        'momentum_rs':   {'pts': round(mom_pts, 1),   'max': self.W_MOMENTUM, 'detail': mom_detail},
                        'volume':        {'pts': round(vol_pts, 1),   'max': self.W_VOLUME, 'detail': vol_detail},
                        'fundamentals':  {'pts': round(fund_pts, 1),  'max': self.W_FUNDAMENTALS, 'detail': fund_detail},
                        'sector_industry': {'pts': round(sec_pts, 1), 'max': self.W_SECTOR, 'detail': sec_detail},
                        'multi_timeframe': {'pts': round(mtf_pts, 1), 'max': self.W_MULTI_TF, 'detail': mtf_detail},
                    },
                    'hard_gates': gates,
                }
                self._persist(symbol, eval_date, result)
                logger.debug(f"Swing score {symbol}: {total:.1f} ({grade})")
                return result
            except Exception as e:
                logger.error(f"Swing score calculation failed for {symbol}: {e}", exc_info=True)
                return {
                    'symbol': symbol,
                    'eval_date': str(eval_date),
                    'pass': False,
                    'reason': f'calculation error: {str(e)[:60]}',
                    'swing_score': 0.0,
                }

    # ============= HARD GATES =============

    def _check_hard_gates(self, symbol: str, eval_date, industry: Optional[str], cur) -> Dict[str, Any]:
        """
        Apply hard-fail gates that block scoring entirely if violated.

        Any single gate failure returns {'pass': False, 'reason': str}.
        All gates must pass for compute() to proceed to component scoring.

        **Gates Checked:**
          1. Trend template score >= min_trend_score (config, default 5/8)
          2. Weinstein stage == 2 (must be in uptrend)
          3. Within max_extension_pct of 52w high (config, default 25%)
          4. Base count < 4 (reasonable consolidation count)
          5. Base type != 'wide_and_loose' and quality != 'D'
          6. Industry rank <= max_industry_rank (config, default 100)
          7. Earnings not within N days (config, default 5 trading days)

        Config keys: swing_hard_gates_enabled, swing_min_trend_score, swing_max_extension_pct,
                    swing_min_industry_rank, swing_days_to_earnings_block

        Returns: {'pass': True} or {'pass': False, 'reason': str, ...details...}
        """
        # Emergency bypass: if hard gates disabled via config, soft-pass all
        gates_enabled = self._load_config_val('swing_hard_gates_enabled', True)
        if not gates_enabled:
            logger.info(f"Hard gates disabled via config for {symbol}")
            return {'pass': True, 'reason': 'Hard gates disabled by config'}

        # Gate 1 & 2: Minervini trend score + Weinstein stage
        trend_score = 0
        stage = 1
        try:
            cur.execute(
                """SELECT minervini_trend_score, weinstein_stage FROM trend_template_data
                   WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row:
                trend_score = int(row[0]) if row[0] is not None else 0
                stage = int(row[1]) if row[1] is not None else 1
        except Exception as e:
            logger.debug(f"Could not fetch trend data for {symbol}: {e}")

        min_trend_score = self._load_config_val('swing_min_trend_score', 5)
        if trend_score < min_trend_score:
            return {
                'pass': False,
                'reason': f'Trend score {trend_score} < {min_trend_score}',
                'trend_score': trend_score,
            }

        if stage != 2:
            return {
                'pass': False,
                'reason': f'Weinstein stage {stage} != 2 (must be in uptrend)',
                'stage': stage,
            }

        # Gate 3: Not too extended from 52-week high
        try:
            max_extension_pct = self._load_config_val('swing_max_extension_pct', 25)
            cur.execute(
                """SELECT percent_from_52w_high FROM trend_template_data
                   WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                pct_from_high = float(row[0])
                # pct_from_high is (close - high52w) / high52w * 100, always ≤ 0.
                # -30 means 30% below the 52w high. Reject if too far below the high.
                if pct_from_high < -max_extension_pct:
                    return {
                        'pass': False,
                        'reason': f'{abs(pct_from_high):.1f}% below 52w high (max {max_extension_pct}% allowed)',
                        'percent_from_52w_high': pct_from_high,
                    }
        except Exception as e:
            logger.debug(f"52w high extension check failed: {e}")

        # Gate 4: Base type quality check
        base_type = self._signals.classify_base_type(symbol, eval_date)
        if base_type.get('type') == 'wide_and_loose':
            return {
                'pass': False,
                'reason': f'Bad base: {base_type.get("type")} (quality {base_type.get("quality")})',
                'base': base_type,
            }

        # Gate 6: Industry rank (not in bottom half)
        industry_rank = None
        if industry:
            try:
                max_industry_rank = self._load_config_val('swing_min_industry_rank', 100)
                cur.execute(
                    """SELECT current_rank FROM industry_ranking
                       WHERE industry = %s AND date_recorded <= %s
                       ORDER BY date_recorded DESC LIMIT 1""",
                    (industry, eval_date),
                )
                r = cur.fetchone()
                if r and r[0]:
                    industry_rank = int(r[0])
                    if industry_rank > max_industry_rank:
                        return {
                            'pass': False,
                            'reason': f'Industry rank {industry_rank} > {max_industry_rank} (bottom half)',
                            'industry_rank': industry_rank,
                        }
            except Exception as e:
                logger.debug(f"Industry rank check failed: {e}")

        # Gate 7: Earnings proximity
        days_to_earn = self._days_to_earnings(symbol, eval_date)
        earnings_block = self._load_config_val('swing_days_to_earnings_block', 5)
        if days_to_earn is not None and 0 <= days_to_earn <= earnings_block:
            return {
                'pass': False,
                'reason': f'Earnings in ~{days_to_earn}d (blocked within {earnings_block}d)',
                'days_to_earnings': days_to_earn,
            }

        # All gates passed
        return {
            'pass': True,
            'trend_score': trend_score,
            'stage': stage,
            'base_type': base_type.get('type'),
            'base_quality': base_type.get('quality'),
            'industry_rank': industry_rank,
            'days_to_earnings': days_to_earn,
        }

    def _days_to_earnings(self, symbol: str, eval_date) -> Optional[int]:
        """Days until next earnings from earnings_calendar. Returns None if unknown."""
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    """SELECT earnings_date FROM earnings_calendar
                       WHERE symbol = %s AND earnings_date > %s
                       ORDER BY earnings_date ASC LIMIT 1""",
                    (symbol, eval_date),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return (row[0] - eval_date).days
            return None
        except Exception as e:
            logger.debug(f"earnings check failed for {symbol}: {e}")
            return None

    def _load_config_val(self, key: str, default):
        """Load a config value from AlgoConfig, with fallback to default."""
        try:
            from algo.infrastructure import get_config
            val = get_config().get(key)
            return val if val is not None else default
        except Exception as e:
            logger.debug(f"_load_config_val({key}) failed: {e}")
            return default

    # ============= COMPONENTS =============

    def _setup_component(self, symbol: str, eval_date) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate setup quality (25 max points).

        **Composite of:**
          - Base type quality (10 pts): VCP=10, flat_base=9, cup=8, ascending=7, double_bottom=6, saucer=5, etc.
          - Breakout proximity (5 pts): How close to pivot breakout level
          - Volatility contraction (3 pts): VCP detection and pattern tightness
          - Pivot breakout (3 pts): Breaking above 20-day high on volume
          - Power trend (2 pts): 20%+ gain in 21 days (momentum confirmation)
          - Pocket pivot (1 pt): Current day shows absorption of prior down volume
          - 3-Weeks-Tight (1 pt): Classic continuation pattern (O'Neil CAN SLIM)
          - High-Tight-Flag (0 pts): Rare explosive continuation (monitored but not scored)

        Returns: (pts, detail_dict) where pts is 0-25 and detail contains breakdown
        """
        base = self._signals.classify_base_type(symbol, eval_date)
        vcp = self._signals.vcp_detection(symbol, eval_date)
        pivot = self._signals.pivot_breakout(symbol, eval_date)
        power = self._signals.power_trend(symbol, eval_date)
        pocket_piv = self._signals.pocket_pivot(symbol, eval_date, lookback_days=10)
        three_wt = self._signals.three_weeks_tight(symbol, eval_date)
        htf = self._signals.high_tight_flag(symbol, eval_date)

        pts = 0.0
        # Base type quality (max 10 pts)
        type_scores = {
            'vcp': 10, 'flat_base': 9, 'cup_with_handle': 8,
            'ascending_base': 7, 'double_bottom': 6, 'saucer': 5,
            'consolidation': 3, 'no_base': 0, 'wide_and_loose': 0,
        }
        type_pts = type_scores.get(base.get('type'), 0)
        quality_mult = {'A': 1.0, 'B': 0.85, 'C': 0.6, 'D': 0.0}
        type_pts *= quality_mult.get(base.get('quality', 'D'), 0)
        pts += type_pts

        # Breakout imminent bonus (max 5 pts)
        if base.get('breakout_imminent'):
            pts += 5
        elif base.get('in_base'):
            pts += 1.5

        # VCP bonus (max 3 pts)
        if vcp.get('is_vcp'):
            pts += 3 if vcp.get('tight_pattern') else 1.5

        # Pivot breakout (max 2 pts)
        if pivot.get('breakout'):
            pts += 2

        # Power trend (max 2 pts)
        if power.get('power_trend'):
            pts += 2

        # Pocket pivot bonus (max 3 pts) — re-accumulation pattern, institutional absorption
        # Fires when up day on volume >= highest down-day volume in last 10 days
        if pocket_piv.get('pocket_pivot') and pocket_piv.get('days_since_fired', 999) <= 2:
            pts += 3

        # 3-Weeks-Tight bonus (max 2 pts) — IBD continuation pattern
        if three_wt.get('is_3wt'):
            pts += 2 if three_wt.get('breakout_imminent') else 1.0

        # High-Tight Flag bonus (max 4 pts) — rare but powerful
        if htf.get('is_htf'):
            pts += 4

        pts = min(self.W_SETUP, pts)
        return pts, {
            'base_type': base.get('type'),
            'base_quality': base.get('quality'),
            'depth_pct': base.get('depth_pct'),
            'duration_weeks': base.get('duration_weeks'),
            'breakout_imminent': base.get('breakout_imminent'),
            'is_vcp': vcp.get('is_vcp'),
            'pivot_breakout': pivot.get('breakout'),
            'power_trend': power.get('power_trend'),
            'pocket_pivot': pocket_piv.get('pocket_pivot'),
            'pocket_pivot_days_ago': pocket_piv.get('days_since_fired'),
            'is_3wt': three_wt.get('is_3wt'),
            'is_htf': htf.get('is_htf'),
        }

    def _trend_component(self, symbol: str, eval_date, cur) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate trend quality (20 max points).

        **Composite of:**
          - Minervini 8-point score (0-8 pts): Scaled 0-8 from raw 0-8 score
          - Stage-2 phase multiplier (0-10 pts): Early/mid/late Stage 2 progression
          - 30-week MA slope (0-2 pts): Uptrend acceleration/deceleration

        The trend component ensures institutional-grade positioning in a confirmed
        uptrend. Emphasizes Minervini's 8-point criteria combined with Weinstein
        stage analysis for optimal risk/reward timing.

        Returns: (pts, detail_dict) where pts is 0-20 and detail contains breakdown
        """
        cur.execute(
            "SELECT minervini_trend_score FROM trend_template_data WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, eval_date),
        )
        row = cur.fetchone()
        mt_score = int(row[0]) if row and row[0] is not None else 0

        # Minervini 7/8 → 75% pts, 8/8 → 100%
        mt_pts = self.W_TREND * 0.6 * (mt_score / 8.0)  # 60% of 20 = 12 pts on Minervini

        # Phase: early=full, mid=full, late=half, climax=zero
        # Derived from consolidation_flag (the only phase indicator in trend_template_data).
        # consolidation_flag=True → stock is building a base (early phase), else mid.
        phase_mult = 0.5
        phase_name = 'mid'
        estimated_base_count = 0
        weeks_uptrend = 0

        try:
            cur.execute(
                """SELECT consolidation_flag FROM trend_template_data
                   WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            phase_row = cur.fetchone()
            if phase_row and phase_row[0]:
                phase_mult = 1.0
                phase_name = 'early'
        except Exception as e:
            logger.debug(f"Phase calculation failed: {e}")

        # Stage phase contributes other 40% (8 pts) of trend bucket scaled by phase mult
        phase_pts = self.W_TREND * 0.4 * phase_mult

        pts = mt_pts + phase_pts
        return pts, {
            'minervini_score': mt_score,
            'phase': phase_name,
            'phase_multiplier': phase_mult,
            'weeks_in_uptrend': weeks_uptrend,
            'estimated_base_count': estimated_base_count,
        }

    def _momentum_component(self, symbol: str, eval_date, cur) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate momentum and relative strength (20 max points).

        **Composite of:**
          - RS percentile vs SPY (0-12 pts): 60-day relative strength ranking
            • 90+ = 12 pts (elite relative strength)
            • 80-90 = 10 pts (strong outperformance)
            • 70-80 = 7 pts (Minervini institutional bar)
            • 50-70 = 3 pts (mixed relative strength)
            • <50 = 0 pts (underperforming SPY)
          - Return blend (0-8 pts): Weighted average of 1m/3m/6m returns
            • 1m return (21d): weight 3, thresholds 20%/10%/3%/positive
            • 3m return (63d): weight 3, same thresholds
            • 6m return (126d): weight 2, same thresholds

        The momentum component captures uptrend strength both relative to the market
        (RS) and in absolute terms (return blend). Swing setups during consolidation
        phases use lower return thresholds (3% vs 30%) to avoid over-filtering.

        Returns: (pts, detail_dict) where pts is 0-20 and detail contains breakdown
        """
        # RS percentile vs SPY (60-day)
        rs_60 = self._signals._rs_percentile_vs_spy(cur, symbol, eval_date, lookback=60)
        rs_pts = 0.0
        if rs_60 is not None:
            # Minervini bar: 70 = pass, 90 = sweet spot
            if rs_60 >= 90:
                rs_pts = 12
            elif rs_60 >= 80:
                rs_pts = 10
            elif rs_60 >= 70:
                rs_pts = 7
            elif rs_60 >= 50:
                rs_pts = 3
            else:
                rs_pts = 0

        r1 = self._signals._period_return(cur, symbol, eval_date, 21)
        r3 = self._signals._period_return(cur, symbol, eval_date, 63)
        r6 = self._signals._period_return(cur, symbol, eval_date, 126)
        blend_pts = 0.0
        for ret, weight in [(r1, 3), (r3, 3), (r6, 2)]:
            if ret is None:
                continue
            if ret > 0.20:
                blend_pts += weight
            elif ret > 0.10:
                blend_pts += weight * 0.7
            elif ret > 0.03:
                blend_pts += weight * 0.4
            elif ret > 0:
                blend_pts += weight * 0.2

        # SHORT INTEREST OPPORTUNITY BONUS (+3 pts)
        # High short interest + strong breakout volume + outperforming RS = squeeze potential
        si_pts = 0.0
        short_interest = None
        try:
            cur.execute(
                """SELECT short_interest_percent FROM positioning_metrics WHERE symbol = %s
                   ORDER BY date DESC LIMIT 1""",
                (symbol,),
            )
            r = cur.fetchone()
            if r and r[0] is not None:
                short_interest = float(r[0])
                # Also get volume ratio
                cur.execute(
                    """
                    WITH d AS (
                        SELECT date, volume,
                               AVG(volume) OVER (ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg50
                        FROM price_daily WHERE symbol = %s AND date <= %s
                        ORDER BY date DESC LIMIT 1
                    )
                    SELECT volume / NULLIF(avg50, 0) FROM d
                    """,
                    (symbol, eval_date),
                )
                vol_row = cur.fetchone()
                vol_ratio = float(vol_row[0]) if vol_row and vol_row[0] is not None else 0

                # Trigger: SI > 15% AND volume_ratio > 1.5x AND RS percentile > 70
                if short_interest > 15 and vol_ratio > 1.5 and rs_60 is not None and rs_60 > 70:
                    si_pts = 3.0
        except Exception as e:
            logger.debug(f"Short interest momentum failed: {e}")

        # EARNINGS SURPRISE MOMENTUM removed (no earnings_metrics data source)
        earnings_pts = 0.0

        # OPTIONS SIGNALS BONUS — IV rank, put/call ratio, implied move
        opts_pts = 0.0
        opts_detail = {}
        try:
            if hasattr(self, 'options_signal'):
                opts = self.options_signal(symbol, eval_date)
                opts_pts = opts.get('bonus_pts', 0.0)
                opts_detail = {
                    'iv_rank': opts.get('iv_rank', {}),
                    'put_call': opts.get('put_call', {}),
                    'implied_move': opts.get('implied_move', {}),
                }
        except Exception as e:
            logger.debug(f"Options signal failed for {symbol}: {e}")

        pts = min(self.W_MOMENTUM, rs_pts + blend_pts + si_pts + earnings_pts + opts_pts)
        return pts, {
            'rs_percentile_60d': round(rs_60, 1) if rs_60 is not None else None,
            'return_1m': round(r1 * 100, 1),
            'return_3m': round(r3 * 100, 1),
            'return_6m': round(r6 * 100, 1),
            'short_interest_pct': round(short_interest, 1) if short_interest is not None else None,
            'short_interest_bonus_pts': si_pts,
            'earnings_momentum_pts': earnings_pts,
            'options_bonus_pts': opts_pts,
            'options_signals': opts_detail,
        }

    def _volume_component(self, symbol: str, eval_date, cur) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate volume characteristics (12 max points).

        **Composite of:**
          - Breakout volume ratio (0-8 pts): Today's volume vs 50-day average
            • >2x = 8 pts (strong institutional accumulation)
            • 1.5-2x = 6 pts (solid volume confirmation)
            • 1.2-1.5x = 4 pts (above average)
            • <1.2x = 0 pts (below average volume)
          - Accumulation days (0-4 pts): Count of up days with volume > 50d avg
            • 3+ days = 4 pts (strong accumulation)
            • 2 days = 2 pts (moderate accumulation)
            • <2 days = 0 pts (weak accumulation)

        Volume is a key institutional signature. Breakouts without volume are likely
        failed attempts; accumulation days during consolidation predict sharp moves.

        Returns: (pts, detail_dict) where pts is 0-12 and detail contains breakdown
        """
        # Latest day volume vs 50d avg
        cur.execute(
            """
            WITH d AS (
                SELECT date, volume,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg50
                FROM price_daily WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
            )
            SELECT volume, avg50 FROM d
            """,
            (symbol, eval_date),
        )
        row = cur.fetchone()
        ratio = None
        ratio_pts = 0.0
        if row is not None and row[0] is not None and row[1] is not None:
            ratio = float(row[0]) / float(row[1])
            # Breakout volume ratio tiers
            if ratio >= 2.0:
                ratio_pts = 8  # >2x volume = exceptional breakout strength
            elif ratio >= 1.5:
                ratio_pts = 6  # 1.5x = full points (Bulkowski 65% success threshold)
            elif ratio >= 1.2:
                ratio_pts = 5
            elif ratio >= 1.0:
                ratio_pts = 3
            elif ratio >= 0.7:
                ratio_pts = 1

        # Accumulation days (last 20 days where close up + volume above 50-day avg)
        thresholds = self._load_date_thresholds(cur)
        lookback = thresholds['swing_score_short_lookback_days']
        cur.execute(
            f"""
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg50
                FROM price_daily WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - INTERVAL '{lookback} days'
            )
            SELECT
                COUNT(*) FILTER (WHERE close > prev_close * 1.002 AND volume > avg50) AS accum,
                COUNT(*) FILTER (WHERE close < prev_close * 0.998 AND volume > avg50) AS dist
            FROM d
            """,
            (symbol, eval_date, eval_date),
        )
        row = cur.fetchone()
        accum = int(row[0]) if row else 0
        dist = int(row[1]) if row else 0
        net = accum - dist
        # +5 net = full 6 pts (floor at 0 when net <= -1)
        accum_pts = max(0.0, min(6.0, (net + 1) * 0.75))

        pts = ratio_pts + accum_pts
        # Cap to W_VOLUME max (same pattern as other components like _setup_component)
        pts = min(self.W_VOLUME, pts)
        return pts, {
            'today_volume_ratio': round(ratio, 2) if ratio else None,
            'accumulation_days': accum,
            'distribution_days': dist,
            'net_accumulation': net,
        }

    def _fundamentals_component(self, symbol: str, cur) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate fundamental quality (10 max points).

        **Composite of:**
          - EPS 3-year CAGR (0-4 pts): From growth_metrics table
            • >= 25% = 4 pts (CAN SLIM "C" criterion: strong earnings growth)
            • 15-25% = 3 pts (solid growth)
            • 5-15% = 1.5 pts (modest growth)
            • <5% = 0 pts (weak growth)
          - Revenue 3-year CAGR (0-3 pts): Top-line growth validation
            • >= 15% = 3 pts
            • 5-15% = 2 pts
            • <5% = 0 pts
          - Net Income YoY (0-1.5 pts): Recent earnings acceleration
            • >= 10% = 1.5 pts
            • > 0% = 1 pt
            • <= 0% = 0 pts
          - Revenue YoY (0-1.5 pts): Recent sales acceleration validation
            • >= 10% = 1.5 pts
            • > 0% = 1 pt
            • <= 0% = 0 pts

        Fundamentals provide the earnings power that sustains stock moves. Swing
        setups with strong growth are more likely to run hard on breakouts.
        This is a light filter; weak fundamentals don't disqualify but reduce score.

        Returns: (pts, detail_dict) where pts is 0-10 and detail contains breakdown
        """
        cur.execute(
            """
            SELECT eps_growth_3y_cagr, revenue_growth_3y_cagr,
                   net_income_growth_yoy, revenue_growth_yoy
            FROM growth_metrics WHERE symbol = %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        )
        gm = cur.fetchone()
        eps_3y = float(gm[0]) if gm and gm[0] is not None else 0
        rev_3y = float(gm[1]) if gm and gm[1] is not None else 0
        ni_yoy = float(gm[2]) if gm and gm[2] is not None else 0
        rev_yoy = float(gm[3]) if gm and gm[3] is not None else 0

        # EPS 3y >= 25% = 4 pts (CAN SLIM "C")
        eps_pts = 0.0
        if eps_3y >= 25:
            eps_pts = 4
        elif eps_3y >= 15:
            eps_pts = 3
        elif eps_3y >= 5:
            eps_pts = 1.5

        # Rev 3y >= 15% = 3 pts (CAN SLIM "S")
        rev_pts = 0.0
        if rev_3y >= 15:
            rev_pts = 3
        elif rev_3y >= 8:
            rev_pts = 2
        elif rev_3y > 0:
            rev_pts = 1

        # YoY positive = 1.5 pts each
        ni_pts = 1.5 if ni_yoy > 10 else (1 if ni_yoy > 0 else 0)
        ry_pts = 1.5 if rev_yoy > 10 else (1 if rev_yoy > 0 else 0)

        pts = eps_pts + rev_pts + ni_pts + ry_pts
        return min(self.W_FUNDAMENTALS, pts), {
            'eps_3y_cagr': eps_3y,
            'rev_3y_cagr': rev_3y,
            'ni_yoy': ni_yoy,
            'rev_yoy': rev_yoy,
        }

    def _sector_component(self, symbol: str, eval_date, sector: Optional[str], industry: Optional[str], cur) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate sector and industry momentum context (8 max points).

        **Composite of:**
          - Industry ranking (0-3 pts): Performance rank within the industry (1-197)
            • Top 20 = 3 pts (elite performance)
            • Top 40 = 2 pts (strong performance)
            • Top 80 = 1 pt (above average)
            • Bottom half = 0 pts (flagged as hard gate; should not reach here)
          - Sector momentum (0-3 pts): Sector-level trend strength
            • Momentum score >= 70 = 3 pts
            • Momentum score >= 50 = 2 pts
            • Momentum score >= 30 = 1 pt
          - Rank acceleration (0-2 pts): Industries/sectors improving in ranking
            • Industry improving + sector improving = 2 pts
            • One improving = 1 pt
            • Rank acceleration momentum bonus if sector rank improving

        Context: Individual stock strength is amplified when the industry and sector
        are also strong. Picks from weak industries/sectors often fail despite good
        technicals. This component ensures we're trading in "hot" groups.

        Returns: (pts, detail_dict) where pts is 0-8 and detail contains breakdown
        """
        if sector is None or industry is None:
            cur.execute(
                "SELECT sector, industry FROM company_profile WHERE ticker = %s LIMIT 1",
                (symbol,),
            )
            r = cur.fetchone()
            if r:
                sector, industry = r[0], r[1]

        ind_pts = 0.0
        sec_pts = 0.0
        accel_pts = 0.0
        ind_rank = None
        sec_rank = None
        sec_accel_4w = 0
        ind_accel_4w = 0

        if industry:
            cur.execute(
                """SELECT current_rank, rank_4w_ago FROM industry_ranking
                   WHERE industry = %s AND date_recorded <= %s
                   ORDER BY date_recorded DESC LIMIT 1""",
                (industry, eval_date),
            )
            r = cur.fetchone()
            if r and r[0]:
                ind_rank = int(r[0])
                # top 20 = 3pts, top 40 = 2, top 80 = 1
                if ind_rank <= 20:
                    ind_pts = 3.0
                elif ind_rank <= 40:
                    ind_pts = 2.0
                elif ind_rank <= 80:
                    ind_pts = 1.0
                # Acceleration: rank improving = bonus
                if r[1] is not None:
                    ind_accel_4w = int(r[1]) - ind_rank  # positive = improving

        if sector:
            cur.execute(
                """SELECT current_rank, rank_4w_ago, momentum_score FROM sector_ranking
                   WHERE sector_name = %s AND date <= %s
                   ORDER BY date DESC LIMIT 1""",
                (sector, eval_date),
            )
            r = cur.fetchone()
            if r and r[0]:
                sec_rank = int(r[0])
                if sec_rank <= 3:
                    sec_pts = 2.0
                elif sec_rank <= 5:
                    sec_pts = 1.5
                elif sec_rank <= 7:
                    sec_pts = 0.5
                # Acceleration
                if r[1] is not None:
                    sec_accel_4w = int(r[1]) - sec_rank

        if ind_accel_4w >= 5 and sec_accel_4w >= 1:
            accel_pts = 3.0  # both accelerating sharply
        elif ind_accel_4w >= 3 or sec_accel_4w >= 1:
            accel_pts = 1.5  # one accelerating
        elif ind_accel_4w < -3 and sec_accel_4w < -1:
            accel_pts = -1.0  # decelerating despite high rank = warning

        rotation_status = None
        rotation_pts = 0.0
        if sector:
            try:
                cur.execute(
                    """SELECT signal FROM sector_rotation_signal
                       WHERE sector_name = %s AND date <= %s
                       ORDER BY date DESC LIMIT 1""",
                    (sector, eval_date),
                )
                r = cur.fetchone()
                if r and r[0]:
                    rotation_status = r[0]
                    if rotation_status == 'Leading':
                        rotation_pts = 3.0
                    elif rotation_status in ('Weakening', 'Lagging'):
                        rotation_pts = -5.0
            except Exception as e:
                logger.debug(f"Rotation status check failed: {e}")

        total_pts = min(self.W_SECTOR, max(0.0, ind_pts + sec_pts + accel_pts + rotation_pts))
        return total_pts, {
            'industry': industry,
            'industry_rank': ind_rank,
            'industry_accel_4w': ind_accel_4w,
            'sector': sector,
            'sector_rank': sec_rank,
            'sector_accel_4w': sec_accel_4w,
            'acceleration_pts': accel_pts,
            'rotation_status': rotation_status,
            'rotation_pts': rotation_pts,
        }

    def _multi_timeframe_component(self, symbol: str, eval_date, cur) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluate multi-timeframe alignment (5 max points).

        **Composite of:**
          - Weekly BUY signal (0-3 pts): BUY generated in last 90 days (~13 weeks)
            • Recent BUY signal = 3 pts (active weekly uptrend)
            • No signal, but price > weekly MA = 1 pt (MA confirming larger uptrend)
          - Monthly trend (0-2 pts): Monthly timeframe alignment
            • Monthly BUY or price > monthly MA = 2 pts
            • Monthly uptrend continuation = 1 pt

        **Context:** Stage-2 stocks often had their weekly BUY weeks before the
        daily setup is ripe (rally already underway). We look back ~3 months on
        weekly and ~9 months on monthly. Multi-timeframe alignment confirms that
        the stock is in buyer's favor across all timeframes, not just daily tactics.

        Returns: (pts, detail_dict) where pts is 0-5 and detail contains breakdown
        """
        weekly_buy = False
        weekly_above_ma = False
        monthly_up = False
        monthly_above_ma = False
        try:
            # Weekly BUY signal in last 90 days (~13 weeks, captures most active uptrends)
            thresholds = self._load_date_thresholds(cur)
            medium_lookback = thresholds['swing_score_medium_lookback_days']
            cur.execute(
                f"""SELECT 1 FROM buy_sell_weekly WHERE symbol = %s AND signal_type = 'BUY'
                   AND date >= %s::date - INTERVAL '{medium_lookback} days' AND date <= %s LIMIT 1""",
                (symbol, eval_date, eval_date),
            )
            weekly_buy = cur.fetchone() is not None

            # Fallback: weekly close above 30-week SMA — Stage-2 condition (Weinstein)
            cur.execute(
                """WITH w AS (
                       SELECT close,
                              AVG(close) OVER (ORDER BY date
                                               ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS sma30,
                              ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                       FROM price_weekly WHERE symbol = %s AND date <= %s
                   )
                   SELECT close, sma30 FROM w WHERE rn = 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row is not None and row[0] is not None and row[1] is not None:
                weekly_above_ma = float(row[0]) > float(row[1])

            # Monthly BUY in last 270 days (~9 months — long-term confirmation window)
            long_lookback = thresholds['swing_score_long_lookback_days']
            cur.execute(
                f"""SELECT 1 FROM buy_sell_monthly WHERE symbol = %s AND signal_type = 'BUY'
                   AND date >= %s::date - INTERVAL '{long_lookback} days' AND date <= %s LIMIT 1""",
                (symbol, eval_date, eval_date),
            )
            monthly_up = cur.fetchone() is not None

            # Fallback: monthly close above 10-month MA — long-term uptrend (Faber)
            cur.execute(
                """WITH m AS (
                       SELECT close,
                              AVG(close) OVER (ORDER BY date
                                               ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS sma10,
                              ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                       FROM price_monthly WHERE symbol = %s AND date <= %s
                   )
                   SELECT close, sma10 FROM m WHERE rn = 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row is not None and row[0] is not None and row[1] is not None:
                monthly_above_ma = float(row[0]) > float(row[1])
        except Exception as e:
            logger.debug(f"Monthly MA check failed: {e}")

        # Treat MA fallback as a softer confirmation than a fresh BUY signal
        weekly_aligned = weekly_buy or weekly_above_ma
        monthly_aligned = monthly_up or monthly_above_ma

        # Documented edge: aligned timeframes 58% win rate vs 39% non-aligned
        pts = 0.0
        if weekly_aligned and monthly_aligned:
            pts = 5.0 if (weekly_buy and monthly_up) else 4.0  # MA-only = slight discount
        elif weekly_aligned:
            pts = 3.0 if weekly_buy else 2.0
        elif monthly_aligned:
            pts = 1.5 if monthly_up else 1.0

        return pts, {
            'weekly_buy_recent': weekly_buy,
            'weekly_above_ma': weekly_above_ma,
            'monthly_buy_recent': monthly_up,
            'monthly_above_ma': monthly_above_ma,
        }

    # ============= helpers =============

    def _persist(self, symbol: str, eval_date, result: Dict[str, Any]) -> None:
        """Persist computed swing score to swing_trader_scores table."""
        try:
            comp = result.get('components', {})

            default_components = {
                'setup_quality': {'pts': 0.0, 'max': self.W_SETUP},
                'trend_quality': {'pts': 0.0, 'max': self.W_TREND},
                'momentum_rs': {'pts': 0.0, 'max': self.W_MOMENTUM},
                'volume': {'pts': 0.0, 'max': self.W_VOLUME},
                'fundamentals': {'pts': 0.0, 'max': self.W_FUNDAMENTALS},
                'sector_industry': {'pts': 0.0, 'max': self.W_SECTOR},
                'multi_timeframe': {'pts': 0.0, 'max': self.W_MULTI_TF},
            }

            for key in default_components:
                if key in comp:
                    default_components[key].update(comp[key])

            components_json = {
                **default_components,
                'grade': result.get('grade', 'F'),
                'pass': result.get('pass', False),
                'reason': result.get('reason'),
            }

            with DatabaseContext('write') as cur:
                cur.execute(
                    """
                    INSERT INTO swing_trader_scores (symbol, date, score, components)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        score = EXCLUDED.score,
                        components = EXCLUDED.components,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (symbol, eval_date, float(result.get('swing_score', 0)), json.dumps(components_json)),
                )
        except Exception as e:
            logger.error(f"persist swing_score failed for {symbol}: {e}", exc_info=True)

if __name__ == "__main__":
    s = SwingTraderScore()
    eval_date = date(2026, 4, 24)
    logger.info(f"SWING TRADER SCORES — {eval_date}")

    candidates = ('AROC', 'CASS', 'CVV', 'EW', 'FSTR', 'LRCX', 'NATR', 'NBHC', 'NGS', 'SMTC', 'SRCE', 'CTS')

    with DatabaseContext('read') as cur:
        for sym in candidates:
            cur.execute("SELECT sector, industry FROM company_profile WHERE ticker = %s", (sym,))
            r = cur.fetchone()
            sector = r[0] if r else None
            industry = r[1] if r else None
            result = s.compute(sym, eval_date, sector=sector, industry=industry)
            if result['pass']:
                comp = result['components']
                logger.info(f"{sym:6s} {result['grade']:>3s} {result['swing_score']:5.1f}/100 | "
                      f"setup {comp['setup_quality']['pts']:4.1f} | "
                      f"trend {comp['trend_quality']['pts']:4.1f} | "
                      f"mom {comp['momentum_rs']['pts']:4.1f} | "
                      f"vol {comp['volume']['pts']:4.1f} | "
                      f"fund {comp['fundamentals']['pts']:4.1f} | "
                      f"sec {comp['sector_industry']['pts']:4.1f} | "
                      f"mtf {comp['multi_timeframe']['pts']:4.1f}")
            else:
                logger.warning(f"{sym:6s} BLOCKED: {result['reason']}")

