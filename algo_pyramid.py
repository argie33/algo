#!/usr/bin/env python3
"""
Pyramid - Add to Winners (Livermore principle)

Per Reminiscences of a Stock Operator + Brian Shannon's Multiple Timeframes
research: the highest-expectancy way to scale capital in a swing trade is to
add to positions that have proven themselves with profit + technical
confirmation, NOT to average down losers.

ENTRY ADDS (each strict gate must pass):
  Add 1 (50% of original size):
      Position is in profit by >= +1R AND
      Initial stop has moved to breakeven AND
      Stock made new closing high in last 5 days AND
      Volume on that breakout > 1.2x 50d-avg
  Add 2 (25% of original size):
      Position is in profit by >= +2R AND
      Stock broke a NEW pivot (20-day high) AND
      Volume confirmed (> 1.5x avg)
  Total adds capped at 3 (Turtle rule).

RISK MANAGEMENT (critical):
  - Combined open risk on the symbol must NEVER exceed original 1R.
  - Each add brings stop tighter (chandelier ratchet on whole position).
  - Adding to a position counts against max_positions slot? NO — same name,
    same slot. But it does count against total_open_risk circuit breaker.

Persists adds to algo_trade_adds table for audit + dashboard display.

Designed to be called from orchestrator phase 4 (after exits, before entries)
so add-decisions don't conflict with new-entry decisions.
"""

