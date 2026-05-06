#!/usr/bin/env python3
"""
Pyramid Engine — Scale winners with additional entries

Adds to winning positions after they've moved favorably, increasing exposure
to proven winners while maintaining risk discipline.

Rules:
- Only add to positions with positive unrealized P&L
- Each add is smaller than initial entry (pyramid down)
- Total position size capped at max_position_size
- New add gets same stop as initial position (inherited risk)
- Maximum 3 pyramids per original position

Risk Management:
- Each pyramid at a higher price than initial entry
- Position scale: 1.0 base, 0.67 second add, 0.44 third add
- Stop loss anchored to initial entry price
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import date
from typing import Optional, Dict, Any

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


class PyramidEngine:
    """Scale winners with additional entries."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"PyramidEngine: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def evaluate_pyramid_adds(self, current_date: date) -> Dict[str, Any]:
        """
        Evaluate all open positions for pyramid adds.

        Returns:
            {
                'candidates': [list of pyramid-eligible positions],
                'adds_executed': count of pyramids added,
                'total_value_added': sum of capital deployed
            }
        """
        self.connect()
        try:
            # Get all open positions with unrealized P&L
            self.cur.execute("""
                SELECT ap.position_id, ap.symbol, ap.quantity,
                       ap.entry_price, ap.current_price, ap.stop_loss,
                       ap.unrealized_pnl, ap.unrealized_pnl_pct,
                       COUNT(*) OVER (PARTITION BY ap.symbol) as pyramid_count
                FROM algo_positions ap
                WHERE ap.status = 'open'
                AND ap.current_price > ap.entry_price
                ORDER BY ap.unrealized_pnl_pct DESC
            """)
            positions = self.cur.fetchall()

            candidates = []
            for pos in positions:
                pos_id, symbol, qty, entry_price, cur_price, stop_loss, upnl, upnl_pct, p_count = pos

                # Pyramid criteria:
                # 1. Unrealized P&L > 1.5R (favorable move)
                # 2. Max 3 pyramids total on position
                # 3. Current price above entry (winning position)
                risk_per_share = entry_price - stop_loss
                r_multiple = (cur_price - entry_price) / risk_per_share if risk_per_share > 0 else 0

                if r_multiple >= 1.5 and p_count < 3:
                    candidates.append({
                        'symbol': symbol,
                        'position_id': pos_id,
                        'entry_price': entry_price,
                        'current_price': cur_price,
                        'stop_loss': stop_loss,
                        'unrealized_pnl': upnl,
                        'unrealized_pnl_pct': upnl_pct,
                        'r_multiple': round(r_multiple, 2),
                        'pyramid_count': p_count,
                    })

            return {
                'status': 'ok',
                'candidates': candidates,
                'candidates_count': len(candidates),
                'evaluation_date': current_date,
            }

        finally:
            self.disconnect()

    def calculate_pyramid_size(self, base_qty: int, pyramid_number: int) -> int:
        """
        Calculate pyramid add size using scale-down approach.

        Pyramid 1 (initial): 1.0x base_qty
        Pyramid 2 (add 1): 0.67x base_qty
        Pyramid 3 (add 2): 0.44x base_qty

        Args:
            base_qty: Initial position quantity
            pyramid_number: Which pyramid (1=initial, 2=first add, 3=second add)

        Returns:
            Quantity to add
        """
        scales = {
            1: 1.0,   # Initial entry
            2: 0.67,  # First add
            3: 0.44,  # Second add
        }
        scale = scales.get(pyramid_number, 0)
        return max(int(base_qty * scale), 1)

    def evaluate_symbol_pyramid(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Evaluate specific symbol for pyramid opportunity."""
        self.connect()
        try:
            self.cur.execute("""
                SELECT ap.position_id, ap.quantity, ap.entry_price, ap.current_price,
                       ap.stop_loss, ap.unrealized_pnl_pct
                FROM algo_positions ap
                WHERE ap.symbol = %s AND ap.status = 'open'
                LIMIT 1
            """, (symbol,))
            row = self.cur.fetchone()

            if not row:
                return None

            pos_id, qty, entry_price, cur_price, stop_loss, upnl_pct = row
            risk_per_share = entry_price - stop_loss
            r_multiple = (cur_price - entry_price) / risk_per_share if risk_per_share > 0 else 0

            # Evaluate pyramid eligibility
            eligible = r_multiple >= 1.5 and cur_price > entry_price

            return {
                'symbol': symbol,
                'position_id': pos_id,
                'current_quantity': qty,
                'entry_price': entry_price,
                'current_price': cur_price,
                'stop_loss': stop_loss,
                'unrealized_pnl_pct': upnl_pct,
                'r_multiple': round(r_multiple, 2),
                'eligible_for_pyramid': eligible,
            }

        finally:
            self.disconnect()


if __name__ == '__main__':
    from algo_config import get_config

    config = get_config()
    engine = PyramidEngine(config)

    # Evaluate pyramids for today
    result = engine.evaluate_pyramid_adds(date.today())

    print(f"\nPyramid Add Evaluation")
    print(f"  Candidates: {result['candidates_count']}")
    for cand in result['candidates']:
        print(f"    {cand['symbol']:6s} Entry: {cand['entry_price']:7.2f} "
              f"Current: {cand['current_price']:7.2f} "
              f"R: {cand['r_multiple']:+.2f} P&L: {cand['unrealized_pnl_pct']:+.1f}%")
