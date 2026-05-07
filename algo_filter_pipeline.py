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
from algo_config import get_config
from algo_advanced_filters import AdvancedFilters
from algo_swing_score import SwingTraderScore
from filter_rejection_tracker import RejectionTracker

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

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def evaluate_signals(self, eval_date=None):
        """Evaluate all buy signals through filter pipeline.

        If eval_date is None, uses the most recent date in buy_sell_daily that
        has both market_health_daily Stage 2 confirmation and trend_template
        coverage. This avoids evaluating today when no fresh data has been loaded.
        """
        try:
            self.connect()

            if not eval_date:
                eval_date = self._resolve_evaluation_date()

            print(f"\n{'='*70}")
            print(f"FILTER PIPELINE EVALUATION - {eval_date}")
            print(f"{'='*70}\n")

            self.cur.execute(
                """
                SELECT symbol, date, signal, entry_price
                FROM buy_sell_daily
                WHERE date = %s AND signal = 'BUY'
                ORDER BY symbol
                """,
                (eval_date,),
            )
            signals = self.cur.fetchall()
            print(f"Found {len(signals)} BUY signals to evaluate\n")

            # Initialize advanced filters and pre-load market context once
            if self.advanced is None:
                self.advanced = AdvancedFilters(self.config, cur=self.cur)
            ctx = self.advanced.load_market_context(eval_date)
            print(f"Market context: top sectors = {ctx['strong_sectors']}")
            if ctx['market_breadth']:
                print(f"  AAII bull/bear spread: {ctx['market_breadth']['bull_bear_spread']:+.1f}")
            print()

            tier_pass_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            advanced_passed = 0
            advanced_blocked = 0
            passed_all_tiers = []

            # NEW: Initialize rejection tracker (Phase 3 integration)
            tracker = RejectionTracker()

            for symbol, signal_date, _signal, entry_price in signals:
                if entry_price is None or not entry_price:
                    continue
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

            print(f"\n{'='*70}")
            print("Tier pass-through summary:")
            print(f"  T1 Data Quality:     {tier_pass_counts[1]:3d}/{len(signals)}")
            print(f"  T2 Market Health:    {tier_pass_counts[2]:3d}/{len(signals)}")
            print(f"  T3 Trend Template:   {tier_pass_counts[3]:3d}/{len(signals)}")
            print(f"  T4 Signal Quality:   {tier_pass_counts[4]:3d}/{len(signals)}")
            print(f"  T5 Portfolio:        {tier_pass_counts[5]:3d}/{len(signals)}")
            print(f"  T6 Advanced Filters: {advanced_passed:3d}/{tier_pass_counts[5]} passed, "
                  f"{advanced_blocked} blocked")
            print(f"{'='*70}")

            # PRIMARY RANKING: swing_score (research-weighted, swing-specific)
            for t in passed_all_tiers:
                t['final_score'] = t.get('swing_score', 0)

            passed_all_tiers.sort(key=lambda x: x['final_score'], reverse=True)
            max_positions = int(self.config.get('max_positions', 6))
            final_trades = passed_all_tiers[:max_positions]

            print(f"\nFinal Trades (Top {max_positions} by swing_score):")
            print("=" * 100)
            print(f"{'#':<3}{'Sym':<8}{'Grade':<6}{'Score':>6}  {'Entry':>9}{'Stop':>9}{'Setup':>6}"
                  f"{'Trend':>6}{'Mom':>5}{'Vol':>5}{'Fund':>5}{'Sec':>5}{'MTF':>5}  {'Sector':<20}")
            print("-" * 100)
            for i, trade in enumerate(final_trades, 1):
                comp = trade.get('swing_components', {})
                gr = trade.get('swing_grade', 'D')
                print(
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
                print("(no qualifying trades — gates too strict for current market)")
            if not final_trades:
                print("(no qualifying trades)")
            print(f"\n{'='*70}\n")

            try:
                self.conn.commit()
            except Exception:
                pass

            return final_trades

        except Exception as e:
            print(f"ERROR in evaluate_signals: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            self.disconnect()

    def _resolve_evaluation_date(self):
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

    def evaluate_signal(self, symbol, signal_date, entry_price):
        """Evaluate single signal through all 5 tiers (short-circuits on first failure)."""
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

        # Tier 1
        t1 = self._tier1_data_quality(symbol)
        result['tiers'][1] = t1
        result['completeness_pct'] = t1.get('completeness_pct', 0)
        if not t1['pass']:
            return result

        # Tier 2 (market health uses signal_date, falls back to most recent within 5 days)
        t2 = self._tier2_market_health(signal_date)
        result['tiers'][2] = t2
        if not t2['pass']:
            return result

        # Tier 3 (trend template)
        t3 = self._tier3_trend_template(symbol, signal_date)
        result['tiers'][3] = t3
        result['trend_score'] = t3.get('trend_score', 0)
        result['stop_loss_price'] = t3.get('stop_loss_price')
        if not t3['pass']:
            return result

        # Tier 4 (signal quality)
        t4 = self._tier4_signal_quality(symbol, signal_date)
        result['tiers'][4] = t4
        result['sqs'] = t4.get('sqs', 0)
        if not t4['pass']:
            return result

        # Tier 5 (portfolio health)
        t5 = self._tier5_portfolio_health(symbol, entry_price, result['stop_loss_price'])
        result['tiers'][5] = t5
        result['shares'] = t5.get('shares', 0)
        result['risk_dollars'] = t5.get('risk_dollars', 0.0)
        result['position_size_pct'] = t5.get('position_size_pct', 0.0)
        result['passed_all_tiers'] = t5['pass']
        return result

    # ---------- Tier implementations ----------

    def _tier1_data_quality(self, symbol):
        try:
            self.cur.execute(
                """
                SELECT composite_completeness_pct, is_tradeable
                FROM data_completeness_scores WHERE symbol = %s
                """,
                (symbol,),
            )
            row = self.cur.fetchone()
            if not row or row[0] is None:
                return {'pass': False, 'reason': 'No completeness data', 'completeness_pct': 0}

            completeness = float(row[0])
            min_required = float(self.config.get('min_completeness_score', 70))
            if completeness < min_required:
                return {
                    'pass': False,
                    'reason': f'Completeness {completeness:.0f}% < {min_required:.0f}%',
                    'completeness_pct': completeness,
                }

            self.cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
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

    def _tier2_market_health(self, signal_date):
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

    def _tier3_trend_template(self, symbol, signal_date):
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

    def _compute_stop_loss(self, symbol, signal_date, sma_50, atr):
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
            print(f"  (base_type_stop failed for {symbol}: {e})")

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

    def _tier4_signal_quality(self, symbol, signal_date):
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
            min_sqs = float(self.config.get('min_signal_quality_score', 60))
            if sqs < min_sqs:
                return {'pass': False, 'reason': f'SQS {sqs:.0f} < {min_sqs:.0f}', 'sqs': sqs}
            return {'pass': True, 'reason': f'SQS {sqs:.0f}', 'sqs': sqs}
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'sqs': 0}

    def _tier5_portfolio_health(self, symbol, entry_price, stop_loss_price):
        """Portfolio health check + actual share calculation using PositionSizer."""
        try:
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

            # Use PositionSizer for all risk calculations (includes drawdown cascade, exposure mult, phase mult)
            if not stop_loss_price or stop_loss_price >= entry_price:
                stop_loss_price = entry_price * 0.92

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
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'shares': 0}

    def _get_sector_info(self, symbol):
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

    def _count_sector_industry_overlap(self, new_info, existing_symbols):
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

    # ---------- Helpers ----------

    def _load_portfolio_state(self):
        """Cache portfolio state for the run (positions, value, drawdown)."""
        if self._portfolio_state_cache is not None:
            return self._portfolio_state_cache

        # Open positions
        self.cur.execute(
            "SELECT symbol, position_value FROM algo_positions WHERE status = 'open'"
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

    def _log_signal_evaluation(self, result):
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
        print(f"{symbol:6s} | [{passed}] | {first_fail_reason}")

    def _persist_signal_evaluation(self, result, eval_date):
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
            print(f"  (audit log skipped for {result['symbol']}: {e})")
            try:
                self.conn.rollback()
            except Exception:
                pass


if __name__ == "__main__":
    pipeline = FilterPipeline()
    final_trades = pipeline.evaluate_signals()
    print(f"\nFinal trade count: {len(final_trades)}")
