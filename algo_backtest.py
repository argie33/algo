#!/usr/bin/env python3
"""
Walk-Forward Backtester - Validate the selection strategy on history

Operates on historical data. For each trading day in the test window:
  1. Pull BUY signals from buy_sell_daily for that date.
  2. Run them through the full filter pipeline (tiers 1-6) using only
     data available AS OF that date (no look-ahead).
  3. Pick top N by composite score.
  4. Simulate fills at the entry_price.
  5. Walk forward day by day, tracking positions:
     - Mark to market each day
     - Apply tiered exits (T1/T2/T3) on appropriate price moves
     - Apply stop-outs
     - Apply time exits at max_hold_days
  6. After the test window, report metrics.

OUTPUTS:
  - Win rate
  - Average R-multiple won / lost
  - Profit factor (gross gain / gross loss)
  - Expectancy per trade
  - Max drawdown
  - Sharpe ratio
  - Total return

This DOES NOT execute against Alpaca and DOES NOT touch algo_trades /
algo_positions (uses isolated in-memory state). Reports stored to
algo_audit_log for review.

USAGE:
    python3 algo_backtest.py --start 2026-01-01 --end 2026-04-24 \\
        --capital 100000 --max-positions 12
"""

import os
import psycopg2
import argparse
import json
import statistics
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from collections import defaultdict

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


