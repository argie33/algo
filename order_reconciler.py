#!/usr/bin/env python3
"""
Continuous Order Reconciliation - Sync local orders with Alpaca

Problem:
  - Algo places order, marks as PENDING in DB
  - Alpaca fills the order
  - But we don't know it's filled until end-of-day reconciliation
  - If order is orphaned (API lost response), we never know

Solution:
  - Periodic checks: compare local orders vs Alpaca reality
  - Detect: discrepancies (local pending, Alpaca filled), stuck orders, orphaned orders
  - Alert: when issues found
  - Recover: manual override or auto-cancel

Run continuous (every 5 min):
  python3 order_reconciler.py --check

Manual override:
  python3 order_reconciler.py --cancel-order <order_id> <symbol>
  python3 order_reconciler.py --force-sell <symbol> <quantity>
"""

import logging
import os
import psycopg2
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

from credential_manager import get_credential_manager
from structured_logger import get_logger, set_trace_id

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = get_logger(__name__)
credential_manager = get_credential_manager()

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class OrderStatus(Enum):
    """Order states (from Alpaca)."""
    PENDING_NEW = "pending_new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"


class DiscrepancyType(Enum):
    """Types of discrepancies found."""
    ORPHANED = "orphaned"  # Local pending, Alpaca says doesn't exist
    FILLED_UNKNOWN = "filled_unknown"  # Local pending, Alpaca says filled
    PARTIAL_FILL = "partial_fill"  # Partial fill not updated locally
    STUCK = "stuck"  # Order pending >30 min (shouldn't be)
    CONFLICTING = "conflicting"  # Local says X, Alpaca says Y


