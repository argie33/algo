#!/usr/bin/env python3
"""
Order Execution Audit Trail

Tracks every order attempt:
- Pre-execution: What are we about to trade?
- Execution: Did the order fill?
- Post-execution: What was the slippage?

Enables:
- Pre-execution dashboard (show 3 trades, approve before submitting)
- Order audit trail (why did this order reject?)
- Fill quality analysis (avg slippage %, fill rate)
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import logging
from typing import List, Dict, Optional

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class OrderExecutionTracker:
    """Track order execution for audit and quality analysis."""

    def __init__(self, config=None):
        self.config = config or {}
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def log_order_attempt(self, trade_id: int, symbol: str, order_type: str,
                          side: str, requested_shares: int, requested_price: float,
                          alpaca_order_id: str):
        """
        Log a new order being sent to Alpaca.

        Args:
            trade_id: Reference to algo_trades.id
            symbol: Stock symbol
            order_type: 'entry', 'exit_t1', 'exit_t2', 'exit_t3'
            side: 'BUY' or 'SELL'
            requested_shares: Number of shares
            requested_price: Limit price
            alpaca_order_id: Alpaca order ID from API response
        """
        self.connect()

        try:
            # Count existing attempts for this trade + type to get sequence number
            self.cur.execute("""
                SELECT COUNT(*) FROM order_execution_log
                WHERE trade_id = %s AND order_type = %s
            """, (trade_id, order_type))
            attempt_num = (self.cur.fetchone()[0] or 0) + 1

            self.cur.execute("""
                INSERT INTO order_execution_log
                (trade_id, symbol, order_sequence_num, order_timestamp, order_type,
                 side, requested_shares, requested_price, order_status, alpaca_order_id, retry_count)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, 'pending', %s, 0)
            """, (trade_id, symbol, attempt_num, order_type, side, requested_shares,
                  requested_price, alpaca_order_id))

            self.conn.commit()
            log.info(f"Logged order: {symbol} {side} {requested_shares}sh @ ${requested_price:.2f}")

        except Exception as e:
            log.error(f"Failed to log order attempt: {e}")
            self.conn.rollback()

        finally:
            self.disconnect()

    def log_order_fill(self, alpaca_order_id: str, filled_shares: int,
                       filled_price: float, status: str, rejection_reason: Optional[str] = None):
        """
        Log order result (filled, partial, rejected, etc.).

        Args:
            alpaca_order_id: Alpaca order ID
            filled_shares: Number of shares actually filled
            filled_price: Actual execution price
            status: 'filled', 'partial', 'rejected', 'cancelled', etc.
            rejection_reason: Reason if rejected
        """
        self.connect()

        try:
            # Fetch original order request
            self.cur.execute("""
                SELECT id, requested_price, requested_shares, side, trade_id
                FROM order_execution_log
                WHERE alpaca_order_id = %s
                ORDER BY id DESC LIMIT 1
            """, (alpaca_order_id,))

            order = self.cur.fetchone()
            if not order:
                log.warning(f"Order {alpaca_order_id} not found in log")
                self.disconnect()
                return

            order_id, req_price, req_shares, side, trade_id = order

            # Calculate fill metrics
            fill_rate = (filled_shares / req_shares * 100) if req_shares > 0 else 0
            if side == 'BUY':
                # For buy: adverse if filled_price > requested (paid more)
                slippage_bps = ((filled_price - req_price) / req_price * 10000) if req_price > 0 else 0
            else:
                # For sell: adverse if filled_price < requested (got less)
                slippage_bps = ((req_price - filled_price) / req_price * 10000) if req_price > 0 else 0

            # Update order log
            self.cur.execute("""
                UPDATE order_execution_log SET
                    order_status = %s,
                    filled_shares = %s,
                    filled_price = %s,
                    fill_rate_pct = %s,
                    slippage_bps = %s,
                    rejection_reason = %s
                WHERE alpaca_order_id = %s
            """, (status, filled_shares, filled_price, fill_rate, slippage_bps,
                  rejection_reason, alpaca_order_id))

            self.conn.commit()

            # Alert if slippage excessive (>300 bps = 3%)
            if abs(slippage_bps) > 300:
                log.warning(f"High slippage on {alpaca_order_id}: {slippage_bps:.0f}bps "
                           f"({side} {filled_shares}sh @ ${filled_price:.2f}, "
                           f"expected ${req_price:.2f})")

            log.info(f"Filled order: {alpaca_order_id} {status} "
                    f"{filled_shares}/{req_shares}sh @ ${filled_price:.2f} "
                    f"(slippage {slippage_bps:.0f}bps)")

        except Exception as e:
            log.error(f"Failed to log order fill: {e}")
            self.conn.rollback()

        finally:
            self.disconnect()

    def get_pending_orders(self) -> List[Dict]:
        """
        Fetch all pending/submitted orders (for pre-execution review dashboard).

        Returns:
            list of dicts with: symbol, order_type, side, requested_shares, requested_price,
                               order_timestamp, trade_id
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT id, trade_id, symbol, order_type, side, requested_shares,
                       requested_price, order_timestamp
                FROM order_execution_log
                WHERE order_status IN ('pending', 'submitted')
                ORDER BY order_timestamp DESC
                LIMIT 10
            """)

            orders = []
            for row in self.cur.fetchall():
                orders.append({
                    'order_id': row[0],
                    'trade_id': row[1],
                    'symbol': row[2],
                    'order_type': row[3],
                    'side': row[4],
                    'requested_shares': row[5],
                    'requested_price': float(row[6]),
                    'order_timestamp': row[7].isoformat() if row[7] else None,
                })

            return orders

        except Exception as e:
            log.error(f"Failed to get pending orders: {e}")
            return []

        finally:
            self.disconnect()

    def get_execution_quality_metrics(self, days: int = 30) -> Dict:
        """
        Summary: fill rate, avg slippage, rejection count.

        Args:
            days: Look back N days

        Returns:
            dict with: total_orders, filled, rejected, fill_rate_pct, avg_slippage_bps
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN order_status = 'filled' THEN 1 ELSE 0 END) as filled,
                    SUM(CASE WHEN order_status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                    SUM(CASE WHEN order_status = 'partial' THEN 1 ELSE 0 END) as partial,
                    AVG(fill_rate_pct) as avg_fill_rate,
                    AVG(ABS(slippage_bps)) as avg_slippage_bps,
                    MAX(ABS(slippage_bps)) as max_slippage_bps
                FROM order_execution_log
                WHERE order_timestamp >= NOW() - INTERVAL %s
            """, (f'{days} days',))

            row = self.cur.fetchone()
            if not row:
                return {
                    'total_orders': 0,
                    'filled': 0,
                    'rejected': 0,
                    'partial': 0,
                    'fill_rate_pct': None,
                    'avg_slippage_bps': None,
                    'max_slippage_bps': None,
                }

            return {
                'total_orders': row[0] or 0,
                'filled': row[1] or 0,
                'rejected': row[2] or 0,
                'partial': row[3] or 0,
                'fill_rate_pct': round(row[4], 2) if row[4] else None,
                'avg_slippage_bps': round(row[5], 2) if row[5] else None,
                'max_slippage_bps': round(row[6], 2) if row[6] else None,
            }

        except Exception as e:
            log.error(f"Failed to get execution quality metrics: {e}")
            return {}

        finally:
            self.disconnect()

    def get_recent_orders(self, limit: int = 20) -> List[Dict]:
        """
        Get recent orders (filled, rejected, etc.) for order history.

        Args:
            limit: Maximum number of orders to return

        Returns:
            list of dicts with full order details
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT id, symbol, order_type, side, requested_shares, requested_price,
                       filled_shares, filled_price, order_status, slippage_bps,
                       order_timestamp, rejection_reason
                FROM order_execution_log
                WHERE order_status IN ('filled', 'rejected', 'partial', 'cancelled')
                ORDER BY order_timestamp DESC
                LIMIT %s
            """, (limit,))

            orders = []
            for row in self.cur.fetchall():
                orders.append({
                    'order_id': row[0],
                    'symbol': row[1],
                    'order_type': row[2],
                    'side': row[3],
                    'requested_shares': row[4],
                    'requested_price': float(row[5]),
                    'filled_shares': row[6],
                    'filled_price': float(row[7]) if row[7] else None,
                    'status': row[8],
                    'slippage_bps': float(row[9]) if row[9] else None,
                    'timestamp': row[10].isoformat() if row[10] else None,
                    'rejection_reason': row[11],
                })

            return orders

        except Exception as e:
            log.error(f"Failed to get recent orders: {e}")
            return []

        finally:
            self.disconnect()
