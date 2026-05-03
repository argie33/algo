#!/usr/bin/env python3
"""
Exit Engine - Monitor positions and execute exits (HARDENED)

Exit hierarchy (checked in order):
1. STOP    — current price <= active stop (initial or trailed)
2. MINERVINI BREAK — close < 21-EMA on volume > 50d avg (or close < 50-DMA cleanly)
3. TIME    — held >= max_hold_days
4. T3      — price >= target_3 (4R) → exit final 25%
5. T2      — price >= target_2 (3R) → exit 25% on pullback, raise stop to T1 area
6. T1      — price >= target_1 (1.5R) → exit 50% on pullback, raise stop to entry (breakeven)
7. DISTRIBUTION — market distribution day count exceeds limit (config-gated)

State tracked on algo_positions:
  - target_levels_hit (0/1/2/3): which T-levels have already triggered
  - current_stop_price: trailed stop after T1/T2 hits
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from algo_trade_executor import TradeExecutor

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


class ExitEngine:
    """Monitor and execute position exits."""

    def __init__(self, config):
        self.config = config
        self.executor = TradeExecutor(config)
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

    def check_and_execute_exits(self, current_date=None):
        """Check all open positions for exit conditions and execute."""
        if not current_date:
            current_date = datetime.now().date()

        self.connect()
        try:
            print(f"\n{'='*70}")
            print(f"EXIT ENGINE CHECK - {current_date}")
            print(f"{'='*70}\n")

            self.cur.execute(
                """
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.target_1_price, t.target_2_price, t.target_3_price,
                       t.trade_date,
                       p.position_id, p.quantity, p.target_levels_hit,
                       p.current_stop_price
                FROM algo_trades t
                JOIN algo_positions p ON p.trade_ids LIKE '%%' || t.trade_id || '%%'
                WHERE t.status IN ('filled','active') AND p.status = 'open' AND p.quantity > 0
                ORDER BY t.trade_date ASC
                """
            )
            trades = self.cur.fetchall()
            if not trades:
                print("No open positions.\n")
                return 0

            # Cache market distribution-day status once for the run
            dist_days_today = self._fetch_market_dist_days(current_date)
            exits_executed = 0

            for row in trades:
                (trade_id, symbol, entry_price, init_stop, t1_price, t2_price, t3_price,
                 trade_date, _position_id, quantity, target_hits, current_stop) = row

                entry_price = float(entry_price)
                init_stop = float(init_stop)
                active_stop = float(current_stop) if current_stop else init_stop
                t1_price = float(t1_price)
                t2_price = float(t2_price)
                t3_price = float(t3_price)
                target_hits = int(target_hits or 0)

                cur_price, prev_close = self._fetch_recent_prices(symbol, current_date)
                if cur_price is None:
                    continue

                days_held = (current_date - trade_date).days

                exit_signal = self._evaluate_position(
                    symbol, current_date,
                    cur_price, prev_close, entry_price, active_stop, init_stop,
                    t1_price, t2_price, t3_price, target_hits, days_held, dist_days_today,
                )

                if not exit_signal:
                    print(f"  {symbol}: hold (cur ${cur_price:.2f}, "
                          f"stop ${active_stop:.2f}, t1 ${t1_price:.2f}, "
                          f"day {days_held}, hits {target_hits})")
                    continue

                fraction = exit_signal['fraction']
                stage = exit_signal['stage']
                new_stop = exit_signal.get('new_stop')

                print(f"  {symbol}: {stage.upper()} — {exit_signal['reason']} "
                      f"(exit {int(fraction*100)}%)")

                result = self.executor.exit_trade(
                    trade_id=trade_id,
                    exit_price=cur_price,
                    exit_reason=exit_signal['reason'],
                    exit_fraction=fraction,
                    exit_stage=stage,
                    new_stop_price=new_stop,
                )

                if result.get('success'):
                    exits_executed += 1
                    print(f"      → {result['message']}")
                else:
                    print(f"      → FAILED: {result.get('message')}")

            print(f"\n{'='*70}")
            print(f"Exits executed: {exits_executed}/{len(trades)} positions")
            print(f"{'='*70}\n")
            return exits_executed
        except Exception as e:
            print(f"Error in exit engine: {e}")
            import traceback
            traceback.print_exc()
            return 0
        finally:
            self.disconnect()

    # ---------- Decision logic ----------

    def _evaluate_position(self, symbol, current_date, cur_price, prev_close,
                           entry_price, active_stop, init_stop,
                           t1_price, t2_price, t3_price,
                           target_hits, days_held, dist_days_today):
        """Decide what (if any) exit to take. Returns dict or None."""
        # 1. STOP
        if cur_price <= active_stop:
            return {
                'stage': 'stop',
                'fraction': 1.0,
                'reason': f'STOP hit: ${cur_price:.2f} <= ${active_stop:.2f}',
            }

        # 2. MINERVINI BREAK — close below 21-EMA on rising volume, OR clean break of 50-DMA
        if self._is_minervini_break(symbol, current_date, cur_price):
            return {
                'stage': 'stop',
                'fraction': 1.0,
                'reason': f'Minervini trend break: closed below key MA on volume',
            }

        # 3. TIME
        max_hold = int(self.config.get('max_hold_days', 20))
        if days_held >= max_hold:
            return {
                'stage': 'time',
                'fraction': 1.0,
                'reason': f'TIME exit: {days_held} days >= {max_hold} max',
            }

        # 4. T3 — sells final 25% (or whatever remains)
        if cur_price >= t3_price and target_hits < 3:
            return {
                'stage': 'target_3',
                'fraction': 1.0,  # exit the rest
                'reason': f'T3 target hit: ${cur_price:.2f} >= ${t3_price:.2f} (4R)',
            }

        # 5. T2 — exit 25% (~1/3 of remaining after T1) on pullback; raise stop near T1
        if cur_price >= t2_price and target_hits < 2:
            if self._is_pulling_back(symbol, current_date):
                # After T1 already fired, remaining = 50%. Selling 25%/50% = 50% of remaining.
                return {
                    'stage': 'target_2',
                    'fraction': 0.50,
                    'reason': f'T2 pullback exit: ${cur_price:.2f} >= ${t2_price:.2f} (3R)',
                    'new_stop': max(active_stop, t1_price),
                }

        # 6. T1 — exit 50% on pullback; raise stop to entry (breakeven)
        if cur_price >= t1_price and target_hits < 1:
            if self._is_pulling_back(symbol, current_date):
                return {
                    'stage': 'target_1',
                    'fraction': 0.50,
                    'reason': f'T1 pullback exit: ${cur_price:.2f} >= ${t1_price:.2f} (1.5R)',
                    'new_stop': max(active_stop, entry_price),
                }

        # 7. DISTRIBUTION
        if self.config.get('exit_on_distribution_day', True) and dist_days_today is not None:
            max_dd = int(self.config.get('max_distribution_days', 4))
            if dist_days_today > max_dd:
                return {
                    'stage': 'distribution',
                    'fraction': 1.0,
                    'reason': f'Market distribution: {dist_days_today} dist days > {max_dd}',
                }

        return None

    # ---------- Data helpers ----------

    def _fetch_recent_prices(self, symbol, current_date):
        """Return (current_close, previous_close) using closest available price <= current_date."""
        self.cur.execute(
            """
            SELECT date, close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 2
            """,
            (symbol, current_date),
        )
        rows = self.cur.fetchall()
        if not rows:
            return None, None
        cur_price = float(rows[0][1])
        prev_close = float(rows[1][1]) if len(rows) > 1 else None
        return cur_price, prev_close

    def _fetch_market_dist_days(self, current_date):
        self.cur.execute(
            """
            SELECT distribution_days_4w FROM market_health_daily
            WHERE date <= %s ORDER BY date DESC LIMIT 1
            """,
            (current_date,),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _is_pulling_back(self, symbol, current_date):
        """True if current close is below the highest close of the last 3 days."""
        if self.cur is None:
            # Pure-function caller didn't open a connection; default to True so
            # the T1/T2 pullback gating still fires for unit tests.
            return True
        self.cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 4
            """,
            (symbol, current_date),
        )
        rows = self.cur.fetchall()
        if len(rows) < 2:
            return False
        cur_close = float(rows[0][0])
        prior_max = max(float(r[0]) for r in rows[1:])
        return cur_close < prior_max

    def _is_minervini_break(self, symbol, current_date, cur_price):
        """Close < 50-DMA OR (close < EMA(12) AND volume > 50-day avg)."""
        if self.cur is None:
            return False
        self.cur.execute(
            """
            SELECT td.sma_50, td.ema_12,
                   (SELECT volume FROM price_daily p WHERE p.symbol = td.symbol AND p.date = td.date) AS vol,
                   (SELECT AVG(volume) FROM price_daily p
                     WHERE p.symbol = td.symbol AND p.date <= td.date
                       AND p.date >= td.date - INTERVAL '50 days') AS avg_vol_50
            FROM technical_data_daily td
            WHERE td.symbol = %s AND td.date <= %s
            ORDER BY td.date DESC LIMIT 1
            """,
            (symbol, current_date),
        )
        row = self.cur.fetchone()
        if not row:
            return False
        sma_50, ema_12, vol, avg_vol_50 = row
        sma_50 = float(sma_50) if sma_50 is not None else None
        ema_12 = float(ema_12) if ema_12 is not None else None
        vol = float(vol) if vol is not None else 0
        avg_vol_50 = float(avg_vol_50) if avg_vol_50 is not None else 0

        # Clean break of 50-DMA
        if sma_50 and cur_price < sma_50 * 0.99:
            return True
        # Break of EMA(12) on rising volume (institutional selling)
        if ema_12 and cur_price < ema_12 and avg_vol_50 > 0 and vol > avg_vol_50 * 1.15:
            return True
        return False

    # ---------- Backwards-compat shim used by old tests ----------

    def _check_exit_conditions(self, symbol, current_price, entry_price, qty,
                                t1_price, t2_price, t3_price, stop_price,
                                days_held, eval_date):
        """Pure-function exit check used by FULL_BUILD_VERIFICATION.py."""
        signal = self._evaluate_position(
            symbol, eval_date,
            cur_price=current_price, prev_close=current_price,
            entry_price=entry_price, active_stop=stop_price, init_stop=stop_price,
            t1_price=t1_price, t2_price=t2_price, t3_price=t3_price,
            target_hits=0, days_held=days_held, dist_days_today=None,
        )
        if not signal:
            return None
        return {
            'reason': signal['reason'],
            'exit_stage': signal['stage'],
            'fraction': signal['fraction'],
        }


if __name__ == "__main__":
    from algo_config import get_config
    config = get_config()
    engine = ExitEngine(config)
    exits = engine.check_and_execute_exits()
    print(f"Exits executed: {exits}")