class OrderReconciler:
    """Reconcile local orders with Alpaca reality."""

    def __init__(self):
        self.conn = None
        self.alpaca_client = None
        self.discrepancies: List[Dict[str, Any]] = []

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**_get_db_config())

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_alpaca(self):
        """Initialize Alpaca client."""
        if self.alpaca_client is None:
            try:
                from alpaca_trade_api import REST
                api_key = credential_manager.get_alpaca_credentials()['key']
                api_secret = credential_manager.get_alpaca_credentials()['secret']
                self.alpaca_client = REST(
                    key_id=api_key,
                    secret_key=api_secret,
                    base_url='https://paper-api.alpaca.markets'
                )
            except ImportError:
                logger.warning("alpaca-trade-api not installed; reconciliation disabled")
                self.alpaca_client = False

    def reconcile_all(self) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Reconcile all pending orders with Alpaca.

        Returns:
            (discrepancy_count, discrepancies)
        """
        self.connect()
        self.init_alpaca()

        if not self.alpaca_client:
            logger.warning("Alpaca client not available; skipping reconciliation")
            return 0, []

        self.discrepancies = []

        # Get all pending orders from local DB
        local_pending = self._get_pending_orders()
        logger.info(f"Found {len(local_pending)} pending orders locally")

        if not local_pending:
            logger.info("No pending orders to reconcile")
            return 0, []

        # Get all orders from Alpaca
        try:
            alpaca_orders = self.alpaca_client.list_orders(status='all')
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca orders: {e}")
            return 0, []

        # Index by order ID for quick lookup
        alpaca_by_id = {str(o.id): o for o in alpaca_orders}

        # Check each local pending order
        for local_order in local_pending:
            self._check_order(local_order, alpaca_by_id)

        # Check for orphaned orders (in Alpaca but not local)
        self._check_orphaned_orders(local_pending, alpaca_by_id)

        # Log findings
        logger.info(f"Reconciliation complete: {len(self.discrepancies)} discrepancies found")
        for disc in self.discrepancies:
            logger.warning(f"  [{disc['type']}] {disc['symbol']} - {disc['message']}")

        return len(self.discrepancies), self.discrepancies

    def _get_pending_orders(self) -> List[Dict[str, Any]]:
        """Get all locally pending orders."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id, symbol, side, shares, entry_price,
                        alpaca_order_id, status, created_at,
                        EXTRACT(EPOCH FROM (NOW() - created_at)) as age_seconds
                    FROM algo_trades
                    WHERE status IN ('PENDING', 'PARTIALLY_FILLED')
                    AND created_at >= NOW() - INTERVAL '1 day'
                    ORDER BY created_at DESC
                """)

                columns = [desc[0] for desc in cur.description]
                orders = []
                for row in cur.fetchall():
                    orders.append(dict(zip(columns, row)))
                return orders

        except Exception as e:
            logger.error(f"Failed to get pending orders: {e}")
            return []

    def _check_order(self, local_order: Dict[str, Any], alpaca_by_id: Dict[str, Any]):
        """Check if a local order matches Alpaca state."""
        order_id = local_order['alpaca_order_id']
        if not order_id:
            # No Alpaca order ID recorded — this shouldn't happen
            self.discrepancies.append({
                'type': DiscrepancyType.ORPHANED.value,
                'symbol': local_order['symbol'],
                'message': f"Local order has no Alpaca order ID (DB ID: {local_order['id']})",
                'local_order': local_order,
                'alpaca_order': None,
            })
            return

        alpaca_order = alpaca_by_id.get(str(order_id))
        if not alpaca_order:
            # Local says pending, Alpaca says doesn't exist → orphaned
            age_minutes = local_order['age_seconds'] / 60
            self.discrepancies.append({
                'type': DiscrepancyType.ORPHANED.value,
                'symbol': local_order['symbol'],
                'message': f"Order {order_id} not found in Alpaca (pending {age_minutes:.0f} min)",
                'local_order': local_order,
                'alpaca_order': None,
            })
            return

        # Order exists in Alpaca — check status
        alpaca_status = alpaca_order.status

        if alpaca_status == 'filled' and local_order['status'] == 'PENDING':
            # Alpaca filled, but we didn't know
            self.discrepancies.append({
                'type': DiscrepancyType.FILLED_UNKNOWN.value,
                'symbol': local_order['symbol'],
                'message': f"Order filled in Alpaca but local says pending",
                'local_order': local_order,
                'alpaca_order': {
                    'status': alpaca_status,
                    'filled_qty': alpaca_order.filled_qty,
                    'filled_avg_price': alpaca_order.filled_avg_price,
                },
            })
            return

        if alpaca_status == 'partially_filled':
            # Partial fill — ensure we know about it
            if alpaca_order.filled_qty and alpaca_order.filled_qty > 0:
                self.discrepancies.append({
                    'type': DiscrepancyType.PARTIAL_FILL.value,
                    'symbol': local_order['symbol'],
                    'message': f"Partial fill: {alpaca_order.filled_qty}/{local_order['shares']} shares",
                    'local_order': local_order,
                    'alpaca_order': {
                        'status': alpaca_status,
                        'filled_qty': alpaca_order.filled_qty,
                        'filled_avg_price': alpaca_order.filled_avg_price,
                    },
                })

        if alpaca_status in ['pending_new', 'accepted']:
            # Still pending in Alpaca — check if stuck (>30 min old)
            age_minutes = local_order['age_seconds'] / 60
            if age_minutes > 30:
                self.discrepancies.append({
                    'type': DiscrepancyType.STUCK.value,
                    'symbol': local_order['symbol'],
                    'message': f"Order stuck for {age_minutes:.0f} minutes",
                    'local_order': local_order,
                    'alpaca_order': {'status': alpaca_status},
                })

    def _check_orphaned_orders(self, local_orders: List[Dict[str, Any]], alpaca_by_id: Dict[str, Any]):
        """Check for orders in Alpaca that aren't in our local DB."""
        # Get all local order IDs
        local_ids = {str(o['alpaca_order_id']) for o in local_orders if o['alpaca_order_id']}

        # Check each Alpaca order
        for order_id, alpaca_order in alpaca_by_id.items():
            if order_id not in local_ids and alpaca_order.status in ['partially_filled', 'filled']:
                # Filled order that we don't have locally — shouldn't happen, but flag it
                logger.warning(f"Alpaca order {order_id} not found locally but is filled")

    def update_from_alpaca(self, discrepancy: Dict[str, Any]) -> bool:
        """
        Update local order based on Alpaca state.

        Used for FILLED_UNKNOWN or PARTIAL_FILL discrepancies.
        """
        local_order = discrepancy['local_order']
        alpaca_order = discrepancy['alpaca_order']

        try:
            self.connect()
            with self.conn.cursor() as cur:
                if discrepancy['type'] == DiscrepancyType.FILLED_UNKNOWN.value:
                    # Mark as filled
                    cur.execute("""
                        UPDATE algo_trades
                        SET status = 'FILLED',
                            exit_price = %s,
                            exit_date = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                    """, (alpaca_order.get('filled_avg_price'), local_order['id']))

                elif discrepancy['type'] == DiscrepancyType.PARTIAL_FILL.value:
                    # Update partial fill
                    cur.execute("""
                        UPDATE algo_trades
                        SET status = 'PARTIALLY_FILLED',
                            exit_price = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (alpaca_order.get('filled_avg_price'), local_order['id']))

                self.conn.commit()
                logger.info(f"Updated {local_order['symbol']} order to {discrepancy['type']}")
                return True

        except Exception as e:
            logger.error(f"Failed to update order: {e}")
            return False

    def cancel_order(self, symbol: str, alpaca_order_id: str) -> bool:
        """
        Cancel a stuck order in Alpaca and mark locally as cancelled.
        """
        if not self.alpaca_client:
            logger.error("Alpaca client not available")
            return False

        try:
            # Cancel in Alpaca
            self.alpaca_client.cancel_order(alpaca_order_id)
            logger.info(f"Cancelled {symbol} order {alpaca_order_id} in Alpaca")

            # Mark locally as cancelled
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE algo_trades
                    SET status = 'CANCELLED',
                        exit_reason = 'Manual cancellation - stuck order',
                        exit_date = NOW(),
                        updated_at = NOW()
                    WHERE alpaca_order_id = %s
                """, (alpaca_order_id,))
                self.conn.commit()

            logger.info(f"Marked {symbol} order as cancelled locally")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    def force_sell(self, symbol: str, quantity: int) -> Optional[str]:
        """
        Force-sell a position immediately (bypass normal exit logic).

        Returns: Alpaca order ID if successful, None if failed
        """
        if not self.alpaca_client:
            logger.error("Alpaca client not available")
            return None

        try:
            # Market sell order
            order = self.alpaca_client.submit_order(
                symbol=symbol,
                qty=quantity,
                side='sell',
                type='market',
                time_in_force='day'
            )
            logger.info(f"Force-sold {quantity} {symbol} - Order ID: {order.id}")

            # Log in audit trail
            logger.info("Force sell executed", extra={
                "symbol": symbol,
                "quantity": quantity,
                "order_id": order.id,
                "reason": "Manual override - stuck order recovery",
            })

            return str(order.id)

        except Exception as e:
            logger.error(f"Failed to force-sell {symbol}: {e}")
            return None