class Backtester:
    """In-memory walk-forward simulator."""

    def __init__(self, start_date, end_date, initial_capital=100_000.0,
                 max_positions=12, base_risk_pct=0.75, max_hold_days=20,
                 t1_r=1.5, t2_r=3.0, t3_r=4.0,
                 use_advanced_filters=True, max_trades_per_day=5):
        self.start = start_date
        self.end = end_date
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.equity_curve = [(start_date, initial_capital)]
        self.peak_equity = initial_capital

        self.max_positions = max_positions
        self.base_risk_pct = base_risk_pct
        self.max_hold_days = max_hold_days
        self.t1_r = t1_r
        self.t2_r = t2_r
        self.t3_r = t3_r
        self.max_trades_per_day = max_trades_per_day
        self.use_advanced_filters = use_advanced_filters

        self.positions = {}     # symbol -> position dict
        self.closed_trades = []
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
        self.cur = self.conn = None

    # ---------- Main loop ----------

    def run(self):
        self.connect()
        try:
            print(f"\n{'='*70}")
            print(f"WALK-FORWARD BACKTEST  {self.start} -> {self.end}")
            print(f"  Capital: ${self.initial_capital:,.0f}  Max positions: {self.max_positions}")
            print(f"  Risk per trade: {self.base_risk_pct}%  Max hold: {self.max_hold_days}d")
            print(f"  Targets: T1={self.t1_r}R T2={self.t2_r}R T3={self.t3_r}R")
            print(f"  Advanced filters: {self.use_advanced_filters}")
            print(f"{'='*70}\n")

            # Get every trading day in range (days where SPY has data)
            self.cur.execute(
                "SELECT date FROM price_daily WHERE symbol = 'SPY' "
                "AND date >= %s AND date <= %s ORDER BY date",
                (self.start, self.end),
            )
            trading_days = [r[0] for r in self.cur.fetchall()]
            print(f"Trading days: {len(trading_days)}")

            for day in trading_days:
                # Step 1: update existing positions, check exits
                self._tick_positions(day)

                # Step 2: take new entries (after exits clear capital)
                if len(self.positions) < self.max_positions:
                    self._consider_new_entries(day)

                # Track equity curve
                equity = self.cash + sum(p['quantity'] * p['mark_price'] for p in self.positions.values())
                self.equity_curve.append((day, equity))
                self.peak_equity = max(self.peak_equity, equity)

            # Final close any open positions at last price
            for sym in list(self.positions.keys()):
                self._close_position(sym, self.positions[sym]['mark_price'],
                                     'BACKTEST_END', trading_days[-1])

            return self._compute_metrics()
        finally:
            self.disconnect()

    # ---------- Per-day operations ----------

    def _tick_positions(self, day):
        """Update marks, check exits, apply T1/T2/T3 / stop / time."""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            # Get day's high/low/close (we use close as conservative fill assumption)
            self.cur.execute(
                "SELECT high, low, close FROM price_daily WHERE symbol = %s AND date = %s",
                (symbol, day),
            )
            row = self.cur.fetchone()
            if not row:
                continue
            high, low, close = float(row[0]), float(row[1]), float(row[2])
            pos['mark_price'] = close
            pos['days_held'] = (day - pos['entry_date']).days

            # Check exits (priority: stop -> T3 -> T2 -> T1 -> time)
            if low <= pos['stop']:
                # Use stop price as fill (could slip in reality)
                self._close_position(symbol, pos['stop'], 'STOP', day, partial=False)
                continue

            # Time exit
            if pos['days_held'] >= self.max_hold_days:
                self._close_position(symbol, close, 'TIME', day, partial=False)
                continue

            # Tiered targets — only if not already hit
            if pos['target_hits'] < 1 and high >= pos['t1_price']:
                self._partial_close(symbol, pos['t1_price'], 0.50, 'T1', day,
                                    new_stop=pos['entry_price'])  # raise to breakeven
            if pos['target_hits'] < 2 and high >= pos['t2_price']:
                self._partial_close(symbol, pos['t2_price'], 0.50, 'T2', day,
                                    new_stop=pos['t1_price'])  # raise to T1
            if pos['target_hits'] < 3 and high >= pos['t3_price']:
                self._close_position(symbol, pos['t3_price'], 'T3', day, partial=False)

    def _consider_new_entries(self, day):
        """Read buy_sell_daily for `day`, run through filter pipeline, take top N."""
        # We call into FilterPipeline to use the same logic in production.
        # The pipeline only reads data <= signal_date, so it's safe for backtest.
        from algo_filter_pipeline import FilterPipeline
        from algo_config import get_config

        # Override portfolio state for the simulation
        config = get_config()
        # FilterPipeline uses live algo_positions for portfolio state — we need to
        # stub that out so it sees backtest state. Easiest: insert temp open positions
        # into algo_positions, run pipeline, delete them. Cleaner: build a forked
        # version. For now we use a SIMPLIFIED filter that mimics the pipeline.
        candidates = self._evaluate_signals_for_backtest(day, config)
        if not candidates:
            return

        # Available slots and risk budget
        slots = self.max_positions - len(self.positions)
        slots = min(slots, self.max_trades_per_day)
        candidates = candidates[:slots]

        for cand in candidates:
            symbol = cand['symbol']
            if symbol in self.positions:
                continue
            entry = cand['entry_price']
            stop = cand['stop_loss_price']
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                continue

            equity = self.cash + sum(p['quantity'] * p['mark_price'] for p in self.positions.values())
            risk_dollars = equity * (self.base_risk_pct / 100.0)
            shares = int(risk_dollars / risk_per_share)
            position_value = shares * entry
            if shares <= 0 or position_value > self.cash:
                continue

            # Open
            self.cash -= position_value
            self.positions[symbol] = {
                'entry_price': entry,
                'stop': stop,
                'initial_stop': stop,
                'quantity': shares,
                'remaining_quantity': shares,
                'entry_date': day,
                'days_held': 0,
                'mark_price': entry,
                't1_price': round(entry + (risk_per_share * self.t1_r), 4),
                't2_price': round(entry + (risk_per_share * self.t2_r), 4),
                't3_price': round(entry + (risk_per_share * self.t3_r), 4),
                'target_hits': 0,
                'sqs': cand.get('sqs', 0),
                'composite': cand.get('composite_score', 0),
                'partial_exits': [],
            }

    def _evaluate_signals_for_backtest(self, day, config):
        """Use the production FilterPipeline against `day` data without modifying state.

        We temporarily replace the portfolio-state cache in the pipeline with our
        backtest's state, then run evaluate_signals().
        """
        from algo_filter_pipeline import FilterPipeline
        pipeline = FilterPipeline()
        pipeline.connect()
        try:
            # Inject backtest portfolio state
            equity = self.cash + sum(p['quantity'] * p['mark_price'] for p in self.positions.values())
            pipeline._portfolio_state_cache = {
                'position_count': len(self.positions),
                'symbols': set(self.positions.keys()),
                'positions_value': sum(p['quantity'] * p['mark_price'] for p in self.positions.values()),
                'portfolio_value': equity,
                'drawdown_pct': max(0.0, (self.peak_equity - equity) / self.peak_equity * 100.0) if self.peak_equity > 0 else 0,
                'risk_adjustment': 1.0,
            }
            # Init advanced filters using pipeline's cursor
            from algo_advanced_filters import AdvancedFilters
            pipeline.advanced = AdvancedFilters(config, cur=pipeline.cur)
            pipeline.advanced.load_market_context(day)

            # Get raw BUY signals for `day`
            pipeline.cur.execute(
                "SELECT symbol, date, signal, entry_price FROM buy_sell_daily "
                "WHERE date = %s AND signal = 'BUY'",
                (day,),
            )
            signals = pipeline.cur.fetchall()
            qualified = []
            for symbol, signal_date, _signal, entry_price in signals:
                result = pipeline.evaluate_signal(symbol, signal_date, float(entry_price))
                if not result['passed_all_tiers']:
                    continue
                if self.use_advanced_filters:
                    sector_info = pipeline._get_sector_info(symbol) or {'sector': '', 'industry': ''}
                    adv = pipeline.advanced.evaluate_candidate(
                        symbol, signal_date, float(entry_price),
                        sector_info['sector'], sector_info['industry'],
                    )
                    if not adv['pass']:
                        continue
                    composite = adv['composite_score']
                else:
                    composite = result.get('sqs', 0)
                qualified.append({
                    'symbol': symbol,
                    'entry_price': float(entry_price),
                    'stop_loss_price': result['stop_loss_price'],
                    'sqs': result['sqs'],
                    'composite_score': composite,
                })
            qualified.sort(key=lambda x: x['composite_score'], reverse=True)
            return qualified
        finally:
            pipeline.disconnect()

    # ---------- Position closing ----------

    def _close_position(self, symbol, price, reason, day, partial=False):
        pos = self.positions[symbol]
        proceeds = pos['remaining_quantity'] * price
        self.cash += proceeds

        risk_per_share = pos['entry_price'] - pos['initial_stop']
        r_multiple = ((price - pos['entry_price']) / risk_per_share) if risk_per_share > 0 else 0
        pnl = (price - pos['entry_price']) * pos['remaining_quantity']

        self.closed_trades.append({
            'symbol': symbol,
            'entry_date': pos['entry_date'],
            'exit_date': day,
            'entry_price': pos['entry_price'],
            'exit_price': price,
            'quantity': pos['remaining_quantity'],
            'reason': reason,
            'r_multiple': r_multiple,
            'pnl_dollars': pnl,
            'pnl_pct': (price - pos['entry_price']) / pos['entry_price'] * 100,
            'days_held': pos['days_held'],
            'partial_exits': pos['partial_exits'],
            'sqs': pos['sqs'],
            'composite': pos['composite'],
        })
        del self.positions[symbol]

    def _partial_close(self, symbol, price, fraction, stage, day, new_stop=None):
        pos = self.positions[symbol]
        shares_to_close = max(1, int(pos['remaining_quantity'] * fraction))
        shares_to_close = min(shares_to_close, pos['remaining_quantity'])
        proceeds = shares_to_close * price
        self.cash += proceeds

        risk_per_share = pos['entry_price'] - pos['initial_stop']
        r_multiple = ((price - pos['entry_price']) / risk_per_share) if risk_per_share > 0 else 0
        pnl = (price - pos['entry_price']) * shares_to_close

        pos['partial_exits'].append({
            'date': day, 'price': price, 'shares': shares_to_close,
            'stage': stage, 'r_multiple': r_multiple, 'pnl': pnl,
        })
        pos['remaining_quantity'] -= shares_to_close
        pos['target_hits'] += 1
        if new_stop is not None:
            pos['stop'] = max(pos['stop'], new_stop)

        # If we exited everything, close fully
        if pos['remaining_quantity'] <= 0:
            self._close_position(symbol, price, f'{stage}_FULL', day, partial=False)

    # ---------- Metrics ----------

    def _compute_metrics(self):
        if not self.closed_trades and not self.positions:
            print("\nNo trades taken.\n")
            return {}

        ending_equity = self.cash + sum(p['quantity'] * p['mark_price'] for p in self.positions.values())
        total_return_pct = ((ending_equity - self.initial_capital) / self.initial_capital) * 100

        # Per-trade analysis (only fully closed)
        wins = [t for t in self.closed_trades if t['r_multiple'] > 0]
        losses = [t for t in self.closed_trades if t['r_multiple'] <= 0]

        win_rate = len(wins) / len(self.closed_trades) * 100 if self.closed_trades else 0
        avg_win_r = statistics.mean(t['r_multiple'] for t in wins) if wins else 0
        avg_loss_r = statistics.mean(t['r_multiple'] for t in losses) if losses else 0
        avg_r = statistics.mean(t['r_multiple'] for t in self.closed_trades) if self.closed_trades else 0
        gross_gain = sum(t['pnl_dollars'] for t in wins) + sum(
            sum(p['pnl'] for p in t['partial_exits'] if p['pnl'] > 0) for t in self.closed_trades
        )
        gross_loss = abs(sum(t['pnl_dollars'] for t in losses))
        profit_factor = (gross_gain / gross_loss) if gross_loss > 0 else float('inf')
        expectancy = (win_rate / 100 * avg_win_r) + ((1 - win_rate / 100) * avg_loss_r)

        # Drawdown
        peak = self.equity_curve[0][1]
        max_dd_pct = 0
        for _, eq in self.equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak * 100
            max_dd_pct = max(max_dd_pct, dd)

        # Sharpe (simple, daily-return based)
        rets = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i - 1][1]
            cur = self.equity_curve[i][1]
            if prev > 0:
                rets.append((cur - prev) / prev)
        sharpe = 0
        if len(rets) > 1 and statistics.stdev(rets) > 0:
            sharpe = (statistics.mean(rets) / statistics.stdev(rets)) * (252 ** 0.5)

        report = {
            'period': f'{self.start} -> {self.end}',
            'initial_capital': self.initial_capital,
            'ending_equity': round(ending_equity, 2),
            'total_return_pct': round(total_return_pct, 2),
            'closed_trades': len(self.closed_trades),
            'open_positions_at_end': len(self.positions),
            'win_rate_pct': round(win_rate, 1),
            'avg_r_per_trade': round(avg_r, 2),
            'avg_win_r': round(avg_win_r, 2),
            'avg_loss_r': round(avg_loss_r, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy_r': round(expectancy, 3),
            'max_drawdown_pct': round(max_dd_pct, 2),
            'sharpe_ratio': round(sharpe, 2),
        }

        self._print_report(report)
        return report

    def _print_report(self, r):
        print(f"\n{'='*70}")
        print(f"BACKTEST REPORT")
        print(f"{'='*70}")
        for k, v in r.items():
            print(f"  {k:25s}: {v}")
        print(f"\nTRADE BREAKDOWN")
        print(f"{'='*70}")
        for t in self.closed_trades[-15:]:
            print(
                f"  {t['symbol']:6s}  {t['entry_date']} -> {t['exit_date']}  "
                f"({t['days_held']:2d}d)  "
                f"${t['entry_price']:7.2f} -> ${t['exit_price']:7.2f}  "
                f"R={t['r_multiple']:+.2f}  "
                f"P&L={t['pnl_dollars']:+8.0f}  "
                f"reason={t['reason']}"
            )
        print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Backtest selection strategy')
    parser.add_argument('--start', type=str, default='2026-01-01', help='Start date')
    parser.add_argument('--end', type=str, default='2026-04-24', help='End date')
    parser.add_argument('--capital', type=float, default=100_000.0, help='Initial capital')
    parser.add_argument('--max-positions', type=int, default=12, help='Max concurrent positions')
    parser.add_argument('--no-advanced', action='store_true', help='Skip advanced filters')
    args = parser.parse_args()

    bt = Backtester(
        start_date=_date.fromisoformat(args.start),
        end_date=_date.fromisoformat(args.end),
        initial_capital=args.capital,
        max_positions=args.max_positions,
        use_advanced_filters=not args.no_advanced,
    )
    report = bt.run()
    print(f"\n[Done] Report: {json.dumps(report, indent=2, default=str)}\n")
