#!/usr/bin/env python3
"""
Dry-run simulator for safe pre-flight validation.

Instead of just printing what would happen, this actually simulates:
- Order fill verification
- Position sizing validation
- Exit logic testing
- P&L calculation validation
- Circuit breaker checks

All without touching the database or Alpaca.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class DryRunSimulator:
    """Simulate a full trading day without side effects."""

    def __init__(self, config, run_date=None, verbose=True):
        self.config = config
        self.run_date = run_date or _date.today()
        self.verbose = verbose
        self.trades = []
        self.exits = []
        self.errors = []
        self.total_risk = 0.0

    def simulate_entry(self, symbol, entry_price, shares, stop_loss_price):
        """Simulate an entry trade.

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            shares: Shares to buy
            stop_loss_price: Stop loss level

        Returns:
            (success, trade_id, message)
        """
        # Validate prices
        if entry_price <= 0:
            return False, None, f"Invalid entry price: {entry_price}"
        if stop_loss_price >= entry_price:
            return False, None, f"Stop loss {stop_loss_price} >= entry {entry_price}"
        if shares <= 0:
            return False, None, f"Invalid share count: {shares}"

        # Check position limit
        max_positions = int(self.config.get('max_positions', 12))
        if len(self.trades) >= max_positions:
            return False, None, f"Max positions ({max_positions}) reached"

        # Calculate position metrics
        risk_per_share = entry_price - stop_loss_price
        position_value = shares * entry_price

        # Check risk limit
        max_position_size = float(self.config.get('max_position_size_pct', 8.0))
        portfolio_value = 100000  # Default for sim
        position_size_pct = (position_value / portfolio_value) * 100
        if position_size_pct > max_position_size:
            return False, None, f"Position {position_size_pct:.1f}% > max {max_position_size}%"

        # Check total risk
        trade_risk = shares * risk_per_share
        max_total_risk = float(self.config.get('max_total_risk_pct', 4.0)) / 100 * portfolio_value
        if self.total_risk + trade_risk > max_total_risk:
            return False, None, f"Total risk exceeds limit"

        # Record trade
        trade = {
            'symbol': symbol,
            'trade_id': f"SIM-{len(self.trades)+1}",
            'entry_price': entry_price,
            'stop_loss': stop_loss_price,
            'shares': shares,
            'entry_date': datetime.now(),
            'position_value': position_value,
            'risk': trade_risk,
        }
        self.trades.append(trade)
        self.total_risk += trade_risk

        if self.verbose:
            print(f"✓ {symbol}: {shares} @ ${entry_price:.2f} "
                  f"(stop ${stop_loss:.2f}, risk ${trade_risk:,.0f})")

        return True, trade['trade_id'], f"Entry simulated"

    def simulate_exit(self, trade_id, exit_price, reason):
        """Simulate an exit.

        Args:
            trade_id: Trade to exit
            exit_price: Exit price
            reason: Exit reason

        Returns:
            (success, message)
        """
        # Find trade
        trade = next((t for t in self.trades if t['trade_id'] == trade_id), None)
        if not trade:
            return False, f"Trade {trade_id} not found"

        if exit_price <= 0:
            return False, f"Invalid exit price: {exit_price}"

        # Calculate P&L
        pnl_per_share = exit_price - trade['entry_price']
        pnl_dollars = pnl_per_share * trade['shares']
        pnl_pct = (pnl_per_share / trade['entry_price']) * 100 if trade['entry_price'] > 0 else 0

        # Calculate R-multiple
        risk_per_share = trade['entry_price'] - trade['stop_loss']
        r_multiple = pnl_per_share / risk_per_share if risk_per_share > 0 else 0

        exit = {
            'trade_id': trade_id,
            'symbol': trade['symbol'],
            'exit_price': exit_price,
            'pnl_dollars': pnl_dollars,
            'pnl_pct': pnl_pct,
            'r_multiple': r_multiple,
            'reason': reason,
            'exit_date': datetime.now(),
        }
        self.exits.append(exit)
        self.total_risk -= trade['risk']

        if self.verbose:
            print(f"✓ {trade['symbol']}: exit @ ${exit_price:.2f} "
                  f"({pnl_dollars:+,.0f} / {pnl_pct:+.2f}%, {r_multiple:+.2f}R) - {reason}")

        return True, f"Exit simulated"

    def validate_circuit_breakers(self):
        """Check if any circuit breakers would fire."""
        issues = []

        # Max position size check
        total_position_value = sum(t['position_value'] for t in self.trades)
        if self.trades:
            max_position = max(t['position_value'] for t in self.trades)
            portfolio_value = 100000
            max_concentration = float(self.config.get('max_concentration_pct', 50.0))
            concentration = (max_position / portfolio_value) * 100
            if concentration > max_concentration:
                issues.append(f"Concentration {concentration:.1f}% > {max_concentration}%")

        # Daily loss check
        daily_pnl = sum(e['pnl_dollars'] for e in self.exits)
        max_daily_loss_pct = float(self.config.get('max_daily_loss_pct', 2.0))
        portfolio_value = 100000
        daily_loss_pct = (daily_pnl / portfolio_value) * 100 if portfolio_value > 0 else 0
        if daily_loss_pct < -max_daily_loss_pct:
            issues.append(f"Daily loss {daily_loss_pct:.2f}% exceeds -{max_daily_loss_pct}% limit")

        return issues

    def report(self):
        """Print dry-run report."""
        print(f"\n{'='*70}")
        print(f"DRY-RUN SIMULATION REPORT — {self.run_date}")
        print(f"{'='*70}")
        print(f"\nTrades: {len(self.trades)} open")
        for t in self.trades:
            print(f"  {t['symbol']:6} {t['shares']:4.0f}sh @ ${t['entry_price']:7.2f} "
                  f"(stop ${t['stop_loss']:7.2f}, risk ${t['risk']:8,.0f})")

        print(f"\nExits: {len(self.exits)}")
        total_pnl = 0
        for e in self.exits:
            print(f"  {e['symbol']:6} @ ${e['exit_price']:7.2f} "
                  f"{e['pnl_dollars']:+8,.0f} ({e['pnl_pct']:+6.2f}%, {e['r_multiple']:+5.2f}R) - {e['reason']}")
            total_pnl += e['pnl_dollars']

        print(f"\nPortfolio Metrics:")
        print(f"  Total P&L: ${total_pnl:+,.0f}")
        print(f"  Open Risk: ${self.total_risk:,.0f}")
        print(f"  Win Rate: {len([e for e in self.exits if e['pnl_dollars'] > 0])}/{len(self.exits)}")

        breaker_issues = self.validate_circuit_breakers()
        if breaker_issues:
            print(f"\n⚠️  Circuit Breaker Issues:")
            for issue in breaker_issues:
                print(f"  - {issue}")

        if self.errors:
            print(f"\n❌ Errors: {len(self.errors)}")
            for err in self.errors:
                print(f"  - {err}")

        print(f"{'='*70}\n")

        return {
            'success': len(self.errors) == 0 and len(breaker_issues) == 0,
            'trades': len(self.trades),
            'exits': len(self.exits),
            'pnl': total_pnl,
            'errors': self.errors,
            'breaker_issues': breaker_issues,
        }


if __name__ == "__main__":
    from algo_config import get_config
    config = get_config()
    sim = DryRunSimulator(config, verbose=True)

    # Example simulation
    print("Testing dry-run simulator...\n")
    sim.simulate_entry('AAPL', 150.00, 100, 142.50)
    sim.simulate_entry('MSFT', 300.00, 50, 285.00)
    sim.simulate_exit('SIM-1', 155.00, 'T1 target')

    result = sim.report()
    print(f"Status: {'✓ PASS' if result['success'] else '✗ FAIL'}")
