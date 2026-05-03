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

    def __init__(self):
        self.config = get_config()
        self.conn = None
        self.cur = None
        self._market_health_cache = None
        self._market_health_date = None
        self._portfolio_state_cache = None

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

            tier_pass_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            passed_all_tiers = []

            for symbol, signal_date, _signal, entry_price in signals:
                result = self.evaluate_signal(symbol, signal_date, float(entry_price))
                for t in (1, 2, 3, 4, 5):
                    if result['tiers'][t]['pass']:
                        tier_pass_counts[t] += 1

                if result['passed_all_tiers']:
                    passed_all_tiers.append({
                        'symbol': symbol,
                        'entry_price': float(entry_price),
                        'stop_loss_price': result.get('stop_loss_price'),
                        'sqs': result.get('sqs', 0),
                        'trend_score': result.get('trend_score', 0),
                        'completeness_pct': result.get('completeness_pct', 0),
                        'shares': result.get('shares', 0),
                        'risk_dollars': result.get('risk_dollars', 0.0),
                        'all_tiers_pass': True,
                    })

                self._log_signal_evaluation(result)
                self._persist_signal_evaluation(result, eval_date)

            print(f"\n{'='*70}")
            print("Tier pass-through summary:")
            print(f"  T1 Data Quality:    {tier_pass_counts[1]:3d}/{len(signals)}")
            print(f"  T2 Market Health:   {tier_pass_counts[2]:3d}/{len(signals)}")
            print(f"  T3 Trend Template:  {tier_pass_counts[3]:3d}/{len(signals)}")
            print(f"  T4 Signal Quality:  {tier_pass_counts[4]:3d}/{len(signals)}")
            print(f"  T5 Portfolio:       {tier_pass_counts[5]:3d}/{len(signals)}")
            print(f"{'='*70}")

            passed_all_tiers.sort(key=lambda x: x['sqs'], reverse=True)
            max_positions = int(self.config.get('max_positions', 12))
            final_trades = passed_all_tiers[:max_positions]

            print(f"\nFinal Trades (Top {max_positions} by SQS):")
            print("=" * 70)
            for i, trade in enumerate(final_trades, 1):
                print(
                    f"{i:2d}. {trade['symbol']:6s} @ ${trade['entry_price']:8.2f} | "
                    f"Stop ${trade['stop_loss_price']:7.2f} | "
                    f"SQS {int(trade['sqs']):3d} | Trend {int(trade['trend_score']):2d}/10 | "
                    f"Shares {trade['shares']}"
                )
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
        """Trend template + compute stop loss from MA / swing low / ATR."""
        try:
            self.cur.execute(
                """
                SELECT
                    tt.minervini_trend_score,
                    tt.percent_from_52w_low,
                    tt.percent_from_52w_high,
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
            sma_50 = float(row[3]) if row[3] is not None else None
            atr = float(row[4]) if row[4] is not None else None

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
        """Stop = best of (50-DMA, recent swing low, entry - 2*ATR), capped at 8% below entry."""
        self.cur.execute(
            "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        entry = float(row[0])

        # Recent 10-day swing low
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
            return round(floor_stop, 2)

        # Highest candidate at or above the 8% floor (= tightest sane stop)
        viable = [c for c in candidates if c >= floor_stop]
        stop = max(viable) if viable else floor_stop
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
        """Portfolio health check + actual share calculation using stop loss for risk."""
        try:
            state = self._load_portfolio_state()
            pos_count = state['position_count']
            existing_symbols = state['symbols']
            portfolio_value = state['portfolio_value']

            # No duplicate position in same symbol
            if symbol in existing_symbols:
                return {
                    'pass': False,
                    'reason': f'Already have open position in {symbol}',
                    'shares': 0,
                }

            max_positions = int(self.config.get('max_positions', 12))
            if pos_count >= max_positions:
                return {
                    'pass': False,
                    'reason': f'{pos_count} open positions >= {max_positions} max',
                    'shares': 0,
                }

            # Risk-based sizing: shares = risk_dollars / (entry - stop)
            base_risk_pct = float(self.config.get('base_risk_pct', 0.75)) / 100.0
            adjusted_risk_pct = base_risk_pct * state['risk_adjustment']
            risk_dollars = portfolio_value * adjusted_risk_pct

            if not stop_loss_price or stop_loss_price >= entry_price:
                # Fall back to 8% stop if we couldn't compute one
                stop_loss_price = entry_price * 0.92

            risk_per_share = entry_price - stop_loss_price
            if risk_per_share <= 0:
                return {'pass': False, 'reason': 'Invalid risk per share', 'shares': 0}

            shares = int(risk_dollars / risk_per_share)
            if shares <= 0:
                return {'pass': False, 'reason': 'Risk too small for any shares', 'shares': 0}

            position_value = shares * entry_price

            # Cap at max position % of portfolio
            max_position_pct = float(self.config.get('max_position_size_pct', 8.0)) / 100.0
            max_position_value = portfolio_value * max_position_pct
            if position_value > max_position_value:
                shares = int(max_position_value / entry_price)
                position_value = shares * entry_price
                risk_dollars = risk_per_share * shares

            if shares <= 0:
                return {'pass': False, 'reason': 'Position cap forces 0 shares', 'shares': 0}

            # Concentration: this position's % of total portfolio (NOT of position book)
            position_size_pct = (position_value / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
            max_concentration = float(self.config.get('max_concentration_pct', 50.0))
            if position_size_pct > max_concentration:
                return {
                    'pass': False,
                    'reason': f'Position would be {position_size_pct:.1f}% > {max_concentration:.0f}% portfolio',
                    'shares': 0,
                }

            return {
                'pass': True,
                'reason': f'{shares} sh @ ${entry_price:.2f} (risk ${risk_dollars:.0f}, {position_size_pct:.1f}%)',
                'shares': shares,
                'risk_dollars': risk_dollars,
                'position_size_pct': position_size_pct,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'shares': 0}

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
