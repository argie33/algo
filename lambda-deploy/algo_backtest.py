#!/usr/bin/env python3
"""
Walk-Forward Backtester

Strategies:
  raw      - Pure buy/sell signals, no filters (baseline)
  filtered - Full 5-tier pipeline, no advanced scoring
  advanced - Full pipeline + advanced filters + swing score (default)

USAGE:
    python3 algo_backtest.py --start 2025-01-01 --end 2025-12-31
    python3 algo_backtest.py --start 2024-01-01 --end 2025-12-31 --strategy raw
    python3 algo_backtest.py --start 2024-01-01 --end 2025-12-31 --strategy filtered
"""

import os
import psycopg2
import argparse
import json
import statistics
from pathlib import Path
from dotenv import load_dotenv
from datetime import date as _date
from collections import defaultdict

from credential_manager import get_credential_manager

credential_manager = get_credential_manager()

env_file = Path(__file__).parent / ".env.local"
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}

STRATEGIES = ("raw", "filtered", "advanced")


class Backtester:
    """In-memory walk-forward simulator.

    strategy:
      'raw'      - No filters. All BUY signals taken as-is (baseline).
      'filtered' - 5-tier pipeline (T1-T5), no advanced scoring.
      'advanced' - Full pipeline + advanced filters + swing score. (default)
    """

    def __init__(self, start_date, end_date, initial_capital=100_000.0,
                 max_positions=12, base_risk_pct=0.75, max_hold_days=20,
                 t1_r=1.5, t2_r=3.0, t3_r=4.0,
                 strategy="advanced", max_trades_per_day=5,
                 use_advanced_filters=True):
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
        self.strategy = strategy
        self.use_advanced_filters = (strategy == "advanced")
        self.positions = {}
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

    def run(self):
        self.connect()
        try:
            strat_label = self.strategy.upper()
            print(f"\n{'='*70}")
            print(f"WALK-FORWARD BACKTEST  [{strat_label}]  {self.start} -> {self.end}")
            print(f"  Capital: ${self.initial_capital:,.0f}  Max positions: {self.max_positions}")
            print(f"  Risk per trade: {self.base_risk_pct}%  Max hold: {self.max_hold_days}d")
            print(f"  Targets: T1={self.t1_r}R T2={self.t2_r}R T3={self.t3_r}R")
            print(f"{'='*70}\n")
            self.cur.execute(
                "SELECT date FROM price_daily WHERE symbol = 'SPY' AND date >= %s AND date <= %s ORDER BY date",
                (self.start, self.end),
            )
            trading_days = [r[0] for r in self.cur.fetchall()]
            print(f"Trading days: {len(trading_days)}")
            for day in trading_days:
                self._tick_positions(day)
                if len(self.positions) < self.max_positions:
                    self._consider_new_entries(day)
                equity = self._equity()
                self.equity_curve.append((day, equity))
                self.peak_equity = max(self.peak_equity, equity)
            for sym in list(self.positions.keys()):
                self._close_position(sym, self.positions[sym]["mark_price"], "BACKTEST_END", trading_days[-1])
            return self._compute_metrics()
        finally:
            self.disconnect()

    def _equity(self):
        return self.cash + sum(p["quantity"] * p["mark_price"] for p in self.positions.values())

    def _tick_positions(self, day):
        """Update marks, check exits. Guards against double-close via .get() and mid-loop presence checks."""
        for symbol in list(self.positions.keys()):
            pos = self.positions.get(symbol)
            if pos is None:
                continue
            self.cur.execute(
                "SELECT high, low, close FROM price_daily WHERE symbol = %s AND date = %s",
                (symbol, day),
            )
            row = self.cur.fetchone()
            if not row:
                continue
            high, low, close = float(row[0]), float(row[1]), float(row[2])
            pos["mark_price"] = close
            pos["days_held"] = (day - pos["entry_date"]).days
            if low <= pos["stop"]:
                self._close_position(symbol, pos["stop"], "STOP", day)
                continue
            if pos["days_held"] >= self.max_hold_days:
                self._close_position(symbol, close, "TIME", day)
                continue
            if pos["target_hits"] < 1 and high >= pos["t1_price"]:
                self._partial_close(symbol, pos["t1_price"], 0.50, "T1", day, new_stop=pos["entry_price"])
            if symbol not in self.positions:
                continue
            if pos["target_hits"] < 2 and high >= pos["t2_price"]:
                self._partial_close(symbol, pos["t2_price"], 0.50, "T2", day, new_stop=pos["t1_price"])
            if symbol not in self.positions:
                continue
            if pos["target_hits"] < 3 and high >= pos["t3_price"]:
                self._close_position(symbol, pos["t3_price"], "T3", day)

    def _consider_new_entries(self, day):
        if self.strategy == "raw":
            self._entries_raw(day)
        else:
            self._entries_pipeline(day)

    def _entries_raw(self, day):
        """Baseline: take all BUY signals with zero filtering."""
        self.cur.execute(
            "SELECT symbol, entry_price, stoplevel, atr FROM buy_sell_daily "
            "WHERE date = %s AND signal = 'BUY' ORDER BY symbol",
            (day,),
        )
        signals = self.cur.fetchall()
        if not signals:
            return
        slots = min(self.max_positions - len(self.positions), self.max_trades_per_day)
        taken = 0
        for symbol, entry_price, stop_level, atr in signals:
            if taken >= slots or symbol in self.positions:
                continue
            if entry_price is None or float(entry_price) <= 0:
                continue
            entry = float(entry_price)
            if stop_level is not None and float(stop_level) > 0 and float(stop_level) < entry:
                stop = float(stop_level)
            elif atr is not None and float(atr) > 0:
                stop = entry - 2.0 * float(atr)
            else:
                stop = entry * 0.92
            stop = max(stop, entry * 0.92)
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                continue
            equity = self._equity()
            shares = int(equity * (self.base_risk_pct / 100.0) / risk_per_share)
            if shares <= 0 or shares * entry > self.cash:
                continue
            self.cash -= shares * entry
            self.positions[symbol] = self._make_position(entry, stop, shares, day)
            taken += 1

    def _make_position(self, entry, stop, shares, entry_date, sqs=0, composite=0):
        risk = entry - stop
        return {
            "entry_price": entry, "stop": stop, "initial_stop": stop,
            "quantity": shares, "remaining_quantity": shares,
            "entry_date": entry_date, "days_held": 0, "mark_price": entry,
            "t1_price": round(entry + risk * self.t1_r, 4),
            "t2_price": round(entry + risk * self.t2_r, 4),
            "t3_price": round(entry + risk * self.t3_r, 4),
            "target_hits": 0, "sqs": sqs, "composite": composite, "partial_exits": [],
        }

    def _entries_pipeline(self, day):
        """Filtered / Advanced: inline backtest-safe filter evaluation.

        Avoids pre-computed tables (data_completeness_scores, algo_signals_evaluated)
        which suffer from incomplete local data and look-ahead bias.
        All quality checks are computed directly from price_daily and other
        time-series tables using data available on or before `day`.
        """
        candidates = self._eval_pipeline_backtest(day)
        if not candidates:
            return
        slots = min(self.max_positions - len(self.positions), self.max_trades_per_day)
        for cand in candidates[:slots]:
            symbol = cand["symbol"]
            if symbol in self.positions:
                continue
            entry, stop = cand["entry_price"], cand["stop_loss_price"]
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                continue
            equity = self._equity()
            shares = int(equity * (self.base_risk_pct / 100.0) / risk_per_share)
            if shares <= 0 or shares * entry > self.cash:
                continue
            self.cash -= shares * entry
            self.positions[symbol] = self._make_position(
                entry, stop, shares, day,
                sqs=cand.get("sqs", 0), composite=cand.get("composite_score", 0),
            )

    def _eval_pipeline_backtest(self, day):
        """Backtest-safe inline filter evaluation.

        Quality checks computed directly from historical data — no pre-computed
        completeness scores (which have look-ahead bias and are incomplete for
        local dev datasets).

        Filters applied in order (short-circuit on first failure):
          T1  Price >= $5, 50d avg volume >= $2M traded (price × volume)
          T2  Market health: VIX < 35, distribution days <= 4, stage == 2
              (skipped gracefully if market_health_daily has no data for day)
          T3  Trend template: stock Weinstein stage == 2, Minervini score >= 7
              for 'filtered'; >= 8 with 52w-high proximity for 'advanced'
              (skipped gracefully if trend_template_data has no data for day)
          T4  Valid stop: stoplevel in buy_sell_daily must be < entry (already
              in signal data). Falls back to 2×ATR, then 8% floor.
        """
        self.cur.execute(
            "SELECT symbol, entry_price, stoplevel, atr FROM buy_sell_daily "
            "WHERE date = %s AND signal = 'BUY' ORDER BY symbol",
            (day,),
        )
        raw_signals = self.cur.fetchall()
        if not raw_signals:
            return []

        # --- T2: market health (cached per day) ---
        self.cur.execute(
            "SELECT market_stage, distribution_days_4w, vix_level FROM market_health_daily "
            "WHERE date <= %s AND date >= %s::date - INTERVAL '5 days' ORDER BY date DESC LIMIT 1",
            (day, day),
        )
        mh = self.cur.fetchone()
        if mh is not None:
            mkt_stage, dist_days, vix = (int(mh[0] or 0), int(mh[1] or 0), float(mh[2] or 0))
            if vix > 35.0 or dist_days > 4 or mkt_stage != 2:
                return []  # Market-wide reject: no trades today

        # --- Pre-fetch trend template data for all symbols on this day ---
        symbols = [r[0] for r in raw_signals]
        self.cur.execute(
            """
            SELECT DISTINCT ON (symbol) symbol, weinstein_stage, minervini_trend_score,
                   percent_from_52w_high, percent_from_52w_low
            FROM trend_template_data
            WHERE symbol = ANY(%s) AND date <= %s
              AND date >= %s::date - INTERVAL '10 days'
            ORDER BY symbol, date DESC
            """,
            (symbols, day, day),
        )
        trend_rows = {r[0]: r[1:] for r in self.cur.fetchall()}

        # --- Per-symbol evaluation ---
        qualified = []
        for symbol, entry_price, stop_level, sig_atr in raw_signals:
            if symbol in self.positions:
                continue
            if entry_price is None or float(entry_price) <= 0:
                continue
            entry = float(entry_price)

            # T1: price floor
            if entry < 5.0:
                continue

            # T1: volume check — 50d avg dollar volume >= $2M
            self.cur.execute(
                "SELECT AVG(close * volume) FROM ("
                "  SELECT close, volume FROM price_daily WHERE symbol=%s AND date <= %s"
                "  ORDER BY date DESC LIMIT 50) sub",
                (symbol, day),
            )
            vrow = self.cur.fetchone()
            avg_dollar_vol = float(vrow[0]) if vrow and vrow[0] else 0
            if avg_dollar_vol < 2_000_000:
                continue

            # T3: trend template (skip gracefully if no data)
            trend = trend_rows.get(symbol)
            minervini = 0
            if trend is not None:
                stock_stage = int(trend[0]) if trend[0] is not None else 0
                minervini = int(trend[1]) if trend[1] is not None else 0
                pct_from_high = float(trend[2]) if trend[2] is not None else 100.0

                min_score = 8 if self.strategy == "advanced" else 7
                if stock_stage != 2:
                    continue
                if minervini < min_score:
                    continue
                # Advanced: also require within 25% of 52w high (not overextended)
                if self.strategy == "advanced" and pct_from_high > 25.0:
                    continue

            # T4: compute stop (use signal stoplevel → 2×ATR → 8% floor)
            atr_val = float(sig_atr) if sig_atr else None
            if stop_level is not None and float(stop_level) > 0 and float(stop_level) < entry:
                stop = float(stop_level)
            elif atr_val and atr_val > 0:
                stop = entry - 2.0 * atr_val
            else:
                stop = entry * 0.92
            stop = max(stop, entry * 0.92)
            if stop >= entry:
                continue

            # Composite score: rank by Minervini score for 'advanced'
            composite = minervini

            qualified.append({
                "symbol": symbol,
                "entry_price": entry,
                "stop_loss_price": stop,
                "sqs": composite,
                "composite_score": composite,
            })

        # Rank by composite score descending
        qualified.sort(key=lambda x: x["composite_score"], reverse=True)
        return qualified

    def _close_position(self, symbol, price, reason, day, partial=False):
        pos = self.positions.get(symbol)
        if pos is None:
            return
        self.cash += pos["remaining_quantity"] * price
        risk = pos["entry_price"] - pos["initial_stop"]
        r_multiple = ((price - pos["entry_price"]) / risk) if risk > 0 else 0
        self.closed_trades.append({
            "symbol": symbol,
            "entry_date": pos["entry_date"],
            "exit_date": day,
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "quantity": pos["remaining_quantity"],
            "reason": reason,
            "r_multiple": r_multiple,
            "pnl_dollars": (price - pos["entry_price"]) * pos["remaining_quantity"],
            "pnl_pct": (price - pos["entry_price"]) / pos["entry_price"] * 100,
            "days_held": pos["days_held"],
            "partial_exits": pos["partial_exits"],
            "sqs": pos["sqs"],
            "composite": pos["composite"],
        })
        del self.positions[symbol]

    def _partial_close(self, symbol, price, fraction, stage, day, new_stop=None):
        pos = self.positions.get(symbol)
        if pos is None:
            return
        shares = max(1, int(pos["remaining_quantity"] * fraction))
        shares = min(shares, pos["remaining_quantity"])
        self.cash += shares * price
        risk = pos["entry_price"] - pos["initial_stop"]
        r_multiple = ((price - pos["entry_price"]) / risk) if risk > 0 else 0
        pos["partial_exits"].append({
            "date": day, "price": price, "shares": shares,
            "stage": stage, "r_multiple": r_multiple,
            "pnl": (price - pos["entry_price"]) * shares,
        })
        pos["remaining_quantity"] -= shares
        pos["target_hits"] += 1
        if new_stop is not None:
            pos["stop"] = max(pos["stop"], new_stop)
        if pos["remaining_quantity"] <= 0:
            self._close_position(symbol, price, f"{stage}_FULL", day)

    def _compute_metrics(self):
        if not self.closed_trades:
            print("\nNo trades taken.\n")
            return {"strategy": self.strategy, "closed_trades": 0}
        ending_equity = self._equity()
        total_return_pct = (ending_equity - self.initial_capital) / self.initial_capital * 100
        wins = [t for t in self.closed_trades if t["r_multiple"] > 0]
        losses = [t for t in self.closed_trades if t["r_multiple"] <= 0]
        win_rate = len(wins) / len(self.closed_trades) * 100
        avg_win_r = statistics.mean(t["r_multiple"] for t in wins) if wins else 0
        avg_loss_r = statistics.mean(t["r_multiple"] for t in losses) if losses else 0
        avg_r = statistics.mean(t["r_multiple"] for t in self.closed_trades)
        gross_gain = sum(t["pnl_dollars"] for t in wins) + sum(
            sum(p["pnl"] for p in t["partial_exits"] if p["pnl"] > 0) for t in self.closed_trades
        )
        gross_loss = abs(sum(t["pnl_dollars"] for t in losses))
        profit_factor = (gross_gain / gross_loss) if gross_loss > 0 else float("inf")
        expectancy = (win_rate / 100 * avg_win_r) + ((1 - win_rate / 100) * avg_loss_r)
        peak = self.equity_curve[0][1]
        max_dd_pct = 0
        for _, eq in self.equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak * 100
            max_dd_pct = max(max_dd_pct, dd)
        rets = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i-1][1]
            cur = self.equity_curve[i][1]
            if prev > 0:
                rets.append((cur - prev) / prev)
        sharpe = 0.0
        if len(rets) > 1 and statistics.stdev(rets) > 0:
            sharpe = (statistics.mean(rets) / statistics.stdev(rets)) * (252 ** 0.5)
        sortino = 0.0
        downside = [r for r in rets if r < 0]
        if len(downside) > 1:
            dstd = statistics.stdev(downside)
            if dstd > 0:
                sortino = (statistics.mean(rets) / dstd) * (252 ** 0.5)
        years = (self.end - self.start).days / 365.25
        cagr = ((ending_equity / self.initial_capital) ** (1.0 / years) - 1) * 100 if years > 0 else 0
        spy_return = self._spy_return()
        by_year = self._per_year()
        avg_hold = statistics.mean(t["days_held"] for t in self.closed_trades)
        report = {
            "strategy": self.strategy,
            "period": f"{self.start} -> {self.end}",
            "initial_capital": self.initial_capital,
            "ending_equity": round(ending_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "cagr_pct": round(cagr, 2),
            "spy_buy_hold_pct": round(spy_return, 2) if spy_return is not None else None,
            "alpha_vs_spy_pct": round(total_return_pct - spy_return, 2) if spy_return is not None else None,
            "closed_trades": len(self.closed_trades),
            "open_at_end": len(self.positions),
            "win_rate_pct": round(win_rate, 1),
            "avg_r_per_trade": round(avg_r, 2),
            "avg_win_r": round(avg_win_r, 2),
            "avg_loss_r": round(avg_loss_r, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy_r": round(expectancy, 3),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "avg_hold_days": round(avg_hold, 1),
            "per_year": by_year,
        }
        self._print_report(report)
        return report

    def _spy_return(self):
        try:
            self.cur.execute(
                "SELECT close FROM price_daily WHERE symbol = 'SPY' AND date >= %s ORDER BY date ASC LIMIT 1",
                (self.start,),
            )
            r = self.cur.fetchone()
            spy_start = float(r[0]) if r else None
            self.cur.execute(
                "SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s ORDER BY date DESC LIMIT 1",
                (self.end,),
            )
            r = self.cur.fetchone()
            spy_end = float(r[0]) if r else None
            if spy_start and spy_end and spy_start > 0:
                return (spy_end - spy_start) / spy_start * 100
        except Exception:
            pass
        return None

    def _per_year(self):
        by_year = defaultdict(list)
        for t in self.closed_trades:
            by_year[t["entry_date"].year].append(t)
        result = {}
        for year, trades in sorted(by_year.items()):
            wins_y = [t for t in trades if t["r_multiple"] > 0]
            result[year] = {
                "trades": len(trades),
                "win_rate": round(len(wins_y) / len(trades) * 100, 1),
                "pnl_dollars": round(sum(t["pnl_dollars"] for t in trades), 0),
                "avg_r": round(statistics.mean(t["r_multiple"] for t in trades), 2),
            }
        return result

    def _print_report(self, r):
        spy_str = ""
        if r.get("spy_buy_hold_pct") is not None:
            spy_str = f"  vs SPY: {r['spy_buy_hold_pct']:+.1f}%  alpha: {r['alpha_vs_spy_pct']:+.1f}%"
        print(f"\n{'='*70}")
        print(f"BACKTEST REPORT  [{r['strategy'].upper()}]")
        print(f"{'='*70}")
        print(f"  Period     : {r['period']}")
        print(f"  Total Ret  : {r['total_return_pct']:+.2f}%   CAGR: {r['cagr_pct']:+.2f}%{spy_str}")
        print(f"  Ending Eq  : ${r['ending_equity']:,.0f}")
        print(f"  Trades     : {r['closed_trades']}  Win Rate: {r['win_rate_pct']:.1f}%")
        print(f"  Avg R      : {r['avg_r_per_trade']:+.2f}  (W: {r['avg_win_r']:+.2f} / L: {r['avg_loss_r']:+.2f})")
        print(f"  Prof.Factor: {r['profit_factor']:.2f}   Expect: {r['expectancy_r']:+.3f}R")
        print(f"  Max DD     : {r['max_drawdown_pct']:.2f}%")
        print(f"  Sharpe     : {r['sharpe_ratio']:.2f}   Sortino: {r['sortino_ratio']:.2f}")
        print(f"  Avg Hold   : {r['avg_hold_days']:.1f}d")
        if r.get("per_year"):
            print("  Year-by-Year:")
            for yr, ydata in r["per_year"].items():
                print(f"    {yr}: {ydata['trades']:3d} trades | WR {ydata['win_rate']:4.1f}% | "
                      f"Avg R {ydata['avg_r']:+.2f} | P&L ${ydata['pnl_dollars']:+,.0f}")
        print("  Last 15 Trades:")
        for t in self.closed_trades[-15:]:
            print(f"  {t['symbol']:<6}  {str(t['entry_date']):>10} -> {str(t['exit_date']):>10}  "
                  f"{t['days_held']:>3}d  ${t['entry_price']:>7.2f} ${t['exit_price']:>7.2f}  "
                  f"{t['r_multiple']:>+5.2f}  ${t['pnl_dollars']:>+8.0f}  {t['reason']}")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--start", type=str, default="2025-01-01")
    parser.add_argument("--end", type=str, default="2025-12-31")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--max-positions", type=int, default=12)
    parser.add_argument("--strategy", choices=STRATEGIES, default="advanced",
                        help="raw=no filters, filtered=5-tier only, advanced=full")
    parser.add_argument("--risk-pct", type=float, default=0.75)
    parser.add_argument("--max-hold", type=int, default=20)
    args = parser.parse_args()
    bt = Backtester(
        start_date=_date.fromisoformat(args.start),
        end_date=_date.fromisoformat(args.end),
        initial_capital=args.capital,
        max_positions=args.max_positions,
        strategy=args.strategy,
        base_risk_pct=args.risk_pct,
        max_hold_days=args.max_hold,
    )
    report = bt.run()
    summary = {k: v for k, v in report.items() if k != "per_year"}
    print(f"\n[Done] JSON:\n{json.dumps(summary, indent=2, default=str)}\n")
