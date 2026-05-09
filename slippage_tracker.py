#!/usr/bin/env python3
"""
Slippage Tracking - Measure order execution quality

Slippage = (Expected Fill Price - Actual Fill Price)

For BUY orders:
  - Expected: signal entry price or last market price
  - Actual: price we actually filled at
  - Negative slippage (filled at lower price) = GOOD

For SELL orders:
  - Expected: last market price or target
  - Actual: price we filled at
  - Positive slippage (filled at higher price) = GOOD

Tracks:
- Per-symbol average slippage
- Slippage as % of price
- Alerts if slippage is bad
"""

import logging
import os
import psycopg2
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

from credential_manager import get_credential_manager
from structured_logger import get_logger

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = get_logger(__name__)
credential_manager = get_credential_manager()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}


class SlippageTracker:
    """Track order execution slippage."""

    def __init__(self):
        self.conn = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**DB_CONFIG)

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def record_slippage(
        self,
        symbol: str,
        side: str,  # 'BUY' or 'SELL'
        expected_price: float,
        actual_price: float,
        quantity: int,
        order_id: str,
    ) -> bool:
        """
        Record slippage for a filled order.

        Args:
            symbol: Stock symbol
            side: 'BUY' or 'SELL'
            expected_price: Expected fill price
            actual_price: Actual fill price
            quantity: Shares filled
            order_id: Alpaca order ID

        Returns:
            True if recorded successfully
        """
        # Calculate slippage
        if side.upper() == 'BUY':
            # For buys, negative slippage is good (filled cheaper)
            slippage = actual_price - expected_price
        else:  # SELL
            # For sells, positive slippage is good (filled higher)
            slippage = expected_price - actual_price

        slippage_pct = (slippage / expected_price * 100) if expected_price > 0 else 0

        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO order_slippage
                    (symbol, side, expected_price, actual_price, slippage, slippage_pct,
                     quantity, alpaca_order_id, recorded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    symbol,
                    side.upper(),
                    expected_price,
                    actual_price,
                    slippage,
                    slippage_pct,
                    quantity,
                    order_id,
                ))
                self.conn.commit()

                logger.info("Slippage recorded", extra={
                    "symbol": symbol,
                    "side": side,
                    "expected_price": expected_price,
                    "actual_price": actual_price,
                    "slippage": slippage,
                    "slippage_pct": slippage_pct,
                })

                return True

        except Exception as e:
            logger.error(f"Failed to record slippage: {e}")
            return False

    def get_daily_slippage(self, target_date: date) -> Dict[str, Any]:
        """Get slippage statistics for a date."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                # Overall stats
                cur.execute("""
                    SELECT
                        COUNT(*) as trade_count,
                        AVG(slippage) as avg_slippage,
                        AVG(ABS(slippage_pct)) as avg_slippage_pct,
                        MIN(slippage) as best_slippage,
                        MAX(slippage) as worst_slippage,
                        SUM(slippage * quantity) as total_slippage_impact
                    FROM order_slippage
                    WHERE DATE(recorded_at) = %s
                """, (target_date,))

                row = cur.fetchone()
                if not row or row[0] == 0:
                    return {}

                cols = ['trade_count', 'avg_slippage', 'avg_slippage_pct',
                        'best_slippage', 'worst_slippage', 'total_slippage_impact']
                overall = dict(zip(cols, row))

                # Per-symbol stats
                cur.execute("""
                    SELECT
                        symbol,
                        COUNT(*) as count,
                        AVG(slippage) as avg_slippage,
                        AVG(ABS(slippage_pct)) as avg_slippage_pct
                    FROM order_slippage
                    WHERE DATE(recorded_at) = %s
                    GROUP BY symbol
                    ORDER BY AVG(slippage) DESC
                """, (target_date,))

                per_symbol = {}
                for row in cur.fetchall():
                    symbol, count, avg_slip, avg_slip_pct = row
                    per_symbol[symbol] = {
                        'count': count,
                        'avg_slippage': avg_slip,
                        'avg_slippage_pct': avg_slip_pct,
                    }

                return {
                    'overall': overall,
                    'per_symbol': per_symbol,
                }

        except Exception as e:
            logger.error(f"Failed to get slippage stats: {e}")
            return {}

    def get_worst_slippage(self, target_date: date, limit: int = 5) -> List[Dict[str, Any]]:
        """Get worst slippage trades for a date."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        symbol, side, expected_price, actual_price, slippage, slippage_pct,
                        quantity, recorded_at
                    FROM order_slippage
                    WHERE DATE(recorded_at) = %s
                    ORDER BY ABS(slippage_pct) DESC
                    LIMIT %s
                """, (target_date, limit))

                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

        except Exception as e:
            logger.error(f"Failed to get worst slippage: {e}")
            return []

    def print_slippage_report(self, target_date: date):
        """Print slippage report for a date."""
        stats = self.get_daily_slippage(target_date)

        if not stats:
            logger.info(f"No slippage data for {target_date}")
            return

        overall = stats.get('overall', {})
        per_symbol = stats.get('per_symbol', {})

        logger.info(f"\n{'='*80}")
        logger.info(f"SLIPPAGE REPORT - {target_date}")
        logger.info(f"{'='*80}")

        logger.info(f"\nOverall Statistics:")
        logger.info(f"  Trades: {overall.get('trade_count', 0)}")
        logger.info(f"  Avg Slippage: ${overall.get('avg_slippage', 0):.4f}")
        logger.info(f"  Avg Slippage %: {overall.get('avg_slippage_pct', 0):.3f}%")
        logger.info(f"  Best Trade: ${overall.get('best_slippage', 0):.4f}")
        logger.info(f"  Worst Trade: ${overall.get('worst_slippage', 0):.4f}")
        logger.info(f"  Total Impact: ${overall.get('total_slippage_impact', 0):.2f}")

        if per_symbol:
            logger.info(f"\nPer-Symbol Breakdown:")
            for symbol, stats in per_symbol.items():
                logger.info(f"  {symbol}: {stats['count']} trades, "
                           f"avg ${stats['avg_slippage']:.4f} "
                           f"({stats['avg_slippage_pct']:.3f}%)")

        worst = self.get_worst_slippage(target_date, 3)
        if worst:
            logger.info(f"\nWorst Fills:")
            for trade in worst:
                logger.info(f"  {trade['symbol']} {trade['side']}: "
                           f"Expected ${trade['expected_price']:.2f}, "
                           f"Filled ${trade['actual_price']:.2f}, "
                           f"Slippage ${trade['slippage']:.4f} ({trade['slippage_pct']:.3f}%)")


# Create database table if needed
def create_slippage_table():
    """Create order_slippage table."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_slippage (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    side VARCHAR(5) NOT NULL,  -- BUY or SELL
                    expected_price FLOAT NOT NULL,
                    actual_price FLOAT NOT NULL,
                    slippage FLOAT NOT NULL,  -- Actual - Expected (or reverse for sells)
                    slippage_pct FLOAT NOT NULL,  -- As % of expected price
                    quantity INT NOT NULL,
                    alpaca_order_id VARCHAR(50),
                    recorded_at TIMESTAMP DEFAULT NOW(),

                    INDEX (symbol),
                    INDEX (recorded_at DESC)
                )
            """)
            conn.commit()
            conn.close()
            logger.info("Slippage table created")
    except Exception as e:
        logger.error(f"Failed to create slippage table: {e}")


# Singleton
_tracker = None


def get_slippage_tracker() -> SlippageTracker:
    """Get singleton tracker."""
    global _tracker
    if _tracker is None:
        _tracker = SlippageTracker()
    return _tracker


if __name__ == "__main__":
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="Slippage tracking")
    parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD), default today')
    parser.add_argument('--create-table', action='store_true', help='Create slippage table')

    args = parser.parse_args()

    if args.create_table:
        create_slippage_table()
    else:
        target_date = date.today()
        if args.date:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()

        tracker = get_slippage_tracker()
        tracker.print_slippage_report(target_date)
        tracker.disconnect()
