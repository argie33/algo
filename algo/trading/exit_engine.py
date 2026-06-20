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
7. CHANDELIER TRAIL — 3xATR from highest high (or 21-EMA after 10d)
8. TD SEQUENTIAL — 9-count (50%) or 13-count (100%) exhaustion
9. FIRST RED DAY — after 2.5R+ gain, first big down day on heavy volume → exit 50%
10. CLIMAX RUN EXHAUSTION — 30+ days, 5R+ gain, 20%+ in last 10d → exit 50%
11. DISTRIBUTION — market distribution day count exceeds limit (config-gated)

State tracked on algo_positions:
  - target_levels_hit (0/1/2/3): which T-levels have already triggered
  - current_stop_price: trailed stop after T1/T2 hits
"""

import logging
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import requests

from algo.trading.exceptions import DatabaseError, ExchangeAPIError
from utils.db import DatabaseContext


try:
    from trade_performance_auditor import TradePerformanceAuditor
except ImportError:
    TradePerformanceAuditor = None
from typing import Any, cast

from algo.infrastructure import get_alpaca_timeout
from algo.infrastructure.market_calendar import MarketCalendar
from algo.signals import SignalComputer
from algo.trading import TradeExecutor
from config.alpaca_config import get_alpaca_data_url
from config.credential_manager import get_alpaca_credentials
from utils.trading import PositionStatus, TradeStatus


logger = logging.getLogger(__name__)


class ExitEngine:
    """Monitor and execute position exits."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.executor = TradeExecutor(config)
        self.verbose = True

    def check_and_execute_exits(self, current_date=None) -> int:
        """Check all open positions for exit conditions and execute."""
        if not current_date:
            current_date = datetime.now(timezone.utc).date()

        auditor = (
            TradePerformanceAuditor(self.config) if TradePerformanceAuditor else None
        )

        with DatabaseContext("write") as cur:
            try:
                logger.info(f"\n{'='*70}")
                logger.info(f"EXIT ENGINE CHECK - {current_date}")
                logger.info(f"{'='*70}\n")

                cur.execute(
                    """
                    SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                           t.target_1_price, t.target_2_price, t.target_3_price,
                           t.trade_date,
                           p.position_id, p.quantity, p.target_levels_hit,
                           p.current_stop_price, p.target_1_hit_time, p.target_2_hit_time, p.target_3_hit_time
                    FROM algo_trades t
                    JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                    WHERE t.status IN (%s, %s) AND p.status = %s AND p.quantity > 0
                    ORDER BY t.trade_date ASC
                    """,
                    (
                        TradeStatus.OPEN.value,
                        TradeStatus.PENDING.value,
                        PositionStatus.OPEN.value,
                    ),
                )
                trades = cur.fetchall()
                if not trades:
                    logger.info("No open positions.\n")
                    return 0

                # Cache market distribution-day status once for the run
                dist_days_today = self._fetch_market_dist_days(cur, current_date)
                exits_executed = 0

                for row in trades:
                    (
                        trade_id,
                        symbol,
                        entry_price,
                        init_stop,
                        t1_price,
                        t2_price,
                        t3_price,
                        trade_date,
                        _position_id,
                        _quantity,
                        target_hits,
                        current_stop,
                        t1_hit_time,
                        t2_hit_time,
                        t3_hit_time,
                    ) = row

                    # Issue #22: Verify position still open (not already exited in same run)
                    cur.execute(
                        "SELECT status FROM algo_positions WHERE position_id = %s",
                        (_position_id,),
                    )
                    status_row = cur.fetchone()
                    status = status_row[0] if status_row else None
                    if status != "open":
                        logger.debug(
                            f"Position {symbol} already closed, skipping exit check"
                        )
                        continue

                    try:
                        entry_price = float(entry_price)
                        init_stop = float(init_stop)
                        active_stop = float(current_stop) if current_stop else init_stop
                        t1_price = float(t1_price) if t1_price else None
                        t2_price = float(t2_price) if t2_price else None
                        t3_price = float(t3_price) if t3_price else None
                        if target_hits is None:
                            raise ValueError(f"{symbol}: target_hits is NULL in database — data corruption detected")
                        target_hits = int(target_hits)
                    except (TypeError, ValueError) as e:
                        raise ValueError(f"Cannot evaluate exit checks for {symbol}: invalid price data — {e}") from e

                    cur_price, prev_close = self._fetch_recent_prices(
                        cur, symbol, current_date
                    )
                    if cur_price is None:
                        continue

                    days_held = (current_date - trade_date).days

                    # Enforce minimum holding period (no same-day exits per Curtis Faith)
                    if days_held < 1:
                        if self.verbose:
                            logger.info(
                                f"  {symbol}: hold (too new, need 1d hold minimum, held {days_held}d)"
                            )
                        continue

                    exit_signal = self._evaluate_position(
                        cur,
                        symbol,
                        current_date,
                        cur_price,
                        prev_close,
                        entry_price,
                        active_stop,
                        init_stop,
                        t1_price,
                        t2_price,
                        t3_price,
                        target_hits,
                        days_held,
                        dist_days_today,
                        t1_hit_time,
                        t2_hit_time,
                        t3_hit_time,
                    )

                    if not exit_signal:
                        t1_str = f"${t1_price:.2f}" if t1_price is not None else "—"
                        logger.info(
                            f"  {symbol}: hold (cur ${cur_price:.2f}, "
                            f"stop ${active_stop:.2f}, t1 {t1_str}, "
                            f"day {days_held}, hits {target_hits})"
                        )
                        continue

                    fraction = exit_signal["fraction"]
                    stage = exit_signal["stage"]
                    new_stop = exit_signal.get("new_stop")

                    # Route exit through executor (atomicity + audit logging)
                    # Stop-raise-only (fraction=0) skips exit_trade, just updates stop
                    logger.info(
                        f"  {symbol}: {stage.upper()} — {exit_signal['reason']}"
                    )
                    if fraction > 0:
                        logger.info(f"      (exit {int(fraction*100)}%)")

                    # Route through executor for all cases (stop-raise-only when fraction=0)
                    # Pass cursor for transactional integrity: all exit updates in same transaction
                    # as position queries and state checks above (prevents orphaned state)
                    result = self.executor.exit_trade(
                        trade_id=trade_id,
                        exit_price=cur_price if fraction > 0 else None,
                        exit_reason=exit_signal["reason"],
                        exit_fraction=fraction,  # 0 for stop-raise-only
                        exit_stage=stage,
                        new_stop_price=new_stop,
                        cur=cur,
                    )
                    if fraction == 0 and result.get("success"):
                        logger.info(f"      -> Stop raised to ${new_stop:.2f}")
                        exits_executed += 1
                    elif result.get("success"):
                        exits_executed += 1
                        logger.info(f"      -> {result['message']}")
                    else:
                        logger.error(f"      -> FAILED: {result.get('message')}")

                logger.info(f"\n{'='*70}")
                logger.info(f"Exits executed: {exits_executed}/{len(trades)} positions")
                logger.info(f"{'='*70}\n")

                # NEW: Audit closed trades for performance (Phase 2 integration)
                try:
                    cur.execute(
                        """
                        SELECT DISTINCT trade_id FROM algo_trades
                        WHERE status = %s AND exit_date = %s
                    """,
                        (TradeStatus.CLOSED.value, current_date),
                    )
                    closed_trades = cur.fetchall()
                    for (trade_id,) in closed_trades:
                        if auditor:
                            auditor.audit_exit(trade_id)
                except (DatabaseError, ValueError) as audit_err:
                    logger.error(f"Warning: Failed to audit closed trades (non-blocking): {type(audit_err).__name__}: {audit_err}")

                return exits_executed
            except (ValueError, RuntimeError) as e:
                logger.error(f"Exit engine error (configuration or data): {type(e).__name__}: {e}")
                raise
            except DatabaseError as e:
                logger.critical(f"Exit engine database error (halting): {e}")
                raise
            except Exception as e:
                logger.exception(f"Unexpected error in exit engine: {type(e).__name__}: {e}")
                raise

    # ---------- Decision logic ----------

    def _evaluate_position(
        self,
        cur,
        symbol,
        current_date,
        cur_price,
        prev_close,
        entry_price,
        active_stop,
        init_stop,
        t1_price,
        t2_price,
        t3_price,
        target_hits,
        days_held,
        dist_days_today,
        t1_hit_time=None,
        t2_hit_time=None,
        t3_hit_time=None,
    ) -> dict[str, Any] | None:
        """Decide what (if any) exit to take. Returns dict or None.

        Target hit times prevent duplicate exits when price bounces around target levels.
        If a target was hit today, we skip the exit even if price is still above the level.
        """
        # ISSUE #5 FIX: Enforce minimum holding period (no same-day exits)
        # Fail-closed: if config missing, raise error instead of defaulting to 1 day
        min_hold_val = self.config.get("min_hold_days")
        if min_hold_val is None:
            raise ValueError("CRITICAL: min_hold_days config missing. Cannot enforce minimum holding period.")
        min_hold_days = int(min_hold_val)
        if days_held < min_hold_days:
            return None  # Not ready to exit yet

        # Compute R-multiple for use across rules (Curtis Faith's R-unit framework)
        risk_per_share = Decimal(str(entry_price)) - Decimal(str(init_stop))
        if risk_per_share <= 0:
            logger.warning(
                f"[exit_engine] {symbol}: init_stop ({init_stop:.2f}) >= entry ({entry_price:.2f}) "
                "— R-based exits disabled for this position; hard stop still active"
            )
        r_mult = (
            float(((Decimal(str(cur_price)) - Decimal(str(entry_price))) / risk_per_share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if risk_per_share > 0 else 0
        )

        # 1. STOP (capital preservation always wins)
        if cur_price <= active_stop:
            return {
                "stage": "stop",
                "fraction": 1.0,
                "reason": f"STOP hit: ${cur_price:.2f} <= ${active_stop:.2f}",
            }

        # 2. MINERVINI BREAK — close < 21-EMA on volume, OR clean break of 50-DMA
        if self._is_minervini_break(cur, symbol, current_date, cur_price):
            return {
                "stage": "stop",
                "fraction": 1.0,
                "reason": "Minervini trend break: closed below key MA on volume",
            }

        # 3. RS-LINE BREAK vs SPY (O'Neil) — exit if relative strength deteriorates
        if self.config.get("exit_on_rs_line_break_50dma", True):
            if self._rs_line_breaking(cur, symbol, current_date):
                return {
                    "stage": "stop",
                    "fraction": 1.0,
                    "reason": "RS line broke below 50-DMA — relative strength deterioration",
                }

        # 4. TIME — but with O'Neil 8-week rule override for big winners
        max_hold_val = self.config.get("max_hold_days")
        if max_hold_val is None:
            raise ValueError("CRITICAL: max_hold_days config missing. Cannot enforce maximum holding period for exits.")
        max_hold = int(max_hold_val)
        if days_held >= max_hold:
            # 8-week rule: if stock gained >= 20% in first 3 weeks, hold for 8 weeks
            eight_wk_val = self.config.get("eight_week_rule_threshold_pct")
            if eight_wk_val is None:
                raise ValueError("CRITICAL: eight_week_rule_threshold_pct config missing. Cannot apply 8-week rule.")
            eight_wk_threshold = float(eight_wk_val)
            eight_wk_window_val = self.config.get("eight_week_rule_window_days")
            if eight_wk_window_val is None:
                raise ValueError("CRITICAL: eight_week_rule_window_days config missing. Cannot apply 8-week rule.")
            eight_wk_window = int(eight_wk_window_val)
            eight_wk_ext = self._eight_week_rule_active(
                cur,
                symbol,
                current_date,
                entry_price,
                days_held,
                eight_wk_threshold,
                eight_wk_window,
            )
            if (
                eight_wk_ext and days_held < 56
            ):  # 8 weeks = 40 trading days; calendar 56
                # Don't exit on time; let the trail / stop manage it
                pass
            else:
                return {
                    "stage": "time",
                    "fraction": 1.0,
                    "reason": f"TIME exit: {days_held} days >= {max_hold} max",
                }

        # 5. BREAKEVEN STOP MOVE at +1R (Curtis Faith research — premature is worse)
        # This is a "raise stop" not an exit. The orchestrator handles via new_stop.
        move_be_val = self.config.get("move_be_at_r")
        if move_be_val is None:
            raise ValueError("CRITICAL: move_be_at_r config missing. Cannot determine breakeven stop move trigger.")
        if (
            r_mult >= float(move_be_val)
            and active_stop < entry_price
        ):
            return {
                "stage": "raise_stop_be",
                "fraction": 0.0,  # 0 = no exit, just raise stop
                "reason": f"+{r_mult:.2f}R achieved — raise stop to breakeven",
                "new_stop": entry_price,
            }

        # 6-8. Tiered target exits — must scale sequentially T1 → T2 → T3
        # target_hits: 0=no targets, 1=T1 hit, 2=T1+T2 hit, 3=all hit
        # This ensures we scale out properly instead of jumping to final exit
        # target_*_hit_time prevents duplicate exits if price bounces around target levels

        # Check if a target was already hit today (idempotency)
        def _was_hit_today(hit_time):
            if hit_time is None:
                return False
            hit_date = hit_time.date() if hasattr(hit_time, "date") else hit_time
            return hit_date == current_date

        require_pb = bool(self.config.get("require_target_pullback", False))

        # First check T1 if it hasn't been hit yet
        if target_hits == 0 and t1_price is not None and cur_price >= t1_price:
            if not _was_hit_today(t1_hit_time) and (
                not require_pb or self._is_pulling_back(cur, symbol, current_date)
            ):
                return {
                    "stage": "target_1",
                    "fraction": 0.50,
                    "reason": f"T1 exit: ${cur_price:.2f} >= ${t1_price:.2f} (1.5R)",
                    "new_stop": max(active_stop, entry_price),
                }

        # Then check T2 only if T1 already hit
        if target_hits == 1 and t2_price is not None and cur_price >= t2_price:
            if not _was_hit_today(t2_hit_time) and (
                not require_pb or self._is_pulling_back(cur, symbol, current_date)
            ):
                stop_for_t2 = (
                    max(active_stop, t1_price) if t1_price is not None else active_stop
                )
                return {
                    "stage": "target_2",
                    "fraction": 0.50,
                    "reason": f"T2 exit: ${cur_price:.2f} >= ${t2_price:.2f} (3R)",
                    "new_stop": stop_for_t2,
                }

        # Finally check T3 only if T1 and T2 already hit
        if target_hits == 2 and t3_price is not None and cur_price >= t3_price:
            if not _was_hit_today(t3_hit_time):
                return {
                    "stage": "target_3",
                    "fraction": 1.0,
                    "reason": f"T3 target hit: ${cur_price:.2f} >= ${t3_price:.2f} (4R) - FINAL EXIT",
                }

        # 9. CHANDELIER TRAIL — once profitable, trail by 3xATR from highest high
        # Switches to 21-EMA trail after 10 days for tighter management
        chandelier_enabled = self.config.get("use_chandelier_trail")
        if chandelier_enabled is None:
            raise ValueError("CRITICAL: use_chandelier_trail config missing. Cannot determine trailing stop behavior.")
        if bool(chandelier_enabled) and r_mult >= 1.0:
            chand_stop = self._chandelier_or_ema_stop(
                cur, symbol, current_date, days_held
            )
            if chand_stop and chand_stop > active_stop:
                return {
                    "stage": "raise_stop_trail",
                    "fraction": 0.0,
                    "reason": f"Chandelier/EMA trail tightens stop to ${chand_stop:.2f}",
                    "new_stop": chand_stop,
                }

        td_seq_enabled = self.config.get("exit_on_td_sequential")
        if td_seq_enabled is None:
            raise ValueError("CRITICAL: exit_on_td_sequential config missing. Cannot determine TD Sequential exit behavior.")
        if bool(td_seq_enabled) and target_hits >= 1:
            if r_mult >= 0.5:
                td_state = self._get_td_state(cur, symbol, current_date)
                if (
                    td_state.get("combo_13_complete")
                    and td_state.get("setup_type") == "sell"
                ):
                    return {
                        "stage": "td_combo_13",
                        "fraction": 1.0,  # full exit on 13
                        "reason": f"TD Combo 13-count exhaustion (FULL EXIT, R={r_mult:.2f})",
                    }
                if td_state.get("completed_9") and td_state.get("setup_type") == "sell":
                    return {
                        "stage": "td_exhaustion",
                        "fraction": 0.50,
                        "reason": f"TD Sequential 9-count exhaustion (R={r_mult:.2f})",
                        "new_stop": max(active_stop, entry_price),
                    }

        # 9. FIRST RED DAY (O'Neill) — after 20%+ gain, first big down day on heavy volume
        # Institutional distribution day after parabolic run — exit 50%
        if r_mult >= 2.5 and prev_close is not None and prev_close > 0:
            down_pct = float(((Decimal(str(prev_close)) - Decimal(str(cur_price))) / Decimal(str(prev_close)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if down_pct >= 1.5:  # Close < prior close * 0.985 = 1.5% down
                vol_check = self._check_volume_spike(cur, symbol, current_date, 1.5)
                if vol_check:
                    return {
                        "stage": "first_red_day",
                        "fraction": 0.50,
                        "reason": f"First Red Day: down {down_pct:.2f}% on heavy volume (R={r_mult:.2f})",
                        "new_stop": max(active_stop, entry_price),
                    }

        # 13. CLIMAX RUN EXHAUSTION — parabolic moves exhaust and reverse sharply
        # Trigger: 30+ days held, 5R+ gain, 20%+ gain in last 10 days = institutional climax distribution
        if days_held > 30 and r_mult >= 5.0:
            gain_10d = self._compute_gain_last_n_days(cur, symbol, current_date, 10)
            if gain_10d is not None and gain_10d >= 20.0:
                return {
                    "stage": "climax_exhaustion",
                    "fraction": 0.50,
                    "reason": f"Climax run exhaustion: gained {gain_10d:.1f}% in last 10d (R={r_mult:.2f})",
                    "new_stop": max(active_stop, entry_price),
                }

        # 8. DISTRIBUTION — reduce position and raise stop to at least breakeven.
        # Full exit on market distribution is too blunt: it forces out positions that
        # may still be working. Minervini/O'Neil use distribution days as a signal to
        # tighten risk, not automatically liquidate. Partial exit books some profit while
        # the raised stop protects the remainder.
        dist_enabled = self.config.get("exit_on_distribution_day")
        if dist_enabled is None:
            raise ValueError("CRITICAL: exit_on_distribution_day config missing. Cannot determine distribution day exit behavior.")
        if (
            bool(dist_enabled)
            and dist_days_today is not None
        ):
            max_dd_val = self.config.get("max_distribution_days")
            if max_dd_val is None:
                raise ValueError("CRITICAL: max_distribution_days config missing. Cannot enforce distribution day limit.")
            max_dd = int(max_dd_val)
            if dist_days_today > max_dd:
                return {
                    "stage": "distribution",
                    "fraction": 0.5,
                    "new_stop": max(active_stop, entry_price),
                    "reason": f"Market distribution: {dist_days_today} dist days > {max_dd} — reducing 50%, stop raised to breakeven",
                }

        return None

    # ---------- Data helpers ----------

    def _fetch_alpaca_quote(self, symbol: str) -> float | None:
        """Fetch real-time quote from Alpaca Data API.

        Raises on API failure or missing credentials. Returns None only if market is closed.

        When API returns status 200 but no valid price data:
        - Market open: Raises RuntimeError (API is broken, got 200 but no quote)
        - Market closed: Returns None (expected; market closed means no intraday quotes)
        """
        try:
            creds = get_alpaca_credentials()
            key = creds.get("key")
            secret = creds.get("secret")

            if not key or not secret:
                raise RuntimeError(f"CRITICAL: Alpaca credentials missing. Cannot fetch quote for {symbol}.")

            data_url = get_alpaca_data_url()
            # Use latest quotes endpoint for real-time midpoint price
            response = requests.get(
                f"{data_url}/v2/quotes/latest",
                params={"symbols": symbol, "feed": "sip"},
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                timeout=get_alpaca_timeout(),
            )

            if response.status_code == 200:
                data = response.json()
                quotes = data.get("quotes", {})
                quote = quotes.get(symbol, {})

                # Calculate midpoint from bid/ask
                bid = quote.get("bp")
                ask = quote.get("ap")
                if bid is not None and ask is not None and bid > 0 and ask > 0:
                    midpoint = (float(bid) + float(ask)) / 2.0
                    return midpoint
                # Fallback to last price if available
                last_price = quote.get("lp")
                if last_price is not None:
                    return float(last_price)

                # Status 200 but no valid price data: check if market is open
                # During market open, this is an API error (we should get valid data)
                # During market closed, this is expected (no intraday quotes available)
                if MarketCalendar.is_market_open():
                    raise RuntimeError(
                        f"Alpaca quote API returned status 200 but no valid price data for {symbol}. "
                        f"Market is open; this indicates an API issue, not market closure."
                    )
                return None
            elif response.status_code == 401:
                raise RuntimeError(f"Alpaca quote API authentication failed for {symbol}")
            else:
                raise RuntimeError(
                    f"Alpaca quote API error for {symbol}: status {response.status_code}"
                )
        except requests.Timeout as e:
            raise ExchangeAPIError(f"Alpaca quote API timeout for {symbol}") from e
        except requests.RequestException as e:
            raise ExchangeAPIError(f"Alpaca quote API request error for {symbol}: {e}") from e
        except (RuntimeError, ValueError):
            raise
        except Exception as e:
            raise ExchangeAPIError(f"Alpaca quote API error for {symbol}: {type(e).__name__}: {e}") from e

    def _fetch_recent_prices(
        self, cur, symbol: str, current_date
    ) -> tuple[float | None, float | None]:
        """Return (current_price, previous_close) with intraday support.

        Strategy:
        1. Try to fetch real-time quote from Alpaca (for intraday stop checking)
        2. If market closed (quote returns None), fall back to daily closes
        3. If API fails (raises exception), propagate to caller for immediate halt

        This ensures stop losses execute on current prices during market hours.
        On API failure, exit engine halts rather than using stale daily closes.
        """
        # Try real-time quote first (intraday pricing, raises on API failure)
        current_price = self._fetch_alpaca_quote(symbol)

        if current_price is not None:
            # Got real-time quote; fetch previous close from daily data
            cur.execute(
                """
                SELECT close FROM price_daily
                WHERE symbol = %s AND date < %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, current_date),
            )
            prev_row = cur.fetchone()
            prev_close = (
                float(prev_row[0]) if prev_row and prev_row[0] is not None else None
            )
            return current_price, prev_close

        # Fall back to daily closes (market closed or API unavailable)
        cur.execute(
            """
            SELECT date, close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 2
            """,
            (symbol, current_date),
        )
        rows = cur.fetchall()
        if not rows or len(rows[0]) < 2:
            error_msg = f"Price data missing for {symbol} - cannot evaluate exits"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        cur_price = float(rows[0][1]) if rows[0][1] is not None else None
        if cur_price is None:
            error_msg = f"Current price is NULL for {symbol}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        prev_close = (
            float(rows[1][1]) if len(rows) > 1 and rows[1][1] is not None else None
        )
        return cur_price, prev_close

    def _fetch_market_dist_days(self, cur, current_date) -> int | None:
        cur.execute(
            """
            SELECT distribution_days_4w FROM market_health_daily
            WHERE date <= %s ORDER BY date DESC LIMIT 1
            """,
            (current_date,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _is_pulling_back(self, cur, symbol: str, current_date) -> bool:
        """Requires either 2-3% decline from recent high OR 2+ days below 5-day high.

        Real pullbacks show clear consolidation, not just a 0.5% afternoon dip.
        This prevents hair-trigger exits on winners."""
        cur.execute(
            """
            SELECT close, high FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 6
            """,
            (symbol, current_date),
        )
        rows = cur.fetchall()
        if len(rows) < 3:
            return False

        cur_close = Decimal(str(rows[0][0]))
        recent_high = max(
            Decimal(str(r[1])) if r[1] is not None else Decimal(str(r[0])) for r in rows[:5]
        )

        pullback_pct = (
            float(((recent_high - cur_close) / recent_high * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if recent_high > 0 else 0
        )
        if pullback_pct >= 2.0:
            return True

        # OR check if consolidated below high for 2+ days
        days_below_high = sum(1 for r in rows[:5] if Decimal(str(r[0])) < recent_high * Decimal("0.98"))
        return days_below_high >= 2

    def _rs_line_breaking(self, cur, symbol: str, current_date) -> bool:
        """RS line (stock/SPY ratio) breaking below its 50-day MA = exit signal."""
        cur.execute(
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
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(f"Insufficient RS data for {symbol} to calculate RS line break")
        cur_rs = Decimal(str(row[0]))
        rs_50 = Decimal(str(row[1]))
        return cur_rs < rs_50 * Decimal("0.99")

    def _eight_week_rule_active(
        self,
        cur,
        symbol,
        current_date,
        entry_price,
        days_held,
        threshold_pct,
        window_days,
    ) -> bool:
        """O'Neil 8-week rule: if stock gained 20%+ in first 3 weeks, hold for 8 weeks."""
        if days_held < window_days:
            return False
        cur.execute(
            """
            SELECT MAX(close) FROM price_daily
            WHERE symbol = %s
              AND date >= %s::date - MAKE_INTERVAL(days => %s)
              AND date <= %s::date - MAKE_INTERVAL(days => %s)
            """,
            (
                symbol,
                current_date,
                days_held,
                current_date,
                max(0, days_held - window_days),
            ),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise ValueError(f"No price data for {symbol} in 8-week window")
        max_close_in_window = Decimal(str(row[0]))
        if entry_price <= 0:
            raise ValueError(f"Invalid entry price for {symbol}: {entry_price}")
        gain_pct = float(((max_close_in_window - Decimal(str(entry_price))) / Decimal(str(entry_price)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return cast(bool, gain_pct >= threshold_pct)

    def _chandelier_or_ema_stop(
        self, cur, symbol: str, current_date, days_held: int
    ) -> float | None:
        """Trailing stop: chandelier (3xATR from highest high) for first 10d,
        then 21-EMA after."""
        switch_val = self.config.get("switch_to_21ema_after_days")
        if switch_val is None:
            raise ValueError("CRITICAL: switch_to_21ema_after_days config missing. Cannot determine EMA switch point for trailing stop.")
        switch_days = int(switch_val)
        if days_held >= switch_days:
            cur.execute(
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
            rows = cur.fetchall()
            if len(rows) < 21:
                raise ValueError(f"Insufficient price data for {symbol} to calculate 21-EMA stop")
            closes = [Decimal(str(r[0])) for r in rows]
            k = Decimal(2) / Decimal(22)
            ema = closes[0]
            for c in closes[1:]:
                ema = c * k + ema * (Decimal(1) - k)
            stop_price = ema * Decimal("0.99")
            return float(stop_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        else:
            cur.execute(
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
            row = cur.fetchone()
            if not row or not row[0] or not row[1]:
                raise ValueError(f"Insufficient data for {symbol} to calculate chandelier stop")
            hh = float(row[0])
            atr = float(row[1])
            mult_val = self.config.get("chandelier_atr_mult")
            if mult_val is None:
                raise ValueError("CRITICAL: chandelier_atr_mult config missing. Cannot calculate chandelier trailing stop.")
            mult = float(mult_val)
            return round(hh - (mult * atr), 2)

    def _get_td_state(self, cur, symbol, current_date) -> dict[str, Any]:
        """Return full TD state dict (for both 9 and 13 detection).

        Fail-fast — if TD Sequential cannot be computed, raises exception.
        TD Sequential is a required exit signal for positions.
        """
        sc = SignalComputer()
        td_state = sc.td_sequential(symbol, current_date)
        if not td_state:
            raise ValueError(f"TD Sequential calculation failed for {symbol}")
        return td_state

    def _is_minervini_break(self, cur, symbol: str, current_date, cur_price: float) -> bool:
        """Close < 50-DMA OR (close < EMA(21) AND volume > 50-day avg)."""
        cur.execute(
            """
            SELECT td.sma_50, td.ema_21,
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
        row = cur.fetchone()
        if row is None:
            return False
        sma_50, ema_21, vol, avg_vol_50 = row
        sma_50 = Decimal(str(sma_50)) if sma_50 is not None else None
        ema_21 = Decimal(str(ema_21)) if ema_21 is not None else None
        vol = float(vol) if vol is not None else 0
        avg_vol_50 = float(avg_vol_50) if avg_vol_50 is not None else 0
        cur_price_decimal = Decimal(str(cur_price))

        # Clean break of 50-DMA
        if sma_50 and cur_price_decimal < sma_50 * Decimal("0.99"):
            return True
        # Break of EMA(21) on rising volume (institutional selling)
        ema_21_float = float(ema_21) if ema_21 else None
        if ema_21_float and cur_price < ema_21_float and avg_vol_50 > 0 and vol > avg_vol_50 * 1.15:
            return True
        return False

    def _check_volume_spike(self, cur, symbol: str, current_date, volume_multiplier: float) -> bool:
        """Check if today's volume is >= volume_multiplier * average volume."""
        cur.execute(
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
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(f"Volume data unavailable for {symbol} on {current_date}")
        today_vol = float(row[0])
        avg_vol = float(row[1])
        return today_vol >= avg_vol * volume_multiplier

    def _compute_gain_last_n_days(
        self, cur, symbol: str, current_date, n_days: int
    ) -> float | None:
        """Compute % gain over the last N days (from close N days ago to current close)."""
        cur.execute(
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
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(f"Insufficient {n_days}-day price data for {symbol}")
        current = Decimal(str(row[0]))
        prior = Decimal(str(row[1]))
        if prior <= 0:
            raise ValueError(f"Invalid price data for {symbol}: prior close = {prior}")
        return float(((current - prior) / prior * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


if __name__ == "__main__":
    from algo.infrastructure import get_config

    config = get_config()
    engine = ExitEngine(config)
    exits = engine.check_and_execute_exits()
    logger.info(f"Exits executed: {exits}")