# Singleton
_reconciler = None


def get_reconciler() -> OrderReconciler:
    """Get singleton reconciler."""
    global _reconciler
    if _reconciler is None:
        _reconciler = OrderReconciler()
    return _reconciler


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Order reconciliation")
    parser.add_argument('--check', action='store_true', help='Check all pending orders')
    parser.add_argument('--cancel-order', nargs=2, metavar=('SYMBOL', 'ORDER_ID'),
                        help='Cancel a stuck order')
    parser.add_argument('--force-sell', nargs=2, metavar=('SYMBOL', 'QUANTITY'),
                        help='Force-sell a position')

    args = parser.parse_args()

    set_trace_id(f"RECON-{datetime.now().strftime('%Y%m%d-%H%M%S')}")

    reconciler = get_reconciler()

    if args.check:
        count, discs = reconciler.reconcile_all()
        if discs:
            logger.warning(f"\nFound {count} discrepancies:")
            for disc in discs:
                logger.warning(f"  {disc['type']}: {disc['symbol']} - {disc['message']}")
        else:
            logger.info("All orders reconciled ✓")

    elif args.cancel_order:
        symbol, order_id = args.cancel_order
        reconciler.cancel_order(symbol, order_id)

    elif args.force_sell:
        symbol, quantity = args.force_sell
        order_id = reconciler.force_sell(symbol, int(quantity))
        if order_id:
            logger.info(f"Force-sell successful: {order_id}")
        else:
            logger.error("Force-sell failed")

    reconciler.disconnect()
