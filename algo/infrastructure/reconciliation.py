#!/usr/bin/env python3

import json
import logging
import statistics
from datetime import date as _date_type
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
import requests

from algo.reporting import notify
from config.alpaca_config import get_alpaca_base_url
from config.credential_manager import get_credential_manager
from utils.db import DatabaseContext
from utils.trading import PositionStatus, TradeStatus


logger = logging.getLogger(__name__)

PORTFOLIO_SNAPSHOT_LOCK_ID = 2147483647


class DailyReconciliation:
    """Daily reconciliation and portfolio snapshot creation."""

    def __init__(self, config):
        self.config = config
        self.trading_client = None  # Kept for backward compat; HTTP calls used directly
        try:
            credential_manager = get_credential_manager()
            creds = credential_manager.get_alpaca_credentials()
            self._alpaca_key = creds.get("key")
            self._alpaca_secret = creds.get("secret")
            self._alpaca_base_url = get_alpaca_base_url()

            # Validate credentials are present; fail explicitly rather than silently
            if not self._alpaca_key:
                raise ValueError("Alpaca API key missing from credential manager")
            if not self._alpaca_secret:
                raise ValueError("Alpaca API secret missing from credential manager")
            if not self._alpaca_base_url:
                raise ValueError("Alpaca base URL not configured")

            self.trading_client = True  # Signals credentials are available
        except (KeyError, ValueError, AttributeError) as e:
            logger.critical(f"Alpaca credential initialization FAILED: {e}")
            try:
                notify(
                    "critical",
                    title="Reconciliation Initialization Failed",
                    message=f"Alpaca credentials unavailable: {e}. Reconciliation cannot proceed.",
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError):
                logger.warning("Failed to send credential failure notification")
            raise ValueError(f"Alpaca credential initialization failed: {e}") from e

    def run_daily_reconciliation(self, reconcile_date=None, dry_run=False):
        """Run full daily reconciliation. If dry_run=True, skip Alpaca API calls and return mock data.

        CRITICAL SAFETY: dry_run mode must be explicitly enabled via ORCHESTRATOR_DRY_RUN environment variable
        to prevent accidental trading with mock portfolio values if the flag is misconfigured.
        """
        if dry_run:
            import os

            dry_run_enabled = os.getenv("ORCHESTRATOR_DRY_RUN", "false").strip().lower() in ("true", "1", "yes")
            if not dry_run_enabled:
                logger.critical(
                    "[RECONCILIATION SAFETY GATE FAILED] dry_run=True passed but ORCHESTRATOR_DRY_RUN environment variable not explicitly set. "
                    "Refusing to return mock portfolio data to prevent accidental trading with fake values. "
                    "This is a critical safety check. If you intentionally want dry run mode, set ORCHESTRATOR_DRY_RUN=true"
                )
                raise ValueError(
                    "CRITICAL: dry_run=True but ORCHESTRATOR_DRY_RUN not enabled. "
                    "Mock data rejected to prevent accidental trading. Set ORCHESTRATOR_DRY_RUN=true to enable dry-run mode."
                )

            logger.warning(
                "[RECONCILIATION] DRY RUN ACTIVE: Returning mock portfolio snapshot. "
                "This is for testing only — all returned data is synthetic. "
                "ENSURE ORCHESTRATOR_DRY_RUN is set to false in production."
            )
            return {
                "success": True,
                "portfolio_value": 100000.0,
                "cash": 50000.0,
                "positions": 0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "trades_closed_today": [],
                "snapshot_date": reconcile_date or datetime.now(timezone.utc).date(),
                "_is_mock_data": True,
            }

        if not reconcile_date:
            reconcile_date = datetime.now(timezone.utc).date()
        elif isinstance(reconcile_date, str):
            reconcile_date = datetime.strptime(reconcile_date, "%Y-%m-%d").date()
        elif hasattr(reconcile_date, "date") and not isinstance(reconcile_date, _date_type):
            reconcile_date = reconcile_date.date()

        try:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"DAILY RECONCILIATION - {reconcile_date}")
            logger.info(f"{'=' * 70}\n")

            # 1. Fetch Alpaca account (required - no fallback to stale DB data)
            alpaca_data = self._fetch_alpaca_account()
            if not alpaca_data:
                logger.critical("Alpaca account fetch failed — reconciliation cannot proceed without live account data")
                try:
                    notify(
                        "critical",
                        title="Reconciliation Halted",
                        message="Alpaca unavailable. Reconciliation requires live account data — cannot use stale DB cache.",
                    )
                except Exception as e:
                    logger.warning(f"Failed to send notification: {e}")
                raise ValueError(
                    "Alpaca account data required for reconciliation — cannot proceed with DB-only fallback"
                )
            else:
                logger.info("1. Alpaca Account:")
                pv = alpaca_data.get("portfolio_value")
                cash = alpaca_data.get("cash")
                equity = alpaca_data.get("equity")

                # Validate critical fields are present — fail immediately, not silently
                if pv is None:
                    logger.critical(
                        "Alpaca portfolio_value is missing — reconciliation cannot proceed without live portfolio value"
                    )
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Alpaca portfolio_value missing — reconciliation requires live portfolio value for drawdown limits. Cannot use stale DB cache.",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send notification: {e}")
                    raise ValueError("Alpaca portfolio_value required for reconciliation — cannot proceed")

                if cash is None:
                    logger.critical("Alpaca cash is missing — reconciliation cannot proceed without live cash value")
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Alpaca cash missing — reconciliation requires live cash value for position sizing. Cannot use stale DB cache.",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send notification: {e}")
                    raise ValueError("Alpaca cash required for reconciliation — cannot proceed")

                logger.info(f"   Portfolio Value: ${pv:,.2f}")
                logger.info(f"   Cash: ${cash:,.2f}")
                logger.info(f"   Equity: ${equity:,.2f}" if equity is not None else "   Equity: UNAVAILABLE")

            with DatabaseContext("write") as cur:
                # 1b. Sync Alpaca positions into our DB (imports any external positions)
                sync_result = self.sync_alpaca_positions(cur)
                logger.info("\n1b. Position Sync:")
                logger.info(f"   {sync_result['message']}")
                if sync_result.get("orphan_symbols"):
                    logger.info(f"   Orphans flagged: {', '.join(sync_result['orphan_symbols'][:5])}")

                # 1b2. Reconcile actual Alpaca fill prices with DB exit records
                fill_result = self.reconcile_exit_fills(cur, reconcile_date)
                logger.info("\n1b2. Exit Fill Reconciliation:")
                logger.info(f"   {fill_result['message']}")

                # 1b3. Check for trades pending Phase 7 price reconciliation
                pending_result = self.check_pending_reconciliations(cur)
                if pending_result.get("pending_count", 0) > 0:
                    logger.info("\n1b3. Pending Reconciliations:")
                    logger.info(f"   {pending_result['message']}")
                    if pending_result.get("stuck_count", 0) > 0:
                        for p in pending_result.get("pending", [])[:5]:
                            logger.warning(
                                f"   STUCK: {p['symbol']} {p['trade_id']} "
                                f"(Est: ${p['estimated_price']:.2f} vs ${p['current_exit_price']:.2f}, "
                                f"{p['days_pending']}d pending)"
                            )

                # 1c. Compute MAE/MFE metrics for recently closed trades (E3 analytics)
                mae_result = self.compute_closed_trade_metrics(cur)
                logger.info("\n1c. MAE/MFE Metrics:")
                logger.info(f"   {mae_result['reason']}")

                # 1d. Compute analytics metrics: IC and expectancy (E4-E5)
                analytics = self.compute_analytics_metrics(cur)
                logger.info("\n1d. Analytics Metrics:")
                if analytics["ic"].get("valid"):
                    logger.info(
                        f"   IC (Information Coefficient): {analytics['ic']['ic']:.4f} ({analytics['ic']['trade_count']} trades)"
                    )
                    if analytics["ic"]["alert"]:
                        logger.info(f"   ⚠ {analytics['ic']['alert']}")
                if analytics["expectancy"].get("valid"):
                    logger.info(
                        f"   Expectancy: {analytics['expectancy']['expectancy']:+.4f}% (win rate {analytics['expectancy']['win_rate']:.1f}%)"
                    )
                    logger.info(
                        f"   Kelly Fraction (25% conservative): {analytics['expectancy']['kelly_fraction']:.4f}"
                    )
                    if analytics["expectancy"]["alert"]:
                        logger.info(f"   [FAIL] {analytics['expectancy']['alert']}")

                # FIXED: Read from algo_trades (source of truth) instead of algo_positions (stale).
                # algo_positions drifts over time; algo_trades is authoritative for open positions.
                # CRITICAL: Do NOT fall back to entry_price when current_price is missing.
                # When price_daily has no entry, current_price must be NULL to indicate missing data.
                # This prevents position_value from being calculated incorrectly (showing 0% gain/loss).
                cur.execute("""
                    WITH latest_prices AS (
                        SELECT DISTINCT ON (symbol) symbol, close as current_price
                        FROM price_daily
                        ORDER BY symbol, date DESC
                    ),
                    open_trades AS (
                        SELECT DISTINCT ON (at.symbol)
                            at.symbol, at.entry_quantity as quantity, at.entry_price as avg_entry_price,
                            lp.current_price,
                            (at.entry_quantity * lp.current_price) as position_value
                        FROM algo_trades at
                        LEFT JOIN latest_prices lp ON at.symbol = lp.symbol
                        WHERE at.status IN ('open', 'filled', 'active', 'partially_filled')
                          AND at.exit_date IS NULL
                        ORDER BY at.symbol, at.trade_date DESC
                    )
                    SELECT symbol, quantity, avg_entry_price, current_price, position_value
                    FROM open_trades
                    ORDER BY symbol
                """)

                positions = cur.fetchall()
                logger.info(f"\n2. Database Positions: {len(positions)} open")

                total_position_value = 0.0
                unrealized_pnl = 0.0
                unrealized_pnl_pct = 0.0
                positions_with_prices = 0
                # Track unrealized PnL breakdown: winning, losing, breakeven positions
                unrealized_pnl_winning_count = 0
                unrealized_pnl_losing_count = 0
                unrealized_pnl_breakeven_count = 0

                for symbol, qty, entry, current, pos_value in positions:
                    # Validate critical fields before processing — fail fast on missing data
                    if entry is None:
                        raise ValueError(f"[RECONCILIATION CRITICAL] {symbol}: ENTRY PRICE MISSING — cannot compute P&L for open position")
                    if current is None:
                        entry_dec = Decimal(str(entry))
                        qty_dec = Decimal(str(qty)) if qty is not None else Decimal(0)
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] {symbol}: {qty_dec:.0f} @ ${entry_dec:.2f} -> CURRENT PRICE MISSING — cannot compute P&L for open position"
                        )

                    if qty is None or pos_value is None:
                        raise ValueError(f"[RECONCILIATION CRITICAL] {symbol}: QUANTITY OR VALUE MISSING — cannot compute P&L for open position")

                    # Keep all calculations in Decimal for precision; convert only for storage
                    from decimal import Decimal
                    entry_dec = Decimal(str(entry))
                    current_dec = Decimal(str(current))
                    qty_dec = Decimal(str(qty))
                    pos_value_dec = Decimal(str(pos_value))
                    pnl_dec = (current_dec - entry_dec) * qty_dec
                    pnl_pct_dec = ((current_dec - entry_dec) / entry_dec * Decimal(100)) if entry_dec > 0 else Decimal(0)
                    total_position_value += pos_value_dec
                    unrealized_pnl += pnl_dec
                    positions_with_prices += 1

                    # Track winning/losing/breakeven status for unrealized P&L breakdown
                    if pnl_dec > 0:
                        unrealized_pnl_winning_count += 1
                    elif pnl_dec < 0:
                        unrealized_pnl_losing_count += 1
                    else:
                        unrealized_pnl_breakeven_count += 1

                    logger.info(
                        f"   {symbol}: {float(qty_dec):.0f} @ ${float(entry_dec):.2f} -> ${float(current_dec):.2f} | {float(pnl_dec):+,.2f} ({float(pnl_pct_dec):+.2f}%)"
                    )

                # 3. Calculate metrics
                # Values already validated at initial Alpaca fetch; keep as Decimal for precision
                # Use Alpaca's authoritative portfolio_value for the snapshot (includes live prices).
                # Our DB position_value sum may lag — Alpaca is the ground truth for drawdown math.
                from decimal import Decimal
                cash_dec = Decimal(str(cash))
                alpaca_portfolio_value_dec = Decimal(str(pv))
                if alpaca_portfolio_value_dec <= 0:
                    logger.critical(
                        "Alpaca portfolio_value is zero/negative — cannot proceed with drawdown calculations. Halting."
                    )
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Alpaca portfolio_value zero/negative — reconciliation requires positive portfolio value. Cannot use stale DB cache.",
                        )
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        logger.warning(f"Failed to send notification: {e}")
                    raise ValueError("Alpaca portfolio_value must be positive for reconciliation — cannot proceed")

                # DB-computed total (kept for drift reporting)
                from decimal import Decimal
                total_equity_db_dec = cash_dec + total_position_value
                # Always use Alpaca's live value (never fall back to stale DB cache)
                total_equity_dec = alpaca_portfolio_value_dec

                if total_equity_db_dec > 0:
                    drift_pct = ((alpaca_portfolio_value_dec - total_equity_db_dec) / total_equity_db_dec) * Decimal(100)
                    if abs(drift_pct) > Decimal("1.0"):
                        logger.warning(
                            f"Position value drift: Alpaca ${float(alpaca_portfolio_value_dec):,.2f} vs DB-computed ${float(total_equity_db_dec):,.2f} ({float(drift_pct):+.1f}%)"
                        )

                if total_equity_dec > 0:
                    unrealized_pnl_pct_dec = (unrealized_pnl / total_equity_dec) * Decimal(100)
                else:
                    unrealized_pnl_pct_dec = Decimal(0)

                position_values = [p[4] for p in positions if p[4] is not None]
                largest_position_dec = Decimal(str(max(position_values))) if position_values else Decimal(0)
                max_concentration_dec = (largest_position_dec / total_equity_dec * Decimal(100)) if total_equity_dec > 0 else Decimal(0)

                avg_position_size_dec = (total_position_value / len(positions)) if positions else Decimal(0)

                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)

                from decimal import Decimal
                prev_snapshot = cur.fetchone()
                prev_value_dec = Decimal(str(prev_snapshot[0])) if prev_snapshot else total_equity_dec
                daily_return_dec = total_equity_dec - prev_value_dec
                daily_return_pct_dec = (daily_return_dec / prev_value_dec * Decimal(100)) if prev_value_dec > 0 else Decimal(0)

                cur.execute(
                    """
                    SELECT market_trend, distribution_days_4w
                    FROM market_health_daily
                    WHERE date <= %s
                    ORDER BY date DESC LIMIT 1
                """,
                    (reconcile_date,),
                )

                market = cur.fetchone()
                market_trend = market[0] if market else "unknown"

                # Calculate additional metrics
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                        COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                        COALESCE(SUM(profit_loss_dollars) FILTER (WHERE DATE(exit_date) = %s::date), 0) as realized_pnl_today,
                        COALESCE(SUM(profit_loss_dollars), 0) as cumulative_pnl
                    FROM algo_trades
                    WHERE status = %s
                """,
                    (str(reconcile_date), "closed"),
                )
                result = cur.fetchone()
                if result is None:
                    raise ValueError("No trades data returned from database")
                win_count = int(result[0]) if result[0] is not None else 0
                loss_count = int(result[1]) if result[1] is not None else 0
                realized_pnl_today = float(result[2]) if result[2] is not None else 0.0
                cumulative_pnl = float(result[3]) if result[3] is not None else 0.0

                # Get cumulative return (normalize to actual initial capital from Alpaca account history)
                try:
                    initial_capital = self._fetch_initial_capital(cur)
                    cumulative_return_pct = (cumulative_pnl / initial_capital * 100) if initial_capital > 0 else 0.0
                    logger.info(
                        f"   Cumulative Return: {cumulative_return_pct:+.2f}% (on initial capital ${initial_capital:,.2f})"
                    )
                except ValueError as e:
                    logger.error(f"CRITICAL: {e} — cannot calculate cumulative return")
                    raise

                # Calculate max drawdown from historical snapshots
                from decimal import Decimal
                max_drawdown_pct_dec = Decimal(0)
                cur.execute("""
                    SELECT
                        MAX(total_portfolio_value) as peak,
                        MIN(total_portfolio_value) as trough
                    FROM algo_portfolio_snapshots
                """)
                peak_row = cur.fetchone()
                if peak_row is not None and peak_row[0] is not None and peak_row[1] is not None:
                    peak_val_dec = Decimal(str(peak_row[0]))
                    trough_val_dec = Decimal(str(peak_row[1]))
                    if peak_val_dec > 0:
                        max_drawdown_pct_dec = ((peak_val_dec - trough_val_dec) / peak_val_dec) * Decimal(100)

                # Calculate Sharpe ratio: mean_return / std_dev * sqrt(252)
                sharpe_ratio = None
                cur.execute("""
                    SELECT daily_return_pct FROM algo_portfolio_snapshots
                    WHERE daily_return_pct IS NOT NULL
                    ORDER BY snapshot_date DESC LIMIT 252
                """)
                returns = [float(r[0]) / 100.0 for r in cur.fetchall() if r[0] is not None]
                if len(returns) > 1:
                    import statistics

                    try:
                        std_dev = statistics.stdev(returns)
                        mean_return = statistics.mean(returns)
                        if std_dev > 0:
                            sharpe_ratio = mean_return / std_dev * (252**0.5)
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        logger.warning(f"Sharpe calculation failed: {e}")

                cur.execute("SELECT pg_advisory_lock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))
                cur.fetchone()
                try:
                    cur.execute(
                        """
                        INSERT INTO algo_portfolio_snapshots (
                            snapshot_date, total_portfolio_value, total_cash, total_equity,
                            position_count, largest_position_pct, average_position_size_pct,
                            concentration_risk_pct,
                            realized_pnl_today, unrealized_pnl_total, unrealized_pnl_pct,
                            unrealized_pnl_winning_count, unrealized_pnl_losing_count, unrealized_pnl_breakeven_count,
                            unrealized_pnl_source,
                            win_count_today, loss_count_today,
                            daily_return_pct, cumulative_return_pct, max_drawdown_pct,
                            sharpe_ratio, market_health_status, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (snapshot_date) DO UPDATE SET
                        total_portfolio_value = EXCLUDED.total_portfolio_value,
                        total_cash = EXCLUDED.total_cash,
                        total_equity = EXCLUDED.total_equity,
                        position_count = EXCLUDED.position_count,
                        largest_position_pct = EXCLUDED.largest_position_pct,
                        average_position_size_pct = EXCLUDED.average_position_size_pct,
                        concentration_risk_pct = EXCLUDED.concentration_risk_pct,
                        realized_pnl_today = EXCLUDED.realized_pnl_today,
                        unrealized_pnl_total = EXCLUDED.unrealized_pnl_total,
                        unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                        unrealized_pnl_winning_count = EXCLUDED.unrealized_pnl_winning_count,
                        unrealized_pnl_losing_count = EXCLUDED.unrealized_pnl_losing_count,
                        unrealized_pnl_breakeven_count = EXCLUDED.unrealized_pnl_breakeven_count,
                        unrealized_pnl_source = EXCLUDED.unrealized_pnl_source,
                        win_count_today = EXCLUDED.win_count_today,
                        loss_count_today = EXCLUDED.loss_count_today,
                        daily_return_pct = EXCLUDED.daily_return_pct,
                        cumulative_return_pct = EXCLUDED.cumulative_return_pct,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        market_health_status = EXCLUDED.market_health_status
                """,
                        (
                            reconcile_date,
                            float(total_equity_dec),
                            float(cash_dec),
                            float(total_equity_dec),
                            positions_with_prices,
                            float(max_concentration_dec),
                            float((avg_position_size_dec / total_equity_dec * Decimal(100)) if total_equity_dec > 0 else Decimal(0)),
                            float(max_concentration_dec),
                            realized_pnl_today,
                            float(unrealized_pnl),
                            float(unrealized_pnl_pct_dec),
                            unrealized_pnl_winning_count,
                            unrealized_pnl_losing_count,
                            unrealized_pnl_breakeven_count,
                            "open_positions_only",
                            win_count,
                            loss_count,
                            float(daily_return_pct_dec),
                            cumulative_return_pct,
                            float(max_drawdown_pct_dec),
                            sharpe_ratio,
                            market_trend,
                        ),
                    )
                finally:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))

            logger.info("\n3. Portfolio Summary:")
            logger.info(f"   Total Value: ${float(total_equity_dec):,.2f}")
            logger.info(f"   Position Value: ${float(total_position_value):,.2f}")
            logger.info(f"   Cash: ${float(cash_dec):,.2f}")
            logger.info(f"   Unrealized P&L (OPEN POSITIONS ONLY): {float(unrealized_pnl):+,.2f} ({float(unrealized_pnl_pct_dec):+.2f}%)")
            logger.info(f"     - Winning positions: {unrealized_pnl_winning_count}")
            logger.info(f"     - Losing positions: {unrealized_pnl_losing_count}")
            logger.info(f"     - Breakeven positions: {unrealized_pnl_breakeven_count}")
            logger.info(f"   Daily Return: {float(daily_return_pct_dec):+.2f}%")
            logger.info(f"   Concentration: {float(max_concentration_dec):.1f}%")

            logger.info(f"\n{'=' * 70}")
            logger.info("Reconciliation complete - snapshot created")
            logger.info(f"{'=' * 70}\n")

            return {
                "success": True,
                "portfolio_value": float(total_equity_dec),
                "positions": len(positions),
                "unrealized_pnl": float(unrealized_pnl),
            }

        except (ValueError, requests.RequestException, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Error in reconciliation: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def reconcile_exit_fills(self, cur, reconcile_date) -> dict:
        """Update DB trade exit prices with actual Alpaca fill prices.

        Phase 4 marks trades 'closed' immediately using the last known market price
        when placing market exit orders before market open. This reconciles those
        estimated prices with actual Alpaca fill prices after market opens.
        """
        if not self._alpaca_key or not self._alpaca_secret:
            return {"updated": 0, "message": "No Alpaca credentials"}
        try:
            import requests

            since = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            resp = requests.get(
                f"{self._alpaca_base_url}/v2/orders",
                params={
                    "status": "closed",
                    "side": "sell",
                    "after": since,
                    "direction": "desc",
                    "limit": 500,
                },
                headers={
                    "APCA-API-KEY-ID": self._alpaca_key,
                    "APCA-API-SECRET-KEY": self._alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code != 200:
                return {
                    "updated": 0,
                    "message": f"Alpaca orders API {resp.status_code}",
                }

            orders = resp.json()
            if not isinstance(orders, list):
                return {"updated": 0, "message": "Unexpected Alpaca response format"}

            updated = 0
            two_days_ago = reconcile_date - timedelta(days=2)

            for order in orders:
                if order.get("status") != "filled" or order.get("side") != "sell":
                    continue
                symbol = order.get("symbol")
                filled_price_str = order.get("filled_avg_price")
                if not symbol or not filled_price_str:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Filled sell order missing symbol or filled_price: {order}")
                try:
                    filled_price = float(filled_price_str)
                except (TypeError, ValueError) as e:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Filled price not numeric '{filled_price_str}' for {symbol}") from e
                if filled_price <= 0:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Filled price invalid {filled_price} for {symbol} — must be > 0")

                cur.execute("SAVEPOINT reconcile_fill")
                try:
                    cur.execute(
                        """
                        SELECT trade_id, entry_price, stop_loss_price, entry_quantity
                        FROM algo_trades
                        WHERE symbol = %s
                          AND status = 'closed'
                          AND exit_date >= %s
                          AND exit_date <= %s
                        ORDER BY exit_date DESC LIMIT 1
                    """,
                        (symbol, two_days_ago, reconcile_date),
                    )

                    row = cur.fetchone()
                    if row is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(f"[RECONCILIATION CRITICAL] No closed trade found for {symbol} within 2 days — cannot reconcile fill")

                    trade_id, entry_price, stop_loss_price, entry_qty = row
                    if entry_price is None or stop_loss_price is None or entry_qty is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) missing entry_price, stop_loss_price, or entry_qty — cannot reconcile")

                    try:
                        entry_price = float(entry_price)
                        stop_loss_price = float(stop_loss_price)
                        entry_qty = int(entry_qty)
                    except (ValueError, TypeError) as e:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has non-numeric price/qty — cannot reconcile") from e

                    if entry_price <= 0 or stop_loss_price <= 0 or entry_qty <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid prices/qty (entry={entry_price}, stop={stop_loss_price}, qty={entry_qty}) — must be > 0")

                    pnl_pct = (filled_price - entry_price) / entry_price * 100.0
                    pnl_dollars = (filled_price - entry_price) * entry_qty
                    risk = entry_price - stop_loss_price
                    exit_r_multiple = ((filled_price - entry_price) / risk) if risk > 0 else 0.0

                    # Check if this trade had an estimated exit price (Phase 4 pre-market exit)
                    cur.execute(
                        "SELECT estimated_exit_price FROM algo_trades WHERE trade_id = %s",
                        (trade_id,),
                    )
                    est_row = cur.fetchone()
                    estimated_price = float(est_row[0]) if est_row is not None and est_row[0] is not None else None

                    # Calculate reconciliation note with variance if estimated price exists
                    reconciliation_note = None
                    if estimated_price and estimated_price > 0:
                        variance_pct = (filled_price - estimated_price) / estimated_price * 100.0
                        reconciliation_note = (
                            f"Actual: ${filled_price:.2f} vs Estimated: ${estimated_price:.2f} ({variance_pct:+.2f}%)"
                        )

                    cur.execute(
                        """
                        UPDATE algo_trades
                        SET exit_price = %s, profit_loss_pct = %s,
                            profit_loss_dollars = %s, exit_r_multiple = %s,
                            exit_price_reconciled_at = CURRENT_TIMESTAMP,
                            reconciliation_note = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE trade_id = %s
                    """,
                        (
                            filled_price,
                            pnl_pct,
                            pnl_dollars,
                            exit_r_multiple,
                            reconciliation_note,
                            trade_id,
                        ),
                    )

                    cur.execute("RELEASE SAVEPOINT reconcile_fill")
                    updated += 1
                    logger.info(f"   Exit fill reconciled: {symbol} {trade_id} @ ${filled_price:.2f} ({pnl_pct:.1f}%)")
                except (psycopg2.DatabaseError, ValueError, TypeError) as e:
                    cur.execute("ROLLBACK TO SAVEPOINT reconcile_fill")
                    logger.warning(f"   Exit fill reconcile failed for {symbol}: {e}")

            return {
                "updated": updated,
                "message": f"Reconciled {updated} exit fills with actual Alpaca prices",
            }
        except (requests.RequestException, json.JSONDecodeError, psycopg2.DatabaseError) as e:
            logger.warning(f"Exit fill reconciliation error: {e}")
            return {"updated": 0, "message": f"Error: {e}"}

    def audit_stale_estimated_prices(self, cur) -> dict:
        """Audit for trades with estimated exit prices that haven't been reconciled.

        CRITICAL: If Phase 7 reconciliation doesn't run or fails, estimated prices
        remain permanent with no way to distinguish them from actual prices.
        This audit detects stale estimated prices > 1 day old that are stuck.

        Returns: dict with stale_count, stale_trades list, alert message if any found
        """
        try:
            # Find trades with estimated prices that should have been reconciled by now
            # Trades closed yesterday or earlier with NO reconciliation timestamp
            cur.execute("""
                SELECT trade_id, symbol, exit_date, estimated_exit_price, exit_price,
                       exit_price_reconciled_at
                FROM algo_trades
                WHERE estimated_exit_price IS NOT NULL
                  AND exit_price_reconciled_at IS NULL
                  AND exit_date < CURRENT_DATE
                ORDER BY exit_date ASC
                LIMIT 100
            """)
            stale_trades = cur.fetchall()

            if stale_trades:
                alert_msg = (
                    f"CRITICAL: {len(stale_trades)} trades have estimated exit prices "
                    "that were not reconciled. Phase 7 reconciliation may have failed. "
                    f"First stale trade: {stale_trades[0][1]} closed {stale_trades[0][2]}"
                )
                logger.critical(alert_msg)
                try:
                    notify(
                        "critical",
                        title="Exit Price Reconciliation Failed",
                        message=alert_msg,
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"Failed to send reconciliation alert: {e}")
                return {
                    "status": "STALE_ESTIMATED_PRICES",
                    "stale_count": len(stale_trades),
                    "stale_trades": [
                        {
                            "trade_id": t[0],
                            "symbol": t[1],
                            "exit_date": t[2],
                            "estimated": float(t[3]),
                            "actual": float(t[4]),
                        }
                        for t in stale_trades
                    ],
                    "message": alert_msg,
                }
            return {
                "status": "OK",
                "stale_count": 0,
                "message": "All estimated prices reconciled",
            }
        except (psycopg2.DatabaseError, ValueError, TypeError) as e:
            logger.error(f"Stale price audit failed: {e}")
            return {"status": "ERROR", "error": str(e)}

    def sync_alpaca_positions(self, cur):
        """Pull live positions from Alpaca and sync with algo_trades (single source of truth).

        Best practice: our DB should reflect what Alpaca actually holds.
        This catches:
          - Positions opened outside our algo (manual trades)
          - Positions we tracked but Alpaca never filled
          - Drift between systems

        Since algo_trades is the single source of truth for the dashboard:
        - Compare Alpaca positions against algo_trades (not algo_positions)
        - Mark positions in algo_trades that don't exist in Alpaca as closed
        - Import new Alpaca positions as external trades
        """
        if not self._alpaca_key or not self._alpaca_secret:
            return {"imported": 0, "orphaned": 0, "message": "No Alpaca credentials"}
        try:
            import requests

            resp = requests.get(
                f"{self._alpaca_base_url}/v2/positions",
                headers={
                    "APCA-API-KEY-ID": self._alpaca_key,
                    "APCA-API-SECRET-KEY": self._alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code != 200:
                return {
                    "imported": 0,
                    "orphaned": 0,
                    "message": f"Alpaca /v2/positions HTTP {resp.status_code}",
                }
            raw_positions = resp.json()

            # Wrap raw dicts to match expected attribute access pattern
            class _Pos:
                def __init__(self, d):
                    self.__dict__.update(d)

            alpaca_positions = [_Pos(p) for p in raw_positions]
        except (requests.RequestException, json.JSONDecodeError, KeyError, TypeError) as e:
            return {"imported": 0, "orphaned": 0, "message": f"Fetch failed: {e}"}

        # Check both algo_positions and algo_trades for open positions
        cur.execute(
            "SELECT symbol FROM algo_positions WHERE status = %s",
            (PositionStatus.OPEN.value,),
        )
        our_symbols = {row[0] for row in cur.fetchall()}

        # Also check algo_trades (the actual source of truth)
        cur.execute("""
            SELECT DISTINCT symbol FROM algo_trades
            WHERE status IN ('open', 'filled', 'partially_filled', 'active')
        """)
        algo_trades_symbols = {row[0] for row in cur.fetchall()}
        our_symbols.update(algo_trades_symbols)

        # Fetch actual portfolio value for position_size_pct calculation (not a hardcoded constant).
        cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
        _pv_row = cur.fetchone()
        if _pv_row is None or _pv_row[0] is None:
            raise ValueError(
                "Portfolio snapshot missing — cannot calculate position_size_pct without current portfolio value"
            )
        try:
            _portfolio_value_for_pct = float(_pv_row[0])
        except (ValueError, TypeError) as e:
            raise ValueError(f"Portfolio snapshot value not numeric: {_pv_row[0]} ({e})")
        if _portfolio_value_for_pct <= 0:
            raise ValueError("Portfolio value must be > 0 for position sizing calculations")

        alpaca_symbols = {}  # symbol -> qty for drift detection
        imported = 0

        for ap in alpaca_positions:
            sym = ap.symbol
            qty = float(ap.qty)
            alpaca_symbols[sym] = qty

            if sym in our_symbols:
                cur.execute(
                    "SELECT quantity FROM algo_positions WHERE symbol = %s AND status = %s",
                    (sym, PositionStatus.OPEN.value),
                )
                row = cur.fetchone()
                if row is not None:
                    db_qty = int(row[0]) if row[0] is not None else 0
                    # Shares should be integers; only allow rounding error on tiny positions (<1 share)
                    qty_int = round(qty)
                    if abs(db_qty - qty_int) > 0:
                        # Alpaca is the source of truth — correct the DB quantity
                        try:
                            cur.execute(
                                "UPDATE algo_positions SET quantity = %s WHERE symbol = %s AND status = %s",
                                (qty_int, sym, PositionStatus.OPEN.value),
                            )
                            logger.warning(
                                f"[RECONCILE] Corrected {sym} quantity: DB had {db_qty}, Alpaca has {qty_int}"
                            )
                        except psycopg2.DatabaseError as e:
                            logger.error(f"  Could not correct {sym} quantity in DB: {e}")
                        try:
                            notify(
                                severity="warning",
                                title="Quantity Corrected",
                                message=f"{sym}: DB quantity corrected {db_qty} → {qty_int} to match Alpaca.",
                                symbol=sym,
                                details={
                                    "symbol": sym,
                                    "alpaca_qty": qty_int,
                                    "db_qty_before": db_qty,
                                },
                            )
                        except (ValueError, ZeroDivisionError, TypeError) as e:
                            logger.warning(f"  Could not send quantity correction alert: {e}")
                continue  # already tracked

            # Import this Alpaca position as a manual/external one
            try:
                qty_raw = getattr(ap, "qty", None)
                if qty_raw is None or qty_raw == 0:
                    continue  # skip zero/missing quantities
                qty = float(qty_raw)

                # Validate entry price (critical)
                avg_entry_raw = getattr(ap, "avg_entry_price", None)
                if avg_entry_raw is None:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: missing or invalid entry price — cannot import")
                try:
                    avg_entry = float(avg_entry_raw)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: entry price not numeric '{avg_entry_raw}' — cannot import") from e
                if avg_entry <= 0:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: entry price {avg_entry} <= 0 — cannot import")

                # Validate current price
                cur_price_raw = getattr(ap, "current_price", None)
                if cur_price_raw is None:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: missing or invalid current price — cannot import")
                try:
                    cur_price = float(cur_price_raw)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: current price not numeric '{cur_price_raw}' — cannot import") from e
                if cur_price <= 0:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: current price {cur_price} <= 0 — cannot import")

                # Validate market value if provided
                pos_value_raw = getattr(ap, "market_value", None)
                if pos_value_raw is not None:
                    pos_value = float(pos_value_raw)
                    if pos_value <= 0:
                        logger.warning(f"[import_alpaca] {sym}: Market value invalid {pos_value} — recalculating")
                        pos_value = qty * cur_price
                else:
                    pos_value = qty * cur_price

                # Get PnL (may be missing for very new positions — compute from prices, don't mask with 0)
                pnl_raw = getattr(ap, "unrealized_pl", None)
                pnl_pct_raw = getattr(ap, "unrealized_plpc", None)

                if pnl_raw is not None and pnl_pct_raw is not None:
                    pnl = float(pnl_raw)
                    pnl_pct = float(pnl_pct_raw) * 100
                elif cur_price is not None and avg_entry is not None and cur_price > 0 and avg_entry > 0:
                    pnl_pct = ((cur_price - avg_entry) / avg_entry) * 100
                    pnl = (cur_price - avg_entry) * qty
                else:
                    raise ValueError(f"[RECONCILIATION CRITICAL] Alpaca position {sym}: Cannot compute PnL (missing prices) — cannot import")

                position_id = f"EXT-{sym}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
                trade_id = f"EXT-{sym}"

                # For imported positions, calculate realistic stops + targets using volatility
                # This replaces the hardcoded placeholder values (0.92, 1.10/1.20/1.30)
                stop_loss_price = None
                target_1 = None
                target_2 = None
                target_3 = None
                stop_loss_method = "imported_no_risk_calc"

                cur.execute("SAVEPOINT import_sp")
                try:
                    # Use pre-computed ATR from technical_data_daily (includes gap moves via
                    # max(H-L, |H-PC|, |L-PC|)). AVG(high-low) from price_daily underestimates
                    # true ATR for gap-prone stocks and sets stops too tight.
                    cur.execute(
                        """
                        SELECT atr FROM technical_data_daily
                        WHERE symbol = %s AND atr IS NOT NULL
                        ORDER BY date DESC LIMIT 1
                    """,
                        (sym,),
                    )
                    atr_row = cur.fetchone()
                    if atr_row is not None and atr_row[0] is not None:
                        atr = float(atr_row[0])
                        # Stop = 2 * ATR below entry (standard risk management)
                        stop_loss_price = max(0.01, avg_entry - (2 * atr))
                        stop_loss_method = "imported_2x_atr"
                        # Targets = 1:2 and 1:3 reward/risk ratio
                        r = avg_entry - stop_loss_price
                        target_1 = avg_entry + (2 * r)  # 2R
                        target_2 = avg_entry + (3 * r)  # 3R
                        target_3 = avg_entry + (4 * r)  # 4R
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.critical(
                        f"[RECONCILIATION] Failed to calculate stop/targets for imported {sym}: {e} — "
                        f"cannot proceed with risk calculation. Position cannot be imported without proper risk limits."
                    )
                    raise ValueError(
                        f"Cannot import external position for {sym}: "
                        f"risk/target calculation failed ({type(e).__name__}: {str(e)[:100]}). "
                        "Reconciliation requires ATR-based risk management; fall-through to defaults is not allowed "
                        "to prevent incorrect stop prices."
                    ) from e

                # Verify risk calculation succeeded before proceeding
                if stop_loss_price is None or target_1 is None:
                    logger.critical(
                        f"[RECONCILIATION] Stop/target calculation for {sym} produced None values "
                        f"(stop={stop_loss_price}, target_1={target_1}); this should not happen if exception was raised"
                    )
                    raise ValueError(
                        f"Internal error: stop/target calculation for {sym} incomplete. "
                        "Risk limits are critical; cannot use percentage defaults without explicit retry."
                    )

                cur.execute(
                    """
                    INSERT INTO algo_trades (
                        trade_id, symbol, signal_date, trade_date,
                        entry_time, entry_price, entry_quantity, entry_reason,
                        stop_loss_price, stop_loss_method,
                        target_1_price, target_2_price, target_3_price,
                        status, execution_mode, alpaca_order_id,
                        position_size_pct, base_type, created_at
                    )
                    VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE, CURRENT_TIMESTAMP, %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (trade_id) DO NOTHING
                """,
                    (
                        trade_id,
                        sym,
                        avg_entry,
                        int(qty),
                        "EXTERNAL: existing Alpaca position imported",
                        stop_loss_price,
                        stop_loss_method,
                        target_1,
                        target_2,
                        target_3,
                        PositionStatus.OPEN.value,
                        "external",
                        f"ALPACA-EXT-{sym}",
                        ((pos_value / _portfolio_value_for_pct * 100) if _portfolio_value_for_pct > 0 else 0.0),
                        "imported_external",
                    ),
                )

                # Insert position (use same stop as calculated in trade above)
                cur.execute(
                    """
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price,
                        current_price, position_value, unrealized_pnl,
                        unrealized_pnl_pct, status, trade_ids_arr,
                        current_stop_price, stop_loss_price, target_levels_hit, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT (position_id) DO NOTHING
                """,
                    (
                        position_id,
                        sym,
                        int(qty),
                        avg_entry,
                        cur_price,
                        pos_value,
                        pnl,
                        pnl_pct,
                        PositionStatus.OPEN.value,
                        [trade_id],
                        stop_loss_price,
                        stop_loss_price,
                    ),
                )
                imported += 1
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"  Failed to import {sym}: {e}")
                cur.execute("ROLLBACK TO SAVEPOINT import_sp")
                try:
                    cur.execute(
                        "INSERT INTO alpaca_import_failures (symbol, error_message, retry_count) VALUES (%s, %s, 0)",
                        (sym, str(e)[:500]),
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as fail_e:
                    logger.error(f"  Could not log import failure for {sym}: {fail_e}")

        # Retry failed imports and alert if multiple failures
        failed_retried = self._process_failed_imports(cur, alpaca_positions)

        # Find pending orders that haven't been filled yet (don't show in /v2/positions)
        # These should NOT be marked as orphaned, as they may still fill
        pending_symbols = set()
        if alpaca_positions:  # Only check if we successfully fetched positions
            try:
                resp = requests.get(
                    f"{self._alpaca_base_url}/v2/orders?status=pending&status=accepted&status=held",
                    headers={
                        "APCA-API-KEY-ID": self._alpaca_key,
                        "APCA-API-SECRET-KEY": self._alpaca_secret,
                    },
                    timeout=self.config.get("api_request_timeout_seconds", 5),
                )
                if resp.status_code == 200:
                    pending_orders = resp.json() if isinstance(resp.json(), list) else []
                    pending_symbols = {order.get("symbol") for order in pending_orders if order.get("symbol")}
                    logger.debug(f"Found {len(pending_symbols)} symbols with pending orders: {pending_symbols}")
            except (requests.RequestException, requests.Timeout) as e:
                logger.warning(f"Could not fetch pending orders: {e}")

        # Find orphans (in our DB but not in Alpaca positions AND not pending)
        orphans = (our_symbols - set(alpaca_symbols.keys())) - pending_symbols
        if orphans:
            orphan_list = list(orphans)

            # Bulk update algo_positions for all orphans
            cur.execute(
                """
                UPDATE algo_positions
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE symbol = ANY(%s) AND status = %s
            """,
                (PositionStatus.ORPHANED.value, orphan_list, PositionStatus.OPEN.value),
            )

            # Bulk close all orphan positions in algo_trades (single source of truth for dashboard)
            # This ensures the dashboard doesn't show positions that don't exist in Alpaca
            # Close both: trades with no exit_date AND trades with old exit_date but wrong status
            cur.execute(
                """
                UPDATE algo_trades
                SET status = 'closed', exit_date = COALESCE(exit_date, CURRENT_DATE), updated_at = CURRENT_TIMESTAMP
                WHERE symbol = ANY(%s) AND status IN ('open', 'filled', 'partially_filled', 'active')
            """,
                (orphan_list,),
            )

            # Alert on each orphan
            for sym in orphans:
                try:
                    notify(
                        severity="critical",
                        title="CRITICAL: Position Drift Detected",
                        message=f"{sym} shows as open in DB but not found in Alpaca. "
                        "Position closed in DB to match Alpaca reality. Manual verification recommended.",
                        symbol=sym,
                        details={
                            "symbol": sym,
                            "drift_type": "orphaned_in_db",
                            "action": "closed_to_sync",
                        },
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"  Could not send orphan alert: {e}")

        return {
            "imported": imported,
            "orphaned": len(orphans),
            "alpaca_total": len(alpaca_positions),
            "orphan_symbols": list(orphans),
            "failed_retried": failed_retried,
            "message": f"Imported {imported} external Alpaca positions, "
            f"{len(orphans)} orphans flagged, {failed_retried} retried",
        }

    def _process_failed_imports(self, cur, alpaca_positions):
        """Retry failed imports and alert on multiple failures."""
        if not alpaca_positions:
            raise RuntimeError(
                "CRITICAL: Alpaca position data unavailable. "
                "Cannot safely retry failed imports without current Alpaca positions. "
                "Reconciliation halted to prevent orphaned/stale position records."
            )
        alpaca_map = {ap.symbol: ap for ap in alpaca_positions}
        cur.execute("SELECT DISTINCT symbol FROM alpaca_import_failures WHERE resolved = FALSE AND retry_count < 3")
        failed_symbols = {row[0] for row in cur.fetchall()}
        retryable = failed_symbols & set(alpaca_map.keys())
        retried = 0
        for sym in retryable:
            ap = alpaca_map[sym]
            try:
                qty_raw = getattr(ap, "qty", None)
                if qty_raw is None or qty_raw == 0:
                    continue
                qty = float(qty_raw)
                avg_entry_raw = getattr(ap, "avg_entry_price", None)
                if avg_entry_raw is None or float(avg_entry_raw) <= 0:
                    continue
                avg_entry = float(avg_entry_raw)
                cur_price_raw = getattr(ap, "current_price", None)
                if cur_price_raw is None or float(cur_price_raw) <= 0:
                    continue
                cur_price = float(cur_price_raw)
                pos_value_raw = getattr(ap, "market_value", None)
                pos_value = float(pos_value_raw) if pos_value_raw else qty * cur_price
                pnl_raw = getattr(ap, "unrealized_pl", None)
                pnl = float(pnl_raw) if pnl_raw else 0.0
                pnl_pct_raw = getattr(ap, "unrealized_plpc", None)
                pnl_pct = (float(pnl_pct_raw) * 100) if pnl_pct_raw else 0.0
                position_id = f"EXT-{sym}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
                trade_id = f"EXT-{sym}"
                cur.execute("SAVEPOINT retry_sp")
                try:
                    # Use ATR-based risk calculation (same as main import path)
                    stop_loss_price_retry = None
                    target_1_retry = None
                    target_2_retry = None
                    target_3_retry = None
                    stop_loss_method_retry = "imported_retry_no_risk_calc"

                    try:
                        cur.execute(
                            """
                            SELECT atr FROM technical_data_daily
                            WHERE symbol = %s AND atr IS NOT NULL
                            ORDER BY date DESC LIMIT 1
                        """,
                            (sym,),
                        )
                        atr_retry_row = cur.fetchone()
                        if atr_retry_row is not None and atr_retry_row[0] is not None:
                            atr_retry = float(atr_retry_row[0])
                            stop_loss_price_retry = max(0.01, avg_entry - (2 * atr_retry))
                            stop_loss_method_retry = "imported_retry_2x_atr"
                            r = avg_entry - stop_loss_price_retry
                            target_1_retry = avg_entry + (2 * r)
                            target_2_retry = avg_entry + (3 * r)
                            target_3_retry = avg_entry + (4 * r)
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as atr_e:
                        logger.error(f"[RETRY_IMPORT] Failed to calculate ATR-based stops for {sym}: {atr_e}")

                    # Fail hard if ATR calculation failed — don't fall back to percentages
                    if stop_loss_price_retry is None:
                        logger.warning(
                            f"[RETRY_IMPORT] Skipping retry for {sym}: cannot calculate risk limits without ATR"
                        )
                        cur.execute("RELEASE SAVEPOINT retry_sp")
                        continue

                    cur.execute(
                        "INSERT INTO algo_trades "
                        "(trade_id, symbol, signal_date, trade_date, entry_time, "
                        "entry_price, entry_quantity, entry_reason, "
                        "stop_loss_price, stop_loss_method, target_1_price, "
                        "target_2_price, target_3_price, status, execution_mode, "
                        "alpaca_order_id, position_size_pct, base_type, created_at) "
                        "VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE, "
                        "CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                        "%s, %s, %s, CURRENT_TIMESTAMP) "
                        "ON CONFLICT (trade_id) DO NOTHING",
                        (
                            trade_id,
                            sym,
                            avg_entry,
                            int(qty),
                            "EXTERNAL: retried import",
                            stop_loss_price_retry,
                            stop_loss_method_retry,
                            target_1_retry,
                            target_2_retry,
                            target_3_retry,
                            PositionStatus.OPEN.value,
                            "external",
                            f"ALPACA-EXT-{sym}",
                            0.0,
                            "imported_external",
                        ),
                    )
                    cur.execute(
                        "INSERT INTO algo_positions "
                        "(position_id, symbol, quantity, avg_entry_price, "
                        "current_price, position_value, unrealized_pnl, "
                        "unrealized_pnl_pct, status, trade_ids_arr, "
                        "current_stop_price, stop_loss_price, target_levels_hit, "
                        "created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                        "%s, %s, 0, CURRENT_TIMESTAMP) "
                        "ON CONFLICT (position_id) DO NOTHING",
                        (
                            position_id,
                            sym,
                            int(qty),
                            avg_entry,
                            cur_price,
                            pos_value,
                            pnl,
                            pnl_pct,
                            PositionStatus.OPEN.value,
                            [trade_id],
                            stop_loss_price_retry,
                            stop_loss_price_retry,
                        ),
                    )
                    cur.execute(
                        "UPDATE alpaca_import_failures "
                        "SET resolved = TRUE, resolved_at = CURRENT_TIMESTAMP "
                        "WHERE symbol = %s AND resolved = FALSE",
                        (sym,),
                    )
                    retried += 1
                    logger.info(f"  Retried import of {sym} successfully")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as retry_e:
                    cur.execute("ROLLBACK TO SAVEPOINT retry_sp")
                    logger.warning(f"  Retry import of {sym} failed: {retry_e}")
                    cur.execute(
                        "UPDATE alpaca_import_failures "
                        "SET retry_count = retry_count + 1, "
                        "last_retry_at = CURRENT_TIMESTAMP "
                        "WHERE symbol = %s AND resolved = FALSE",
                        (sym,),
                    )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.debug(f"  Retry prep for {sym} failed: {e}")
        cur.execute(
            "SELECT COUNT(DISTINCT symbol) FROM alpaca_import_failures "
            "WHERE resolved = FALSE AND failed_at > NOW() - INTERVAL '1 day'"
        )
        failure_row = cur.fetchone()
        failure_count = failure_row[0] if failure_row else 0
        if failure_count > 5:
            try:
                notify(
                    severity="warning",
                    title=f"Alpaca Import Failures ({failure_count})",
                    message=">5 failed imports in last 24h. Positions may be orphaned.",
                    details={"failure_count": failure_count},
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as alert_e:
                logger.warning(f"Could not send failure alert: {alert_e}")
        try:
            cur.execute(
                "DELETE FROM alpaca_import_failures WHERE resolved = TRUE AND resolved_at < NOW() - INTERVAL '7 days'"
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Could not cleanup old failures: {e}")
        return retried

    def compute_analytics_metrics(self, cur):
        """E4+E5: Compute Information Coefficient and Expectancy metrics.

        E4: Weekly correlation of entry swing_score vs 5-day post-entry return.
        E5: After 30+ closed trades, compute Kelly fraction for position sizing alerts.

        Args:
            cur: Database cursor from DatabaseContext
        """
        try:
            # E4: Information Coefficient (last 8 weeks of closed trades)
            cur.execute(
                """
                SELECT swing_score, profit_loss_pct, trade_duration_days
                FROM algo_trades
                WHERE status = %s
                  AND exit_date >= NOW()::date - INTERVAL '56 days'
                  AND swing_score IS NOT NULL
                  AND profit_loss_pct IS NOT NULL
                ORDER BY exit_date
            """,
                (TradeStatus.CLOSED.value,),
            )

            trades = cur.fetchall()
            ic_result = {"valid": False, "ic": None, "alert": None}

            if len(trades) >= 10:  # Need min 10 trades for meaningful IC
                # Compute rank correlation (Spearman) between swing_score and 5d returns
                try:
                    scores = [float(t[0]) for t in trades]
                    returns = [float(t[1]) for t in trades]

                    # Rank correlation manually (Spearman)
                    score_ranks = sorted(range(len(scores)), key=lambda i: scores[i])
                    return_ranks = sorted(range(len(returns)), key=lambda i: returns[i])
                    rank_scores = [0] * len(score_ranks)
                    rank_returns = [0] * len(return_ranks)
                    for i, idx in enumerate(score_ranks):
                        rank_scores[idx] = i
                    for i, idx in enumerate(return_ranks):
                        rank_returns[idx] = i

                    # Pearson correlation on ranks (= Spearman IC).
                    # Use n-1 denominator for both covariance and stdev (sample statistics).
                    # Using population cov (÷n) with sample stdev (÷n-1) produces a slightly-off IC.
                    n = len(rank_scores)
                    if n < 2:
                        # Not enough data points for IC calculation
                        ic_result = {
                            "valid": False,
                            "ic": 0,
                            "trade_count": len(trades),
                            "reason": "Insufficient trades for IC",
                        }
                    else:
                        mean_sr = statistics.mean(rank_scores)
                        mean_rr = statistics.mean(rank_returns)
                        cov = sum((rank_scores[i] - mean_sr) * (rank_returns[i] - mean_rr) for i in range(n)) / (n - 1)
                        std_sr = statistics.stdev(rank_scores) if n > 1 else 1
                        std_rr = statistics.stdev(rank_returns) if len(rank_returns) > 1 else 1
                        ic = cov / (std_sr * std_rr) if (std_sr * std_rr) > 0 else 0

                        ic_result = {
                            "valid": True,
                            "ic": round(ic, 4),
                            "trade_count": len(trades),
                            "alert": ("IC < 0.05 (signal quality degraded)" if ic < 0.05 else None),
                        }
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logger.warning(f"IC computation failed: {e}")

            # E5: Expectancy and Kelly sizing (all closed trades)
            cur.execute(
                """
                SELECT COUNT(*), SUM(profit_loss_pct), AVG(profit_loss_pct)
                FROM algo_trades
                WHERE status = %s AND profit_loss_pct IS NOT NULL
            """,
                (TradeStatus.CLOSED.value,),
            )

            stats = cur.fetchone()
            expectancy_result = {"valid": False, "expectancy": None, "alert": None}

            if stats and stats[0] >= 30:  # Need 30+ trades
                total_trades = stats[0]
                float(stats[1]) if stats[1] is not None else 0.0
                float(stats[2]) if stats[2] is not None else 0.0

                # Count wins and losses
                cur.execute(
                    """
                    SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) AS wins,
                           COUNT(*) FILTER (WHERE profit_loss_pct <= 0) AS losses,
                           AVG(profit_loss_pct) FILTER (WHERE profit_loss_pct > 0) AS avg_win,
                           AVG(profit_loss_pct) FILTER (WHERE profit_loss_pct <= 0) AS avg_loss
                    FROM algo_trades
                    WHERE status = %s
                """,
                    (TradeStatus.CLOSED.value,),
                )

                wr = cur.fetchone()
                wins = int(wr[0]) if wr[0] is not None else 0
                int(wr[1]) if wr[1] is not None else 0
                avg_win = float(wr[2]) if wr[2] is not None else 1.0
                avg_loss = float(wr[3]) if wr[3] is not None else -1.0

                win_rate = wins / total_trades if total_trades > 0 else 0
                expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

                # Kelly fraction: f = (bp - q) / b where b=ratio, p=win%, q=loss%
                # Simplified: kelly = (wins/total * avg_win - losses/total * abs(avg_loss)) / max(abs(avg_win), abs(avg_loss))
                if avg_win > 0 or avg_loss < 0:
                    kelly_num = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
                    kelly_denom = max(abs(avg_win), abs(avg_loss))
                    kelly = kelly_num / kelly_denom if kelly_denom > 0 else 0
                else:
                    kelly = 0

                expectancy_result = {
                    "valid": True,
                    "expectancy": round(expectancy, 4),
                    "win_rate": round(win_rate * 100, 1),
                    "kelly_fraction": round(max(0, kelly * 0.25), 4),  # Conservative 25% Kelly
                    "alert": ("NEGATIVE EXPECTANCY (reduce position sizing)" if expectancy < 0 else None),
                }

            return {
                "ic": ic_result,
                "expectancy": expectancy_result,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Error in compute_analytics_metrics: {e}")
            return {"ic": {"valid": False}, "expectancy": {"valid": False}}

    def compute_closed_trade_metrics(self, cur):
        """E3: Compute MAE/MFE for recently closed trades (last 30 days)."""
        try:
            # Find recently closed trades without MAE/MFE
            cur.execute(
                """
                SELECT trade_id, symbol, trade_date, exit_date, entry_price, exit_price, exit_r_multiple
                FROM algo_trades
                WHERE status = %s
                  AND exit_date IS NOT NULL
                  AND exit_date >= NOW()::date - INTERVAL '30 days'
                  AND (mae_pct IS NULL OR mfe_pct IS NULL)
                ORDER BY exit_date DESC
            """,
                (TradeStatus.CLOSED.value,),
            )

            trades_to_update = cur.fetchall()
            if not trades_to_update:
                return {
                    "updated": 0,
                    "reason": "No recently closed trades without MAE/MFE",
                }

            updates = 0
            for (
                trade_id,
                symbol,
                entry_date,
                exit_date,
                entry_price,
                exit_price,
                _r_mult,
            ) in trades_to_update:
                try:
                    cur.execute("SAVEPOINT mae_mfe_update")
                    entry_price = float(entry_price)
                    if not exit_price or float(exit_price) <= 0:
                        logger.warning(
                            f"Trade {trade_id} ({symbol}): invalid exit_price {exit_price}, skipping MAE/MFE"
                        )
                        cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                        continue
                    exit_price = float(exit_price)

                    cur.execute(
                        """
                        SELECT high, low FROM price_daily
                        WHERE symbol = %s AND date >= %s AND date <= %s
                        ORDER BY date ASC
                    """,
                        (symbol, entry_date, exit_date),
                    )

                    prices = cur.fetchall()
                    if not prices:
                        cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                        continue

                    # CRITICAL: Never use entry_price as fallback for high/low.
                    # Entry price is worst-case fill price, using it masks actual market excursion.
                    # Example: stop-loss hit at -5%, entry used as high/low → MAE shows -0.01% (entry price ≈ high/low).
                    # This corrupts strategy evaluation and makes losing trades appear safer.
                    # Instead: skip MAE/MFE if price data incomplete (leave NULL in DB).
                    highs = [float(p[0]) for p in prices if p[0] is not None]
                    lows = [float(p[1]) for p in prices if p[1] is not None]

                    # Only compute MAE/MFE if we have complete high/low data for the period
                    if not highs or not lows:
                        logger.warning(
                            f"Incomplete OHLCV data for trade {trade_id} ({symbol}) {entry_date} to {exit_date}: "
                            "skipping MAE/MFE computation to avoid fallback-induced corruption"
                        )
                        cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                        continue

                    # MAE: worst (lowest) price from entry
                    min_price = min(lows)
                    mae_pct = ((min_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

                    # MFE: best (highest) price from entry
                    max_price = max(highs)
                    mfe_pct = ((max_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

                    cur.execute(
                        """
                        UPDATE algo_trades
                        SET mae_pct = %s, mfe_pct = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE trade_id = %s
                    """,
                        (round(mae_pct, 4), round(mfe_pct, 4), trade_id),
                    )

                    cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                    updates += 1
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    cur.execute("ROLLBACK TO SAVEPOINT mae_mfe_update")
                    logger.warning(f"Failed to compute MAE/MFE for trade {trade_id}: {e}")

            return {
                "updated": updates,
                "reason": f"Computed MAE/MFE for {updates} closed trades",
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Error in compute_closed_trade_metrics: {e}")
            return {"updated": 0, "reason": f"Error: {e}"}

    def check_partial_fills(self, cur) -> dict:
        """Check for partial fills that haven't been reconciled with Alpaca.

        Detects when orders were only partially filled but the local DB thinks
        they're fully filled. This catches the case when Alpaca fills part of an
        order and then network fails before we can sync.

        Returns: dict with reconciliation status and any detected drift
        """
        if not self._alpaca_key or not self._alpaca_secret:
            return {"checked": 0, "message": "No Alpaca credentials"}

        try:
            import requests

            resp = requests.get(
                f"{self._alpaca_base_url}/v2/orders?status=filled&status=partially_filled",
                headers={
                    "APCA-API-KEY-ID": self._alpaca_key,
                    "APCA-API-SECRET-KEY": self._alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )

            if resp.status_code != 200:
                return {"checked": 0, "message": f"Alpaca orders API {resp.status_code}"}

            orders = resp.json()
            if not isinstance(orders, list):
                return {"checked": 0, "message": "Unexpected Alpaca response format"}

            # Check each order against our DB records
            mismatches = []
            for order in orders:
                symbol = order.get("symbol")
                float(order.get("qty", 0))
                alpaca_filled_qty = float(order.get("filled_qty", 0))
                order_status = order.get("status")

                if not symbol or alpaca_filled_qty <= 0:
                    continue

                # Find corresponding trade in our DB
                cur.execute(
                    """
                    SELECT trade_id, entry_quantity, status
                    FROM algo_trades
                    WHERE symbol = %s AND status IN ('open', 'filled', 'partially_filled', 'active')
                    ORDER BY trade_date DESC LIMIT 1
                """,
                    (symbol,),
                )

                db_row = cur.fetchone()
                if db_row is None:
                    continue

                db_trade_id, db_qty, _db_status = db_row

                # Check for mismatch
                db_qty_int = int(db_qty) if db_qty else 0
                alpaca_filled_int = int(alpaca_filled_qty)

                if alpaca_filled_int > 0 and db_qty_int != alpaca_filled_int:
                    # Quantity drift detected — Alpaca has different fill than DB
                    mismatches.append(
                        {
                            "symbol": symbol,
                            "trade_id": db_trade_id,
                            "db_quantity": db_qty_int,
                            "alpaca_filled": alpaca_filled_int,
                            "alpaca_status": order_status,
                        }
                    )

                    # Correct the DB quantity to match Alpaca (source of truth)
                    cur.execute(
                        "UPDATE algo_trades SET entry_quantity = %s, updated_at = CURRENT_TIMESTAMP WHERE trade_id = %s",
                        (alpaca_filled_int, db_trade_id),
                    )
                    logger.warning(
                        f"[PARTIAL_FILL] Corrected {symbol} quantity: DB had {db_qty_int}, Alpaca filled {alpaca_filled_int}"
                    )

                    try:
                        notify(
                            severity="warning",
                            title="Partial Fill Detected and Corrected",
                            message=f"{symbol}: Quantity corrected from {db_qty_int} to {alpaca_filled_int} to match Alpaca.",
                            symbol=symbol,
                            details={
                                "symbol": symbol,
                                "db_quantity": db_qty_int,
                                "alpaca_filled": alpaca_filled_int,
                            },
                        )
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        logger.warning(f"Could not send partial fill alert: {e}")

            return {
                "checked": len(orders),
                "mismatches": len(mismatches),
                "message": f"Checked {len(orders)} orders; corrected {len(mismatches)} partial fills",
                "details": mismatches,
            }

        except (requests.RequestException, json.JSONDecodeError, psycopg2.DatabaseError) as e:
            logger.warning(f"Partial fill check error: {e}")
            return {"checked": 0, "message": f"Error: {e}"}

    def check_pending_reconciliations(self, cur) -> dict:
        """Identify and report on trades pending Phase 7 price reconciliation.

        Trades with estimated exit prices (Phase 4 pre-market exits) that haven't
        been reconciled with actual Alpaca fill prices. Helps diagnose Phase 7
        failures or delays that leave estimated prices permanent.
        """
        try:
            cur.execute("""
                SELECT trade_id, symbol, exit_date, exit_price, estimated_exit_price,
                       exit_price_reconciled_at, reconciliation_note
                FROM algo_trades
                WHERE estimated_exit_price IS NOT NULL
                  AND exit_price_reconciled_at IS NULL
                ORDER BY exit_date DESC
            """)
            pending = cur.fetchall()

            if not pending:
                return {"pending_count": 0, "message": "No pending reconciliations"}

            pending_list = []
            for (
                trade_id,
                symbol,
                exit_date,
                exit_price,
                est_price,
                _recon_at,
                note,
            ) in pending:
                variance_pct = None
                if exit_price is not None and est_price is not None:
                    try:
                        exit_price_f = float(exit_price)
                        est_price_f = float(est_price)
                        if est_price_f > 0:
                            variance_pct = (exit_price_f - est_price_f) / est_price_f * 100
                    except (ValueError, TypeError):
                        variance_pct = None
                pending_list.append(
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "exit_date": exit_date,
                        "estimated_price": float(est_price) if est_price else None,
                        "current_exit_price": float(exit_price) if exit_price else None,
                        "variance_pct": variance_pct,
                        "note": note,
                        "days_pending": ((datetime.now(timezone.utc).date() - exit_date).days if exit_date else None),
                    }
                )

            # Log critical alert if any reconciliations are stuck (> 1 day old)
            stuck = [p for p in pending_list if p["days_pending"] and p["days_pending"] > 1]
            if stuck:
                stuck_examples = ", ".join(["{} {}".format(p["symbol"], p["trade_id"]) for p in stuck[:3]])
                logger.critical(
                    f"RECONCILIATION STUCK: {len(stuck)} trades with estimated exit prices "
                    "stuck > 1 day without Alpaca price reconciliation. "
                    f"Examples: {stuck_examples}"
                )

            return {
                "pending_count": len(pending_list),
                "stuck_count": len(stuck),
                "pending": pending_list,
                "message": f"{len(pending_list)} trades pending reconciliation ({len(stuck)} stuck > 1d)",
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Failed to check pending reconciliations: {e}")
            return {"pending_count": 0, "message": f"Error: {e}"}

    def _fetch_alpaca_account(self):
        """Fetch account data from Alpaca via direct HTTP REST call."""
        if not self._alpaca_key or not self._alpaca_secret:
            raise RuntimeError(
                "CRITICAL: Alpaca API credentials not available. "
                "Cannot reconcile account without valid credentials. "
                "Reconciliation requires live Alpaca connection."
            )
        try:
            import requests

            resp = requests.get(
                f"{self._alpaca_base_url}/v2/account",
                headers={
                    "APCA-API-KEY-ID": self._alpaca_key,
                    "APCA-API-SECRET-KEY": self._alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code == 200:
                data = resp.json()
                cash_val = data.get("cash")
                equity_val = data.get("equity")
                portfolio_value_val = data.get("portfolio_value") or data.get("equity")
                buying_power_val = data.get("buying_power")
                return {
                    "cash": float(cash_val) if cash_val is not None else None,
                    "equity": float(equity_val) if equity_val is not None else None,
                    "portfolio_value": (float(portfolio_value_val) if portfolio_value_val is not None else None),
                    "buying_power": (float(buying_power_val) if buying_power_val is not None else None),
                }
            raise ValueError(f"Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:100]}")
        except (requests.RequestException, requests.Timeout, ValueError, KeyError, AttributeError) as e:
            raise ValueError(f"Could not fetch Alpaca account: {e}") from e

    def _fetch_initial_capital(self, cur):
        """Get the actual initial capital from Alpaca account history.

        Returns the oldest portfolio value from Alpaca portfolio history.
        Falls back to the oldest algo_portfolio_snapshots entry if Alpaca history unavailable.
        Raises ValueError if initial capital cannot be determined.
        """
        if not self._alpaca_key or not self._alpaca_secret:
            logger.warning("No Alpaca credentials; checking database for initial capital")
            try:
                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC LIMIT 1
                """)
                row = cur.fetchone()
                if row is not None and row[0] is not None:
                    val = float(row[0])
                    if val > 0:
                        logger.info(f"Using oldest database snapshot as initial capital: ${val:,.2f}")
                        return val
            except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError) as e:
                logger.warning(f"Could not query database for initial capital: {e}")
            raise ValueError("Cannot determine initial capital: no Alpaca credentials and no database history")

        try:
            import requests

            resp = requests.get(
                f"{self._alpaca_base_url}/v2/account/portfolio/history",
                params={"period": "all"},
                headers={
                    "APCA-API-KEY-ID": self._alpaca_key,
                    "APCA-API-SECRET-KEY": self._alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "equity" in data:
                    equity_list = data.get("equity", [])
                    if equity_list:
                        initial_val = float(equity_list[0])
                        if initial_val > 0:
                            logger.info(f"Initial capital from Alpaca history: ${initial_val:,.2f}")
                            return initial_val
            logger.warning(f"Alpaca portfolio history unavailable (HTTP {resp.status_code}); checking database")
        except (requests.RequestException, requests.Timeout, ValueError, KeyError) as e:
            logger.warning(f"Could not fetch Alpaca portfolio history: {e}; checking database")

        try:
            cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date ASC LIMIT 1
            """)
            row = cur.fetchone()
            if row is not None and row[0] is not None:
                val = float(row[0])
                if val > 0:
                    logger.info(f"Using oldest database snapshot as initial capital: ${val:,.2f}")
                    return val
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, TypeError) as e:
            logger.warning(f"Could not query database for initial capital: {e}")

        raise ValueError("Cannot determine initial capital: Alpaca history unavailable and no database snapshots found")

    def validate_pnl(self, alpaca_equity: float, local_equity: float) -> dict:
        """Validate that local P&L matches Alpaca P&L within tolerance.

        Args:
            alpaca_equity: Equity reported by Alpaca
            local_equity: Equity calculated from local positions and cash

        Returns:
            Dict with validation results: {
                'valid': bool,
                'alpaca_equity': float,
                'local_equity': float,
                'variance_pct': float,
                'variance_dollars': float,
                'status': 'ok'|'alert'|'critical',
                'message': str
            }
        """
        if alpaca_equity is None or local_equity is None:
            return {
                "valid": False,
                "alpaca_equity": alpaca_equity,
                "local_equity": local_equity,
                "variance_pct": None,
                "variance_dollars": None,
                "status": "error",
                "message": "Cannot validate P&L: missing Alpaca or local equity data",
            }

        if alpaca_equity <= 0 or local_equity <= 0:
            return {
                "valid": False,
                "alpaca_equity": alpaca_equity,
                "local_equity": local_equity,
                "variance_pct": None,
                "variance_dollars": None,
                "status": "error",
                "message": "Cannot validate P&L: equity values must be positive",
            }

        variance_dollars = alpaca_equity - local_equity
        variance_pct = (variance_dollars / alpaca_equity) * 100.0 if alpaca_equity > 0 else 0.0

        threshold = 0.1  # 0.1% tolerance

        if abs(variance_pct) <= threshold:
            status = "ok"
            message = f"P&L validated: Alpaca ${alpaca_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%)"
            valid = True
        elif abs(variance_pct) <= 1.0:
            status = "alert"
            message = f"P&L variance ALERT: Alpaca ${alpaca_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%, ${variance_dollars:+,.2f})"
            valid = False
        else:
            status = "critical"
            message = f"P&L MISMATCH CRITICAL: Alpaca ${alpaca_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%, ${variance_dollars:+,.2f}) - verify position prices and trade exit prices"
            valid = False

        return {
            "valid": valid,
            "alpaca_equity": alpaca_equity,
            "local_equity": local_equity,
            "variance_pct": variance_pct,
            "variance_dollars": variance_dollars,
            "status": status,
            "message": message,
        }


if __name__ == "__main__":
    from algo.infrastructure import get_config

    config = get_config()
    reconciliation = DailyReconciliation(config)

    result = reconciliation.run_daily_reconciliation()
    logger.info(f"Result: {result}")