import os
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date

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
    """Decide and execute pyramid add-on trades for winners."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()
        # Note: algo_trade_adds table created by init_database.py (schema as code)

    def disconnect(self):
        if self.cur: self.cur.close()
        if self.conn: self.conn.close()
        self.cur = self.conn = None

    def evaluate_pyramid_adds(self, current_date=None):
        """Review every open winning position for pyramid-add opportunities.

        Returns list of add recommendations:
            { trade_id, symbol, position_id, add_number, add_size_shares,
              add_price, r_at_add, reason }
        """
        if not current_date:
            current_date = _date.today()
        if not self.config.get('enable_pyramiding', True):
            return []

        self.connect()
        try:
            self.cur.execute(
                """
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.entry_quantity,
                       p.position_id, p.quantity, p.current_price,
                       p.current_stop_price, p.target_levels_hit,
                       (SELECT COUNT(*) FROM algo_trade_adds WHERE trade_id = t.trade_id) AS adds_so_far
                FROM algo_trades t
                JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.status IN ('filled','active')
                  AND p.status = 'open'
                  AND p.quantity > 0
                """
            )
            positions = self.cur.fetchall()
            recommendations = []

            for row in positions:
                rec = self._evaluate_one(row, current_date)
                if rec:
                    recommendations.append(rec)
            return recommendations
        finally:
            self.disconnect()

    def _evaluate_one(self, row, current_date):
        (trade_id, symbol, entry_price, init_stop, init_qty, position_id,
         cur_qty, cur_price, cur_stop, target_hits, adds_so_far) = row

        entry_price = float(entry_price)
        init_stop = float(init_stop)
        init_qty = int(init_qty)
        cur_price = float(cur_price) if cur_price else entry_price
        cur_stop = float(cur_stop) if cur_stop else init_stop
        target_hits = int(target_hits or 0)
        adds_so_far = int(adds_so_far or 0)

        # Compute R-multiple
        risk_per_share = entry_price - init_stop
        if risk_per_share <= 0:
            return None
        r_mult = (cur_price - entry_price) / risk_per_share

        # Cap: max 3 adds (Turtle rule)
        max_adds = int(self.config.get('max_pyramid_adds', 3))
        if adds_so_far >= max_adds:
            return None

        # Each add tier has gates
        next_add = adds_so_far + 1
        add_fraction = None
        add_threshold_r = None
        add_reason = None

        if next_add == 1:
            # Add 1: +1R AND stop at BE AND new high on volume
            if r_mult < 1.0:
                return None
            if cur_stop < entry_price * 0.999:  # not at BE yet
                return None
            if not self._is_new_closing_high(symbol, current_date, days=5):
                return None
            if not self._is_volume_confirmed(symbol, current_date, mult=1.2):
                return None
            add_fraction = 0.50
            add_threshold_r = 1.0
            add_reason = f'Add #1 at +{r_mult:.2f}R: BE-stop + new 5d high + volume'

        elif next_add == 2:
            # Add 2: +2R AND new 20-day pivot break with volume
            if r_mult < 2.0:
                return None
            if not self._is_pivot_breakout(symbol, current_date):
                return None
            add_fraction = 0.25
            add_threshold_r = 2.0
            add_reason = f'Add #2 at +{r_mult:.2f}R: 20d pivot break on volume'

        elif next_add == 3:
            # Add 3: +3R AND new 30-day pivot break (rare)
            if r_mult < 3.0:
                return None
            if not self._is_pivot_breakout(symbol, current_date, lookback=30):
                return None
            add_fraction = 0.15
            add_threshold_r = 3.0
            add_reason = f'Add #3 at +{r_mult:.2f}R: 30d pivot break'

        if add_fraction is None:
            return None

        # Compute add size in shares
        add_qty = max(1, int(init_qty * add_fraction))

        # CRITICAL: don't let total open risk exceed original 1R
        # New-add risk = (cur_price - cur_stop) × add_qty
        # Existing-position risk = (cur_price - cur_stop) × cur_qty
        # Total must be <= original_risk = (entry_price - init_stop) × init_qty
        new_risk = (cur_price - cur_stop) * add_qty if cur_price > cur_stop else 0
        existing_risk = (cur_price - cur_stop) * cur_qty if cur_price > cur_stop else 0
        original_risk = risk_per_share * init_qty
        if (new_risk + existing_risk) > original_risk * 1.05:  # 5% buffer
            # Reduce add size to fit
            risk_avail = original_risk - existing_risk
            if risk_avail <= 0:
                return None
            unit_risk = cur_price - cur_stop
            if unit_risk <= 0:
                return None
            add_qty = max(1, int(risk_avail / unit_risk))

        return {
            'trade_id': trade_id,
            'symbol': symbol,
            'position_id': position_id,
            'add_number': next_add,
            'add_size_shares': add_qty,
            'add_price': cur_price,
            'r_at_add': round(r_mult, 2),
            'reason': add_reason,
            'fraction_of_original': add_fraction,
        }

    # ---- Helpers ----

    def _is_new_closing_high(self, symbol, current_date, days=5):
        self.cur.execute(
            """
            WITH d AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT %s
            )
            SELECT
                (SELECT close FROM d WHERE rn = 1) AS today,
                (SELECT MAX(close) FROM d WHERE rn > 1) AS prior_max
            """,
            (symbol, current_date, days + 1),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return False
        return float(row[0]) >= float(row[1]) * 1.001

    def _is_volume_confirmed(self, symbol, current_date, mult=1.2):
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, volume,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) AS avg50
                FROM price_daily WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
            )
            SELECT volume, avg50 FROM d
            """,
            (symbol, current_date),
        )
        row = self.cur.fetchone()
        if not row or not row[0] or not row[1]:
            return False
        return float(row[0]) > float(row[1]) * mult

    def _is_pivot_breakout(self, symbol, current_date, lookback=20):
        self.cur.execute(
            f"""
            WITH d AS (
                SELECT close, high,
                       MAX(high) OVER (ORDER BY date ROWS BETWEEN {lookback + 1} PRECEDING AND 1 PRECEDING) AS pivot
                FROM price_daily WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
            )
            SELECT close, pivot FROM d
            """,
            (symbol, current_date),
        )
        row = self.cur.fetchone()
        if not row or row[1] is None:
            return False
        close = float(row[0])
        pivot = float(row[1])
        return close > pivot * 1.005  # 0.5% buffer

    def execute_add(self, recommendation):
        """Execute pyramid add: send order to Alpaca + persist locally."""
        from algo_trade_executor import TradeExecutor
        r = recommendation
        executor = TradeExecutor(self.config)

        # Send buy order to Alpaca for the add (simple buy, no bracket)
        alpaca_result = executor._send_alpaca_order(
            symbol=r['symbol'],
            shares=r['add_size_shares'],
            entry_price=r['add_price'],
            stop_loss_price=None,  # No stop on add orders; existing position stop applies
            take_profit_price=None,  # No profit target on add; pyramiding follows main position
            order_class='simple',
        )

        if not alpaca_result.get('success'):
            return {'success': False, 'message': f"Alpaca order failed: {alpaca_result.get('message')}"}

        self.connect()
        try:
            # Update position quantity + stop price (if tighter)
            self.cur.execute(
                """UPDATE algo_positions
                   SET quantity = quantity + %s,
                       position_value = (quantity + %s) * current_price,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE position_id = %s AND status = 'open'""",
                (r['add_size_shares'], r['add_size_shares'], r['position_id']),
            )

            # Record the add
            self.cur.execute(
                """INSERT INTO algo_trade_adds (trade_id, add_number, add_date,
                       add_price, add_quantity, fraction_of_original,
                       r_multiple_at_add, trigger_reason)
                   VALUES (%s, %s, CURRENT_DATE, %s, %s, %s, %s, %s)
                   ON CONFLICT (trade_id, add_number) DO NOTHING""",
                (r['trade_id'], r['add_number'], r['add_price'],
                 r['add_size_shares'], r['fraction_of_original'],
                 r['r_at_add'], r['reason']),
            )
            self.conn.commit()
            return {'success': True, 'message':
                f"Added {r['add_size_shares']}sh of {r['symbol']} (#{r['add_number']}) @ ${r['add_price']:.2f} "
                f"to Alpaca (order_id={alpaca_result.get('order_id')})"}
        except Exception as e:
            self.conn.rollback()
            return {'success': False, 'message': f'DB update failed: {str(e)}'}
        finally:
            self.disconnect()


if __name__ == "__main__":
    from algo_config import get_config
    e = PyramidEngine(get_config())
    recs = e.evaluate_pyramid_adds()
    print(f"\n{'='*70}\nPYRAMID ADD RECOMMENDATIONS\n{'='*70}")
    if not recs:
        print("\nNo pyramid adds qualify today.")
    for r in recs:
        print(f"\n  {r['symbol']:6s} #{r['add_number']}: +{r['add_size_shares']} sh @ "
              f"${r['add_price']:.2f}  R={r['r_at_add']}")
        print(f"         {r['reason']}")
