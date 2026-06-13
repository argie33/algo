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

from config.credential_manager import get_credential_manager
from config.alpaca_config import get_alpaca_base_url
from algo.algo_config import get_alpaca_timeout
from utils.database_context import DatabaseContext
import os
import json
from decimal import Decimal, ROUND_HALF_UP

import requests
from datetime import datetime, timedelta, date as _date, timezone
import logging

logger = logging.getLogger(__name__)

class PositionMonitor:
    """Daily position health checker and stop adjuster."""

    def _with_cursor(self, operation, mode='read'):
        """Execute operation with cursor via DatabaseContext."""
        try:
            with DatabaseContext(mode) as cur:
                return operation(cur)
        except Exception as e:
            logger.debug(f"Database operation failed: {e}")
            return None

    def __init__(self, config):
        self.config = config

    def check_stale_orders(self, current_date=None):
        """Check for orders stuck in pending state >1 hour. Alert if found.

        Stuck orders = likely API issue or rejection. Should be resolved manually.
        Filters out orders for halted symbols (these stay pending naturally).
        """
        if not current_date:
            current_date = _date.today()

        with DatabaseContext('read') as cur:
            try:
                cur.execute("""
                    SELECT trade_id, symbol, entry_price, entry_quantity, created_at
                    FROM algo_trades
                    WHERE status = 'pending'
                      AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 hour'
                    ORDER BY created_at ASC
                """)
                stale_orders = cur.fetchall()
            except Exception as e:
                logger.error(f"Stale orders query failed: {e}")
                return {'status': 'ERROR', 'error': str(e)}

            if stale_orders:
                # Filter out halted symbols (halts are normal, not actionable)
                try:
                    from algo.algo_market_events import MarketEventHandler
                    meh = MarketEventHandler(self.config)
                    filtered_stale = []
                    for row in stale_orders:
                        trade_id, symbol, price, qty, created_at = row
                        halt_check = meh.check_single_stock_halt(symbol)
                        if halt_check and halt_check.get('halted'):
                            logger.info(f"    {trade_id} {symbol} pending (but halted, expected)")
                            continue
                        filtered_stale.append(row)
                    stale_orders = filtered_stale
                except Exception as e:
                    logger.warning(f"Could not check halts for stale orders: {e}")

                if stale_orders:
                    logger.info(f"\n  [ALERT] Found {len(stale_orders)} orders pending >1 hour (excluding halted):")
                    for row in stale_orders:
                        trade_id, symbol, price, qty, created_at = row
                        # Ensure created_at is timezone-aware (UTC) for subtraction from datetime.now(timezone.utc)
                        if not getattr(created_at, 'tzinfo', None):
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        age_minutes = int((datetime.now(timezone.utc) - created_at).total_seconds() / 60)
                        logger.info(f"    {trade_id} {symbol} {qty}@{price} (pending {age_minutes}m)")
                    return {'status': 'STALE_ORDERS_FOUND', 'count': len(stale_orders), 'orders': stale_orders}
                return {'status': 'OK', 'count': 0}

    def check_sector_concentration(self, current_date=None):
        """Check if portfolio is overly concentrated in one sector.

        Alert if >3 positions in same sector (concentration risk).
        """
        if not current_date:
            current_date = _date.today()

        with DatabaseContext('read') as cur:
            try:
                cur.execute("""
                    SELECT COALESCE(cp.sector, 'Unknown') as sector, COUNT(DISTINCT ap.symbol) as position_count
                    FROM algo_positions ap
                    LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                    WHERE ap.status = 'open' AND ap.quantity > 0
                    GROUP BY COALESCE(cp.sector, 'Unknown')
                    HAVING COUNT(DISTINCT ap.symbol) > 3
                    ORDER BY position_count DESC
                """)
                concentrated = cur.fetchall()
                if concentrated:
                    logger.info(f"\n  [CONCENTRATION ALERT]")
                    for sector, count in concentrated:
                        logger.info(f"    {sector}: {count} positions (>3 is risky)")
                    return {'status': 'HIGH_CONCENTRATION', 'sectors': concentrated}
                return {'status': 'OK', 'sectors': []}
            except Exception as e:
                return {'status': 'ERROR', 'error': str(e)}

    def review_positions(self, current_date=None):
        """Review every open position. Returns list of recommendations."""
        if not current_date:
            current_date = _date.today()

        recs = []
        with DatabaseContext('write') as cur:
            # Issue #24: Check margin utilization and warn/halt if excessive
            try:
                cur.execute("""
                    SELECT total_equity FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                eq_row = cur.fetchone()
                if eq_row is not None and eq_row[0] is not None:
                    total_equity = float(eq_row[0])
                    # Compute margin usage = (equity - buying_power) / equity
                    # Using proxy: if total open position value > 90% of equity, halt new entries
                    cur.execute("""
                        SELECT SUM(position_value) FROM algo_positions WHERE status = 'open'
                    """)
                    pos_val_row = cur.fetchone()
                    pos_value = float(pos_val_row[0]) if pos_val_row is not None and pos_val_row[0] is not None else 0
                    margin_util_pct = (pos_value / total_equity * 100) if total_equity > 0 else 0
                    if margin_util_pct > 90:
                        logger.critical(f"[MARGIN HALT] Position value {margin_util_pct:.1f}% of equity — liquidation risk imminent")
                    elif margin_util_pct > 80:
                        logger.warning(f"[MARGIN WARNING] Position value {margin_util_pct:.1f}% of equity > 80%")
            except Exception as margin_e:
                logger.debug(f"Could not check margin: {margin_e}")

            conc = self.check_sector_concentration(current_date)
            if conc['status'] == 'HIGH_CONCENTRATION':
                logger.info(f"  [WARNING]  Portfolio concentration risk detected")

            cur.execute(
                """
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.target_1_price, t.target_2_price, t.target_3_price,
                       t.trade_date, t.signal_date,
                       p.position_id, p.quantity, p.target_levels_hit,
                       p.current_stop_price, p.current_price
                FROM algo_trades t
                JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.status IN ('open','pending') AND p.status = 'open' AND p.quantity > 0
                  AND p.trade_ids_arr IS NOT NULL AND array_length(p.trade_ids_arr, 1) > 0
                """
            )
            positions = cur.fetchall()

            logger.info(f"\n{'='*70}")
            logger.info(f"POSITION MONITOR — {current_date}")
            logger.info(f"{'='*70}")
            logger.info(f"Reviewing {len(positions)} open position(s)\n")

            for i, row in enumerate(positions):
                rec = self._evaluate_position(row, current_date, cur)
                if rec is None:
                    continue
                recs.append(rec)
                self._print_recommendation(rec)
                try:
                    sp_name = f"sp_pos_{i}"
                    cur.execute(f"SAVEPOINT {sp_name}")
                    self._persist_review(rec, cur)
                except Exception as e:
                    logger.error(f"Failed to persist review for {rec['symbol']}: {e}")
                    cur.execute(f"ROLLBACK TO SAVEPOINT sp_pos_{i}")
                    continue
            return recs

    def _evaluate_position(self, row, current_date, cur):
        (trade_id, symbol, entry_price, init_stop, t1_price, t2_price, t3_price,
         trade_date, signal_date, position_id, quantity, target_hits,
         current_stop, db_current_price) = row

        entry_price = float(entry_price)
        init_stop = float(init_stop)

        if entry_price <= 0:
            logger.error(f"ERROR: Invalid entry price {entry_price} for {symbol} — cannot monitor")
            return None
        if init_stop <= 0:
            logger.error(f"ERROR: Invalid stop {init_stop} for {symbol} — cannot monitor")
            return None
        if init_stop >= entry_price:
            logger.error(f"ERROR: Stop {init_stop} >= entry {entry_price} for {symbol} — invalid trade")
            return None
        active_stop = float(current_stop) if current_stop else init_stop
        target_hits = int(target_hits or 0)
        days_held = (current_date - trade_date).days
        max_hold = int(self.config.get('max_hold_days', 20))

        # 1. Current market data
        cur_price, atr, sma_50, ema_12 = self._fetch_current_market(symbol, current_date, cur)

        # CRITICAL: Do NOT use entry_price as fallback for cur_price. This distorts stop-loss and P&L calculations.
        # If market data is unavailable, skip the position entirely.
        if cur_price is None or cur_price <= 0:
            logger.error(f"REJECT: Position {symbol} has no valid current market price (got {cur_price}). Cannot monitor without real market data.")
            return None

        # P&L (using Decimal for precision)
        risk_per_share = entry_price - init_stop
        r_multiple = ((cur_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0

        # Use Decimal for monetary calculations to avoid floating point precision loss
        price_diff = Decimal(str(cur_price)) - Decimal(str(entry_price))
        entry_price_dec = Decimal(str(entry_price))
        quantity_dec = Decimal(str(quantity))

        unrealized_pnl = float((price_diff * quantity_dec).quantize(Decimal('0.01'), ROUND_HALF_UP))
        unrealized_pct = float((price_diff / entry_price_dec * 100).quantize(Decimal('0.01'), ROUND_HALF_UP)) if entry_price > 0 else 0

        # 2. Recompute trailing stop (only ratchet UP, never down)
        proposed_stop = self._compute_trailing_stop(
            entry_price, active_stop, cur_price, atr, sma_50, target_hits,
        )

        if proposed_stop > cur_price:
            logger.error(f"ERROR: Proposed stop ${proposed_stop:.2f} > current price ${cur_price:.2f} for {symbol}")
            proposed_stop = cur_price - 0.01  # Clamp to 1c below market
            logger.info(f"  Clamped stop to ${proposed_stop:.2f}")

        # 3. Health flags
        flags = []

        # 3a. Relative strength vs SPY (degrading?)
        rs_state = self._check_relative_strength(symbol, current_date, cur)
        if rs_state == 'weakening':
            flags.append('RS_WEAKENING')
        rs_label = rs_state

        # 3b. Sector turned weak?
        sector_state = self._check_sector_health(symbol, current_date, cur)
        if sector_state == 'weakening':
            flags.append('SECTOR_WEAK')

        # 3c. Giving back gains (>33% retrace from peak)?
        peak_pct = self._max_unrealized_pct(symbol, trade_date, current_date, entry_price, cur)
        if peak_pct > 5 and unrealized_pct < peak_pct * 0.66:
            flags.append('GIVING_BACK_GAINS')

        # 3d. Time decay (>= half of max_hold, but no T1 hit yet)
        if days_held >= max_hold * 0.5 and target_hits == 0 and r_multiple < 0.5:
            flags.append('TIME_DECAY_NO_PROGRESS')

        # 3e. Earnings proximity
        days_to_earn = self._days_to_earnings(symbol, current_date, cur)
        if days_to_earn is not None and 0 <= days_to_earn <= 3:
            flags.append(f'EARNINGS_IN_{days_to_earn}D')

        # 3f. Distribution-day stress
        market_dist_days = self._fetch_market_dist_days(current_date, cur)
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
            'price_source': price_metadata.get('source', 'daily'),  # Issue #33: Fallback indicator
            'price_is_fallback': price_metadata.get('is_fallback', False),  # Issue #33: Mark fallback
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

    def _fetch_current_market(self, symbol, current_date, cur):
        # F-01: Try real-time pricing during market hours, fallback to daily price
        from algo.algo_realtime_prices import RealtimePricingEngine
        engine = RealtimePricingEngine(self.config)

        rt_price = None
        if engine.is_market_hours():
            try:
                rt_prices = engine.get_latest_prices([symbol])
                rt_price = rt_prices.get(symbol)
                if rt_price:
                    logger.info(f"Using real-time price for {symbol}: ${rt_price:.2f}")
            except Exception as e:
                logger.warning(f"Real-time pricing failed for {symbol}: {e} — falling back to daily")

        # Fetch daily price and technical indicators from database
        cur.execute(
            """
            SELECT pd.close, td.atr, td.sma_50, td.ema_12
            FROM price_daily pd
            LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
            WHERE pd.symbol = %s AND pd.date <= %s
            ORDER BY pd.date DESC LIMIT 1
            """,
            (symbol, current_date),
        )
        row = cur.fetchone()
        if not row:
            return None, None, None, None

        # Use real-time price if available, otherwise use daily close
        current_price = rt_price if rt_price else float(row[0]) if row[0] is not None else None

        return (
            current_price,
            float(row[1]) if row[1] is not None else None,
            float(row[2]) if row[2] is not None else None,
            float(row[3]) if row[3] is not None else None,
        )

    def _compute_trailing_stop(self, entry_price, active_stop,
                                cur_price, atr, sma_50, target_hits):
        """Stop ratchets up only.

        - Before T1: keep initial stop OR use 50-DMA (whichever higher) capped at entry-2*ATR
        - After T1: stop = entry (breakeven) at minimum, or trail tighter via ATR
        - After T2: stop = entry area, never target levels (targets are exits, not protection)
        """
        # Sanity check: if active_stop is already > cur_price (shouldn't happen), clamp it.
        # This can occur with stale/imported positions.
        if active_stop > cur_price:
            active_stop = cur_price - 0.01
            logger.warning(f"  Clamped active_stop {active_stop:.2f} to {cur_price - 0.01:.2f} (was above market)")

        candidates = [active_stop]

        if atr and cur_price:
            candidates.append(cur_price - (2.0 * atr))
        if sma_50 and sma_50 < cur_price:
            candidates.append(sma_50)

        if target_hits >= 1:
            candidates.append(entry_price)  # at least breakeven after T1
        # NOTE: target_hits >= 2 does NOT add T1 price. Target prices are exits, not stops.

        # Don't let trailing stop get within 1.0 ATR of price (room to breathe)
        if atr and cur_price:
            cap = cur_price - atr
            candidates = [c for c in candidates if c <= cap]
            if not candidates:
                candidates = [cap]

        # For a stop loss, pick the highest valid candidate (most conservative protection).
        # This ratchets stops UP as price rises, but never above current price - ATR.
        new_stop = max(candidates) if candidates else active_stop
        # NEVER lower the trailing stop below its prior level
        return round(max(new_stop, active_stop), 2)

    def _check_relative_strength(self, symbol, current_date, cur):
        """20-day relative return vs SPY: weakening / neutral / strong."""
        stock = self._period_return(symbol, current_date, 20, cur)
        spy = self._period_return('SPY', current_date, 20, cur)
        if stock is None or spy is None:
            logger.warning(f"RS data missing for {symbol}: stock={stock}, spy={spy} — treating as unknown, not weakening")
            return 'unknown'
        excess = stock - spy
        if excess < -0.05:
            return 'weakening'
        if excess > 0.05:
            return 'strong'
        return 'neutral'

    def _check_sector_health(self, symbol, current_date, cur):
        """Is the symbol's sector currently weakening?"""
        # Skip sector checks for ETFs/indices
        if symbol in ('SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLE', 'XLV', 'XLF', 'XLI', 'XLY', 'XLRE', 'XLC'):
            return 'neutral'

        cur.execute(
            "SELECT sector FROM company_profile WHERE ticker = %s LIMIT 1",
            (symbol,),
        )
        srow = cur.fetchone()
        if not srow:
            logger.debug(f"Sector data not found for {symbol} — assuming neutral")
            return 'neutral'
        if not srow[0]:
            logger.debug(f"NULL sector for {symbol} — assuming neutral")
            return 'neutral'
        sector = srow[0]

        cur.execute(
            """
            SELECT current_rank, date FROM sector_ranking
            WHERE sector_name = %s
              AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (sector, current_date),
        )
        cur_row = cur.fetchone()
        if not cur_row:
            logger.warning(f"Missing sector ranking data for {sector} — cannot assess health")
            return 'unknown'
        cur_rank = int(cur_row[0]) if cur_row[0] else 99

        # Get rank from ~4 weeks ago for comparison
        four_weeks_ago = current_date - timedelta(days=28)
        cur.execute(
            """
            SELECT current_rank FROM sector_ranking
            WHERE sector_name = %s
              AND date >= %s
              AND date <= %s
            ORDER BY date ASC LIMIT 1
            """,
            (sector, four_weeks_ago, four_weeks_ago + timedelta(days=3)),
        )
        old_row = cur.fetchone()
        old_rank = int(old_row[0]) if old_row is not None and old_row[0] is not None else cur_rank
        if cur_rank > old_rank + 3:  # got worse by 3+ ranks
            return 'weakening'
        if cur_rank < old_rank - 3:
            return 'strengthening'
        return 'stable'

    def _max_unrealized_pct(self, symbol, trade_date, current_date, entry_price, cur):
        """Highest closing price since entry, expressed as % gain."""
        cur.execute(
            """
            SELECT MAX(close) FROM price_daily
            WHERE symbol = %s AND date >= %s AND date <= %s
            """,
            (symbol, trade_date, current_date),
        )
        row = cur.fetchone()
        if not row or not row[0] or entry_price <= 0:
            return 0.0
        return ((float(row[0]) - entry_price) / entry_price) * 100.0

    def _days_to_earnings(self, symbol, current_date, cur):
        """Get days until next earnings. Returns None if earnings data missing.

        Primary: query earnings_calendar for accurate scheduled dates.
        Fallback: estimate from earnings_history quarterly cycle if calendar missing.
        """
        try:
            # Primary: use earnings_calendar (populated by earnings loader)
            cur.execute(
                """SELECT earnings_date FROM earnings_calendar
                   WHERE symbol = %s AND earnings_date >= %s
                   ORDER BY earnings_date ASC LIMIT 1""",
                (symbol, current_date),
            )
            row = cur.fetchone()
            if row is not None and row[0] is not None:
                return (row[0] - current_date).days

            # Fallback: estimate from last reported quarter + 90-day cycle
            cur.execute(
                "SELECT MAX(quarter) FROM earnings_history WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            est = row[0] + timedelta(days=45)
            while est < current_date:
                est += timedelta(days=90)
            days = (est - current_date).days
            if days < 0 or days > 200:
                return None
            return days
        except Exception as e:
            logger.warning(f"  [WARN] Could not compute days_to_earnings for {symbol}: {e}")
            return None

    def _fetch_market_dist_days(self, current_date, cur):
        cur.execute(
            "SELECT distribution_days_4w FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _period_return(self, symbol, end_date, lookback_days, cur):
        cur.execute(
            """
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - (%s * INTERVAL '1 day')
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        recent, oldest = float(row[0]), float(row[1])
        if oldest <= 0:
            return None
        return (recent - oldest) / oldest

    def _persist_review(self, rec, cur):
        """Update algo_positions with current price/PnL and log a monitoring audit row (atomic)."""
        cur.execute(
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
                float(rec['current_price']), float(rec['quantity']), float(rec['current_price']),
                float(rec['current_price']), float(rec['current_price']),
                int(rec['days_held']), rec['position_id'],
            ),
        )
        # Log the review to audit (same transaction)
        cur.execute(
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

    def _print_recommendation(self, rec):
        flags_str = ', '.join(rec['flags']) if rec['flags'] else 'none'
        logger.info(
            f"  {rec['symbol']:6s}  qty={rec['quantity']:<5d} "
            f"price=${rec['current_price']:7.2f}  "
            f"R={rec['r_multiple']:+.2f}  "
            f"P&L={rec['unrealized_pct']:+.2f}%  "
            f"days={rec['days_held']:<3d} "
            f"hits={rec['target_hits']}"
        )

    def check_corporate_actions(self):
        """Phase 6.1: Detect stock splits and corporate actions.

        Compares Alpaca current quantity to DB quantity. If different and > 20% change,
        likely a stock split. Adjusts position quantity and recalculates stop loss.

        Returns:
            list of adjustments made
        """
        adjustments = []
        ctx = DatabaseContext('write')
        with ctx as cur:
            cur.execute("""
                SELECT ap.position_id, ap.symbol, ap.quantity, ap.current_stop_price,
                       ap.avg_entry_price AS entry_price
                FROM algo_positions ap
                WHERE ap.status = 'open'
            """)
            positions = cur.fetchall()

            alpaca_base_url = get_alpaca_base_url()
            try:
                cm = get_credential_manager()
                creds = cm.get_alpaca_credentials()
                alpaca_key = creds.get("key")
                alpaca_secret = creds.get("secret")
            except Exception as e:
                logger.warning(f"Could not retrieve Alpaca credentials: {e}. Skipping Alpaca sync.")
                alpaca_key = None
                alpaca_secret = None

            if not alpaca_key or not alpaca_secret:
                logger.warning("Alpaca credentials not available, skipping position sync")
                return adjustments

            for pos_id, symbol, db_qty, db_stop, entry_price in positions:
                try:
                    url = f"{alpaca_base_url}/v2/positions/{symbol}"
                    headers = {
                        'APCA-API-KEY-ID': alpaca_key,
                        'APCA-API-SECRET-KEY': alpaca_secret,
                    }
                    resp = requests.get(url, headers=headers, timeout=get_alpaca_timeout())
                    if resp.status_code != 200:
                        continue

                    try:
                        alpaca_pos = resp.json()
                    except (ValueError, Exception) as e:
                        logger.warning(f"Invalid JSON response for {symbol}: {e}, skipping")
                        continue

                    alpaca_qty = int(alpaca_pos.get('qty', 0))

                    if alpaca_qty == 0:
                        # Position closed at Alpaca but open in DB — likely filled by stop
                        cur.execute("""
                            UPDATE algo_positions SET status = 'closed'
                            WHERE position_id = %s
                        """, (pos_id,))
                        adjustments.append({
                            'symbol': symbol,
                            'action': 'POSITION_CLOSED_AT_ALPACA',
                            'db_qty': db_qty,
                            'alpaca_qty': alpaca_qty,
                        })
                        continue

                    if alpaca_qty != db_qty:
                        qty_change_pct = abs(alpaca_qty - db_qty) / db_qty * 100 if db_qty > 0 else 0

                        if qty_change_pct > 20:  # Likely a split
                            split_ratio = alpaca_qty / db_qty if db_qty > 0 else 1.0
                            if not db_stop:
                                # FAIL-CLOSED: Can't apply split ratio without knowing original stop
                                logger.critical(f'STOCK SPLIT DETECTED but no stop price in DB for {symbol} {pos_id}. Cannot auto-adjust stop. Manual review required.')
                                # Update quantity but leave stop untouched
                                cur.execute("""
                                    UPDATE algo_positions
                                    SET quantity = %s
                                    WHERE position_id = %s
                                """, (alpaca_qty, pos_id))
                                cur.execute("""
                                    INSERT INTO algo_audit_log (
                                        action_type, action_date, details, severity
                                    ) VALUES (%s, %s, %s, %s)
                                """, (
                                    'CORPORATE_ACTION_SPLIT_NO_STOP',
                                    datetime.now(timezone.utc),
                                    f'Stock split detected: {symbol} {db_qty} → {alpaca_qty} shares (ratio {split_ratio:.2f}). Original stop price missing in DB. Quantity updated but STOP NOT ADJUSTED. Manual review required.',
                                    'CRITICAL'
                                ))
                                continue

                            new_stop = db_stop / split_ratio

                            cur.execute("""
                                UPDATE algo_positions
                                SET quantity = %s, current_stop_price = %s
                                WHERE position_id = %s
                            """, (alpaca_qty, new_stop, pos_id))

                            # Log the corporate action
                            cur.execute("""
                                INSERT INTO algo_audit_log (
                                    action_type, action_date, details, severity
                                ) VALUES (%s, %s, %s, %s)
                            """, (
                                'CORPORATE_ACTION_SPLIT',
                                datetime.now(timezone.utc),
                                f'Stock split detected: {symbol} {db_qty} → {alpaca_qty} shares (ratio {split_ratio:.2f}). Stop adjusted from ${db_stop:.2f} to ${new_stop:.2f}',
                                'WARN'
                            ))

                            adjustments.append({
                                'symbol': symbol,
                                'action': 'STOCK_SPLIT',
                                'old_qty': db_qty,
                                'new_qty': alpaca_qty,
                                'split_ratio': round(split_ratio, 2),
                                'old_stop': db_stop,
                                'new_stop': new_stop,
                            })

                except Exception as e:
                    logger.warning(f"  Warning: Could not check Alpaca position for {symbol}: {e}")
                    continue

            return adjustments

    def can_enter_new_position(self):
        """Check if buying power allows a new entry.

        Returns (True, None) if entries are allowed, (False, reason) if blocked.
        Fails open on error so check failures don't silently block trading.
        """
        try:
            from config.alpaca_config import get_alpaca_base_url
            from config.credential_manager import get_alpaca_credentials
            import requests
            from algo.algo_config import get_api_timeout

            creds = get_alpaca_credentials()
            base_url = get_alpaca_base_url()
            resp = requests.get(
                f'{base_url}/v2/account',
                headers={'APCA-API-KEY-ID': creds['key'], 'APCA-API-SECRET-KEY': creds['secret']},
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                data = resp.json()
                bp = data.get('buying_power')
                if bp is None:
                    bp = data.get('cash')
                if bp is None:
                    bp = 0
                buying_power = float(bp)
                if buying_power < 100:
                    return False, f'Insufficient buying power: ${buying_power:.2f}'
                logger.debug(f"[MARGIN] Buying power ${buying_power:.2f} — entry allowed")
            return True, None
        except Exception as e:
            logger.debug(f"[MARGIN] can_enter_new_position skipped ({e}); defaulting to allow")
            return True, None

    def get_margin_usage(self):
        """Return current margin usage dict with margin_usage_pct key, or None if unavailable."""
        try:

            creds = get_alpaca_credentials()
            base_url = get_alpaca_base_url()
            resp = requests.get(
                f'{base_url}/v2/account',
                headers={'APCA-API-KEY-ID': creds['key'], 'APCA-API-SECRET-KEY': creds['secret']},
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                data = resp.json()
                equity_val = data.get('equity') or data.get('portfolio_value')
                equity = float(equity_val) if equity_val is not None else 1
                long_market_value_val = data.get('long_market_value')
                long_market_value = float(long_market_value_val) if long_market_value_val is not None else None
                margin_usage_pct = (long_market_value / equity * 100.0) if long_market_value is not None and equity > 0 else None
                return {
                    'margin_usage_pct': round(margin_usage_pct, 1) if margin_usage_pct is not None else None,
                    'long_market_value': long_market_value,
                    'equity': equity,
                }
            return None
        except Exception as e:
            logger.debug(f"[MARGIN] get_margin_usage skipped: {e}")
            return None

    def get_open_positions(self):
        """Get list of open positions for halt checking and monitoring.

        Returns a list of dicts with at least 'symbol' and optionally 'name'.
        Used by orchestrator for single-stock halt detection.
        """
        with DatabaseContext('read') as cur:
            try:
                cur.execute("""
                    SELECT DISTINCT symbol FROM algo_positions
                    WHERE status = 'open' AND quantity > 0
                    ORDER BY symbol
                """)
                positions = cur.fetchall()
                return [{'symbol': row[0], 'name': row[0]} for row in positions] if positions else []
            except Exception as e:
                logger.warning(f"Failed to fetch open positions: {e}")
                return []

if __name__ == "__main__":
    from algo.algo_config import get_config
    monitor = PositionMonitor(get_config())
    monitor.review_positions()

