#!/usr/bin/env python3
"""
Position Monitor - Institutional-grade daily position health checks

Runs each trading day on every open position. For each one:
  1. Refresh current price + position value + unrealized P&L
  2. Recompute trailing stop using ATR / swing low / 50-DMA - STOPS ONLY GO UP
  3. Score position health across factors:
        a. Relative strength vs SPY (degrading = warning)
        b. Sector strength (turned weak = warning)
        c. Distance from peak unrealized (giving back gains = warning)
        d. Time decay (over half of max_hold without progress = warning)
        e. Earnings proximity (block_window approaching = warning)
        f. Distribution day count
  4. Aggregate health flags. >= halt_flag_count -> propose early exit.
  5. Persist updated state on algo_positions and write audit entries.

The monitor PROPOSES adjustments - actual stop-raising executes via
TradeExecutor.exit_trade(new_stop_price=...) in the orchestrator.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

import psycopg2
import requests
from psycopg2.extensions import cursor as PsycopgCursor

from config.api_endpoints import get_alpaca_base_url
from config.credential_manager import get_alpaca_credentials, get_credential_manager
from utils.db import DatabaseContext

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class PositionValidationError(Exception):
    """Raised when a position fails validation and cannot be monitored."""


class PositionMonitor:
    """Daily position health checker and stop adjuster."""

    def _with_cursor(self, operation: Callable[[PsycopgCursor[Any]], Any], mode: str = "read") -> Any:
        """Execute operation with cursor via DatabaseContext."""
        with DatabaseContext(mode) as cur:
            return operation(cur)

    def __init__(self, config: AlgoConfig) -> None:
        self.config = config

    def check_stale_orders(self, current_date: _date | None = None) -> dict[str, Any]:
        """Check for orders stuck in pending state >1 hour. Auto-cancel if >2 hours.

        Stuck orders = likely API issue or rejection. Orders >2 hours old are auto-cancelled
        (fail-closed: stuck orders block exit logic, so cancellation is safer than waiting).
        Filters out orders for halted symbols (these stay pending naturally).

        Returns dict with:
          - status: "OK", "STALE_ORDERS_FOUND", "AUTO_CANCELLED", or "ERROR"
          - count: number of orders in that state
          - orders: list of order tuples
          - cancelled: list of cancelled order details (if auto_cancelled)
        """
        if current_date is None:
            current_date = _date.today()

        try:
            alert_threshold = int(self.config["stale_order_alert_minutes"])
            auto_cancel_threshold = int(self.config["stale_order_auto_cancel_minutes"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        with DatabaseContext("write") as cur:
            try:
                cur.execute(
                    """
                    SELECT trade_id, symbol, entry_price, entry_quantity, created_at
                    FROM algo_trades
                    WHERE status = 'pending'
                      AND created_at < CURRENT_TIMESTAMP - INTERVAL %s
                    ORDER BY created_at ASC
                """,
                    (f"{alert_threshold} minutes",),
                )
                stale_orders = cur.fetchall()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Failed to check for stale orders: {e}. Cannot proceed without this critical check."
                ) from e

            if stale_orders:
                # Filter out halted symbols (halts are normal, not actionable)
                # Fail fast if halt check fails - don't skip filtering silently
                try:
                    from algo.infrastructure import MarketEventHandler

                    meh = MarketEventHandler(self.config)
                    filtered_stale = []
                    halted_orders = []
                    for row in stale_orders:
                        trade_id, symbol, price, qty, created_at = row
                        halt_check = meh.check_single_stock_halt(symbol)
                        if halt_check and halt_check.get("halted") is True:
                            logger.info(f"    {trade_id} {symbol} pending (but halted, expected)")
                            halted_orders.append(row)
                            continue
                        filtered_stale.append(row)
                    stale_orders = filtered_stale
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logger.critical(
                        f"[HALT_CHECK] Could not check halts for stale orders: {e}. "
                        f"Continuing without halt filtering will process halted orders."
                    )
                    raise RuntimeError(
                        f"Halt check failed: {e}. Cannot proceed without knowing which orders are halted."
                    ) from e

                if stale_orders:
                    logger.info(
                        f"\n  [ALERT] Found {len(stale_orders)} orders pending >{alert_threshold}m (excluding halted):"
                    )

                    cancelled_orders = []
                    trades_to_update = []
                    audit_entries = []

                    for row in stale_orders:
                        trade_id, symbol, price, qty, created_at = row
                        # Ensure created_at is timezone-aware (UTC) for subtraction
                        if not getattr(created_at, "tzinfo", None):
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        age_minutes = int((datetime.now(timezone.utc) - created_at).total_seconds() / 60)
                        logger.info(f"    {trade_id} {symbol} {qty}@{price} (pending {age_minutes}m)")

                        # Auto-cancel if > 2 hours (or configured threshold)
                        if age_minutes >= auto_cancel_threshold:
                            # Fail fast on Alpaca cancellation - don't mark DB as cancelled if API call fails
                            try:
                                self._cancel_on_alpaca(trade_id)
                            except (ValueError, ZeroDivisionError, TypeError) as api_e:
                                logger.critical(
                                    f"[STALE_ORDER] Could not cancel {trade_id} on Alpaca: {api_e}. "
                                    f"Alpaca and database will diverge if we mark cancelled in DB. Aborting auto-cancel."
                                )
                                raise RuntimeError(
                                    f"Alpaca cancellation failed for {trade_id}: {api_e}. "
                                    f"Cannot proceed with DB update to avoid state divergence."
                                ) from api_e

                            # Only mark as cancelled after successful Alpaca cancellation
                            trades_to_update.append(trade_id)
                            audit_entries.append(
                                (
                                    "STALE_ORDER_AUTO_CANCELLED",
                                    symbol,
                                    f"Trade {trade_id}: {qty}@${price} pending {age_minutes}m >= auto-cancel threshold",
                                    "WARN",
                                    "position_monitor",
                                    "auto_cancelled",
                                )
                            )
                            cancelled_orders.append(
                                {
                                    "trade_id": trade_id,
                                    "symbol": symbol,
                                    "qty": qty,
                                    "price": price,
                                    "age_minutes": age_minutes,
                                }
                            )
                            logger.warning(
                                f"  [AUTO-CANCEL] {trade_id} {symbol} (pending {age_minutes}m >= {auto_cancel_threshold}m threshold)"
                            )

                    # Batch update database (atomic: trades + audit logs via savepoint)
                    if trades_to_update:
                        sp_name = "sp_stale_cancel"
                        cur.execute(f"SAVEPOINT {sp_name}")
                        try:
                            cur.execute(
                                """UPDATE algo_trades
                                   SET status = %s, updated_at = CURRENT_TIMESTAMP
                                   WHERE trade_id = ANY(%s)""",
                                ("cancelled", trades_to_update),
                            )
                            cur.executemany(
                                """INSERT INTO algo_audit_log (
                                       action_type, symbol, action_date, details, severity, actor, status, created_at
                                   ) VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                                audit_entries,
                            )
                        except (
                            psycopg2.DatabaseError,
                            psycopg2.OperationalError,
                        ) as audit_e:
                            cur.execute(f"ROLLBACK TO {sp_name}")
                            logger.critical(
                                f"[AUDIT_FAILURE] Stale order batch transaction failed (rolled back): {audit_e}"
                            )
                            raise

                    # Proceed to return (outer transaction will commit)
                    if cancelled_orders:
                        return {
                            "status": "AUTO_CANCELLED",
                            "count": len(cancelled_orders),
                            "cancelled": cancelled_orders,
                            "alert_count": len(stale_orders) - len(cancelled_orders),
                        }

                    return {
                        "status": "STALE_ORDERS_FOUND",
                        "count": len(stale_orders),
                        "orders": stale_orders,
                    }
            return {"status": "OK", "count": 0}

    def check_sector_concentration(self, current_date: _date | None = None) -> dict[str, Any]:
        """Check if portfolio is overly concentrated in one sector.

        Alert if >3 positions in same sector (concentration risk).

        Raises:
            RuntimeError: If concentration check fails (fail-fast for risk management)
        """
        if current_date is None:
            current_date = _date.today()

        with DatabaseContext("read") as cur:
            try:
                cur.execute("""
                    -- CRITICAL FIX: Return NULL for missing sector (don't hide with 'Unknown')
                    SELECT cp.sector, COUNT(DISTINCT ap.symbol) as position_count
                    FROM algo_positions ap
                    LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                    WHERE ap.status = 'open' AND ap.quantity > 0
                    GROUP BY cp.sector
                    HAVING COUNT(DISTINCT ap.symbol) > 3
                    ORDER BY position_count DESC
                """)
                concentrated = cur.fetchall()
                if concentrated:
                    logger.info("\n  [CONCENTRATION ALERT]")
                    for sector, count in concentrated:
                        logger.info(f"    {sector}: {count} positions (>3 is risky)")
                    return {"status": "HIGH_CONCENTRATION", "sectors": concentrated}
                return {"status": "OK", "sectors": []}
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Sector concentration check failed: {e}. "
                    f"Cannot proceed with position monitoring without valid concentration metrics."
                ) from e

    def review_positions(self, current_date: _date | None = None) -> list[dict[str, Any]]:
        """Review every open position. Returns list of recommendations."""
        if current_date is None:
            current_date = _date.today()

        recs = []
        with DatabaseContext("write") as cur:
            # Issue #24: Check margin utilization and warn/halt if excessive
            try:
                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                eq_row = cur.fetchone()

                if eq_row is None or eq_row[0] is None:
                    logger.warning(
                        "[POSITION_MONITOR] Portfolio snapshot unavailable yet (Phase 9 reconciliation not completed). "
                        "Skipping margin utilization check for now."
                    )
                    return []  # Return empty recommendations if no snapshot yet

                total_equity = float(eq_row[0])
                if total_equity <= 0:
                    raise PositionValidationError(
                        f"Invalid portfolio equity: {total_equity} <= 0. Cannot monitor positions with zero or negative equity."
                    )

                # Compute margin usage = (equity - buying_power) / equity
                # Using proxy: if total open position value > 90% of equity, halt new entries
                cur.execute("""
                    SELECT COUNT(*), SUM(position_value) FROM algo_positions WHERE status = 'open'
                """)
                count_row = cur.fetchone()
                if count_row is None:
                    raise PositionValidationError("Query for open positions returned None - database error")
                position_count = count_row[0]
                pos_value_sum = count_row[1] if len(count_row) > 1 else None

                # CRITICAL: If we have open positions but position_value is NULL, that's data corruption
                if position_count > 0 and pos_value_sum is None:
                    raise PositionValidationError(
                        f"CRITICAL: {position_count} open positions exist but SUM(position_value) is NULL. "
                        "Database corruption detected. Margin calculation halted."
                    )

                # NULL sum means no open positions (SUM of empty set is NULL, not 0)
                pos_value = float(pos_value_sum) if pos_value_sum is not None else 0.0
                if pos_value < 0:
                    # Negative total may be caused by a short position written during
                    # an Alpaca sync anomaly. Log at ERROR but do not halt - Phase 4
                    # reconciliation will close any short positions in DB. A true
                    # corruption scenario (negative equity from math error) is caught
                    # by the total_equity <= 0 check above.
                    logger.error(
                        f"[MARGIN_CHECK] Total position value {pos_value:.2f} < 0 - "
                        "likely stale short position in algo_positions. "
                        "Reconciliation (Phase 4) will close it. Continuing with pos_value=0."
                    )
                    pos_value = 0.0

                margin_util_pct = pos_value / total_equity * 100
                if margin_util_pct > 90:
                    logger.critical(
                        f"[MARGIN HALT] Position value {margin_util_pct:.1f}% of equity - liquidation risk imminent"
                    )
                    raise PositionValidationError(
                        f"Margin utilization critical: {margin_util_pct:.1f}% of equity (>90%). Cannot proceed with position monitoring."
                    )
                elif margin_util_pct > 80:
                    logger.warning(f"[MARGIN WARNING] Position value {margin_util_pct:.1f}% of equity > 80%")
            except PositionValidationError:
                raise
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as margin_e:
                raise PositionValidationError(
                    f"Margin validation failed: {margin_e}. Cannot proceed without valid margin check."
                ) from margin_e

            try:
                conc = self.check_sector_concentration(current_date)
                if conc["status"] == "HIGH_CONCENTRATION":
                    logger.info("  [WARNING]  Portfolio concentration risk detected")
            except RuntimeError as conc_e:
                raise PositionValidationError(
                    f"Sector concentration check failed: {conc_e}. Cannot proceed without valid concentration metrics."
                ) from conc_e

            cur.execute("""
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.target_1_price, t.target_2_price, t.target_3_price,
                       t.trade_date, t.signal_date,
                       p.position_id, p.quantity, p.target_levels_hit,
                       p.current_stop_price, p.current_price
                FROM algo_trades t
                JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.status IN ('open','pending') AND p.status = 'open' AND p.quantity > 0
                  AND p.trade_ids_arr IS NOT NULL AND array_length(p.trade_ids_arr, 1) > 0
                """)
            positions = cur.fetchall()

            logger.info(f"\n{'=' * 70}")
            logger.info(f"POSITION MONITOR - {current_date}")
            logger.info(f"{'=' * 70}")
            logger.info(f"Reviewing {len(positions)} open position(s)\n")

            validation_errors = []
            for i, row in enumerate(positions):
                try:
                    rec = self._evaluate_position(row, current_date, cur)
                except PositionValidationError as e:
                    symbol = row[1]  # symbol is at index 1 in the row tuple
                    trade_id = row[0]
                    position_id = row[9]
                    error_msg = str(e)
                    validation_errors.append((symbol, error_msg))
                    # Include failed position in results so orchestrator has complete visibility
                    recs.append(
                        {
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "position_id": position_id,
                            "action": "FAILED_VALIDATION",
                            "error": error_msg,
                        }
                    )
                    logger.warning(f"  Validation failed for {symbol}: {error_msg}")
                    continue

                recs.append(rec)
                self._print_recommendation(rec)
                try:
                    sp_name = f"sp_pos_{i}"
                    cur.execute(f"SAVEPOINT {sp_name}")
                    self._persist_review(rec, cur, i)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.error(f"Failed to persist review for {rec['symbol']}: {e}")
                    cur.execute(f"ROLLBACK TO {sp_name}")
                    continue

            # Log warning for any validation failures (included in recs as FAILED_VALIDATION)
            if validation_errors:
                logger.warning(
                    f"[WARNING] {len(validation_errors)}/{len(positions)} position(s) failed validation (included in results)"
                )

            return recs

    def _evaluate_position(self, row: Any, current_date: _date | datetime, cur: PsycopgCursor[Any]) -> dict[str, Any]:  # noqa: C901
        (
            trade_id,
            symbol,
            entry_price,
            init_stop,
            _t1_price,
            _t2_price,
            _t3_price,
            trade_date,
            _signal_date,
            position_id,
            quantity,
            target_hits,
            current_stop,
            _db_current_price,
        ) = row

        if entry_price is None:
            msg = f"Entry price missing for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        if init_stop is None:
            msg = f"Stop loss price missing for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)

        try:
            entry_price = float(entry_price)
        except (ValueError, TypeError) as e:
            msg = f"Invalid entry price {entry_price} for {symbol}: {e}"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg) from e

        try:
            init_stop = float(init_stop)
        except (ValueError, TypeError) as e:
            msg = f"Invalid stop price {init_stop} for {symbol}: {e}"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg) from e

        if entry_price <= 0:
            msg = f"Invalid entry price {entry_price} for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        if init_stop <= 0:
            msg = f"Invalid stop {init_stop} for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        if init_stop >= entry_price:
            msg = f"Stop {init_stop} >= entry {entry_price} for {symbol} - invalid trade"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        active_stop = float(current_stop) if current_stop else init_stop
        if target_hits is None:
            logger.critical(
                f"CRITICAL: {symbol} - target_hits is NULL in algo_trades. "
                f"Cannot evaluate position without target hit count. "
                f"Database schema or trade data corrupted."
            )
            raise ValueError(f"Position {symbol}: target_hits missing. Cannot evaluate target progress.")
        target_hits = int(target_hits)
        days_held = (current_date - trade_date).days
        try:
            max_hold = int(self.config["max_hold_days"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        # 1. Current market data
        try:
            cur_price, atr, sma_50, _ema_12 = self._fetch_current_market(symbol, current_date, cur)
        except ValueError as e:
            msg = f"Position {symbol} cannot be monitored: {e}"
            logger.error(f"REJECT: {msg}")
            raise PositionValidationError(msg) from e

        # P&L (using Decimal for precision)
        risk_per_share = entry_price - init_stop
        if risk_per_share <= 0:
            raise PositionValidationError(
                f"Invalid risk per share for {symbol}: entry {entry_price} - stop {init_stop} = {risk_per_share}. "
                "Stop must be strictly below entry price."
            )
        r_multiple = (cur_price - entry_price) / risk_per_share

        # Use Decimal for monetary calculations to avoid floating point precision loss
        if quantity <= 0:
            raise PositionValidationError(f"Invalid quantity for {symbol}: {quantity} <= 0")

        price_diff = Decimal(str(cur_price)) - Decimal(str(entry_price))
        entry_price_dec = Decimal(str(entry_price))
        quantity_dec = Decimal(str(quantity))

        if entry_price_dec <= 0:
            raise PositionValidationError(f"Invalid entry price for {symbol}: {entry_price_dec} <= 0")

        unrealized_pnl = float((price_diff * quantity_dec).quantize(Decimal("0.01"), ROUND_HALF_UP))
        unrealized_pct = float((price_diff / entry_price_dec * 100).quantize(Decimal("0.01"), ROUND_HALF_UP))

        # 2. Recompute trailing stop (only ratchet UP, never down)
        proposed_stop = self._compute_trailing_stop(
            entry_price,
            active_stop,
            cur_price,
            atr,
            sma_50,
            target_hits,
        )

        if proposed_stop > cur_price:
            logger.error(f"ERROR: Proposed stop ${proposed_stop:.2f} > current price ${cur_price:.2f} for {symbol}")
            proposed_stop = cur_price - 0.01  # Clamp to 1c below market
            logger.info(f"  Clamped stop to ${proposed_stop:.2f}")

        # 3. Health flags
        flags = []

        # 3a. Relative strength vs SPY (degrading?)
        rs_state = self._check_relative_strength(symbol, current_date, cur)
        if rs_state == "weakening":
            flags.append("RS_WEAKENING")
        rs_label = rs_state

        # 3b. Sector turned weak?
        sector_state = self._check_sector_health(symbol, current_date, cur)
        if sector_state == "weakening":
            flags.append("SECTOR_WEAK")

        # 3c. Giving back gains (>33% retrace from peak)?
        peak_pct = self._max_unrealized_pct(symbol, trade_date, current_date, entry_price, cur)
        if peak_pct > 5 and unrealized_pct < peak_pct * 0.66:
            flags.append("GIVING_BACK_GAINS")

        # 3d. Time decay (>= half of max_hold, but no T1 hit yet)
        if days_held >= max_hold * 0.5 and target_hits == 0 and r_multiple < 0.5:
            flags.append("TIME_DECAY_NO_PROGRESS")

        # 3e. Earnings proximity (warn and skip if data unavailable - earnings data is optional enrichment)
        days_to_earn: int | None = None
        try:
            days_to_earn = self._days_to_earnings(symbol, current_date, cur)
            if 0 <= days_to_earn <= 3:
                flags.append(f"EARNINGS_IN_{days_to_earn}D")
        except ValueError as e:
            logger.warning(f"[POSITION_MONITOR] Earnings data unavailable for {symbol} - skipping proximity check: {e}")
        except RuntimeError as e:
            raise PositionValidationError(f"Cannot evaluate earnings proximity for {symbol}: {e}") from e

        # 3f. Distribution-day stress
        try:
            market_dist_days = self._fetch_market_dist_days(current_date, cur)
        except (ValueError, RuntimeError) as e:
            raise PositionValidationError(f"Cannot evaluate market distribution days for position {symbol}: {e}") from e

        try:
            max_dist_days = int(self.config["max_distribution_days"])
            halt_flag_count = int(self.config["position_halt_flag_count"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        if market_dist_days is not None and market_dist_days > max_dist_days:
            flags.append("MARKET_DISTRIBUTION_STRESS")

        # Decision logic
        action = "HOLD"
        action_reason = ""
        urgent_exit = False
        new_stop_recommended = None

        if proposed_stop > active_stop:
            # Always recommend stop-raise when computed
            new_stop_recommended = proposed_stop
            action = "RAISE_STOP"
            action_reason = f"Trail stop ${active_stop:.2f} -> ${proposed_stop:.2f}"

        if len(flags) >= halt_flag_count:
            action = "EARLY_EXIT"
            action_reason = f"{len(flags)} health flags: {', '.join(flags)}"
            urgent_exit = True

        # Special case: earnings within 1-2 days = always exit
        if days_to_earn is not None and 0 <= days_to_earn <= 2:
            action = "EARLY_EXIT"
            action_reason = f"Earnings in {days_to_earn} day(s) - flatten before report"
            urgent_exit = True

        return {
            "trade_id": trade_id,
            "symbol": symbol,
            "position_id": position_id,
            "days_held": days_held,
            "quantity": quantity,
            "entry_price": entry_price,
            "current_price": cur_price,
            "r_multiple": round(r_multiple, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pct": round(unrealized_pct, 2),
            "active_stop": active_stop,
            "proposed_stop": proposed_stop,
            "target_hits": target_hits,
            "rs_label": rs_label,
            "sector_state": sector_state,
            "flags": flags,
            "days_to_earnings": days_to_earn,
            "action": action,
            "action_reason": action_reason,
            "urgent_exit": urgent_exit,
            "new_stop_recommended": new_stop_recommended,
        }

    # ---------- Helpers ----------

    def _cancel_on_alpaca(self, trade_id: str) -> None:
        """Cancel a stale pending order on Alpaca API only.

        Raises:
            RuntimeError: If cancellation cannot be verified (fail-fast to prevent state divergence)
        """
        creds = get_alpaca_credentials()
        base_url = get_alpaca_base_url()
        alpaca_key = creds.get("key")
        alpaca_secret = creds.get("secret")

        if not alpaca_key or not alpaca_secret:
            raise RuntimeError(
                f"Cannot cancel stale order {trade_id}: Alpaca credentials unavailable. "
                f"Cannot proceed without ability to verify cancellation at broker."
            )

        url = f"{base_url}/v2/orders/{trade_id}"
        headers = {
            "APCA-API-KEY-ID": alpaca_key,
            "APCA-API-SECRET-KEY": alpaca_secret,
        }
        try:
            timeout = int(self.config["api_request_timeout_seconds"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e
        try:
            resp = requests.delete(url, headers=headers, timeout=timeout)
        except (requests.RequestException, requests.Timeout) as e:
            raise RuntimeError(
                f"Failed to cancel stale order {trade_id} on Alpaca: {e}. "
                f"Cannot proceed without confirmation of cancellation (DB/broker state would diverge)."
            ) from e

        if resp.status_code == 204 or resp.status_code == 200:
            logger.info(f"Successfully cancelled order {trade_id} on Alpaca")
        elif resp.status_code == 404:
            logger.info(f"Order {trade_id} not found on Alpaca (already closed/cancelled)")
        else:
            raise RuntimeError(
                f"Alpaca cancel failed for {trade_id} (unexpected status {resp.status_code}): {resp.text}. "
                f"Cannot mark order as cancelled in DB without broker confirmation."
            )

    def _auto_cancel_stale_order(
        self, trade_id: str, symbol: str, qty: int, price: float, age_minutes: int, cur: Any
    ) -> None:
        """Cancel a stale pending order on Alpaca and mark as cancelled in DB.

        Attempts Alpaca API cancellation first. Marks trade as cancelled in DB + adds audit log
        only if cancellation succeeds (200/204) or order already closed (404).

        Raises RuntimeError if:
        - Alpaca credentials unavailable
        - Alpaca API call fails (network/timeout/exception)
        - Alpaca returns unexpected status code
        - Database update fails

        This ensures broker/DB state consistency: if DB is marked cancelled, trade must be
        successfully cancelled at Alpaca (or already was).
        """
        try:
            creds = get_alpaca_credentials()
            base_url = get_alpaca_base_url()
            alpaca_key = creds.get("key")
            alpaca_secret = creds.get("secret")

            if not alpaca_key or not alpaca_secret:
                raise RuntimeError(
                    f"Cannot cancel order {trade_id}: Alpaca credentials unavailable. DB update blocked to maintain broker/DB state consistency."
                )
            # Attempt to cancel on Alpaca
            try:
                url = f"{base_url}/v2/orders/{trade_id}"
                headers = {
                    "APCA-API-KEY-ID": alpaca_key,
                    "APCA-API-SECRET-KEY": alpaca_secret,
                }
                try:
                    timeout = int(self.config["api_request_timeout_seconds"])
                except KeyError as e:
                    raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e
                resp = requests.delete(url, headers=headers, timeout=timeout)

                if resp.status_code == 204 or resp.status_code == 200:
                    logger.info(f"Successfully cancelled order {trade_id} on Alpaca")
                elif resp.status_code == 404:
                    logger.info(f"Order {trade_id} not found on Alpaca (already closed/cancelled)")
                else:
                    raise RuntimeError(
                        f"Alpaca cancel returned unexpected status {resp.status_code} for {trade_id}: {resp.text}. DB update blocked to maintain broker/DB state consistency."
                    )
            except (requests.RequestException, requests.Timeout) as api_e:
                raise RuntimeError(
                    f"Failed to cancel order {trade_id} on Alpaca: {api_e}. DB update blocked to maintain broker/DB state consistency."
                ) from api_e

            # Update database (atomic with audit log)
            cur.execute(
                """UPDATE algo_trades
                   SET status = %s, updated_at = CURRENT_TIMESTAMP
                   WHERE trade_id = %s""",
                ("cancelled", trade_id),
            )

            cur.execute(
                """INSERT INTO algo_audit_log (
                       action_type, symbol, action_date, details, severity, actor, status, created_at
                   ) VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                (
                    "STALE_ORDER_AUTO_CANCELLED",
                    symbol,
                    f"Trade {trade_id}: {qty}@${price} pending {age_minutes}m >= auto-cancel threshold",
                    "WARN",
                    "position_monitor",
                    "auto_cancelled",
                ),
            )

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_e:
            raise RuntimeError(f"Failed to cancel and update {trade_id}: {db_e}") from db_e

    def _fetch_current_market(
        self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any]
    ) -> tuple[float, float | None, float | None, float | None]:
        """Fetch current price and technical indicators for a symbol.

        Raises:
            ValueError: If price data is missing - price_daily is required,
                       technical_data_daily may be None (handled by caller)
        """
        cur.execute(
            """
            SELECT pd.close, td.atr, td.sma_50, td.sma_200
            FROM price_daily pd
            INNER JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
            WHERE pd.symbol = %s AND pd.date <= %s
            ORDER BY pd.date DESC LIMIT 1
            """,
            (symbol, current_date),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Price data missing for {symbol} on {current_date} or earlier - no price_daily entry")

        close_price = float(row[0]) if row[0] is not None else None
        if close_price is None:
            raise ValueError(f"Invalid price for {symbol} on {current_date} - close price is NULL")

        atr = float(row[1]) if row[1] is not None else None
        sma_50 = float(row[2]) if row[2] is not None else None
        sma_200 = float(row[3]) if row[3] is not None else None

        # CRITICAL: Trailing stop calculations REQUIRE both ATR and SMA_50
        # ATR provides volatility-based placement; SMA_50 provides trend context
        # Both are REQUIRED for proper risk management-cannot silently degrade
        if atr is None or sma_50 is None:
            raise ValueError(
                f"[POSITION_MONITOR] Cannot compute trailing stop for {symbol} on {current_date}: "
                f"missing critical technical data (atr={atr}, sma_50={sma_50}). "
                f"Trailing stop calculations require both ATR (volatility) and SMA_50 (trend). "
                f"Check: load_technical_data_daily logs for data loading failures."
            )

        return (close_price, atr, sma_50, sma_200)

    def _compute_trailing_stop(
        self,
        entry_price: float,
        active_stop: float,
        cur_price: float,
        atr: float | None,
        sma_50: float | None,
        target_hits: int,
    ) -> float:
        """Stop ratchets up only.

        - Before T1: keep initial stop OR use 50-DMA (whichever higher) capped at entry-2*ATR
        - After T1: stop = entry (breakeven) at minimum, or trail tighter via ATR
        - After T2: stop = entry area, never target levels (targets are exits, not protection)
        """
        # Validate inputs
        if cur_price is None or cur_price <= 0:
            raise PositionValidationError(f"Invalid current price for trailing stop: {cur_price}")
        if active_stop is None or active_stop <= 0:
            raise PositionValidationError(f"Invalid active stop for trailing stop: {active_stop}")
        if entry_price is None or entry_price <= 0:
            raise PositionValidationError(f"Invalid entry price for trailing stop: {entry_price}")

        # Sanity check: if active_stop is already > cur_price (shouldn't happen), clamp it.
        # This can occur with stale/imported positions.
        if active_stop > cur_price:
            active_stop = cur_price - 0.01
            logger.warning(f"  Clamped active_stop {active_stop:.2f} to {cur_price - 0.01:.2f} (was above market)")

        candidates = [active_stop]

        if atr is not None and atr > 0:
            candidates.append(cur_price - (2.0 * atr))
        if sma_50 is not None and sma_50 > 0 and sma_50 < cur_price:
            candidates.append(sma_50)

        if target_hits >= 1:
            candidates.append(entry_price)  # at least breakeven after T1
        # NOTE: target_hits >= 2 does NOT add T1 price. Target prices are exits, not stops.

        # Don't let trailing stop get within 1.0 ATR of price (room to breathe)
        if atr is not None and atr > 0:
            cap = cur_price - atr
            candidates = [c for c in candidates if c <= cap]
            if not candidates:
                candidates = [cap]

        # For a stop loss, pick the highest valid candidate (most conservative protection).
        # This ratchets stops UP as price rises, but never above current price - ATR.
        new_stop = max(candidates) if candidates else active_stop
        # NEVER lower the trailing stop below its prior level
        return round(max(new_stop, active_stop), 2)

    def _check_relative_strength(self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any]) -> str:
        """20-day relative return vs SPY: weakening / neutral / strong."""
        try:
            stock = self._period_return(symbol, current_date, 20, cur)
        except (ValueError, RuntimeError) as e:
            raise PositionValidationError(
                f"[RS_CALCULATION_FAILED] Cannot evaluate relative strength for {symbol}: {e}. "
                f"Period return calculation failed - cannot proceed without RS data for position health assessment."
            ) from e

        try:
            spy = self._period_return("SPY", current_date, 20, cur)
        except (ValueError, RuntimeError) as e:
            raise PositionValidationError(
                f"[RS_CALCULATION_FAILED] Cannot evaluate market baseline (SPY) for RS: {e}. "
                f"Cannot assess relative strength without market comparison data."
            ) from e
        excess = stock - spy
        if excess < -0.05:
            return "weakening"
        if excess > 0.05:
            return "strong"
        return "neutral"

    def _check_sector_health(self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any]) -> str:
        """Is the symbol's sector currently weakening?"""
        # Skip sector checks for index/macro ETFs (Session 196: removed unused sector ETFs)
        # Only kept SPY, QQQ, IWM for critical market factors; GLD, TLT for macro
        if symbol in ("SPY", "QQQ", "IWM", "GLD", "TLT", "^GSPC", "^IXIC", "^DJI"):
            return "neutral"

        cur.execute(
            "SELECT sector FROM company_profile WHERE ticker = %s LIMIT 1",
            (symbol,),
        )
        srow = cur.fetchone()
        if srow is None or len(srow) < 1:
            raise ValueError(
                f"[POSITION MONITOR] Sector data missing for {symbol}. "
                f"Cannot classify position without sector information for exposure calculations."
            )
        if srow[0] is None:
            raise ValueError(
                f"[POSITION MONITOR] Sector is NULL for {symbol}. "
                f"Cannot classify position without valid sector for exposure calculations."
            )
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
        if not cur_row or cur_row[0] is None:
            raise RuntimeError(
                f"[POSITION_MONITOR] Sector ranking data missing for {sector}. "
                f"Cannot assess sector health without current ranking. Position monitoring halted."
            )
        cur_rank = int(cur_row[0])

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
        if not old_row or old_row[0] is None:
            msg = (
                f"[POSITION_MONITOR CRITICAL] Cannot assess sector trend without 4-week historical baseline. "
                f"sector={sector}, date={four_weeks_ago}. "
                f"Check sector_rotation_signal table for data gaps. "
                f"Position monitoring requires complete sector history."
            )
            logger.error(msg)
            raise ValueError(msg)
        old_rank = int(old_row[0])
        if cur_rank > old_rank + 3:  # got worse by 3+ ranks
            return "weakening"
        if cur_rank < old_rank - 3:
            return "strengthening"
        return "stable"

    def _max_unrealized_pct(
        self,
        symbol: str,
        trade_date: _date,
        current_date: _date | datetime,
        entry_price: float,
        cur: PsycopgCursor[Any],
    ) -> float:
        """Highest closing price since entry, expressed as % gain."""
        if entry_price <= 0:
            raise PositionValidationError(
                f"Invalid entry price for {symbol}: {entry_price} <= 0. Cannot calculate max unrealized %."
            )

        cur.execute(
            """
            SELECT MAX(close) FROM price_daily
            WHERE symbol = %s AND date >= %s AND date <= %s
            """,
            (symbol, trade_date, current_date),
        )
        row = cur.fetchone()
        if row is None or len(row) < 1 or row[0] is None:
            raise PositionValidationError(
                f"No price data available for {symbol} from {trade_date} to {current_date}. Cannot calculate peak unrealized gain."
            )

        max_close = float(row[0])
        if max_close <= 0:
            raise PositionValidationError(f"Invalid price data for {symbol}: max close {max_close} <= 0")
        return ((max_close - entry_price) / entry_price) * 100.0

    def _days_to_earnings(self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any]) -> int:
        """Get days until next earnings from earnings_calendar or earnings_history.

        Raises:
            ValueError: If earnings data unavailable (no calendar, estimates, or history)
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
                return int((row[0] - current_date).days)

            # Fallback: estimate from last reported quarter using quarterly cycle math
            cur.execute(
                "SELECT MAX(earnings_date) FROM earnings_history WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row is None or len(row) < 1 or row[0] is None:
                raise ValueError(f"Earnings data unavailable for {symbol}: no calendar, estimates, or history found")

            last_report = row[0]
            month = last_report.month
            year = last_report.year

            if month < 4:
                next_q = _date(year, 4, 15)
            elif month < 7:
                next_q = _date(year, 7, 15)
            elif month < 10:
                next_q = _date(year, 10, 15)
            else:
                next_q = _date(year + 1, 1, 15)

            while next_q <= current_date:
                if next_q.month == 1:
                    next_q = _date(next_q.year, 4, 15)
                elif next_q.month == 4:
                    next_q = _date(next_q.year, 7, 15)
                elif next_q.month == 7:
                    next_q = _date(next_q.year, 10, 15)
                else:
                    next_q = _date(next_q.year + 1, 1, 15)

            return int((next_q - current_date).days)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Earnings query failed for {symbol}: {e}") from e

    def _fetch_market_dist_days(self, current_date: _date | datetime, cur: PsycopgCursor[Any]) -> int:
        """Get market distribution days from health data.

        Raises:
            ValueError: If market health data is unavailable for the date
        """
        cur.execute(
            "SELECT distribution_days_4w FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            raise ValueError(
                f"Market distribution days not available for {current_date} - market_health_daily table missing or empty"
            )
        return int(row[0])

    def _period_return(self, symbol: str, end_date: _date, lookback_days: int, cur: PsycopgCursor[Any]) -> float:
        """Compute simple return over a lookback period.

        Raises:
            ValueError: If price data is missing or invalid for the period
        """
        from algo.infrastructure.config.sql_intervals import get_interval_sql

        interval_1d = get_interval_sql("1d")
        cur.execute(
            f"""
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - (%s * {interval_1d})
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(
                f"Period return data missing for {symbol} on {end_date} ({lookback_days}d lookback) - insufficient price history"
            )
        recent, oldest = float(row[0]), float(row[1])
        if oldest <= 0:
            raise ValueError(f"Invalid historical price for {symbol}: oldest close {oldest} <= 0")
        return (recent - oldest) / oldest

    def _persist_review(self, rec: dict[str, Any], cur: PsycopgCursor[Any], position_index: int) -> None:
        """Update algo_positions with current price/PnL and log a monitoring audit row (atomic).

        Uses savepoint to ensure both position update and audit log succeed together.
        If audit log fails, both are rolled back.
        """
        sp_name = f"sp_persist_review_{position_index}"
        cur.execute(f"SAVEPOINT {sp_name}")
        try:
            if "current_price" not in rec or rec["current_price"] is None:
                raise ValueError(
                    f"Cannot persist review for position {rec['position_id']}: current_price missing or None"
                )
            if "quantity" not in rec or rec["quantity"] is None:
                raise ValueError(f"Cannot persist review for position {rec['position_id']}: quantity missing or None")

            try:
                current_price = float(rec["current_price"])
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid current_price {rec['current_price']} for position {rec['position_id']}: {e}"
                ) from e

            try:
                quantity = float(rec["quantity"])
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid quantity {rec['quantity']} for position {rec['position_id']}: {e}") from e

            cur.execute(
                """
                UPDATE algo_positions
                SET current_price = %s,
                    position_value = %s * %s,
                    unrealized_pnl = (%s - avg_entry_price) * %s,
                    unrealized_pnl_pct = CASE WHEN avg_entry_price > 0 THEN ((%s - avg_entry_price) / avg_entry_price) * 100 ELSE NULL END,
                    days_since_entry = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE position_id = %s
                """,
                (
                    current_price,
                    quantity,
                    current_price,
                    current_price,
                    quantity,
                    current_price,
                    int(rec["days_held"]),
                    rec["position_id"],
                ),
            )
            # Log the review to audit (atomic with position update)
            cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, symbol, action_date,
                                            details, actor, status, created_at)
                VALUES ('position_review', %s, CURRENT_TIMESTAMP, %s, 'position_monitor',
                        %s, CURRENT_TIMESTAMP)
                """,
                (
                    rec["symbol"],
                    json.dumps(
                        {
                            "trade_id": rec["trade_id"],
                            "r_multiple": rec["r_multiple"],
                            "unrealized_pct": rec["unrealized_pct"],
                            "flags": rec["flags"],
                            "rs_label": rec["rs_label"],
                            "sector_state": rec["sector_state"],
                            "action": rec["action"],
                            "action_reason": rec["action_reason"],
                            "days_to_earnings": rec["days_to_earnings"],
                            "proposed_stop": float(rec["proposed_stop"]),
                        }
                    ),
                    rec["action"],
                ),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            cur.execute(f"ROLLBACK TO {sp_name}")
            logger.error(f"Failed to persist review for {rec['symbol']}: {e} (rolled back)")
            raise

    def _print_recommendation(self, rec: dict[str, Any]) -> None:
        flags_str = ", ".join(rec["flags"]) if rec["flags"] else "none"
        logger.info(
            f"  {rec['symbol']:6s}  qty={rec['quantity']:<5d} "
            f"price=${rec['current_price']:7.2f}  "
            f"R={rec['r_multiple']:+.2f}  "
            f"P&L={rec['unrealized_pct']:+.2f}%  "
            f"days={rec['days_held']:<3d} "
            f"hits={rec['target_hits']}  "
            f"flags={flags_str}"
        )

    def check_corporate_actions(self) -> list[dict[str, Any]]:
        """Phase 6.1: Detect stock splits and corporate actions.

        Compares Alpaca qty to DB qty. If different and greater than 20%,
        likely a stock split. Adjusts position qty and recalculates stop loss.

        Returns:
            list of adjustments made
        """
        adjustments: list[dict[str, Any]] = []
        ctx = DatabaseContext("write")
        with ctx as cur:
            cur.execute("""
                SELECT ap.position_id, ap.symbol, ap.quantity, ap.current_stop_price,
                       ap.avg_entry_price AS entry_price
                FROM algo_positions ap
                WHERE ap.status = 'open'
            """)
            positions = cur.fetchall()

            alpaca_base_url, alpaca_key, alpaca_secret = self._get_alpaca_creds()

            for pos_id, symbol, db_qty, db_stop, _entry_price in positions:
                try:
                    alpaca_qty = self._fetch_alpaca_qty(alpaca_base_url, alpaca_key, alpaca_secret, symbol)
                    self._handle_qty_variance(cur, pos_id, symbol, db_qty, db_stop, alpaca_qty, adjustments)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    error_msg = (
                        f"Corporate action detection failed for {symbol}: Database error during qty variance handling. "
                        f"Cannot proceed without complete position verification. {e}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

            return adjustments

    def _get_alpaca_creds(self) -> tuple[str, str, str]:
        """Retrieve Alpaca credentials, raise if unavailable."""
        alpaca_base_url = get_alpaca_base_url()
        try:
            cm = get_credential_manager()
            creds = cm.get_alpaca_credentials()
            alpaca_key = creds.get("key")
            alpaca_secret = creds.get("secret")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Could not retrieve Alpaca credentials: {e}")
            alpaca_key = None
            alpaca_secret = None

        if not alpaca_key or not alpaca_secret:
            raise RuntimeError("Alpaca credentials unavailable - cannot detect corporate actions. Halted.")
        return alpaca_base_url, alpaca_key, alpaca_secret

    def _fetch_alpaca_qty(self, alpaca_base_url: str, alpaca_key: str, alpaca_secret: str, symbol: str) -> int:
        """Fetch position quantity from Alpaca API.

        Raises:
            RuntimeError: If qty field is missing from Alpaca response (fail-fast for data integrity)
        """
        url = f"{alpaca_base_url}/v2/positions/{symbol}"
        headers = {
            "APCA-API-KEY-ID": alpaca_key,
            "APCA-API-SECRET-KEY": alpaca_secret,
        }
        try:
            timeout = int(self.config["api_request_timeout_seconds"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}") from e

        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Alpaca API returned {resp.status_code} for {symbol}")

        try:
            alpaca_pos = resp.json()
        except (ValueError, Exception) as e:
            raise RuntimeError(f"Invalid JSON response from Alpaca: {e}") from e

        if "qty" not in alpaca_pos or alpaca_pos["qty"] is None:
            raise RuntimeError(
                f"Alpaca response for {symbol} missing qty field (malformed response). "
                f"Response: {alpaca_pos}. Cannot verify position quantity - halting corporate action check."
            )
        return int(alpaca_pos["qty"])

    def _handle_qty_variance(
        self,
        cur: PsycopgCursor[Any],
        pos_id: int,
        symbol: str,
        db_qty: int,
        db_stop: float,
        alpaca_qty: int,
        adjustments: list[dict[str, Any]],
    ) -> None:
        """Handle quantity changes between DB and Alpaca."""
        if alpaca_qty == 0:
            cur.execute(
                "UPDATE algo_positions SET status = 'closed' WHERE position_id = %s",
                (pos_id,),
            )
            adjustments.append(
                {
                    "symbol": symbol,
                    "action": "POSITION_CLOSED_AT_ALPACA",
                    "db_qty": db_qty,
                    "alpaca_qty": alpaca_qty,
                }
            )
            return

        if alpaca_qty == db_qty:
            return

        if db_qty <= 0:
            raise RuntimeError(
                f"[POSITION_MONITOR] Cannot calculate quantity variance for {symbol} (db_qty={db_qty}). "
                f"Position has invalid or missing quantity in database. "
                f"Data integrity check failed - reconciliation cannot proceed without valid position data."
            )
        qty_change_pct = abs(alpaca_qty - db_qty) / db_qty * 100
        if qty_change_pct <= 20:
            return

        self._apply_split_adjustment(cur, pos_id, symbol, db_qty, db_stop, alpaca_qty, adjustments)

    def _apply_split_adjustment(
        self,
        cur: PsycopgCursor[Any],
        pos_id: int,
        symbol: str,
        db_qty: int,
        db_stop: float,
        alpaca_qty: int,
        adjustments: list[dict[str, Any]],
    ) -> None:
        """Apply stock split adjustment to both quantity and stop loss.

        Raises:
            RuntimeError: If stop_loss is missing when stock split detected. Missing
            stop loss means position has no protection - cannot silently proceed.
        """
        if db_qty <= 0:
            raise PositionValidationError(
                f"CRITICAL: Database position quantity invalid ({db_qty}) - cannot calculate split ratio. "
                f"Position data corruption detected for {symbol}."
            )
        split_ratio = alpaca_qty / db_qty

        if not db_stop:
            raise RuntimeError(
                f"STOCK SPLIT DETECTED for {symbol} but current_stop_price is NULL in database. "
                f"Cannot adjust stop loss - position protection broken. "
                f"Manual intervention required to restore stop loss protection before trading continues."
            )

        new_stop = db_stop / split_ratio
        cur.execute(
            "UPDATE algo_positions SET quantity = %s, current_stop_price = %s WHERE position_id = %s",
            (alpaca_qty, new_stop, pos_id),
        )

        cur.execute(
            "INSERT INTO algo_audit_log (action_type, action_date, details, severity) VALUES (%s, %s, %s, %s)",
            (
                "CORPORATE_ACTION_SPLIT",
                datetime.now(timezone.utc),
                f"Split: {symbol} {db_qty} -> {alpaca_qty} ratio {split_ratio:.2f}. Stop adjusted {db_stop:.2f} to {new_stop:.2f}",
                "WARN",
            ),
        )

        adjustments.append(
            {
                "symbol": symbol,
                "action": "STOCK_SPLIT",
                "old_qty": db_qty,
                "new_qty": alpaca_qty,
                "split_ratio": round(split_ratio, 2),
                "old_stop": db_stop,
                "new_stop": new_stop,
            }
        )

    def get_open_positions(self) -> list[dict[str, str]]:
        """Get list of open positions for halt checking and monitoring.

        Returns a list of dicts with at least 'symbol' and optionally 'name'.
        Used by orchestrator for single-stock halt detection.

        Raises:
            RuntimeError: If position data cannot be retrieved from database (fail-fast for visibility)
        """
        with DatabaseContext("read") as cur:
            try:
                cur.execute("""
                    SELECT DISTINCT symbol FROM algo_positions
                    WHERE status = 'open' AND quantity > 0
                    ORDER BY symbol
                """)
                positions = cur.fetchall()
                return [{"symbol": row[0], "name": row[0]} for row in positions] if positions else []
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Failed to fetch open positions from database: {e}. "
                    f"Cannot proceed with halt checking and position monitoring without access to position data."
                ) from e


if __name__ == "__main__":
    from algo.infrastructure import get_config

    monitor = PositionMonitor(get_config())
    monitor.review_positions()
