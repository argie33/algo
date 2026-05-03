#!/usr/bin/env python3
"""
Swing Trading Algo - Filter Pipeline

5-tier filtering system to identify trade-worthy signals:
Tier 1: Data quality gates
Tier 2: Market health gates
Tier 3: Trend template confirmation
Tier 4: Signal quality scores
Tier 5: Portfolio health and position sizing

Only signals passing ALL tiers → actual trades
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal
from datetime import datetime, timedelta
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
        self.log = []

    def connect(self):
        """Open database connection."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def evaluate_signals(self, eval_date=None):
        """Evaluate all buy signals through filter pipeline."""
        try:
            if not eval_date:
                eval_date = datetime.now().date()

            self.connect()

            print(f"\n{'='*70}")
            print(f"FILTER PIPELINE EVALUATION - {eval_date}")
            print(f"{'='*70}\n")

            # Get all buy signals from today
            self.cur.execute("""
                SELECT symbol, date, signal, entry_price
                FROM buy_sell_daily
                WHERE date = %s AND signal = 'BUY'
                ORDER BY symbol
            """, (eval_date,))

            signals = self.cur.fetchall()
            print(f"Found {len(signals)} BUY signals to evaluate\n")

            passed_all_tiers = []

            for symbol, signal_date, signal, entry_price in signals:
                result = self.evaluate_signal(symbol, signal_date, entry_price)
                if result['passed_all_tiers']:
                    passed_all_tiers.append({
                        'symbol': symbol,
                        'entry_price': entry_price,
                        'sqs': result.get('sqs', 0),
                        'position_size': result.get('position_size', 0)
                    })

                self.log_signal_evaluation(result)

            # Sort by SQS and select top 12
            passed_all_tiers.sort(key=lambda x: x['sqs'], reverse=True)
            final_trades = passed_all_tiers[:12]

            print(f"\nFinal Trades (Top 12 by SQS):")
            print("="*70)
            for i, trade in enumerate(final_trades, 1):
                print(f"{i:2d}. {trade['symbol']:6s} @ ${trade['entry_price']:7.2f} | SQS: {trade['sqs']:3d} | Size: {trade['position_size']:6.2f}%")

            print(f"\n{'='*70}\n")

            return final_trades

        except Exception as e:
            print(f"ERROR: {e}")
            return []
        finally:
            self.disconnect()

    def evaluate_signal(self, symbol, signal_date, entry_price):
        """Evaluate single signal through all 5 tiers."""
        result = {
            'symbol': symbol,
            'signal_date': signal_date,
            'entry_price': entry_price,
            'tiers': {
                1: {'pass': False, 'reason': ''},
                2: {'pass': False, 'reason': ''},
                3: {'pass': False, 'reason': ''},
                4: {'pass': False, 'reason': ''},
                5: {'pass': False, 'reason': ''}
            },
            'passed_all_tiers': False,
            'sqs': 0,
            'position_size': 0
        }

        # Tier 1: Data Quality
        tier1 = self.tier1_data_quality(symbol)
        result['tiers'][1] = tier1

        if not tier1['pass']:
            result['passed_all_tiers'] = False
            return result

        # Tier 2: Market Health
        tier2 = self.tier2_market_health()
        result['tiers'][2] = tier2

        if not tier2['pass']:
            result['passed_all_tiers'] = False
            return result

        # Tier 3: Trend Template
        tier3 = self.tier3_trend_template(symbol, signal_date)
        result['tiers'][3] = tier3

        if not tier3['pass']:
            result['passed_all_tiers'] = False
            return result

        # Tier 4: Signal Quality Score
        tier4 = self.tier4_signal_quality(symbol, signal_date)
        result['tiers'][4] = tier4
        result['sqs'] = tier4.get('sqs', 0)

        if not tier4['pass']:
            result['passed_all_tiers'] = False
            return result

        # Tier 5: Portfolio Health
        tier5 = self.tier5_portfolio_health(symbol, entry_price)
        result['tiers'][5] = tier5
        result['position_size'] = tier5.get('position_size', 0)

        result['passed_all_tiers'] = tier5['pass']
        return result

    def tier1_data_quality(self, symbol):
        """Tier 1: Data quality gates."""
        try:
            # Check completeness score
            query = "SELECT composite_completeness_pct FROM data_completeness_scores WHERE symbol = %s"
            self.cur.execute(query, (symbol,))
            result = self.cur.fetchone()

            if not result or not result[0]:
                return {
                    'pass': False,
                    'reason': 'No completeness data'
                }

            completeness = result[0]
            min_required = self.config.get('min_completeness_score', 70)

            if completeness < min_required:
                return {
                    'pass': False,
                    'reason': f'Completeness {completeness:.0f}% < {min_required}%'
                }

            # Check stock price
            query = "SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1"
            self.cur.execute(query, (symbol,))
            result = self.cur.fetchone()

            if not result or not result[0]:
                return {'pass': False, 'reason': 'No price data'}

            price = float(result[0])
            min_price = self.config.get('min_stock_price', 5.0)

            if price < min_price:
                return {'pass': False, 'reason': f'Price ${price:.2f} < ${min_price}'}

            return {
                'pass': True,
                'reason': f'Completeness {completeness:.0f}%, Price ${price:.2f}'
            }

        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}'}

    def tier2_market_health(self):
        """Tier 2: Market health gates."""
        try:
            # Get latest market health
            query = """
                SELECT market_stage, distribution_days_4w, vix_level
                FROM market_health_daily
                ORDER BY date DESC LIMIT 1
            """
            self.cur.execute(query)
            result = self.cur.fetchone()

            if not result:
                return {'pass': False, 'reason': 'No market health data'}

            stage = result[0]
            dist_days = result[1] or 0
            vix = result[2] or 0

            # Check VIX
            max_vix = self.config.get('vix_max_threshold', 35.0)
            if vix > max_vix:
                return {'pass': False, 'reason': f'VIX {vix:.1f} > {max_vix}'}

            # Check distribution days
            max_dd = self.config.get('max_distribution_days', 4)
            if dist_days > max_dd:
                return {'pass': False, 'reason': f'Dist Days {dist_days} > {max_dd}'}

            # Check market stage
            require_stage_2 = self.config.get('require_stage_2_market', True)
            if require_stage_2 and stage != 2:
                return {'pass': False, 'reason': f'Market Stage {stage} != 2'}

            return {
                'pass': True,
                'reason': f'Stage {stage}, DD {dist_days}, VIX {vix:.1f}'
            }

        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}'}

    def tier3_trend_template(self, symbol, signal_date):
        """Tier 3: Minervini trend template confirmation."""
        try:
            query = """
                SELECT minervini_trend_score, percent_from_52w_low, percent_from_52w_high
                FROM trend_template_data
                WHERE symbol = %s AND date = %s
            """
            self.cur.execute(query, (symbol, signal_date))
            result = self.cur.fetchone()

            if not result:
                return {'pass': False, 'reason': 'No trend data'}

            trend_score = result[0] or 0
            pct_from_low = result[1] or 0
            pct_from_high = result[2] or 0

            min_score = self.config.get('min_trend_template_score', 8)
            if trend_score < min_score:
                return {'pass': False, 'reason': f'Trend {trend_score} < {min_score}'}

            min_from_low = self.config.get('min_percent_from_52w_low', 25.0)
            if pct_from_low < min_from_low:
                return {'pass': False, 'reason': f'{pct_from_low:.0f}% from low < {min_from_low:.0f}%'}

            max_from_high = self.config.get('max_percent_from_52w_high', 25.0)
            if pct_from_high > max_from_high:
                return {'pass': False, 'reason': f'{pct_from_high:.0f}% from high > {max_from_high:.0f}%'}

            return {
                'pass': True,
                'reason': f'Trend {trend_score}/10, {pct_from_low:.0f}% from low'
            }

        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}'}

    def tier4_signal_quality(self, symbol, signal_date):
        """Tier 4: Signal quality score confirmation."""
        try:
            query = """
                SELECT composite_sqs
                FROM signal_quality_scores
                WHERE symbol = %s AND date = %s
            """
            self.cur.execute(query, (symbol, signal_date))
            result = self.cur.fetchone()

            sqs = result[0] if result else 0
            min_sqs = self.config.get('min_signal_quality_score', 60)

            if sqs < min_sqs:
                return {
                    'pass': False,
                    'reason': f'SQS {sqs} < {min_sqs}',
                    'sqs': sqs
                }

            return {
                'pass': True,
                'reason': f'SQS {sqs}',
                'sqs': sqs
            }

        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'sqs': 0}

    def tier5_portfolio_health(self, symbol, entry_price):
        """Tier 5: Portfolio health and position sizing."""
        try:
            # Check current positions
            query = """
                SELECT COUNT(*) as pos_count,
                       SUM(position_value) as total_value,
                       MAX(position_value) as max_pos_value
                FROM algo_positions
                WHERE status = 'open'
            """
            self.cur.execute(query)
            result = self.cur.fetchone()

            pos_count = result[0] or 0
            total_value = float(result[1]) if result[1] else 0
            max_pos_value = float(result[2]) if result[2] else 0

            max_positions = self.config.get('max_positions', 12)
            if pos_count >= max_positions:
                return {
                    'pass': False,
                    'reason': f'{pos_count} open positions >= {max_positions}',
                    'position_size': 0
                }

            # Get portfolio value
            query = "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
            self.cur.execute(query)
            result = self.cur.fetchone()

            portfolio_value = float(result[0]) if result and result[0] else 100000

            # Calculate position size
            base_risk = self.config.get('base_risk_pct', 0.75) / 100
            position_size = base_risk * portfolio_value / entry_price if entry_price > 0 else 0

            max_position_pct = self.config.get('max_position_size_pct', 8.0) / 100
            max_position_size = max_position_pct * portfolio_value / entry_price if entry_price > 0 else 0

            if position_size > max_position_size:
                position_size = max_position_size

            # Check concentration
            new_pos_value = position_size * entry_price
            new_total = total_value + new_pos_value
            new_concentration = (new_pos_value / new_total * 100) if new_total > 0 else 0
            max_concentration = self.config.get('max_concentration_pct', 50.0)

            if new_concentration > max_concentration:
                return {
                    'pass': False,
                    'reason': f'Concentration {new_concentration:.1f}% > {max_concentration}%',
                    'position_size': 0
                }

            return {
                'pass': True,
                'reason': f'{pos_count}/{max_positions} positions, size {position_size:.0f} shares',
                'position_size': position_size
            }

        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'position_size': 0}

    def log_signal_evaluation(self, result):
        """Log signal evaluation for audit trail."""
        try:
            symbol = result.get('symbol', 'UNKNOWN')
            tiers = result.get('tiers', {})

            # Print summary
            passed = ' '.join([
                'T1' if tiers[1]['pass'] else '',
                'T2' if tiers[2]['pass'] else '',
                'T3' if tiers[3]['pass'] else '',
                'T4' if tiers[4]['pass'] else '',
                'T5' if tiers[5]['pass'] else '',
            ]).strip()

            if not passed:
                passed = 'FAILED'

            print(f"{symbol:6s} | {passed:15s} | {tiers[1]['reason']}")

        except Exception as e:
            print(f"Error logging: {e}")

if __name__ == "__main__":
    pipeline = FilterPipeline()
    final_trades = pipeline.evaluate_signals()
    print(f"\nFinal trade count: {len(final_trades)}")
