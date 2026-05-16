#!/usr/bin/env python3
"""
Swing Trading Algo - Filter Pipeline (HARDENED)

5-tier filtering system to identify trade-worthy signals:
Tier 1: Data quality gates (completeness, price floor, recent data)
Tier 2: Market health gates (stage 2 uptrend, distribution days, VIX)
Tier 3: Trend template confirmation (Minervini 8-pt, distance from 52w hi/lo)
Tier 4: Signal quality scores (composite SQS ranking)
Tier 5: Portfolio health (open positions, concentration, sector limits)

Only signals passing ALL tiers reach the final trade list, ranked by SQS.
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from typing import Dict, List, Any, Optional, Tuple
from credential_helper import get_db_password, get_db_config
from algo_config import get_config
from algo_advanced_filters import AdvancedFilters
from algo_swing_score import SwingTraderScore
from filter_rejection_tracker import RejectionTracker
from algo_earnings_blackout import EarningsBlackout
from algo_trendline_support import TrendlineSupport
from trade_status import PositionStatus
from feature_flags import get_flags
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    # Get DB password from environment first, fall back to credential manager if needed
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        try:
            from credential_manager import get_credential_manager
            credential_manager = get_credential_manager()
            db_password = get_db_password()
        except Exception:
            db_password = "postgres"  # Default for local dev

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": db_password,
        "database": os.getenv("DB_NAME", "stocks"),
    }


class FilterPipeline:
    """5-tier filtering and signal evaluation."""

    def __init__(self, exposure_risk_multiplier=1.0):
        self.config = get_config()
        self.exposure_risk_multiplier = exposure_risk_multiplier  # From exposure policy tier
        self.conn = None
        self.cur = None
        self._market_health_cache = None
        self._market_health_date = None
        self._portfolio_state_cache = None
        self._sector_cache = {}
        self._candidate_holdings = {}  # symbols that passed T5 in this run, for sector counting
        self.advanced = None  # AdvancedFilters instance, lazy-init
        self._snapshot_eval_date = None  # Immutable snapshot of eval_date for this run

    def connect(self) -> None:
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self) -> None:
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def evaluate_signals(self, eval_date=None) -> List[Dict[str, Any]]:
        """Evaluate all buy signals through filter pipeline.

        If eval_date is None, uses the most recent date in buy_sell_daily that
        has both market_health_daily Stage 2 confirmation and trend_template
        coverage. This avoids evaluating today when no fresh data has been loaded.
        """
        try:
            self.connect()

            if not eval_date:
                eval_date = self._resolve_evaluation_date()

            # Snapshot eval_date immutably for this run (prevents sector rotation mid-evaluation)
            self._snapshot_eval_date = eval_date

            logger.info(f"\n{'='*70}")
            logger.info(f"FILTER PIPELINE EVALUATION - {eval_date}")
            logger.info(f"{'='*70}\n")

            self.cur.execute(
                """
                SELECT symbol, date, signal
                FROM buy_sell_daily
                WHERE date = %s AND signal = 'BUY'
                ORDER BY symbol
                """,
                (eval_date,),
            )
            signals = self.cur.fetchall()
            logger.info(f"Found {len(signals)} BUY signals to evaluate\n")

            # Initialize advanced filters and pre-load market context once
            if self.advanced is None:
                self.advanced = AdvancedFilters(self.config, cur=self.cur)
            ctx = self.advanced.load_market_context(eval_date)
            logger.info(f"Market context: top sectors = {ctx['strong_sectors']}")
            if ctx['market_breadth']:
                logger.info(f"  AAII bull/bear spread: {ctx['market_breadth']['bull_bear_spread']:+.1f}")

            tier_pass_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            advanced_passed = 0
            advanced_blocked = 0
            passed_all_tiers = []

            # NEW: Initialize rejection tracker (Phase 3 integration)
            tracker = RejectionTracker()

            # Initialize earnings blackout and trendline checks
            earnings_blackout = EarningsBlackout(self.config)
            trendline = TrendlineSupport(cur=self.cur)

            for symbol, signal_date, _signal in signals:
                # Check earnings blackout FIRST (fail-closed on earnings risk)
                blackout_check = earnings_blackout.run(symbol, signal_date)
                if not blackout_check['pass']:
                    logger.info(f"  SKIP {symbol}: {blackout_check['reason']}")
                    continue

                # A1: Signal Age Gate — reject signals older than max_signal_age_days
                max_signal_age_days = int(self.config.get('max_signal_age_days', 3))
                signal_age = (eval_date - signal_date).days
                if signal_age > max_signal_age_days:
                    logger.info(f"  SKIP {symbol}: Signal {signal_age}d old (max {max_signal_age_days}d)")
                    continue

                # Fetch stage, trend score, and price data for signal date
                self.cur.execute(
                    """SELECT t.weinstein_stage, p.volume, p.high, p.low, p.close,
                              (SELECT AVG(volume) FROM price_daily WHERE symbol = %s
                               AND date >= %s - INTERVAL '50 days' AND date <= %s) AS avg_vol_50d
                       FROM trend_template_data t
                       LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                       WHERE t.symbol = %s AND t.date = %s LIMIT 1""",
                    (symbol, signal_date, signal_date, symbol, signal_date),
                )
                row = self.cur.fetchone()
                if row:
                    stage_number, volume, day_high, day_low, close, avg_vol_50d = row

                    # A1: Stage 2 + Volume check
                    if stage_number != 2:
                        logger.info(f"  SKIP {symbol}: Stage {stage_number} (need Stage 2)")
                        continue

                    # A2: Close Quality Gate — close must be in upper N% of day's range
                    if day_high and day_low and close is not None and day_high > day_low:
                        min_close_quality_pct = float(self.config.get('min_close_quality_pct', 60.0))
                        day_range = day_high - day_low
                        close_pct_of_range = ((close - day_low) / day_range * 100) if day_range > 0 else 0
                        if close_pct_of_range < min_close_quality_pct:
                            logger.info(f"  SKIP {symbol}: Close at {close_pct_of_range:.0f}% of range (need >{min_close_quality_pct:.0f}%)")
                            continue

                    # A3: Volume Hard Gate — min breakout volume ratio
                    min_vol_ratio = float(self.config.get('min_breakout_volume_ratio', 1.25))
                    if volume and avg_vol_50d and avg_vol_50d > 0:
                        vol_ratio = volume / avg_vol_50d
                        if vol_ratio < min_vol_ratio:
                            logger.info(f"  SKIP {symbol}: Vol {vol_ratio:.2f}x 50-day avg (need >{min_vol_ratio}x)")
                            continue
                else:
                    logger.info(f"  SKIP {symbol}: No trend or price data for {signal_date}")
                    continue

                # Fetch fresh market close for entry date (Day 1: signal_date or next trading day)
                entry_date = self._get_next_trading_day(signal_date)
                entry_price = self._get_market_close(symbol, entry_date)
                if entry_price is None:
                    continue

                # Validate entry near trendline support (optional confluence check)
                trendline_check = trendline.validate_entry_near_trendline(symbol, signal_date, float(entry_price))
                if not trendline_check['near_trendline']:
                    logger.info(f"  WARN {symbol}: {trendline_check['reason']}")
                    # Note: This is a soft check (warn, not skip) - trendline is optional confluence

                result = self.evaluate_signal(symbol, signal_date, float(entry_price))
                for t in (1, 2, 3, 4, 5):
                    if result['tiers'][t]['pass']:
                        tier_pass_counts[t] += 1

                if result['passed_all_tiers']:
                    # Run advanced filters
                    sector_info = self._get_sector_info(symbol) or {'sector': '', 'industry': ''}
                    adv = self.advanced.evaluate_candidate(
                        symbol, signal_date, float(entry_price),
                        sector_info['sector'], sector_info['industry'],
                    )
                    result['advanced'] = adv

                    if adv['pass']:
                        advanced_passed += 1

                        # NEW: compute the SWING-SPECIFIC score (research-weighted)
                        if not hasattr(self, '_swing'):
                            self._swing = SwingTraderScore(cur=self.cur)
                        swing = self._swing.compute(
                            symbol, signal_date,
                            sector=sector_info['sector'], industry=sector_info['industry'],
                        )

                        # Hard gate: must pass swing-score gates AND meet min score
                        min_swing = float(self.config.get('min_swing_score', 60.0))
                        if not swing['pass']:
                            result['swing_block_reason'] = swing['reason']
                            advanced_blocked += 1
                        elif swing['swing_score'] < min_swing:
                            result['swing_block_reason'] = (
                                f'swing_score {swing["swing_score"]} < {min_swing}'
                            )
                            advanced_blocked += 1
                        else:
                            passed_all_tiers.append({
                                'symbol': symbol,
                                'signal_date': signal_date,
                                'entry_date': entry_date,
                                'entry_price': float(entry_price),
                                'stop_loss_price': result.get('stop_loss_price'),
                                'sqs': result.get('sqs', 0),
                                'trend_score': result.get('trend_score', 0),
                                'completeness_pct': result.get('completeness_pct', 0),
                                'shares': result.get('shares', 0),
                                'risk_dollars': result.get('risk_dollars', 0.0),
                                'composite_score': adv['composite_score'],
                                'swing_score': swing['swing_score'],
                                'swing_grade': swing['grade'],
                                'swing_components': swing['components'],
                                'sector': sector_info['sector'],
                                'industry': sector_info['industry'],
                                'advanced_components': adv['components'],
                                'all_tiers_pass': True,
                            })
                    else:
                        advanced_blocked += 1
                        result['advanced_block_reason'] = adv['reason']

                # NEW: Log rejection if not passed (Phase 3 integration)
                if not result.get('passed_all_tiers', False):
                    tier_results = {}
                    for t in [1, 2, 3, 4, 5]:
                        tier_results[t] = {
                            'pass': result['tiers'][t].get('pass', False),
                            'reason': result['tiers'][t].get('reason', '')
                        }
                    adv_result = {'reason': result.get('advanced_block_reason', '')} if 'advanced_block_reason' in result else None
                    tracker.log_rejection(eval_date, symbol, float(entry_price), tier_results, adv_result)

                self._log_signal_evaluation(result)
                self._persist_signal_evaluation(result, eval_date)

            logger.info(f"\n{'='*70}")
            logger.info("Tier pass-through summary:")
            logger.info(f"  T1 Data Quality:     {tier_pass_counts[1]:3d}/{len(signals)}")
            logger.info(f"  T2 Market Health:    {tier_pass_counts[2]:3d}/{len(signals)}")
            logger.info(f"  T3 Trend Template:   {tier_pass_counts[3]:3d}/{len(signals)}")
            logger.info(f"  T4 Signal Quality:   {tier_pass_counts[4]:3d}/{len(signals)}")
            logger.info(f"  T5 Portfolio:        {tier_pass_counts[5]:3d}/{len(signals)}")
            logger.info(f"  T6 Advanced Filters: {advanced_passed:3d}/{tier_pass_counts[5]} passed, "
                        f"{advanced_blocked} blocked")
            logger.info(f"{'='*70}")

            # PRIMARY RANKING: swing_score (research-weighted, swing-specific)
            for t in passed_all_tiers:
                t['final_score'] = t.get('swing_score', 0)

            passed_all_tiers.sort(key=lambda x: x['final_score'], reverse=True)
            max_positions = int(self.config.get('max_positions', 6))
            final_trades = passed_all_tiers[:max_positions]

            logger.info(f"\nFinal Trades (Top {max_positions} by swing_score):")
            logger.info("=" * 100)
            logger.info(f"{'#':<3}{'Sym':<8}{'Grade':<6}{'Score':>6}  {'Entry':>9}{'Stop':>9}{'Setup':>6}"
                        f"{'Trend':>6}{'Mom':>5}{'Vol':>5}{'Fund':>5}{'Sec':>5}{'MTF':>5}  {'Sector':<20}")
            logger.info("-" * 100)
            for i, trade in enumerate(final_trades, 1):
                comp = trade.get('swing_components', {})
                gr = trade.get('swing_grade', 'D')
                logger.info(
                    f"{i:<3d}{trade['symbol']:<8}{gr:<6}{trade['final_score']:>6.1f}  "
                    f"${trade['entry_price']:>8.2f}${trade['stop_loss_price']:>8.2f}"
                    f"{comp.get('setup_quality', {}).get('pts', 0):>6.1f}"
                    f"{comp.get('trend_quality', {}).get('pts', 0):>6.1f}"
                    f"{comp.get('momentum_rs', {}).get('pts', 0):>5.1f}"
                    f"{comp.get('volume', {}).get('pts', 0):>5.1f}"
                    f"{comp.get('fundamentals', {}).get('pts', 0):>5.1f}"
                    f"{comp.get('sector_industry', {}).get('pts', 0):>5.1f}"
                    f"{comp.get('multi_timeframe', {}).get('pts', 0):>5.1f}  "
                    f"{(trade.get('sector') or 'N/A')[:20]:<20}"
                )
            if not final_trades:
                logger.info("(no qualifying trades — gates too strict for current market)")
            if not final_trades:
                logger.info("(no qualifying trades)")
            logger.info(f"\n{'='*70}\n")

            try:
                self.conn.commit()
            except Exception:
                pass

            return final_trades

        except Exception as e:
            logger.error(f"ERROR in evaluate_signals: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            self.disconnect()

    def _resolve_evaluation_date(self) -> _date:
        """Pick the most recent date that has BUY signals + market health + trend data."""
        self.cur.execute(
            """
            SELECT bs.date
            FROM buy_sell_daily bs
            WHERE bs.signal = 'BUY'
              AND EXISTS (SELECT 1 FROM market_health_daily mh WHERE mh.date = bs.date)
              AND EXISTS (SELECT 1 FROM trend_template_data tt WHERE tt.date = bs.date)
            GROUP BY bs.date
            ORDER BY bs.date DESC
            LIMIT 1
            """
        )
        row = self.cur.fetchone()
        return row[0] if row else _date.today()

    def evaluate_signal(self, symbol, signal_date, entry_price) -> Dict[str, Any]:
        """Evaluate single signal through all 5 tiers (short-circuits on first failure)."""
        flags = get_flags()
        result = {
            'symbol': symbol,
            'signal_date': signal_date,
            'entry_price': entry_price,
            'tiers': {i: {'pass': False, 'reason': ''} for i in (1, 2, 3, 4, 5)},
            'passed_all_tiers': False,
            'sqs': 0,
            'trend_score': 0,
            'completeness_pct': 0,
            'stop_loss_price': None,
            'shares': 0,
            'risk_dollars': 0.0,
            'position_size_pct': 0.0,
        }

        # Tier 1 (Data Quality)
        if not flags.is_enabled("signal_tier_1_enabled", default=True):
            result['tiers'][1] = {'pass': True, 'reason': 'Tier 1 disabled by feature flag'}
            logger.info(f"    T1 disabled by feature flag (pass-through)")
        else:
            t1 = self._tier1_data_quality(symbol)
            result['tiers'][1] = t1
            result['completeness_pct'] = t1.get('completeness_pct', 0)
            if not t1['pass']:
                return result

        # Tier 2 (market health uses signal_date, falls back to most recent within 5 days)
        if not flags.is_enabled("signal_tier_2_enabled", default=True):
            result['tiers'][2] = {'pass': True, 'reason': 'Tier 2 disabled by feature flag'}
            logger.info(f"    T2 disabled by feature flag (pass-through)")
        else:
            t2 = self._tier2_market_health(signal_date)
            result['tiers'][2] = t2
            if not t2['pass']:
                return result

        # Tier 3 (trend template)
        if not flags.is_enabled("signal_tier_3_enabled", default=True):
            result['tiers'][3] = {'pass': True, 'reason': 'Tier 3 disabled by feature flag', 'trend_score': 0}
            logger.info(f"    T3 disabled by feature flag (pass-through)")
        else:
            t3 = self._tier3_trend_template(symbol, signal_date)
            result['tiers'][3] = t3
            result['trend_score'] = t3.get('trend_score', 0)
            result['stop_loss_price'] = t3.get('stop_loss_price')
            if not t3['pass']:
                return result

        # Tier 4 (signal quality)
        if not flags.is_enabled("signal_tier_4_enabled", default=True):
            result['tiers'][4] = {'pass': True, 'reason': 'Tier 4 disabled by feature flag', 'sqs': 0}
            logger.info(f"    T4 disabled by feature flag (pass-through)")
        else:
            t4 = self._tier4_signal_quality(symbol, signal_date)
            result['tiers'][4] = t4
            result['sqs'] = t4.get('sqs', 0)
            if not t4['pass']:
                return result

        # Tier 5 (portfolio health)
        if not flags.is_enabled("signal_tier_5_enabled", default=True):
            result['tiers'][5] = {'pass': True, 'reason': 'Tier 5 disabled by feature flag', 'shares': 0, 'risk_dollars': 0.0}
            logger.info(f"    T5 disabled by feature flag (pass-through)")
        else:
            t5 = self._tier5_portfolio_health(symbol, entry_price, result['stop_loss_price'], signal_date)
            result['tiers'][5] = t5
            result['shares'] = t5.get('shares', 0)
            result['risk_dollars'] = t5.get('risk_dollars', 0.0)
            result['position_size_pct'] = t5.get('position_size_pct', 0.0)
            result['passed_all_tiers'] = t5['pass']
            return result

        result['passed_all_tiers'] = True
        return result

    # ---------- Tier implementations ----------

    def _tier1_data_quality(self, symbol) -> Dict[str, Any]:
        try:
            self.cur.execute(
                """
                SELECT composite_completeness_pct, is_tradeable
                FROM data_completeness_scores WHERE symbol = %s
                """,
                (symbol,),
            )
            row = self.cur.fetchone()
            completeness = 0
            if row and row[0] is not None:
                completeness = float(row[0])
                min_required = float(self.config.get('min_completeness_score', 70))
                if completeness < min_required:
                    return {
                        'pass': False,
                        'reason': f'Completeness {completeness:.0f}% < {min_required:.0f}%',
                        'completeness_pct': completeness,
                    }

            # Check price freshness as fallback (if completeness data not ready yet)
            self.cur.execute(
                "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,),
            )
            price_row = self.cur.fetchone()
            if not price_row or price_row[0] is None:
                return {'pass': False, 'reason': 'No price data', 'completeness_pct': completeness}

            price = float(price_row[0])
            min_price = float(self.config.get('min_stock_price', 5.0))
            if price < min_price:
                return {
                    'pass': False,
                    'reason': f'Price ${price:.2f} < ${min_price:.2f}',
                    'completeness_pct': completeness,
                }

            return {
                'pass': True,
                'reason': f'Completeness {completeness:.0f}%, Price ${price:.2f}',
                'completeness_pct': completeness,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'completeness_pct': 0}

    def _tier2_market_health(self, signal_date) -> Dict[str, Any]:
        """Market health for the signal's date, with 5-day fallback."""
        try:
            if self._market_health_cache and self._market_health_date == signal_date:
                row = self._market_health_cache
            else:
                self.cur.execute(
                    """
                    SELECT date, market_stage, distribution_days_4w, vix_level, market_trend
                    FROM market_health_daily
                    WHERE date <= %s AND date >= %s::date - INTERVAL '5 days'
                    ORDER BY date DESC LIMIT 1
                    """,
                    (signal_date, signal_date),
                )
                row = self.cur.fetchone()
                self._market_health_cache = row
                self._market_health_date = signal_date

            if not row:
                return {'pass': False, 'reason': 'No market health data near signal date'}

            _d, stage, dist_days, vix, trend = row
            stage = stage or 0
            dist_days = dist_days or 0
            vix = float(vix) if vix is not None else 0.0

            max_vix = float(self.config.get('vix_max_threshold', 35.0))
            if vix > max_vix:
                return {'pass': False, 'reason': f'VIX {vix:.1f} > {max_vix:.1f}'}

            max_dd = int(self.config.get('max_distribution_days', 4))
            if dist_days > max_dd:
                return {'pass': False, 'reason': f'Distribution days {dist_days} > {max_dd}'}

            require_stage_2 = bool(self.config.get('require_stage_2_market', True))
            if require_stage_2 and stage != 2:
                return {'pass': False, 'reason': f'Market Stage {stage} != 2 (trend={trend})'}

            return {
                'pass': True,
                'reason': f'Stage {stage}, DD {dist_days}, VIX {vix:.1f}, {trend}',
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}'}

    def _tier3_trend_template(self, symbol, signal_date) -> Dict[str, Any]:
        """Trend template (Minervini) + Weinstein stage + compute stop from MA/ATR/swing.

        Pulls every swing-trading-canon factor we have for the stock:
          - Minervini trend_template_score (8-point system)
          - Weinstein stage (must be 2 = uptrend)
          - 52-week range distances
          - Stage-aligned moving averages
          - Consolidation flag (Darvas/Bassal favor breakout-from-consolidation)
        """
        try:
            self.cur.execute(
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
            row = self.cur.fetchone()
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

            min_score = int(self.config.get('min_trend_template_score', 8))
            if trend_score < min_score:
                return {
                    'pass': False,
                    'reason': f'Trend score {trend_score} < {min_score}',
                    'trend_score': trend_score,
                }

            min_from_low = float(self.config.get('min_percent_from_52w_low', 25.0))
            if pct_from_low < min_from_low:
                return {
                    'pass': False,
                    'reason': f'Only {pct_from_low:.0f}% from 52w low (need {min_from_low:.0f})',
                    'trend_score': trend_score,
                }

            max_from_high = float(self.config.get('max_percent_from_52w_high', 25.0))
            if pct_from_high > max_from_high:
                return {
                    'pass': False,
                    'reason': f'{pct_from_high:.0f}% from 52w high (max {max_from_high:.0f})',
                    'trend_score': trend_score,
                }

            # Minervini rule: RS-line (stock vs SPY) must be making new highs or near new highs
            # Don't exit on Minervini break if RS line is strong
            rs_check = self._check_rs_line_strength(symbol, signal_date)
            if rs_check and not rs_check.get('pass', True):
                return {
                    'pass': False,
                    'reason': rs_check.get('reason', 'RS line weak'),
                    'trend_score': trend_score,
                }

            # A4: Weekly Chart Hard Gate — require weekly chart Stage 2 (currently only scored)
            require_weekly_stage_2 = bool(self.config.get('require_weekly_stage_2', True))
            if require_weekly_stage_2:
                weekly_check = self._check_weekly_stage_2(symbol, signal_date)
                if not weekly_check.get('pass', True):
                    return {
                        'pass': False,
                        'reason': weekly_check.get('reason', 'Weekly chart not Stage 2'),
                        'trend_score': trend_score,
                    }

            # A5: RS Line Trending Up — RS line must have positive slope (not just "near high")
            rs_slope_check = self._check_rs_line_slope(symbol, signal_date)
            if not rs_slope_check.get('pass', True):
                return {
                    'pass': False,
                    'reason': rs_slope_check.get('reason', 'RS line not trending up'),
                    'trend_score': trend_score,
                }

            # Volume decay check: declining volume into breakout = false breakout (Minervini warning)
            vol_check = self._check_volume_decay(symbol, signal_date)
            if vol_check and not vol_check.get('pass', True):
                return {
                    'pass': False,
                    'reason': vol_check.get('reason', 'Volume declining'),
                    'trend_score': trend_score,
                }

            # Compute stop loss: best of (50-DMA, swing low, 2x ATR). Cap at 8% below entry.
            stop_loss_price = self._compute_stop_loss(symbol, signal_date, sma_50, atr)

            return {
                'pass': True,
                'reason': f'Trend {trend_score}/10, {pct_from_low:.0f}% from low',
                'trend_score': trend_score,
                'stop_loss_price': stop_loss_price,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'trend_score': 0}

    def _check_volume_decay(self, symbol, signal_date) -> Dict[str, Any]:
        """Minervini warning: declining volume into breakout signals false breakout.

        Checks if 10-day average volume is declining relative to 50-day average.
        A breakout with declining volume = weak accumulation = false setup.
        """
        try:
            self.cur.execute(
                """
                SELECT volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, signal_date),
            )
            rows = self.cur.fetchall()
            if len(rows) < 50:
                return {'pass': True, 'reason': 'Insufficient volume history'}

            volumes = [float(r[0]) for r in rows if r[0]]
            if len(volumes) < 50:
                return {'pass': True, 'reason': 'No volume data'}

            # 10-day vs 50-day average volume
            vol_10d_avg = sum(volumes[:10]) / 10.0
            vol_50d_avg = sum(volumes) / len(volumes)

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

    def _check_rs_line_strength(self, symbol, signal_date) -> Dict[str, Any]:
        """Minervini rule: RS-line (stock vs SPY) should be strong (at/near new highs).

        Checks if the 60-day RS-line (stock close / SPY close) is within 5% of its
        52-week high. If RS-line is weak/broken, it's a warning even if price looks good.
        """
        try:
            # Get stock and SPY prices for RS-line calculation
            self.cur.execute(
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
            rows = self.cur.fetchall()
            if len(rows) < 60:
                return {'pass': True, 'reason': 'Insufficient data for RS check'}

            # Compute RS-line (stock/SPY ratio) for last 60 and all available
            rs_line = [float(r[0]) / float(r[1]) for r in rows if r[0] and r[1]]
            if len(rs_line) < 60:
                return {'pass': True, 'reason': 'Insufficient RS history'}

            current_rs = rs_line[0]  # Most recent
            rs_60day_high = max(rs_line[:60])  # 60-day high
            rs_52week_high = max(rs_line)  # All-time high in available data

            # RS should be within 5% of 52-week high
            rs_pct_from_high = ((rs_52week_high - current_rs) / rs_52week_high * 100.0) if rs_52week_high > 0 else 0

            if rs_pct_from_high > 5.0:
                return {
                    'pass': False,
                    'reason': f'RS-line {rs_pct_from_high:.1f}% below 52w high (need <5% to trade)',
                }

            return {'pass': True, 'reason': f'RS-line strong: {rs_pct_from_high:.1f}% from high'}
        except Exception as e:
            logger.debug(f'RS-line check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'RS check error (continuing)'}

    def _check_weekly_stage_2(self, symbol, signal_date) -> Dict[str, Any]:
        """A4: Weekly Chart Hard Gate — Require weekly chart Stage 2.

        Even if daily is Stage 2, entering when weekly is Stage 3/4 is dangerous.
        Weekly chart shows the longer-term trend.
        """
        try:
            # Check if there's a recent SELL signal on weekly chart (last 20 trading days)
            self.cur.execute(
                """
                SELECT signal FROM buy_sell_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            weekly_signal_row = self.cur.fetchone()
            if weekly_signal_row:
                weekly_signal = weekly_signal_row[0]
                if weekly_signal == 'SELL':
                    return {
                        'pass': False,
                        'reason': 'Weekly chart in SELL mode (avoid entries in Stage 3/4)',
                    }

            # Check weekly price relative to 30-week SMA (Stage 2 should be above it)
            self.cur.execute(
                """
                SELECT pw.close,
                       AVG(pw.close) OVER (ORDER BY pw.date DESC ROWS BETWEEN 0 AND 149) as sma_30w
                FROM price_weekly pw
                WHERE pw.symbol = %s AND pw.date <= %s
                ORDER BY pw.date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            row = self.cur.fetchone()
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

    def _check_rs_line_slope(self, symbol, signal_date) -> Dict[str, Any]:
        """A5: RS Line Trending Up — RS line must have positive slope over last N days.

        Currently the system checks if RS line is within 5% of its 52-week high.
        This adds a direction check: is the RS line trending UP, not just consolidating near the high?
        """
        try:
            slope_days = int(self.config.get('min_rs_line_slope_days', 10))

            # Get stock and SPY prices for RS-line calculation (enough for slope)
            self.cur.execute(
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
            rows = self.cur.fetchall()
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

            # Calculate slope using linear regression on the last N days
            # NOTE: Data is fetched DESC (newest first), so reverse it to get chronological order
            # x=0 should be oldest, x=N-1 should be newest, so slope > 0 means RS is IMPROVING
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

    def _compute_stop_loss(self, symbol, signal_date, sma_50, atr) -> Dict[str, Any]:
        """Compute stop loss — base-type-specific when possible, falls back to MA/ATR.

        First tries the base-type-specific stop (cup-handle uses handle low,
        VCP uses last contraction, etc — research-backed per pattern). If
        that's not available, uses best of (50-DMA, swing low, 2x ATR)
        capped at 8% below entry.
        """
        self.cur.execute(
            "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        entry = float(row[0])

        # Try base-type-specific stop first (most accurate per the canon)
        try:
            from algo_signals import SignalComputer
            sc = SignalComputer(cur=self.cur)
            base_stop_info = sc.base_type_stop(symbol, signal_date, entry, atr)
            if base_stop_info and base_stop_info['stop_price'] > 0:
                # Stash the metadata so the pipeline can show WHY this stop was chosen
                self._last_stop_method = base_stop_info['method']
                self._last_stop_reasoning = base_stop_info['reasoning']
                self._last_stop_base_type = base_stop_info['base_type']
                # Only use base-type stop if it's NOT the fallback (real base detected)
                if 'fallback' not in base_stop_info['method'] and 'sanity' not in base_stop_info['method']:
                    return base_stop_info['stop_price']
        except Exception as e:
            logger.error(f"  (base_type_stop failed for {symbol}: {e})")

        # Fallback: structural stops (MA / swing / ATR)
        self.cur.execute(
            """
            SELECT MIN(low) FROM price_daily
            WHERE symbol = %s AND date <= %s
              AND date >= %s::date - INTERVAL '10 days'
            """,
            (symbol, signal_date, signal_date),
        )
        swing_row = self.cur.fetchone()
        swing_low = float(swing_row[0]) if swing_row and swing_row[0] is not None else None

        atr_stop = (entry - (2.0 * atr)) if atr else None
        max_stop_pct = float(self.config.get('max_stop_distance_pct', 8.0)) / 100.0
        floor_stop = entry * (1.0 - max_stop_pct)

        candidates = [c for c in (sma_50, swing_low, atr_stop) if c is not None and 0 < c < entry]
        if not candidates:
            self._last_stop_method = 'fallback_8pct_floor'
            self._last_stop_reasoning = '8% floor — no structural levels available'
            return round(floor_stop, 2)

        viable = [c for c in candidates if c >= floor_stop]
        stop = max(viable) if viable else floor_stop
        self._last_stop_method = 'best_of_ma_swing_atr'
        self._last_stop_reasoning = f'Best of (50-DMA, swing low, 2×ATR), capped at 8%'
        return round(stop, 2)

    def _tier4_signal_quality(self, symbol, signal_date) -> Dict[str, Any]:
        try:
            self.cur.execute(
                """
                SELECT composite_sqs FROM signal_quality_scores
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            row = self.cur.fetchone()
            sqs = float(row[0]) if row and row[0] is not None else 0
            min_sqs = float(self.config.get('min_signal_quality_score', 40))
            if sqs < min_sqs:
                return {'pass': False, 'reason': f'SQS {sqs:.0f} < {min_sqs:.0f}', 'sqs': sqs}
            return {'pass': True, 'reason': f'SQS {sqs:.0f}', 'sqs': sqs}
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'sqs': 0}

    def _tier5_portfolio_health(self, symbol, entry_price, stop_loss_price, signal_date=None) -> Dict[str, Any]:
        """Portfolio health check + actual share calculation using PositionSizer."""
        try:
            # Production safeguards (Phase 1)
            if signal_date:
                # Check liquidity
                try:
                    from algo_liquidity_checks import LiquidityChecks
                    lq = LiquidityChecks(self.config)
                    lq_passed, lq_reason = lq.run_all(symbol, entry_price, signal_date)
                    if not lq_passed:
                        return {'pass': False, 'reason': f'Liquidity: {lq_reason}', 'shares': 0}
                except Exception as e:
                    logger.warning(f'Liquidity check error for {symbol}: {e}')

                # Check earnings blackout
                try:
                    from algo_earnings_blackout import EarningsBlackout
                    eb = EarningsBlackout(self.config)
                    eb_result = eb.run(symbol, signal_date)
                    if not eb_result.get('pass', True):
                        return {'pass': False, 'reason': f'Earnings: {eb_result.get("reason", "blackout")}', 'shares': 0}
                except Exception as e:
                    logger.warning(f'Earnings check error for {symbol}: {e}')

            state = self._load_portfolio_state()
            existing_symbols = state['symbols']

            # No duplicate position in same symbol
            if symbol in existing_symbols:
                return {
                    'pass': False,
                    'reason': f'Already have open position in {symbol}',
                    'shares': 0,
                }

            # Sector / industry concentration limits (PositionSizer doesn't check these)
            new_sector_info = self._get_sector_info(symbol)
            if new_sector_info and (existing_symbols or self._candidate_holdings):
                sector_count, industry_count = self._count_sector_industry_overlap(
                    new_sector_info, existing_symbols
                )
                max_per_sector = int(self.config.get('max_positions_per_sector', 3))
                max_per_industry = int(self.config.get('max_positions_per_industry', 2))
                if sector_count >= max_per_sector:
                    return {
                        'pass': False,
                        'reason': f'Sector "{new_sector_info["sector"]}" already has {sector_count} positions (max {max_per_sector})',
                        'shares': 0,
                    }
                if industry_count >= max_per_industry:
                    return {
                        'pass': False,
                        'reason': f'Industry "{new_sector_info["industry"]}" already has {industry_count} positions (max {max_per_industry})',
                        'shares': 0,
                    }

            # Correlation check: prevent entering if highly correlated with existing positions (>0.80 correlation)
            if existing_symbols:
                try:
                    corr_check = self._check_correlation_with_holdings(symbol, existing_symbols, signal_date)
                    if not corr_check['pass']:
                        return {
                            'pass': False,
                            'reason': corr_check['reason'],
                            'shares': 0,
                        }
                except Exception as e:
                    logger.warning(f'Correlation check failed for {symbol}: {e} (continuing without check)')

            # Use PositionSizer for all risk calculations (includes drawdown cascade, exposure mult, phase mult)
            if not stop_loss_price or stop_loss_price >= entry_price:
                # Stop calculation failed. Use fallback: 2x ATR from entry (if ATR available), else 5% stop.
                # Compute ATR fresh from price data
                atr_value = None
                try:
                    self.cur.execute(
                        """SELECT atr FROM technical_data_daily WHERE symbol = %s AND date = %s""",
                        (symbol, signal_date)
                    )
                    atr_row = self.cur.fetchone()
                    if atr_row and atr_row[0]:
                        atr_value = float(atr_row[0])
                except Exception:
                    pass

                if atr_value and atr_value > 0:
                    stop_loss_price = max(0.01, entry_price - (2.0 * atr_value))
                    logger.warning(f'[T5] Stop calculation failed for {symbol}; using 2x ATR fallback: {stop_loss_price:.2f} (ATR={atr_value:.2f})')
                else:
                    stop_loss_price = entry_price * 0.95  # Conservative 5% fallback when ATR missing
                    logger.warning(f'[T5] Stop calculation FAILED for {symbol}; using 5% emergency fallback: {stop_loss_price:.2f} (no ATR available) — RISK INFLATED')

            from algo_position_sizer import PositionSizer
            sizer = PositionSizer(self.config)
            result = sizer.calculate_position_size(symbol, entry_price, stop_loss_price)

            # Check sizing result status
            if result['status'] != 'ok':
                return {
                    'pass': False,
                    'reason': result.get('reason', f'Sizing failed: {result["status"]}'),
                    'shares': 0,
                }

            # Apply exposure tier risk multiplier (e.g., PRESSURE tier = 0.5)
            if self.exposure_risk_multiplier != 1.0:
                adjusted_shares = int(result['shares'] * self.exposure_risk_multiplier)
                if adjusted_shares <= 0 and result['shares'] > 0:
                    return {
                        'pass': False,
                        'reason': f'Exposure tier multiplier {self.exposure_risk_multiplier} reduces position to 0 shares',
                        'shares': 0,
                    }
                result['shares'] = adjusted_shares
                result['risk_dollars'] *= self.exposure_risk_multiplier
                result['position_size_pct'] *= self.exposure_risk_multiplier
                result['reason'] = f'{adjusted_shares} sh @ ${entry_price:.2f} (risk ${result["risk_dollars"]:.0f}, {result["position_size_pct"]:.1f}% after tier mult={self.exposure_risk_multiplier})'

            # Mark candidate as "claimed" for sector/industry counting in this run
            if new_sector_info:
                self._candidate_holdings[symbol] = new_sector_info

            return {
                'pass': True,
                'reason': result['reason'],
                'shares': result['shares'],
                'risk_dollars': result['risk_dollars'],
                'position_size_pct': result['position_size_pct'],
            }
        except RuntimeError as e:
            logger.critical(f"[T5] HALT — portfolio value unavailable: {e}")
            raise
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'shares': 0}

    def _get_sector_info(self, symbol) -> Dict[str, Any]:
        try:
            self.cur.execute(
                "SELECT sector, industry FROM company_profile WHERE ticker = %s LIMIT 1",
                (symbol,),
            )
            row = self.cur.fetchone()
            if not row or not row[0]:
                return None
            return {'sector': row[0], 'industry': row[1] or ''}
        except Exception:
            return None

    def _count_sector_industry_overlap(self, new_info, existing_symbols) -> int:
        """Count how many open positions + this-run candidates share sector/industry with new_info."""
        sector_count = 0
        industry_count = 0

        # Open positions
        for sym in existing_symbols:
            info = self._sector_cache.get(sym)
            if info is None:
                info = self._get_sector_info(sym)
                self._sector_cache[sym] = info
            if not info:
                continue
            if info['sector'] == new_info['sector']:
                sector_count += 1
            if info['industry'] == new_info['industry']:
                industry_count += 1

        # Candidates from this run that have already passed T5
        for sym, info in self._candidate_holdings.items():
            if info['sector'] == new_info['sector']:
                sector_count += 1
            if info['industry'] == new_info['industry']:
                industry_count += 1

        return sector_count, industry_count

    # ---------- Market Data Helpers ----------

    def _get_next_trading_day(self, from_date) -> _date:
        """Get the next trading day after from_date (first day with price data).

        For entry purposes, this gives us Day 1 to confirm the signal on real market data.
        """
        self.cur.execute(
            """
            SELECT date FROM price_daily
            WHERE symbol = 'SPY' AND date > %s
            ORDER BY date ASC LIMIT 1
            """,
            (from_date,),
        )
        row = self.cur.fetchone()
        if row:
            return row[0]
        # Fallback: add 1 day and hope it's a trading day
        return from_date + timedelta(days=1)

    def _get_market_close(self, symbol, date) -> Optional[float]:
        """Get market close price for a symbol on a given date.

        Returns the actual market close from price_daily table.
        If the requested date has no data (e.g., future date), falls back to
        most recent available price to avoid rejecting same-day signals.
        This is appropriate for paper/sim trading.
        """
        self.cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND date = %s
            """,
            (symbol, date),
        )
        row = self.cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])

        # Fallback: use most recent price <= requested date (for same-day signal evaluation)
        self.cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol, date),
        )
        row = self.cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return None

    # ---------- Helpers ----------

    def _load_portfolio_state(self) -> Dict[str, Any]:
        """Cache portfolio state for the run (positions, value, drawdown)."""
        if self._portfolio_state_cache is not None:
            return self._portfolio_state_cache

        # Open positions
        self.cur.execute(
            "SELECT symbol, position_value FROM algo_positions WHERE status = %s",
            (PositionStatus.OPEN.value,)
        )
        rows = self.cur.fetchall()
        position_count = len(rows)
        symbols = {r[0] for r in rows}
        positions_value = sum(float(r[1] or 0) for r in rows)

        # Portfolio value: prefer latest snapshot
        self.cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        )
        snap = self.cur.fetchone()
        portfolio_value = float(snap[0]) if snap and snap[0] else 100000.0

        # Drawdown adjustment from peak
        self.cur.execute(
            "SELECT MAX(total_portfolio_value) FROM algo_portfolio_snapshots"
        )
        peak_row = self.cur.fetchone()
        peak = float(peak_row[0]) if peak_row and peak_row[0] else portfolio_value
        drawdown_pct = max(0.0, (peak - portfolio_value) / peak * 100.0) if peak > 0 else 0.0

        if drawdown_pct >= 20:
            risk_adjustment = 0.0
        elif drawdown_pct >= 15:
            risk_adjustment = float(self.config.get('risk_reduction_at_minus_15', 0.25))
        elif drawdown_pct >= 10:
            risk_adjustment = float(self.config.get('risk_reduction_at_minus_10', 0.50))
        elif drawdown_pct >= 5:
            risk_adjustment = float(self.config.get('risk_reduction_at_minus_5', 0.75))
        else:
            risk_adjustment = 1.0

        self._portfolio_state_cache = {
            'position_count': position_count,
            'symbols': symbols,
            'positions_value': positions_value,
            'portfolio_value': portfolio_value,
            'drawdown_pct': drawdown_pct,
            'risk_adjustment': risk_adjustment,
        }
        return self._portfolio_state_cache

    def _log_signal_evaluation(self, result) -> None:
        symbol = result['symbol']
        tiers = result['tiers']
        passed = ''.join(['1' if tiers[t]['pass'] else '.' for t in (1, 2, 3, 4, 5)])
        first_fail_reason = ''
        for t in (1, 2, 3, 4, 5):
            if not tiers[t]['pass']:
                first_fail_reason = f"T{t}: {tiers[t]['reason']}"
                break
        if not first_fail_reason:
            first_fail_reason = (
                f"PASS — SQS {result['sqs']}, Stop ${result['stop_loss_price']:.2f}, "
                f"{result['shares']} sh"
            )
        log_fn = logger.info if passed else logger.debug
        log_fn(f"{symbol:6s} | [{passed}] | {first_fail_reason}")

    def _persist_signal_evaluation(self, result, eval_date) -> bool:
        """Persist evaluation result to algo_signals_evaluated for audit / dashboard."""
        try:
            tiers = result['tiers']
            # Build a concise reason summary
            first_fail = ''
            for t in (1, 2, 3, 4, 5):
                if not tiers[t]['pass']:
                    first_fail = f"T{t}: {tiers[t]['reason']}"
                    break
            reason = first_fail or f"PASS — {tiers[5]['reason']}"

            self.cur.execute(
                """
                INSERT INTO algo_signals_evaluated (
                    signal_date, symbol, source_table, source_timeframe,
                    raw_signal, entry_price,
                    filter_tier_1_pass, filter_tier_2_pass, filter_tier_3_pass,
                    filter_tier_4_pass, filter_tier_5_pass,
                    final_signal_quality_score, final_risk_score,
                    evaluated_at, evaluation_reason, created_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP
                )
                ON CONFLICT (signal_date, symbol, source_timeframe) DO UPDATE SET
                    entry_price = EXCLUDED.entry_price,
                    filter_tier_1_pass = EXCLUDED.filter_tier_1_pass,
                    filter_tier_2_pass = EXCLUDED.filter_tier_2_pass,
                    filter_tier_3_pass = EXCLUDED.filter_tier_3_pass,
                    filter_tier_4_pass = EXCLUDED.filter_tier_4_pass,
                    filter_tier_5_pass = EXCLUDED.filter_tier_5_pass,
                    final_signal_quality_score = EXCLUDED.final_signal_quality_score,
                    final_risk_score = EXCLUDED.final_risk_score,
                    evaluated_at = CURRENT_TIMESTAMP,
                    evaluation_reason = EXCLUDED.evaluation_reason
                """,
                (
                    eval_date, result['symbol'], 'buy_sell_daily', 'daily',
                    'BUY', result['entry_price'],
                    tiers[1]['pass'], tiers[2]['pass'], tiers[3]['pass'],
                    tiers[4]['pass'], tiers[5]['pass'],
                    int(result['sqs']) if result['sqs'] else 0,
                    result['risk_dollars'],
                    reason[:1000],
                ),
            )
        except Exception as e:
            # Don't fail the pipeline because of audit logging
            logger.info(f"  (audit log skipped for {result['symbol']}: {e})")
            try:
                self.conn.rollback()
            except Exception:
                pass
    def _check_correlation_with_holdings(self, new_symbol, existing_symbols, signal_date=None) -> Dict[str, Any]:
        """Check if new symbol is highly correlated (>0.80) with existing open positions.

        Returns {'pass': bool, 'reason': str, 'highest_correlation': float}
        """
        if not existing_symbols:
            return {'pass': True, 'reason': 'No existing positions'}

        try:
            # Fetch 60-day price history for new symbol and each existing symbol
            symbols_to_check = [new_symbol] + list(existing_symbols)
            # Build placeholders dynamically: %s, %s, %s, ... one for each symbol
            placeholders = ','.join(['%s'] * len(symbols_to_check))
            self.cur.execute(
                f"""
                SELECT symbol, date, close FROM price_daily
                WHERE symbol IN ({placeholders})
                  AND date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY symbol, date
                """,
                tuple(symbols_to_check)
            )
            rows = self.cur.fetchall()
            if not rows:
                return {'pass': True, 'reason': 'Insufficient price data'}

            # Build price dataframe
            import pandas as pd
            df = pd.DataFrame(rows, columns=['symbol', 'date', 'close'])
            df['date'] = pd.to_datetime(df['date'])

            # Pivot to get prices by symbol
            pivot = df.pivot(index='date', columns='symbol', values='close')
            if pivot.empty or new_symbol not in pivot.columns:
                return {'pass': True, 'reason': 'Insufficient data for correlation check'}

            # Compute 60-day returns
            returns = pivot.pct_change()
            returns = returns.dropna()

            if len(returns) < 20:
                logger.warning(f'Insufficient data for correlation check {new_symbol}: {len(returns)} days')
                return {'pass': True, 'reason': 'Insufficient history'}

            # Compute correlations with existing holdings
            new_returns = returns[new_symbol]
            max_corr = 0.0
            most_correlated = None
            for existing in existing_symbols:
                if existing in returns.columns:
                    corr = new_returns.corr(returns[existing])
                    if abs(corr) > max_corr:
                        max_corr = abs(corr)
                        most_correlated = existing

            # Halt if correlation > 0.80
            if max_corr > 0.80:
                return {
                    'pass': False,
                    'reason': f'Correlated {max_corr:.2f} with {most_correlated} (60d, threshold 0.80)',
                    'highest_correlation': round(max_corr, 3),
                }
            return {
                'pass': True,
                'reason': f'Max correlation {max_corr:.2f} with portfolio',
                'highest_correlation': round(max_corr, 3),
            }
        except Exception as e:
            logger.debug(f'Correlation check failed: {e}')
            return {'pass': True, 'reason': 'Correlation check error (continuing)'}


if __name__ == "__main__":
    pipeline = FilterPipeline()
    final_trades = pipeline.evaluate_signals()
    logger.info(f"\nFinal trade count: {len(final_trades)}")
