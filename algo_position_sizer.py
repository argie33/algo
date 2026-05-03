#!/usr/bin/env python3
"""
Position Sizer - Calculates trade size based on risk management rules

Rules:
- Base risk: 0.75% of portfolio per trade
- Drawdown defense: reduce risk at -5%, -10%, -15%, -20%
- Pyramid entry: 50/33/17 split across multiple entries
- Max position size: 8% of portfolio
- Max concentration: 50% in single position
- Max positions: 12 concurrent
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from decimal import Decimal

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

class PositionSizer:
    """Calculate position sizes based on risk parameters."""

    def __init__(self, config):
        self.config = config
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

    def get_portfolio_value(self):
        """Get current portfolio value."""
        try:
            self.cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
            result = self.cur.fetchone()
            return float(result[0]) if result and result[0] else 100000.0
        except:
            return 100000.0

    def get_current_drawdown(self):
        """Calculate current drawdown from peak."""
        try:
            self.cur.execute("""
                SELECT
                    MAX(total_portfolio_value) as peak,
                    (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                     ORDER BY snapshot_date DESC LIMIT 1) as current
                FROM algo_portfolio_snapshots
            """)
            result = self.cur.fetchone()
            if not result or not result[0] or not result[1]:
                return 0.0

            peak = float(result[0])
            current = float(result[1])
            if peak == 0:
                return 0.0

            drawdown_pct = ((peak - current) / peak) * 100
            return max(0, drawdown_pct)
        except:
            return 0.0

    def get_risk_adjustment(self):
        """Get risk adjustment factor based on drawdown."""
        dd = self.get_current_drawdown()

        if dd >= 20:
            # Halt all trading
            return 0.0
        elif dd >= 15:
            # Reduce to 25% of base risk
            return self.config.get('risk_reduction_at_minus_15', 0.25)
        elif dd >= 10:
            # Reduce to 50% of base risk
            return self.config.get('risk_reduction_at_minus_10', 0.5)
        elif dd >= 5:
            # Reduce to 75% of base risk
            return self.config.get('risk_reduction_at_minus_5', 0.75)
        else:
            # Full base risk
            return 1.0

    def get_active_positions_value(self):
        """Get sum of active position values."""
        try:
            self.cur.execute("""
                SELECT COALESCE(SUM(position_value), 0) as total
                FROM algo_positions
                WHERE status = 'open'
            """)
            result = self.cur.fetchone()
            return float(result[0]) if result else 0.0
        except:
            return 0.0

    def get_position_count(self):
        """Get count of active positions."""
        try:
            self.cur.execute("""
                SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'
            """)
            result = self.cur.fetchone()
            return result[0] if result else 0
        except:
            return 0

    def calculate_position_size(self, symbol, entry_price, stop_loss_price):
        """
        Calculate position size for a new trade.

        Returns:
        {
            'shares': number of shares,
            'position_size_pct': % of portfolio,
            'risk_dollars': dollar amount at risk,
            'status': 'ok' | 'no_room' | 'drawdown_halt'
        }
        """
        self.connect()

        try:
            portfolio_value = self.get_portfolio_value()
            risk_adjustment = self.get_risk_adjustment()
            active_positions = self.get_position_count()
            active_position_value = self.get_active_positions_value()

            # Check max positions
            max_positions = self.config.get('max_positions', 12)
            if active_positions >= max_positions:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'no_room',
                    'reason': f'{active_positions} open positions >= {max_positions} max'
                }

            # Check if drawdown halt is active
            if risk_adjustment == 0:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'drawdown_halt',
                    'reason': f'Drawdown >= 20%, trading halted'
                }

            # Calculate base risk
            base_risk_pct = self.config.get('base_risk_pct', 0.75) / 100
            adjusted_risk_pct = base_risk_pct * risk_adjustment
            risk_dollars = portfolio_value * adjusted_risk_pct

            # Calculate shares based on stop loss
            if entry_price <= 0 or stop_loss_price >= entry_price:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'invalid',
                    'reason': 'Invalid entry or stop price'
                }

            risk_per_share = entry_price - stop_loss_price
            shares = int(risk_dollars / risk_per_share) if risk_per_share > 0 else 0

            # Check max position size
            position_value = shares * entry_price
            max_position_pct = self.config.get('max_position_size_pct', 8.0) / 100
            max_position_value = portfolio_value * max_position_pct

            if position_value > max_position_value:
                shares = int(max_position_value / entry_price)
                position_value = shares * entry_price
                risk_dollars = risk_per_share * shares

            # Check concentration
            new_total_value = active_position_value + position_value
            position_size_pct = (position_value / new_total_value * 100) if new_total_value > 0 else 0
            max_concentration = self.config.get('max_concentration_pct', 50.0)

            if position_size_pct > max_concentration:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'concentration',
                    'reason': f'Position would be {position_size_pct:.1f}% > {max_concentration}% max'
                }

            position_pct_of_portfolio = (position_value / portfolio_value * 100)

            return {
                'shares': shares,
                'position_size_pct': position_pct_of_portfolio,
                'risk_dollars': risk_dollars,
                'position_value': position_value,
                'status': 'ok',
                'reason': f'{shares} shares @ ${entry_price:.2f} = ${position_value:.2f}'
            }

        except Exception as e:
            return {
                'shares': 0,
                'position_size_pct': 0,
                'risk_dollars': 0,
                'status': 'error',
                'reason': str(e)
            }
        finally:
            self.disconnect()

    def get_pyramid_split(self):
        """Get pyramid entry split percentages."""
        split_str = self.config.get('pyramid_split_pct', '50,33,17')
        try:
            splits = [float(x.strip()) / 100 for x in split_str.split(',')]
            return splits
        except:
            return [0.50, 0.33, 0.17]

if __name__ == "__main__":
    from algo_config import get_config

    config = get_config()
    sizer = PositionSizer(config)

    # Test sizing
    result = sizer.calculate_position_size(
        symbol='AAPL',
        entry_price=150.00,
        stop_loss_price=142.50
    )

    print(f"Position Size Calculation Test:")
    print(f"  Status: {result['status']}")
    print(f"  Shares: {result['shares']}")
    print(f"  Position Value: ${result.get('position_value', 0):.2f}")
    print(f"  Risk %: {result['position_size_pct']:.2f}%")
    print(f"  Reason: {result['reason']}")
