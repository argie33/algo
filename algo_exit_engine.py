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
7. CHANDELIER TRAIL — 3×ATR from highest high (or 21-EMA after 10d)
8. TD SEQUENTIAL — 9-count (50%) or 13-count (100%) exhaustion
9. FIRST RED DAY — after 2.5R+ gain, first big down day on heavy volume → exit 50%
10. CLIMAX RUN EXHAUSTION — 30+ days, 5R+ gain, 20%+ in last 10d → exit 50%
11. DISTRIBUTION — market distribution day count exceeds limit (config-gated)

State tracked on algo_positions:
  - target_levels_hit (0/1/2/3): which T-levels have already triggered
  - current_stop_price: trailed stop after T1/T2 hits
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from trade_performance_auditor import TradePerformanceAuditor
from algo_trade_executor import TradeExecutor
from algo_signals import SignalComputer
from trade_status import TradeStatus, PositionStatus
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Get DB config (lazy-loaded to support testing without credentials)."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": credential_manager.get_db_credentials()["password"],
        "database": os.getenv("DB_NAME", "stocks"),
    }


class ExitEngine:
    """Monitor and execute position exits."""

    def __init__(self, config):
        self.config = config
        self.executor = TradeExecutor(config)
        self.conn = None
        self.cur = None

    def connect(self) -> None:
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self) -> None:
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def check_and_execute_exits(self, current_date=None) -> int:
        """Check all open positions for exit conditions and execute."""
        if not current_date:
            current_date = datetime.now().date()

        # NEW: Initialize performance auditor (Phase 2 integration)
        auditor = TradePerformanceAuditor(self.config)

        self.connect()
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"EXIT ENGINE CHECK - {current_date}")
            logger.info(f"{'='*70}\n")

            self.cur.execute(
                """
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.target_1_price, t.target_2_price, t.target_3_price,
                       t.trade_date,
                       p.position_id, p.quantity, p.target_levels_hit,
                       p.current_stop_price
                FROM algo_trades t
                JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.status IN (%s, %s) AND p.status = %s AND p.quantity > 0
                ORDER BY t.trade_date ASC
                """,
                (TradeStatus.OPEN.value, TradeStatus.PENDING.value, PositionStatus.OPEN.value)
            )
            trades = self.cur.fetchall()
            if not trades:
                logger.info("No open positions.\n")
                return 0

            # Cache market distribution-day status once for the run
            dist_days_today = self._fetch_market_dist_days(current_date)
            exits_executed = 0

            for row in trades:
                (trade_id, symbol, entry_price, init_stop, t1_price, t2_price, t3_price,
                 trade_date, _position_id, quantity, target_hits, current_stop) = row

                try:
                    entry_price = float(entry_price)
                    init_stop = float(init_stop)
                    active_stop = float(current_stop) if current_stop else init_stop
                    t1_price = float(t1_price) if t1_price else None
                    t2_price = float(t2_price) if t2_price else None
                    t3_price = float(t3_price) if t3_price else None
                    target_hits = int(target_hits or 0)
                except (TypeError, ValueError) as e:
                    logger.warning(f"  {symbol}: skip (invalid price data: {e})")
                    continue

                cur_price, prev_close = self._fetch_recent_prices(symbol, current_date)
                if cur_price is None:
                    continue

                days_held = (current_date - trade_date).days

                # CRITICAL FIX: Minimum 1-day hold to prevent same-day entry/exit
                # All 39 closed trades currently at 0% P&L because they exit same day
                if days_held < 1:
                    logger.info(f"  {symbol}: hold (too new, need 1d hold, held {days_held}d)")
                    continue

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

                # Route ALL updates through executor (no direct UPDATE bypass)
                # Even stop-raise-only (fraction=0) must use executor for atomicity and audit logging
                logger.info(f"  {symbol}: {stage.upper()} — {exit_signal['reason']}")
                if fraction > 0:
                    print(f"      (exit {int(fraction*100)}%)")

                result = self.executor.exit_trade(
                    trade_id=trade_id,
                    exit_price=cur_price,
                    exit_reason=exit_signal['reason'],
                    exit_fraction=max(fraction, 1e-6) if fraction >= 0 else 1e-6,
                    exit_stage=stage,
                    new_stop_price=new_stop,
                )

                if result.get('success'):
                    exits_executed += 1
                    logger.info(f"      -> {result['message']}")
                else:
                    logger.error(f"      -> FAILED: {result.get('message')}")

            logger.info(f"\n{'='*70}")
            logger.info(f"Exits executed: {exits_executed}/{len(trades)} positions")
            logger.info(f"{'='*70}\n")

            # NEW: Audit closed trades for performance (Phase 2 integration)
            try:
                self.cur.execute("""
                    SELECT DISTINCT id FROM algo_trades
                    WHERE status = %s AND exit_date = %s
                """, (TradeStatus.CLOSED.value, current_date))
                closed_trades = self.cur.fetchall()
                for (trade_id,) in closed_trades:
                    auditor.audit_exit(trade_id)
            except Exception as audit_err:
                logger.error(f"Warning: Failed to audit closed trades: {audit_err}")

            return exits_executed
        except Exception as e:
            logger.error(f"Error in exit engine: {e}")
            import traceback
            traceback.print_exc()
            return 0
        finally:
            self.disconnect()

    # ---------- Decision logic ----------

    def _evaluate_position(self, symbol, current_date, cur_price, prev_close,
                           entry_price, active_stop, init_stop,
                           t1_price, t2_price, t3_price,
                           target_hits, days_held, dist_days_today) -> Dict[str, Any] | None:
        """Decide what (if any) exit to take. Returns dict or None."""
        # PHASE 1 FIX: Enforce minimum holding period (no same-day exits)
        min_hold_days = int(self.config.get('min_hold_days', 1))
        if days_held < min_hold_days:
            return None  # Not ready to exit yet

        # Compute R-multiple for use across rules (Curtis Faith's R-unit framework)
        risk_per_share = entry_price - init_stop
        r_mult = ((cur_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0

        # 1. STOP (capital preservation always wins)
        if cur_price <= active_stop:
            return {
                'stage': 'stop',
                'fraction': 1.0,
                'reason': f'STOP hit: ${cur_price:.2f} <= ${active_stop:.2f}',
            }

        # 2. MINERVINI BREAK — close < 21-EMA on volume, OR clean break of 50-DMA
        if self._is_minervini_break(symbol, current_date, cur_price):
            return {
                'stage': 'stop',
                'fraction': 1.0,
                'reason': f'Minervini trend break: closed below key MA on volume',
            }

        # 3. RS-LINE BREAK vs SPY (O'Neil) — exit if relative strength deteriorates
        if self.config.get('exit_on_rs_line_break_50dma', True):
            if self._rs_line_breaking(symbol, current_date):
                return {
                    'stage': 'stop',
                    'fraction': 1.0,
                    'reason': 'RS line broke below 50-DMA — relative strength deterioration',
                }

        # 4. TIME — but with O'Neil 8-week rule override for big winners
        max_hold = int(self.config.get('max_hold_days', 15))
        if days_held >= max_hold:
            # 8-week rule: if stock gained >= 20% in first 3 weeks, hold for 8 weeks
            eight_wk_threshold = float(self.config.get('eight_week_rule_threshold_pct', 20.0))
            eight_wk_window = int(self.config.get('eight_week_rule_window_days', 15))
            eight_wk_ext = self._eight_week_rule_active(
                symbol, current_date, entry_price, days_held,
                eight_wk_threshold, eight_wk_window,
            )
            if eight_wk_ext and days_held < 56:  # 8 weeks = 40 trading days; calendar 56
                # Don't exit on time; let the trail / stop manage it
                pass
            else:
                return {
                    'stage': 'time',
                    'fraction': 1.0,
                    'reason': f'TIME exit: {days_held} days >= {max_hold} max',
                }

        # 5. BREAKEVEN STOP MOVE at +1R (Curtis Faith research — premature is worse)
        # This is a "raise stop" not an exit. The orchestrator handles via new_stop.
        if r_mult >= float(self.config.get('move_be_at_r', 1.0)) and active_stop < entry_price:
            return {
                'stage': 'raise_stop_be',
                'fraction': 0.0,  # 0 = no exit, just raise stop
                'reason': f'+{r_mult:.2f}R achieved — raise stop to breakeven',
                'new_stop': entry_price,
            }

        # 6. T3 — exits the rest at 4R
        if t3_price is not None and cur_price >= t3_price and target_hits < 3:
            return {
                'stage': 'target_3',
                'fraction': 1.0,
                'reason': f'T3 target hit: ${cur_price:.2f} >= ${t3_price:.2f} (4R)',
            }

        # 7. T2 — exit 50% of remaining (= 25% of original) on pullback; trail stop to T1
        if t2_price is not None and cur_price >= t2_price and target_hits < 2:
            if self._is_pulling_back(symbol, current_date):
                stop_for_t2 = max(active_stop, t1_price) if t1_price is not None else active_stop
                return {
                    'stage': 'target_2',
                    'fraction': 0.50,
                    'reason': f'T2 pullback exit: ${cur_price:.2f} >= ${t2_price:.2f} (3R)',
                    'new_stop': stop_for_t2,
                }

        # 8. T1 — exit 50% on pullback; raise stop to entry (breakeven)
        if t1_price is not None and cur_price >= t1_price and target_hits < 1:
            if self._is_pulling_back(symbol, current_date):
                return {
                    'stage': 'target_1',
                    'fraction': 0.50,
                    'reason': f'T1 pullback exit: ${cur_price:.2f} >= ${t1_price:.2f} (1.5R)',
                    'new_stop': max(active_stop, entry_price),
                }

        # 9. CHANDELIER TRAIL — once profitable, trail by 3xATR from highest high
        # Switches to 21-EMA trail after 10 days for tighter management
        if self.config.get('use_chandelier_trail', True) and r_mult >= 1.0:
            chand_stop = self._chandelier_or_ema_stop(symbol, current_date, days_held)
            if chand_stop and chand_stop > active_stop:
                return {
                    'stage': 'raise_stop_trail',
                    'fraction': 0.0,
                    'reason': f'Chandelier/EMA trail tightens stop to ${chand_stop:.2f}',
                    'new_stop': chand_stop,
                }

        # 7. TD SEQUENTIAL / COMBO EXHAUSTION (DeMark)
        # 9-count: partial exit (50%) at exhaustion top
        # 13-count COMBO: full exit (much stronger signal)
        if self.config.get('exit_on_td_sequential', True) and target_hits >= 1:
            r_mult_local = ((cur_price - entry_price) / (entry_price - active_stop)) if (entry_price - active_stop) > 0 else 0
            if r_mult_local >= 0.5:
                td_state = self._get_td_state(symbol, current_date)
                if td_state.get('combo_13_complete') and td_state.get('setup_type') == 'sell':
                    return {
                        'stage': 'td_combo_13',
                        'fraction': 1.0,  # full exit on 13
                        'reason': f'TD Combo 13-count exhaustion (FULL EXIT, R={r_mult_local:.2f})',
                    }
                if td_state.get('completed_9') and td_state.get('setup_type') == 'sell':
                    return {
                        'stage': 'td_exhaustion',
                        'fraction': 0.50,
                        'reason': f'TD Sequential 9-count exhaustion (R={r_mult_local:.2f})',
                        'new_stop': max(active_stop, entry_price),
                    }

        # 12. FIRST RED DAY (O'Neill) — after 20%+ gain, first big down day on heavy volume
        # Institutional distribution day after parabolic run — exit 50%
        if r_mult >= 2.5 and prev_close is not None and prev_close > 0:
            down_pct = (prev_close - cur_price) / prev_close * 100.0
            if down_pct >= 1.5:  # Close < prior close * 0.985 = 1.5% down
                vol_check = self._check_volume_spike(symbol, current_date, 1.5)
                if vol_check:
                    return {
                        'stage': 'first_red_day',
                        'fraction': 0.50,
                        'reason': f'First Red Day: down {down_pct:.2f}% on heavy volume (R={r_mult:.2f})',
                        'new_stop': max(active_stop, entry_price),
                    }

        # 13. CLIMAX RUN EXHAUSTION — parabolic moves exhaust and reverse sharply
        # Trigger: 30+ days held, 5R+ gain, 20%+ gain in last 10 days = institutional climax distribution
        if days_held > 30 and r_mult >= 5.0:
            gain_10d = self._compute_gain_last_n_days(symbol, current_date, 10)
            if gain_10d is not None and gain_10d >= 20.0:
                return {
                    'stage': 'climax_exhaustion',
                    'fraction': 0.50,
                    'reason': f'Climax run exhaustion: gained {gain_10d:.1f}% in last 10d (R={r_mult:.2f})',
                    'new_stop': max(active_stop, entry_price),
                }

        # 8. DISTRIBUTION
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

    def _fetch_recent_prices(self, symbol, current_date) -> tuple[float | None, float | None]:
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

    def _fetch_market_dist_days(self, current_date) -> int:
        self.cur.execute(
            """
            SELECT distribution_days_4w FROM market_health_daily
            WHERE date <= %s ORDER BY date DESC LIMIT 1
            """,
            (current_date,),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _is_pulling_back(self, symbol, current_date) -> bool:
        """Requires either 2-3% decline from recent high OR 2+ days below 5-day high.

        Real pullbacks show clear consolidation, not just a 0.5% afternoon dip.
        This prevents hair-trigger exits on winners."""
        if self.cur is None:
            return True
        self.cur.execute(
            """
            SELECT close, HIGH FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 6
            """,
            (symbol, current_date),
        )
        rows = self.cur.fetchall()
        if len(rows) < 3:
            return False

        cur_close = float(rows[0][0])
        recent_high = max(float(r[1]) if r[1] is not None else float(r[0]) for r in rows[:5])

        # Check if pullback is meaningful: 2-3% decline
        pullback_pct = ((recent_high - cur_close) / recent_high * 100.0) if recent_high > 0 else 0
        if pullback_pct >= 2.0:
            return True

        # OR check if consolidated below high for 2+ days
        days_below_high = sum(1 for r in rows[:5] if float(r[0]) < recent_high * 0.98)
        return days_below_high >= 2

    def _rs_line_breaking(self, symbol, current_date) -> bool:
        """RS line (stock/SPY ratio) breaking below its 50-day MA = exit signal."""
        if self.cur is None:
            return False
        try:
            self.cur.execute(
                """
                WITH ratio AS (
                    SELECT s.date,
                           s.close::numeric / NULLIF(spy.close, 0) AS rs
                    FROM price_daily s
                    JOIN price_daily spy ON spy.symbol='SPY' AND spy.date=s.date
                    WHERE s.symbol = %s AND s.date <= %s
                    ORDER BY s.date DESC LIMIT 60
                ),
                ranked AS (
                    SELECT rs, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn FROM ratio
                )
                SELECT
                    (SELECT rs FROM ranked WHERE rn = 1) AS cur,
                    (SELECT AVG(rs) FROM ranked WHERE rn BETWEEN 2 AND 51) AS rs_50dma
                """,
                (symbol, current_date),
            )
            row = self.cur.fetchone()
            if not row or row[0] is None or row[1] is None:
                return False
            cur_rs, rs_50 = float(row[0]), float(row[1])
            # Break if current RS is < 50-day RS-line MA (deteriorating)
            return cur_rs < rs_50 * 0.99
        except Exception as e:
            logger.error(f"Warning: _rs_line_breaking({symbol}) failed: {e}")
            return False

    def _eight_week_rule_active(self, symbol, current_date, entry_price, days_held,
                                 threshold_pct, window_days) -> bool:
        """O'Neil 8-week rule: if stock gained 20%+ in first 3 weeks, hold for 8 weeks."""
        if self.cur is None or days_held < window_days:
            return False
        try:
            # Check if any high in first 3 weeks gave 20%+ gain
            self.cur.execute(
                """
                SELECT MAX(high) FROM price_daily
                WHERE symbol = %s
                  AND date >= %s::date - MAKE_INTERVAL(days => %s)
                  AND date <= %s::date - MAKE_INTERVAL(days => %s)
                """,
                (symbol, current_date, days_held, current_date, max(0, days_held - window_days)),
            )
            row = self.cur.fetchone()
            if not row or not row[0]:
                return False
            max_high_in_window = float(row[0])
            if entry_price <= 0:
                return False
            gain_pct = (max_high_in_window - entry_price) / entry_price * 100.0
            return gain_pct >= threshold_pct
        except Exception as e:
            logger.error(f"Warning: _eight_week_rule_active({symbol}) failed: {e}")
            return False

    def _chandelier_or_ema_stop(self, symbol, current_date, days_held) -> tuple[float | None, bool]:
        """Trailing stop: chandelier (3×ATR from highest high) for first 10d,
        then 21-EMA after."""
        if self.cur is None:
            return None
        try:
            switch_days = int(self.config.get('switch_to_21ema_after_days', 10))
            if days_held >= switch_days:
                # 21-EMA trail
                self.cur.execute(
                    """
                    WITH d AS (
                        SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                        FROM price_daily WHERE symbol = %s AND date <= %s
                        ORDER BY date DESC LIMIT 30
                    )
                    SELECT close FROM d ORDER BY rn DESC
                    """,
                    (symbol, current_date),
                )
                rows = self.cur.fetchall()
                if len(rows) < 21:
                    return None
                closes = [float(r[0]) for r in rows]
                # 21-EMA
                k = 2.0 / 22.0
                ema = closes[0]
                for c in closes[1:]:
                    ema = c * k + ema * (1 - k)
                return round(ema * 0.99, 2)
            else:
                # Chandelier 3×ATR from highest high since entry
                self.cur.execute(
                    """
                    WITH d AS (
                        SELECT pd.high, td.atr,
                               ROW_NUMBER() OVER (ORDER BY pd.date DESC) AS rn
                        FROM price_daily pd
                        LEFT JOIN technical_data_daily td ON td.symbol = pd.symbol AND td.date = pd.date
                        WHERE pd.symbol = %s AND pd.date <= %s
                        ORDER BY pd.date DESC LIMIT %s
                    )
                    SELECT MAX(high) AS hh,
                           (SELECT atr FROM d WHERE rn = 1) AS cur_atr
                    FROM d
                    """,
                    (symbol, current_date, max(days_held, 5)),
                )
                row = self.cur.fetchone()
                if not row or not row[0] or not row[1]:
                    return None
                hh = float(row[0])
                atr = float(row[1])
                mult = float(self.config.get('chandelier_atr_mult', 3.0))
                return round(hh - (mult * atr), 2)
        except Exception as e:
            logger.error(f"Warning: _chandelier_or_ema_stop({symbol}) failed: {e}")
            return None

    def _is_td_sequential_top(self, symbol, current_date) -> bool:
        """Use rigorous DeMark TD Sequential — fires when sell-setup count = 9."""
        if self.cur is None:
            return False
        try:
            sc = SignalComputer(cur=self.cur)
            td = sc.td_sequential(symbol, current_date)
            return td.get('completed_9', False) and td.get('setup_type') == 'sell'
        except Exception as e:
            logger.error(f"Warning: _is_td_sequential_top({symbol}) failed: {e}")
            return False

    def _get_td_state(self, symbol, current_date) -> Dict[str, Any]:
        """Return full TD state dict (for both 9 and 13 detection)."""
        if self.cur is None:
            return {}
        try:
            sc = SignalComputer(cur=self.cur)
            return sc.td_sequential(symbol, current_date)
        except Exception as e:
            logger.error(f"Warning: _get_td_state({symbol}) failed: {e}")
            return {}

    def _is_minervini_break(self, symbol, current_date, cur_price) -> bool:
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

    def _check_volume_spike(self, symbol, current_date, volume_multiplier) -> bool:
        """Check if today's volume is >= volume_multiplier * average volume."""
        if self.cur is None:
            return False
        try:
            self.cur.execute(
                """
                SELECT pd.volume,
                       (SELECT AVG(volume) FROM price_daily p
                        WHERE p.symbol = pd.symbol
                          AND p.date <= pd.date
                          AND p.date > pd.date - INTERVAL '50 days') AS avg_vol_50
                FROM price_daily pd
                WHERE pd.symbol = %s AND pd.date = %s
                """,
                (symbol, current_date),
            )
            row = self.cur.fetchone()
            if not row or row[0] is None or row[1] is None:
                return False
            today_vol = float(row[0])
            avg_vol = float(row[1])
            return today_vol >= avg_vol * volume_multiplier
        except Exception as e:
            logger.warning(f"Warning: _check_volume_spike({symbol}) failed: {e}")
            return False

    def _compute_gain_last_n_days(self, symbol, current_date, n_days) -> float | None:
        """Compute % gain over the last N days (from close N days ago to current close)."""
        if self.cur is None:
            return None
        try:
            self.cur.execute(
                """
                WITH prices AS (
                    SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT %s
                )
                SELECT
                    (SELECT close FROM prices WHERE rn = 1) AS current_close,
                    (SELECT close FROM prices WHERE rn = %s) AS close_n_days_ago
                """,
                (symbol, current_date, n_days + 1, n_days + 1),
            )
            row = self.cur.fetchone()
            if not row or row[0] is None or row[1] is None:
                return None
            current = float(row[0])
            prior = float(row[1])
            if prior <= 0:
                return None
            return ((current - prior) / prior) * 100.0
        except Exception as e:
            logger.warning(f"Warning: _compute_gain_last_n_days({symbol}) failed: {e}")
            return None

    # ---------- Backwards-compat shim used by old tests ----------

    def _check_exit_conditions(self, symbol, current_price, entry_price, qty,
                                t1_price, t2_price, t3_price, stop_price,
                                days_held, eval_date) -> Dict[str, Any]:
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
    logger.info(f"Exits executed: {exits}")
