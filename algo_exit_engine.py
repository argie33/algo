#!/usr/bin/env python3
"""
Exit Engine - Monitor positions and execute exits

Exit Rules:
- T1: 1.5R at first pullback/consolidation
- T2: 3R at pattern break or 50% base
- T3: 4R+ maximum hold or technical break
- Stop: Minervini break (21-EMA, 50-DMA, pivot)
- Time: Max 20 days in position
- Distribution: Exit all on market distribution day
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
from algo_trade_executor import TradeExecutor

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

class ExitEngine:
    """Monitor and execute position exits."""

    def __init__(self, config):
        self.config = config
        self.executor = TradeExecutor(config)
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def check_and_execute_exits(self, current_date=None):
        """Check all open positions for exit conditions."""
        if not current_date:
            current_date = datetime.now().date()

        self.connect()

        try:
            print(f"\n{'='*70}")
            print(f"EXIT ENGINE CHECK - {current_date}")
            print(f"{'='*70}\n")

            # Get all open trades
            self.cur.execute("""
                SELECT trade_id, symbol, entry_price, entry_quantity,
                       target_1_price, target_2_price, target_3_price,
                       stop_loss_price, trade_date
                FROM algo_trades
                WHERE status IN ('filled', 'active')
                ORDER BY trade_date ASC
            """)

            trades = self.cur.fetchall()
            exits_executed = 0

            for trade in trades:
                trade_id, symbol, entry_price, qty, t1, t2, t3, stop, trade_date = trade

                # Get current price
                self.cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND date = %s
                    ORDER BY date DESC LIMIT 1
                """, (symbol, current_date))

                price_result = self.cur.fetchone()
                if not price_result:
                    continue

                current_price = float(price_result[0])
                days_held = (current_date - trade_date).days

                # Check exit conditions
                exit_signal = self._check_exit_conditions(
                    symbol, current_price, entry_price, qty,
                    t1, t2, t3, stop, days_held, current_date
                )

                if exit_signal:
                    print(f"{symbol}: {exit_signal['reason']}")

                    # Execute exit
                    result = self.executor.exit_trade(
                        trade_id, current_price, exit_signal['reason']
                    )

                    if result['success']:
                        exits_executed += 1
                        print(f"  Exited: {result['message']}\n")
                    else:
                        print(f"  Exit failed: {result['message']}\n")

            print(f"{'='*70}")
            print(f"Exits executed: {exits_executed}/{len(trades)}")
            print(f"{'='*70}\n")

            return exits_executed

        except Exception as e:
            print(f"Error in exit engine: {e}")
            return 0
        finally:
            self.disconnect()

    def _check_exit_conditions(self, symbol, current_price, entry_price, qty,
                               t1_price, t2_price, t3_price, stop_price, days_held, eval_date):
        """Check all exit conditions for a position."""

        # 1. Check stops first
        if current_price <= stop_price:
            return {
                'reason': f'STOP: {current_price:.2f} <= {stop_price:.2f}',
                'exit_stage': 'stop'
            }

        # 2. Check max hold time
        max_hold = self.config.get('max_hold_days', 20)
        if days_held >= max_hold:
            return {
                'reason': f'TIME: {days_held} days >= {max_hold} day limit',
                'exit_stage': 'time'
            }

        # 3. Check T3 target (4R) - hard exit
        if current_price >= t3_price:
            return {
                'reason': f'T3: {current_price:.2f} >= {t3_price:.2f} (4R target)',
                'exit_stage': 'target_3'
            }

        # 4. Check T2 target (3R) - conditional exit on pullback
        if current_price >= t2_price:
            # Check if pulling back from T3
            if self._is_pulling_back(symbol, eval_date, current_price, t3_price):
                return {
                    'reason': f'T2: {current_price:.2f} >= {t2_price:.2f} (3R pullback)',
                    'exit_stage': 'target_2'
                }

        # 5. Check T1 target (1.5R) - exit on pullback
        if current_price >= t1_price:
            if self._is_pulling_back(symbol, eval_date, current_price, t2_price):
                return {
                    'reason': f'T1: {current_price:.2f} >= {t1_price:.2f} (1.5R pullback)',
                    'exit_stage': 'target_1'
                }

        # 6. Check distribution days
        self.cur.execute("""
            SELECT distribution_days_4w FROM market_health_daily
            WHERE date <= %s
            ORDER BY date DESC LIMIT 1
        """, (eval_date,))

        dist_result = self.cur.fetchone()
        if dist_result and dist_result[0]:
            max_dist = self.config.get('max_distribution_days', 4)
            if dist_result[0] > max_dist:
                exit_on_dist = self.config.get('exit_on_distribution_day', True)
                if exit_on_dist:
                    return {
                        'reason': f'DIST: {dist_result[0]} distribution days',
                        'exit_stage': 'distribution'
                    }

        # No exit condition
        return None

    def _is_pulling_back(self, symbol, eval_date, current_price, previous_high):
        """Check if price is pulling back from a higher level."""
        try:
            # Get last 5 days of closes
            self.cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = %s
                AND date >= %s::date - INTERVAL '5 days'
                AND date <= %s
                ORDER BY date DESC
                LIMIT 5
            """, (symbol, eval_date, eval_date))

            prices = [float(r[0]) for r in self.cur.fetchall()]

            if len(prices) < 2:
                return False

            # Pullback if current < previous high
            return current_price < max(prices[1:])

        except:
            return False

if __name__ == "__main__":
    from algo_config import get_config

    config = get_config()
    engine = ExitEngine(config)

    # Test exit checking
    exits = engine.check_and_execute_exits()
    print(f"Test complete: {exits} exits checked")
