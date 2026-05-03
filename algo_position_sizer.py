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
        """Get current portfolio value.

        Priority:
        1. Live Alpaca account (most accurate)
        2. Latest portfolio snapshot
        3. Fallback constant ($100k)
        """
        # Try live Alpaca first
        alpaca_value = self._fetch_live_alpaca_equity()
        if alpaca_value is not None:
            return alpaca_value

        try:
            self.cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
            result = self.cur.fetchone()
            if result and result[0]:
                return float(result[0])
        except Exception:
            pass

        return 100000.0

    def _fetch_live_alpaca_equity(self):
        """Fetch live portfolio equity from Alpaca. Returns None on any failure."""
        import requests
        key = os.getenv('APCA_API_KEY_ID')
        secret = os.getenv('APCA_API_SECRET_KEY')
        base = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
        if not key or not secret:
            return None
        try:
            response = requests.get(
                f'{base}/v2/account',
                headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret},
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                # Use portfolio_value (equity + cash)
                pv = data.get('portfolio_value') or data.get('equity')
                if pv is not None:
                    return float(pv)
        except Exception:
            pass
        return None

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
        """Get risk adjustment factor based on drawdown.

        Combined with market_exposure_pct multiplier for dynamic risk:
            effective_risk = base_risk × dd_adjustment × (exposure_pct / 100)
        """
        dd = self.get_current_drawdown()

        if dd >= 20:
            return 0.0  # Halt all trading
        elif dd >= 15:
            return float(self.config.get('risk_reduction_at_minus_15', 0.25))
        elif dd >= 10:
            return float(self.config.get('risk_reduction_at_minus_10', 0.5))
        elif dd >= 5:
            return float(self.config.get('risk_reduction_at_minus_5', 0.75))
        else:
            return 1.0

    def get_market_exposure_multiplier(self):
        """Look up the most recent market exposure pct (0-100). Returns multiplier 0.0-1.0."""
        try:
            self.cur.execute(
                "SELECT exposure_pct FROM market_exposure_daily ORDER BY date DESC LIMIT 1"
            )
            row = self.cur.fetchone()
            if row and row[0] is not None:
                return float(row[0]) / 100.0
        except Exception:
            pass
        return 1.0  # neutral if not computed yet

    def get_phase_size_multiplier(self, symbol):
        """Stage-2 phase mult: Early=1.0, Mid=1.0, Late=0.5, Climax=0.0."""
        try:
            from algo_signals import SignalComputer
            from datetime import date as _date
            sc = SignalComputer(cur=self.cur)
            phase = sc.stage2_phase(symbol, _date.today())
            return phase.get('size_multiplier', 1.0)
        except Exception:
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

            # Dynamic risk = base × drawdown × market_exposure × stage_phase
            base_risk_pct = float(self.config.get('base_risk_pct', 0.75)) / 100
            exposure_mult = self.get_market_exposure_multiplier()
            phase_mult = self.get_phase_size_multiplier(symbol)
            adjusted_risk_pct = base_risk_pct * risk_adjustment * exposure_mult * phase_mult
            risk_dollars = portfolio_value * adjusted_risk_pct

            # If stage phase says zero, halt this entry
            if phase_mult == 0.0:
                return {
                    'shares': 0, 'position_size_pct': 0, 'risk_dollars': 0,
                    'status': 'phase_climax',
                    'reason': f'{symbol} in Stage-2 climax phase — skip entry',
                }

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

            # Concentration: this position's % of total portfolio (not of position book)
            position_pct_of_portfolio = (position_value / portfolio_value * 100) if portfolio_value > 0 else 0
            max_concentration = float(self.config.get('max_concentration_pct', 50.0))

            if position_pct_of_portfolio > max_concentration:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'concentration',
                    'reason': f'Position would be {position_pct_of_portfolio:.1f}% > {max_concentration:.0f}% portfolio'
                }

            # Total invested cap (sum of positions <= portfolio - reserves)
            total_invested = active_position_value + position_value
            max_invested_pct = float(self.config.get('max_total_invested_pct', 95.0))
            if portfolio_value > 0 and (total_invested / portfolio_value * 100) > max_invested_pct:
                return {
                    'shares': 0,
                    'position_size_pct': 0,
                    'risk_dollars': 0,
                    'status': 'no_room',
                    'reason': f'Total invested would be {total_invested/portfolio_value*100:.0f}% > {max_invested_pct:.0f}%'
                }

            return {
                'shares': shares,
                'position_size_pct': position_pct_of_portfolio,
                'risk_dollars': risk_dollars,
                'position_value': position_value,
                'status': 'ok',
                'reason': f'{shares} shares @ ${entry_price:.2f} = ${position_value:.2f} ({position_pct_of_portfolio:.1f}%)'
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
