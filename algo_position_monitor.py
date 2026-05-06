#!/usr/bin/env python3
"""
Position Monitor - Institutional-grade daily position health checks

Runs each trading day on every open position. For each one:
  1. Refresh current price + position value + unrealized P&L
  2. Recompute trailing stop using ATR / swing low / 50-DMA — STOPS ONLY GO UP
  3. Score position health across factors:
        a. Relative strength vs SPY (degrading = warning)
        b. Sector strength (turned weak = warning)
        c. Distance from peak unrealized (giving back gains = warning)
        d. Time decay (over half of max_hold without progress = warning)
        e. Earnings proximity (block_window approaching = warning)
        f. Distribution day count
  4. Aggregate health flags. >= halt_flag_count -> propose early exit.
  5. Persist updated state on algo_positions and write audit entries.

The monitor PROPOSES adjustments — actual stop-raising executes via
TradeExecutor.exit_trade(new_stop_price=...) in the orchestrator.
"""

import os
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date

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


class PositionMonitor:
    """Daily position health checker and stop adjuster."""

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
        self.cur = self.conn = None

    def check_stale_orders(self, current_date=None):
        """Check for orders stuck in pending state >1 hour. Alert if found.

        Stuck orders = likely API issue or rejection. Should be resolved manually.
        """
        if not current_date:
            current_date = _date.today()

        self.connect()
        try:
            self.cur.execute("""
                SELECT trade_id, symbol, entry_price, quantity, created_at
                FROM algo_trades
                WHERE status = 'pending'
                  AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 hour'
                ORDER BY created_at ASC
            """)
            stale_orders = self.cur.fetchall()
            if stale_orders:
                print(f"\n  [ALERT] Found {len(stale_orders)} orders pending >1 hour:")
                for row in stale_orders:
                    trade_id, symbol, price, qty, created_at = row
                    age_minutes = int((datetime.now() - created_at).total_seconds() / 60)
                    print(f"    {trade_id} {symbol} {qty}@{price} (pending {age_minutes}m)")
                return {'status': 'STALE_ORDERS_FOUND', 'count': len(stale_orders), 'orders': stale_orders}
            else:
                return {'status': 'OK', 'count': 0}
        finally:
            self.disconnect()

    def check_sector_concentration(self, current_date=None):
        """Check if portfolio is overly concentrated in one sector.

        Alert if >3 positions in same sector (concentration risk).
        """
        if not current_date:
            current_date = _date.today()

        try:
            self.cur.execute("""
                SELECT cp.sector, COUNT(DISTINCT ap.symbol) as position_count
                FROM algo_positions ap
                JOIN company_profile cp ON ap.symbol = cp.ticker
                WHERE ap.status = 'open' AND ap.quantity > 0
                GROUP BY cp.sector
                HAVING COUNT(DISTINCT ap.symbol) > 3
                ORDER BY position_count DESC
            """)
            concentrated = self.cur.fetchall()
            if concentrated:
                print(f"\n  [CONCENTRATION ALERT]")
                for sector, count in concentrated:
                    print(f"    {sector}: {count} positions (>3 is risky)")
                return {'status': 'HIGH_CONCENTRATION', 'sectors': concentrated}
            return {'status': 'OK', 'sectors': []}
        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}

    def review_positions(self, current_date=None):
        """Review every open position. Returns list of recommendations."""
        if not current_date:
            current_date = _date.today()

        self.connect()
        recs = []
        try:
            # Check sector concentration first
            conc = self.check_sector_concentration(current_date)
            if conc['status'] == 'HIGH_CONCENTRATION':
                print(f"  ⚠️  Portfolio concentration risk detected")

            self.cur.execute(
                """
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.target_1_price, t.target_2_price, t.target_3_price,
                       t.trade_date, t.signal_date,
                       p.position_id, p.quantity, p.target_levels_hit,
                       p.current_stop_price, p.current_price
                FROM algo_trades t
                JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.status IN ('filled','active') AND p.status = 'open' AND p.quantity > 0
                """
            )
            positions = self.cur.fetchall()

            print(f"\n{'='*70}")
            print(f"POSITION MONITOR — {current_date}")
            print(f"{'='*70}")
            print(f"Reviewing {len(positions)} open position(s)\n")

            for row in positions:
                rec = self._evaluate_position(row, current_date)
                recs.append(rec)
                self._print_recommendation(rec)
                self._persist_review(rec, current_date)

            self.conn.commit()
            return recs
        finally:
            self.disconnect()

    def _evaluate_position(self, row, current_date):
        (trade_id, symbol, entry_price, init_stop, t1_price, t2_price, t3_price,
         trade_date, signal_date, position_id, quantity, target_hits,
         current_stop, db_current_price) = row

        entry_price = float(entry_price)
        init_stop = float(init_stop)

        # B15: Validate core prices before all calculations
        if entry_price <= 0:
            print(f"ERROR: Invalid entry price {entry_price} for {symbol} — cannot monitor")
            return None
        if init_stop <= 0:
            print(f"ERROR: Invalid stop {init_stop} for {symbol} — cannot monitor")
            return None
        if init_stop >= entry_price:
            print(f"ERROR: Stop {init_stop} >= entry {entry_price} for {symbol} — invalid trade")
            return None
        active_stop = float(current_stop) if current_stop else init_stop
        target_hits = int(target_hits or 0)
        days_held = (current_date - trade_date).days
        max_hold = int(self.config.get('max_hold_days', 20))

        # 1. Current market data
        cur_price, atr, sma_50, ema_12 = self._fetch_current_market(symbol, current_date)
        if cur_price is None:
            cur_price = float(db_current_price) if db_current_price else entry_price

        # B14: Validate current price is positive
        if cur_price is None or cur_price <= 0:
            print(f"WARNING: Invalid current price {cur_price} for {symbol}, using entry price {entry_price}")
            cur_price = entry_price
        if cur_price <= 0:
            print(f"ERROR: Cannot monitor position {symbol} — invalid prices")
            return None

        # P&L
        risk_per_share = entry_price - init_stop
        r_multiple = ((cur_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0
        unrealized_pnl = (cur_price - entry_price) * quantity
        unrealized_pct = ((cur_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

        # 2. Recompute trailing stop (only ratchet UP, never down)
        proposed_stop = self._compute_trailing_stop(
            symbol, current_date, entry_price, active_stop,
            cur_price, atr, sma_50, target_hits, t1_price, t2_price,
        )

        # B16: Validate stop price is below current price (can't sell above market)
        if proposed_stop > cur_price:
            print(f"ERROR: Proposed stop ${proposed_stop:.2f} > current price ${cur_price:.2f} for {symbol}")
            proposed_stop = cur_price - 0.01  # Clamp to 1c below market
            print(f"  Clamped stop to ${proposed_stop:.2f}")

        # 3. Health flags
        flags = []

        # 3a. Relative strength vs SPY (degrading?)
        rs_state = self._check_relative_strength(symbol, current_date)
        if rs_state == 'weakening':
            flags.append('RS_WEAKENING')
        rs_label = rs_state

        # 3b. Sector turned weak?
        sector_state = self._check_sector_health(symbol, current_date)
        if sector_state == 'weakening':
            flags.append('SECTOR_WEAK')

        # 3c. Giving back gains (>33% retrace from peak)?
        peak_pct = self._max_unrealized_pct(symbol, trade_date, current_date, entry_price)
        if peak_pct > 5 and unrealized_pct < peak_pct * 0.66:
            flags.append('GIVING_BACK_GAINS')

        # 3d. Time decay (>= half of max_hold, but no T1 hit yet)
        if days_held >= max_hold * 0.5 and target_hits == 0 and r_multiple < 0.5:
            flags.append('TIME_DECAY_NO_PROGRESS')

        # 3e. Earnings proximity
        days_to_earn = self._days_to_earnings(symbol, current_date)
        if days_to_earn is not None and 0 <= days_to_earn <= 3:
            flags.append(f'EARNINGS_IN_{days_to_earn}D')

        # 3f. Distribution-day stress
        market_dist_days = self._fetch_market_dist_days(current_date)
        if market_dist_days is not None and market_dist_days > int(self.config.get('max_distribution_days', 4)):
            flags.append('MARKET_DISTRIBUTION_STRESS')

        # Decision logic
        halt_flag_count = int(self.config.get('position_halt_flag_count', 2))
        action = 'HOLD'
        action_reason = ''
        urgent_exit = False
        new_stop_recommended = None

        if proposed_stop > active_stop:
            # Always recommend stop-raise when computed
            new_stop_recommended = proposed_stop
            action = 'RAISE_STOP'
            action_reason = f'Trail stop ${active_stop:.2f} -> ${proposed_stop:.2f}'

        if len(flags) >= halt_flag_count:
            action = 'EARLY_EXIT'
            action_reason = f'{len(flags)} health flags: {", ".join(flags)}'
            urgent_exit = True

        # Special case: earnings within 1-2 days = always exit
        if days_to_earn is not None and 0 <= days_to_earn <= 2:
            action = 'EARLY_EXIT'
            action_reason = f'Earnings in {days_to_earn} day(s) — flatten before report'
            urgent_exit = True

        return {
            'trade_id': trade_id,
            'symbol': symbol,
            'position_id': position_id,
            'days_held': days_held,
            'quantity': quantity,
            'entry_price': entry_price,
            'current_price': cur_price,
            'r_multiple': round(r_multiple, 2),
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_pct': round(unrealized_pct, 2),
            'active_stop': active_stop,
            'proposed_stop': proposed_stop,
            'target_hits': target_hits,
            'rs_label': rs_label,
            'sector_state': sector_state,
            'flags': flags,
            'days_to_earnings': days_to_earn,
            'action': action,
            'action_reason': action_reason,
            'urgent_exit': urgent_exit,
            'new_stop_recommended': new_stop_recommended,
        }

    # ---------- Helpers ----------

    def _fetch_current_market(self, symbol, current_date):
        self.cur.execute(
            """
            SELECT pd.close, td.atr, td.sma_50, td.ema_12
            FROM price_daily pd
            LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
            WHERE pd.symbol = %s AND pd.date <= %s
            ORDER BY pd.date DESC LIMIT 1
            """,
            (symbol, current_date),
        )
        row = self.cur.fetchone()
        if not row:
            return None, None, None, None
        return (
            float(row[0]) if row[0] is not None else None,
            float(row[1]) if row[1] is not None else None,
            float(row[2]) if row[2] is not None else None,
            float(row[3]) if row[3] is not None else None,
        )

    def _compute_trailing_stop(self, symbol, current_date, entry_price, active_stop,
                                cur_price, atr, sma_50, target_hits,
                                t1_price, t2_price):
        """Stop ratchets up only.

        - Before T1: keep initial stop OR use 50-DMA (whichever higher) capped at entry-2*ATR
        - After T1: stop = entry (breakeven) at minimum, or trail tighter via ATR
        - After T2: stop = T1 area or 1.5*ATR below close, whichever higher
        """
        candidates = [active_stop]

        if atr and cur_price:
            candidates.append(cur_price - (2.0 * atr))
        if sma_50 and sma_50 < cur_price:
            candidates.append(sma_50)

        if target_hits >= 1:
            candidates.append(entry_price)  # at least breakeven after T1
        if target_hits >= 2:
            candidates.append(float(t1_price))  # at T1 price after T2

        # Don't let trailing stop get within 1.0 ATR of price (room to breathe)
        if atr and cur_price:
            cap = cur_price - atr
            candidates = [c for c in candidates if c <= cap]
            if not candidates:
                candidates = [cap]

        new_stop = max(candidates)
        # NEVER lower the stop
        return round(max(new_stop, active_stop), 2)

    def _check_relative_strength(self, symbol, current_date):
        """20-day relative return vs SPY: weakening / neutral / strong."""
        stock = self._period_return(symbol, current_date, 20)
        spy = self._period_return('SPY', current_date, 20)
        if stock is None or spy is None:
            return 'unknown'
        excess = stock - spy
        if excess < -0.05:
            return 'weakening'
        if excess > 0.05:
            return 'strong'
        return 'neutral'

    def _check_sector_health(self, symbol, current_date):
        """Is the symbol's sector currently weakening?"""
        self.cur.execute(
            "SELECT sector FROM company_profile WHERE ticker = %s LIMIT 1",
            (symbol,),
        )
        srow = self.cur.fetchone()
        if not srow or not srow[0]:
            return 'unknown'
        sector = srow[0]

        self.cur.execute(
            """
            SELECT current_rank, rank_4w_ago FROM sector_ranking
            WHERE sector_name = %s
              AND date_recorded <= %s
            ORDER BY date_recorded DESC LIMIT 1
            """,
            (sector, current_date),
        )
        row = self.cur.fetchone()
        if not row:
            return 'unknown'
        cur_rank = int(row[0]) if row[0] else 99
        old_rank = int(row[1]) if row[1] else cur_rank
        if cur_rank > old_rank + 3:  # got worse by 3+ ranks
            return 'weakening'
        if cur_rank < old_rank - 3:
            return 'strengthening'
        return 'stable'

    def _max_unrealized_pct(self, symbol, trade_date, current_date, entry_price):
        """Highest closing price since entry, expressed as % gain."""
        self.cur.execute(
            """
            SELECT MAX(close) FROM price_daily
            WHERE symbol = %s AND date >= %s AND date <= %s
            """,
            (symbol, trade_date, current_date),
        )
        row = self.cur.fetchone()
        if not row or not row[0] or entry_price <= 0:
            return 0.0
        return ((float(row[0]) - entry_price) / entry_price) * 100.0

    def _days_to_earnings(self, symbol, current_date):
        """Get days until next earnings. Returns None if earnings data missing.

        B17: Fail-safe if earnings_history is empty (don't crash on NULL).
        """
        try:
            self.cur.execute(
                "SELECT MAX(quarter) FROM earnings_history WHERE symbol = %s",
                (symbol,),
            )
            row = self.cur.fetchone()
            if not row or not row[0]:
                # No earnings history for this symbol
                return None
            est = row[0] + timedelta(days=45)
            while est < current_date:
                est += timedelta(days=90)
            days = (est - current_date).days
            # Sanity check: earnings should be 0-120 days away
            if days < 0 or days > 200:
                return None
            return days
        except Exception as e:
            print(f"  [WARN] Could not compute days_to_earnings for {symbol}: {e}")
            return None

    def _fetch_market_dist_days(self, current_date):
        self.cur.execute(
            "SELECT distribution_days_4w FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _period_return(self, symbol, end_date, lookback_days):
        self.cur.execute(
            """
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - INTERVAL '%s days'
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        recent, oldest = float(row[0]), float(row[1])
        if oldest <= 0:
            return None
        return (recent - oldest) / oldest

    def _persist_review(self, rec, current_date):
        """Update algo_positions with current price/PnL and log a monitoring audit row."""
        try:
            self.cur.execute(
                """
                UPDATE algo_positions
                SET current_price = %s,
                    position_value = %s * %s,
                    unrealized_pnl = (%s - avg_entry_price) * quantity,
                    unrealized_pnl_pct = ((%s - avg_entry_price) / avg_entry_price) * 100,
                    days_since_entry = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE position_id = %s
                """,
                (
                    rec['current_price'], rec['quantity'], rec['current_price'],
                    rec['current_price'], rec['current_price'],
                    rec['days_held'], rec['position_id'],
                ),
            )
            # Log the review to audit
            self.cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, symbol, action_date,
                                            details, actor, status, created_at)
                VALUES ('position_review', %s, CURRENT_TIMESTAMP, %s, 'position_monitor',
                        %s, CURRENT_TIMESTAMP)
                """,
                (
                    rec['symbol'],
                    json.dumps({
                        'trade_id': rec['trade_id'],
                        'r_multiple': rec['r_multiple'],
                        'unrealized_pct': rec['unrealized_pct'],
                        'flags': rec['flags'],
                        'rs_label': rec['rs_label'],
                        'sector_state': rec['sector_state'],
                        'action': rec['action'],
                        'action_reason': rec['action_reason'],
                        'days_to_earnings': rec['days_to_earnings'],
                        'proposed_stop': float(rec['proposed_stop']),
                    }),
                    rec['action'],
                ),
            )
        except Exception as e:
            print(f"  (audit log skipped for {rec['symbol']}: {e})")

    def _print_recommendation(self, rec):
        flags_str = ', '.join(rec['flags']) if rec['flags'] else 'none'
        print(
            f"  {rec['symbol']:6s}  qty={rec['quantity']:<5d} "
            f"price=${rec['current_price']:7.2f}  "
            f"R={rec['r_multiple']:+.2f}  "
            f"P&L={rec['unrealized_pct']:+.2f}%  "
            f"days={rec['days_held']:<3d} "
            f"hits={rec['target_hits']}"
        )
        print(
            f"          stop ${rec['active_stop']:.2f} -> ${rec['proposed_stop']:.2f} | "
            f"RS={rec['rs_label']} | sector={rec['sector_state']} | flags={flags_str}"
        )
        print(f"          -> {rec['action']}: {rec['action_reason']}")


if __name__ == "__main__":
    from algo_config import get_config
    monitor = PositionMonitor(get_config())
    monitor.review_positions()
