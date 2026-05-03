#!/usr/bin/env python3
"""
Trade Executor - Execute trades via Alpaca and track positions

Handles:
- Sending orders to Alpaca
- Creating algo_trades records
- Creating algo_positions
- Handling fills and executions
- Order status tracking
"""

import os
import psycopg2
import uuid
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import requests
import base64

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

class TradeExecutor:
    """Execute trades via Alpaca and track in database."""

    def __init__(self, config):
        self.config = config
        self.alpaca_key = os.getenv('APCA_API_KEY_ID')
        self.alpaca_secret = os.getenv('APCA_API_SECRET_KEY')
        self.alpaca_base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
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

    def execute_trade(self, symbol, entry_price, shares, stop_loss_price,
                     target_1_price, target_2_price, target_3_price, signal_date):
        """
        Execute a new trade:
        1. Create order in Alpaca
        2. Create algo_trades record
        3. Create algo_positions record
        4. Calculate P&L targets

        Returns: {
            'success': bool,
            'trade_id': str,
            'alpaca_order_id': str,
            'status': str,
            'message': str
        }
        """
        self.connect()

        try:
            execution_mode = self.config.get('execution_mode', 'paper')
            trade_id = str(uuid.uuid4())[:8]

            # In 'paper' or 'dry' mode, create order without hitting Alpaca
            if execution_mode in ('paper', 'dry', 'review'):
                alpaca_order_id = f'LOCAL-{trade_id}'
                order_status = 'filled'
                executed_price = entry_price

                if execution_mode == 'review':
                    order_status = 'pending_review'

            else:
                # Send to Alpaca
                order_result = self._send_alpaca_order(
                    symbol, shares, entry_price, stop_loss_price
                )

                if not order_result['success']:
                    return {
                        'success': False,
                        'trade_id': trade_id,
                        'status': 'failed',
                        'message': order_result.get('message', 'Order failed')
                    }

                alpaca_order_id = order_result['order_id']
                order_status = order_result.get('status', 'pending')
                executed_price = order_result.get('executed_price', entry_price)

            # Create algo_trades record
            self.cur.execute("""
                INSERT INTO algo_trades (
                    trade_id, symbol, signal_date, trade_date,
                    entry_price, entry_quantity, entry_reason,
                    stop_loss_price, stop_loss_method,
                    target_1_price, target_1_r_multiple,
                    target_2_price, target_2_r_multiple,
                    target_3_price, target_3_r_multiple,
                    status, execution_mode, alpaca_order_id,
                    position_size_pct, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
            """, (
                trade_id, symbol, signal_date, datetime.now().date(),
                executed_price, shares, 'Algo signal qualified',
                stop_loss_price, 'minervini_break',
                target_1_price, 1.5,
                target_2_price, 3.0,
                target_3_price, 4.0,
                order_status, execution_mode, alpaca_order_id,
                (shares * executed_price / 100000), # placeholder
            ))

            # Create algo_positions record if filled
            if order_status == 'filled':
                position_id = f'POS-{trade_id}'
                position_value = shares * executed_price

                self.cur.execute("""
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price,
                        current_price, position_value, status,
                        trade_ids, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                """, (
                    position_id, symbol, shares, executed_price,
                    executed_price, position_value, 'open', trade_id
                ))

            self.conn.commit()

            return {
                'success': True,
                'trade_id': trade_id,
                'alpaca_order_id': alpaca_order_id,
                'status': order_status,
                'message': f'{shares} shares of {symbol} @ ${executed_price:.2f}'
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            return {
                'success': False,
                'trade_id': str(uuid.uuid4())[:8],
                'status': 'error',
                'message': str(e)
            }
        finally:
            self.disconnect()

    def _send_alpaca_order(self, symbol, shares, entry_price, stop_loss_price):
        """Send order to Alpaca API."""
        try:
            if not self.alpaca_key or not self.alpaca_secret:
                return {
                    'success': False,
                    'message': 'Alpaca credentials not configured'
                }

            # Create order
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret
            }

            order_data = {
                'symbol': symbol,
                'qty': shares,
                'side': 'buy',
                'type': 'limit',
                'time_in_force': 'day',
                'limit_price': str(entry_price),
                'stop_price': str(stop_loss_price) if stop_loss_price else None,
                'trail_price': None
            }

            response = requests.post(
                f'{self.alpaca_base_url}/v2/orders',
                json=order_data,
                headers=headers,
                timeout=10
            )

            if response.status_code in (200, 201):
                data = response.json()
                return {
                    'success': True,
                    'order_id': data.get('id', 'unknown'),
                    'status': data.get('status', 'pending'),
                    'executed_price': entry_price
                }
            else:
                return {
                    'success': False,
                    'message': f'Alpaca error: {response.status_code} {response.text}'
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'Request failed: {str(e)}'
            }

    def exit_trade(self, trade_id, exit_price, exit_reason):
        """
        Exit a position:
        1. Send exit order to Alpaca
        2. Update algo_trades with exit info
        3. Close position in algo_positions
        """
        self.connect()

        try:
            # Get trade info
            self.cur.execute("""
                SELECT symbol, entry_quantity, entry_price
                FROM algo_trades
                WHERE trade_id = %s
            """, (trade_id,))

            trade = self.cur.fetchone()
            if not trade:
                return {'success': False, 'message': 'Trade not found'}

            symbol, shares, entry_price = trade
            profit_loss_pct = ((exit_price - entry_price) / entry_price * 100)
            profit_loss_dollars = (exit_price - entry_price) * shares
            r_multiple = (exit_price - entry_price) / (entry_price - (entry_price * 0.05))  # simplified

            # Update trade
            self.cur.execute("""
                UPDATE algo_trades
                SET exit_date = CURRENT_DATE,
                    exit_price = %s,
                    exit_reason = %s,
                    exit_r_multiple = %s,
                    profit_loss_dollars = %s,
                    profit_loss_pct = %s,
                    status = 'closed'
                WHERE trade_id = %s
            """, (exit_price, exit_reason, r_multiple, profit_loss_dollars, profit_loss_pct, trade_id))

            # Close position
            self.cur.execute("""
                UPDATE algo_positions
                SET status = 'closed',
                    closed_at = CURRENT_TIMESTAMP
                WHERE trade_ids LIKE %s
            """, (f'%{trade_id}%',))

            self.conn.commit()

            return {
                'success': True,
                'trade_id': trade_id,
                'profit_loss': profit_loss_dollars,
                'profit_loss_pct': profit_loss_pct,
                'message': f'Exited {symbol} @ ${exit_price:.2f}: {profit_loss_pct:+.2f}%'
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            return {
                'success': False,
                'message': str(e)
            }
        finally:
            self.disconnect()

if __name__ == "__main__":
    from algo_config import get_config

    config = get_config()
    executor = TradeExecutor(config)

    # Test execution
    result = executor.execute_trade(
        symbol='AAPL',
        entry_price=150.00,
        shares=100,
        stop_loss_price=142.50,
        target_1_price=157.50,
        target_2_price=165.00,
        target_3_price=170.00,
        signal_date='2026-05-03'
    )

    print(f"Trade Execution Test:")
    print(f"  Success: {result['success']}")
    print(f"  Trade ID: {result['trade_id']}")
    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
