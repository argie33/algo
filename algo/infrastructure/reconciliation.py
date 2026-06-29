#!/usr/bin/env python3

import json
import logging
from datetime import date as _date_type
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import psycopg2
import requests

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
from algo.infrastructure.audit_logger import TradeAuditLogger
from algo.infrastructure.broker_adapter import BrokerAdapter
from algo.infrastructure.position_analyzer import PositionAnalyzer
from algo.reporting import notify
from utils.db import DatabaseContext
from utils.trading import PositionStatus

logger = logging.getLogger(__name__)

PORTFOLIO_SNAPSHOT_LOCK_ID = 2147483647


class DailyReconciliation:
    """Daily reconciliation and portfolio snapshot creation.

    Uses broker adapter for position sync, analytics, and price auditing.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config: dict[str, Any] = config
        self.trading_client: bool | None = None  # Kept for backward compat

        # Initialize broker adapter (abstracted from Alpaca-specific implementation)
        import os

        try:
            self.broker: BrokerAdapter = AlpacaBrokerAdapter(config)
            self.audit_logger = TradeAuditLogger()
            self.trading_client = True  # Signals credentials are available
        except (KeyError, ValueError, AttributeError) as e:
            # Only use mock broker when EXPLICITLY in dry-run mode
            dry_run_enabled = os.getenv("ORCHESTRATOR_DRY_RUN", "").lower() in ("true", "1", "yes")
            has_alpaca_creds = bool(os.getenv("APCA_API_KEY_ID")) and bool(os.getenv("APCA_API_SECRET_KEY"))

            # CRITICAL: If NOT in explicit dry-run mode, initialization failure is fatal
            # This prevents silent fallback to mock $100k broker masking real credential issues
            if not dry_run_enabled:
                logger.critical(
                    f"[CRITICAL] Reconciliation broker adapter initialization failed "
                    f"{'(Alpaca credentials missing - production misconfiguration)' if not has_alpaca_creds else '(broker adapter failed to initialize)'}: {e}. "
                    "Reconciliation cannot proceed without live broker connection. "
                    "Set ORCHESTRATOR_DRY_RUN=true to enable dry-run testing mode."
                )
                try:
                    notify(
                        "critical",
                        title="Reconciliation Initialization Failed - Production Blocker",
                        message=f"Broker adapter failed to initialize: {e}. "
                        f"{'Alpaca credentials missing.' if not has_alpaca_creds else 'Broker initialization error.'} "
                        "Reconciliation requires live broker connection in production.",
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError):
                    logger.warning("Failed to send initialization failure notification")
                raise ValueError(
                    f"Reconciliation initialization failed (production mode): {e}. "
                    f"{'Alpaca credentials missing (APCA_API_KEY_ID, APCA_API_SECRET_KEY required).' if not has_alpaca_creds else 'Broker adapter initialization failed.'}"
                ) from e

            # Only reach here if explicitly in dry-run mode
            logger.warning(
                f"[DRY-RUN] Reconciliation broker adapter initialization failed: {e}. "
                "Using dry-run broker for testing only."
            )
            # Import test adapter from test utilities (signals test-only usage)
            from tests.test_utilities import DryRunBrokerAdapter

            self.broker = DryRunBrokerAdapter()
            self.audit_logger = TradeAuditLogger()
            self.trading_client = False  # Dry-run broker, no real credentials

    def run_daily_reconciliation(self, reconcile_date: Any = None, dry_run: bool = False) -> dict[str, Any]:
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

            # CRITICAL: Dry-run mode is incompatible with live reconciliation.
            # Fail immediately instead of returning mock data.
            import os

            env = os.getenv("ENVIRONMENT", "unknown").lower()
            logger.critical(
                f"[RECONCILIATION] Dry-run mode enabled (ORCHESTRATOR_DRY_RUN=true) in {env} environment. "
                "Reconciliation requires live broker connection and cannot proceed with dry-run adapter. "
                "Set ORCHESTRATOR_DRY_RUN=false to disable dry-run mode."
            )
            raise RuntimeError(
                "Dry-run mode incompatible with reconciliation. "
                "Cannot reconcile with mock broker adapter. "
                "Set ORCHESTRATOR_DRY_RUN=false to proceed."
            )

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

            # 1. Fetch broker account (required - no fallback to stale DB data)
            account_data = self._fetch_account()
            if not account_data:
                logger.critical("Broker account fetch failed - reconciliation cannot proceed without live account data")
                try:
                    notify(
                        "critical",
                        title="Reconciliation Halted",
                        message="Broker unavailable. Reconciliation requires live account data - cannot use stale DB cache.",
                    )
                except Exception as e:
                    logger.error(f"Failed to send critical notification (will still raise): {e}", exc_info=True)
                raise ValueError(
                    "Broker account data required for reconciliation - cannot proceed with DB-only fallback"
                )
            else:
                logger.info("1. Broker Account:")
                pv = account_data.get("portfolio_value")
                cash = account_data.get("cash")
                equity = account_data.get("equity")

                # Validate critical fields are present - fail immediately, not silently
                if pv is None:
                    logger.critical(
                        "Broker portfolio_value is missing - reconciliation cannot proceed without live portfolio value"
                    )
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Broker portfolio_value missing - reconciliation requires live portfolio value for drawdown limits. Cannot use stale DB cache.",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send critical notification (will still raise): {e}", exc_info=True)
                    raise ValueError("Broker portfolio_value required for reconciliation - cannot proceed")

                if cash is None:
                    logger.critical("Broker cash is missing - reconciliation cannot proceed without live cash value")
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Broker cash missing - reconciliation requires live cash value for position sizing. Cannot use stale DB cache.",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send critical notification (will still raise): {e}", exc_info=True)
                    raise ValueError("Broker cash required for reconciliation - cannot proceed")

                # CRITICAL: Validate cash is non-negative (indicates account in consistent state)
                if cash < 0:
                    logger.critical(f"Broker reported NEGATIVE cash: ${cash:,.2f} - account in corrupted state")
                    try:
                        notify(
                            "critical",
                            title="Account State Error",
                            message=f"Alpaca account reports negative cash (${cash:,.2f}). "
                            "Account may be in corrupted state. Halting trading until resolved.",
                        )
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        logger.warning(f"Failed to send notification: {e}")
                    raise ValueError(f"CRITICAL: Broker cash is negative (${cash:,.2f}) - account corrupted")

                logger.info(f"   Portfolio Value: ${pv:,.2f}")
                logger.info(f"   Cash: ${cash:,.2f}")
                logger.info(f"   Equity: ${equity:,.2f}" if equity is not None else "   Equity: UNAVAILABLE")

            with DatabaseContext("write") as cur:
                # 1b. Sync broker positions into our DB (imports any external positions)
                sync_result = self.sync_positions(cur)
                logger.info("\n1b. Position Sync:")
                logger.info(f"   {sync_result['message']}")
                if sync_result.get("orphan_symbols"):
                    logger.info(f"   Orphans flagged: {', '.join(sync_result['orphan_symbols'][:5])}")

                # 1b2. Reconcile actual fill prices with DB exit records
                fill_result = self.reconcile_exit_fills(cur, reconcile_date)
                logger.info("\n1b2. Exit Fill Reconciliation:")
                logger.info(f"   {fill_result['message']}")

                # 1b3. Check for trades pending Phase 7 price reconciliation
                pending_result = self.check_pending_reconciliations(cur)
                if "pending_count" not in pending_result:
                    raise RuntimeError("check_pending_reconciliations() returned dict without pending_count key")
                if pending_result["pending_count"] > 0:
                    logger.info("\n1b3. Pending Reconciliations:")
                    logger.info(f"   {pending_result['message']}")
                    from dashboard.data_validation import safe_int

                    if "stuck_count" not in pending_result:
                        raise RuntimeError(
                            "[RECONCILIATION_DATA_QUALITY] pending_count > 0 but stuck_count key missing from result. "
                            "check_pending_reconciliations() returned incomplete data. "
                            f"Available keys: {list(pending_result.keys())}"
                        )
                    stuck_count = safe_int(pending_result.get("stuck_count"), default=None)
                    if stuck_count is None:
                        raise ValueError(
                            "[RECONCILIATION_DATA_QUALITY] stuck_count present but value is not a valid integer. "
                            f"Cannot parse stuck trade count. Got: {pending_result.get('stuck_count')!r}"
                        )
                    if stuck_count > 0:
                        pending_list = pending_result.get("pending")
                        if pending_list is None:
                            raise RuntimeError(
                                "check_pending_reconciliations() reported stuck_count > 0 but pending list is missing. "
                                "Cannot report stuck trade details (incomplete status report)."
                            )
                        for p in pending_list[:5]:
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

                # Analyze positions using PositionAnalyzer service
                analysis = PositionAnalyzer.analyze_positions(positions)
                PositionAnalyzer.log_position_analysis(analysis, logger)

                total_position_value = analysis["total_position_value"]
                unrealized_pnl = analysis["unrealized_pnl"]
                positions_with_prices = analysis["positions_with_prices"]
                unrealized_pnl_winning_count = analysis["winning_count"]
                unrealized_pnl_losing_count = analysis["losing_count"]
                unrealized_pnl_breakeven_count = analysis["breakeven_count"]

                # 3. Calculate metrics
                # Values already validated at initial broker fetch; keep as Decimal for precision
                # Use broker's authoritative portfolio_value for the snapshot (includes live prices).
                # Our DB position_value sum may lag - Broker is the ground truth for drawdown math.
                from decimal import Decimal

                cash_dec = Decimal(str(cash))
                alpaca_portfolio_value_dec = Decimal(str(pv))
                if alpaca_portfolio_value_dec <= 0:
                    logger.critical(
                        "Broker portfolio_value is zero/negative - cannot proceed with drawdown calculations. Halting."
                    )
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Broker portfolio_value zero/negative - reconciliation requires positive portfolio value. Cannot use stale DB cache.",
                        )
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        logger.warning(f"Failed to send notification: {e}")
                    raise ValueError("Broker portfolio_value must be positive for reconciliation - cannot proceed")

                # DB-computed total (kept for drift reporting)
                from decimal import Decimal

                total_equity_db_dec = cash_dec + total_position_value
                # Always use Alpaca's live value (never fall back to stale DB cache)
                total_equity_dec = alpaca_portfolio_value_dec

                if total_equity_db_dec > 0:
                    drift_pct = ((alpaca_portfolio_value_dec - total_equity_db_dec) / total_equity_db_dec) * Decimal(
                        100
                    )
                    if abs(drift_pct) > Decimal("1.0"):
                        logger.warning(
                            f"Position value drift: Alpaca ${float(alpaca_portfolio_value_dec):,.2f} vs DB-computed ${float(total_equity_db_dec):,.2f} ({float(drift_pct):+.1f}%)"
                        )

                if total_equity_dec > 0:
                    unrealized_pnl_pct_dec = (unrealized_pnl / total_equity_dec) * Decimal(100)
                else:
                    unrealized_pnl_pct_dec = Decimal(0)

                position_values = [p[4] for p in positions if p[4] is not None]
                if len(position_values) < len(positions):
                    excluded_count = len(positions) - len(position_values)
                    logger.critical(
                        f"CRITICAL: {excluded_count}/{len(positions)} positions have NULL position_value in reconciliation"
                    )
                    raise ValueError(
                        f"CRITICAL: {excluded_count}/{len(positions)} positions have NULL position_value in reconciliation. "
                        f"Cannot calculate concentration risk without complete position data."
                    )
                if not position_values:
                    raise ValueError(
                        "[RECONCILIATION CRITICAL] No valid position values found after filtering NULLs. "
                        "Cannot calculate concentration risk without position data. Portfolio has no open positions."
                    )
                largest_position_dec = Decimal(str(max(position_values)))
                if total_equity_dec <= 0:
                    logger.critical(
                        f"CRITICAL: Total equity invalid ({total_equity_dec}) for concentration calculation"
                    )
                    raise ValueError(
                        f"CRITICAL: Total equity invalid ({total_equity_dec}) — cannot calculate concentration"
                    )
                max_concentration_dec = largest_position_dec / total_equity_dec * Decimal(100)

                if not positions or len(positions) == 0:
                    raise ValueError(
                        "[RECONCILIATION CRITICAL] Positions list is empty. "
                        "Cannot calculate average position size without open positions."
                    )
                if total_position_value <= 0:
                    raise ValueError(
                        "[RECONCILIATION CRITICAL] Total position value is invalid or zero. "
                        "Cannot calculate average position size with invalid portfolio value."
                    )
                avg_position_size_dec = total_position_value / len(positions)

                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)

                from decimal import Decimal

                prev_snapshot = cur.fetchone()
                prev_value_dec = Decimal(str(prev_snapshot[0])) if prev_snapshot else total_equity_dec
                daily_return_dec = total_equity_dec - prev_value_dec
                if prev_value_dec <= 0:
                    logger.critical(
                        f"CRITICAL: Prior portfolio snapshot value invalid ({prev_value_dec}) — cannot calculate daily return. "
                        f"Check portfolio snapshot data continuity."
                    )
                    raise ValueError(
                        f"Prior portfolio value invalid ({prev_value_dec}) — daily return calculation requires valid historical snapshot"
                    )
                daily_return_pct_dec = daily_return_dec / prev_value_dec * Decimal(100)

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

                # Calculate additional metrics (no COALESCE — catch missing data explicitly)
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                        COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                        SUM(profit_loss_dollars) FILTER (WHERE DATE(exit_date) = %s::date) as realized_pnl_today,
                        SUM(profit_loss_dollars) as cumulative_pnl,
                        COUNT(*) FILTER (WHERE profit_loss_dollars IS NULL) as null_pnl_count
                    FROM algo_trades
                    WHERE status = %s
                """,
                    (str(reconcile_date), "closed"),
                )
                result = cur.fetchone()
                if result is None:
                    raise ValueError("No trades data returned from database")
                win_count = result[0]
                loss_count = result[1]
                realized_pnl_today = result[2]
                cumulative_pnl = result[3]
                null_pnl_count = result[4]

                # Log but don't fail if some trades have missing PnL
                # (incomplete test trades or partial exits can have missing P&L calculations)
                if null_pnl_count and null_pnl_count > 0:
                    logger.warning(
                        f"WARN: {null_pnl_count} closed trades have NULL profit_loss_dollars. "
                        "Using P&L from trades with complete exit data. Check trade execution audit log for details."
                    )

                # Validate counts (null if no matching rows)
                if win_count is None or loss_count is None:
                    raise ValueError(f"Trade counts missing from database: wins={win_count}, losses={loss_count}")

                # Validate PnL values (null if no closed trades or all NULL)
                if realized_pnl_today is None or cumulative_pnl is None:
                    raise ValueError(
                        f"PnL values missing from database: today={realized_pnl_today}, cumulative={cumulative_pnl}"
                    )
                win_count = int(win_count)
                loss_count = int(loss_count)
                realized_pnl_today = float(realized_pnl_today)
                cumulative_pnl = float(cumulative_pnl)

                # Get cumulative return (normalize to actual initial capital from Alpaca account history)
                try:
                    initial_capital = self._fetch_initial_capital(cur)
                    if initial_capital <= 0:
                        raise ValueError(
                            f"CRITICAL: Invalid initial_capital={initial_capital} - cannot calculate cumulative return. "
                            "Check Alpaca account initialization and capital history."
                        )
                    cumulative_return_pct = cumulative_pnl / initial_capital * 100
                    logger.info(
                        f"   Cumulative Return: {cumulative_return_pct:+.2f}% (on initial capital ${initial_capital:,.2f})"
                    )
                except ValueError as e:
                    logger.error(f"CRITICAL: {e} - cannot calculate cumulative return")
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
                            float(
                                (avg_position_size_dec / total_equity_dec * Decimal(100))
                                if total_equity_dec > 0
                                else Decimal(0)
                            ),
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

            # Audit log portfolio snapshot for traceability
            self.audit_logger.log_portfolio_snapshot_audit(
                snapshot_date=reconcile_date,
                total_portfolio_value=float(total_equity_dec),
                total_cash=float(cash_dec),
                position_count=positions_with_prices,
                unrealized_pnl_total=float(unrealized_pnl),
                unrealized_pnl_pct=float(unrealized_pnl_pct_dec),
            )

            logger.info("\n3. Portfolio Summary:")
            logger.info(f"   Total Value: ${float(total_equity_dec):,.2f}")
            logger.info(f"   Position Value: ${float(total_position_value):,.2f}")
            logger.info(f"   Cash: ${float(cash_dec):,.2f}")
            logger.info(
                f"   Unrealized P&L (OPEN POSITIONS ONLY): {float(unrealized_pnl):+,.2f} ({float(unrealized_pnl_pct_dec):+.2f}%)"
            )
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

        except (
            ValueError,
            RuntimeError,
            requests.RequestException,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            NotImplementedError,
        ) as e:
            logger.error(f"Error in reconciliation: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def reconcile_exit_fills(self, cur: Any, reconcile_date: Any) -> dict[str, Any]:
        """Update DB trade exit prices with actual Alpaca fill prices.

        Phase 4 marks trades 'closed' immediately using the last known market price
        when placing market exit orders before market open. This reconciles those
        estimated prices with actual Alpaca fill prices after market opens.
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(days=2)
            orders = self.broker.fetch_closed_orders(since=since)
            if not orders:
                logger.debug("No closed orders found for exit fill reconciliation")
                return {"updated": 0, "message": "No closed orders to reconcile"}

            updated = 0
            two_days_ago = reconcile_date - timedelta(days=2)

            for order in orders:
                if order.get("status") != "filled" or order.get("side") != "sell":
                    continue
                symbol = order.get("symbol")
                filled_price_str = order.get("filled_avg_price")
                if not symbol or not filled_price_str:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled sell order missing symbol or filled_price: {order}"
                    )
                try:
                    filled_price = float(filled_price_str)
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled price not numeric '{filled_price_str}' for {symbol}"
                    ) from e
                if filled_price <= 0:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled price invalid {filled_price} for {symbol} - must be > 0"
                    )

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
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] No closed trade found for {symbol} within 2 days - cannot reconcile fill"
                        )

                    trade_id, entry_price, stop_loss_price, entry_qty = row
                    if entry_price is None or stop_loss_price is None or entry_qty is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) missing entry_price, stop_loss_price, or entry_qty - cannot reconcile"
                        )

                    try:
                        entry_price = float(entry_price)
                        stop_loss_price = float(stop_loss_price)
                        entry_qty = int(entry_qty)
                    except (ValueError, TypeError) as e:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has non-numeric price/qty - cannot reconcile"
                        ) from e

                    if entry_price <= 0 or stop_loss_price <= 0 or entry_qty <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid prices/qty (entry={entry_price}, stop={stop_loss_price}, qty={entry_qty}) - must be > 0"
                        )

                    filled_dec = Decimal(str(filled_price))
                    entry_dec = Decimal(str(entry_price))
                    qty_dec = Decimal(str(entry_qty))
                    pnl_pct = float(
                        ((filled_dec - entry_dec) / entry_dec * Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    )
                    pnl_dollars = float(((filled_dec - entry_dec) * qty_dec).quantize(Decimal("0.01"), ROUND_HALF_UP))
                    risk = entry_price - stop_loss_price
                    if risk <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid risk={risk}: "
                            f"stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). "
                            f"Cannot compute R-multiple with invalid stop price."
                        )
                    exit_r_multiple = float(
                        ((filled_dec - entry_dec) / Decimal(str(risk))).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    )

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
                        if filled_price is None or filled_price <= 0:
                            logger.warning(
                                f"[RECONCILIATION] Cannot calculate variance for {trade_id}: "
                                f"filled_price={filled_price} is not positive. Skipping variance calculation."
                            )
                        else:
                            variance_pct = (filled_price - estimated_price) / estimated_price * 100.0
                            reconciliation_note = f"Actual: ${filled_price:.2f} vs Estimated: ${estimated_price:.2f} ({variance_pct:+.2f}%)"

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
        except (
            ValueError,
            requests.RequestException,
            json.JSONDecodeError,
            psycopg2.DatabaseError,
        ) as e:
            logger.warning(f"Exit fill reconciliation error: {e}")
            return {"updated": 0, "message": f"Error: {e}"}

    def audit_stale_estimated_prices(self, cur: Any) -> dict[str, Any]:
        """Audit for trades with estimated exit prices.

        Returns dict with audit results. If not implemented, returns dict with
        implementation_required flag and detailed requirements.
        """
        return {
            "implementation_required": True,
            "audit_type": "stale_price_audit",
            "message": (
                "[STALE_PRICE_AUDIT] NOT IMPLEMENTED: audit_stale_estimated_prices() requires implementation. "
                "Price staleness auditing is CRITICAL for position reconciliation accuracy. "
                "Cannot reconcile positions with stale or estimated prices — this can cause "
                "incorrect profit/loss calculations and risk miscalculation. "
            ),
            "requirements": [
                "(1) Find trades with estimated exit prices in algo_trades table",
                "(2) Check exit_price_reconciled_at timestamp against current time",
                "(3) Alert on stale prices (estimated prices older than 2 hours)",
                "(4) Raise RuntimeError to halt reconciliation when stale data detected",
                "(5) Return results with stale_trade_count and alert_status",
            ],
        }

    def sync_positions(self, cur: Any) -> dict[str, Any]:
        """Sync broker positions via BrokerAdapter."""
        return self.broker.sync_positions(cur)

    def _process_failed_imports(self, cur: Any, alpaca_positions: list[Any]) -> int:
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
        skipped_count = 0
        skip_reasons = []
        for sym in retryable:
            ap = alpaca_map[sym]
            try:
                qty_raw = getattr(ap, "qty", None)
                if qty_raw is None or qty_raw == 0:
                    skip_reasons.append(f"{sym}: qty missing/zero")
                    skipped_count += 1
                    continue
                qty = float(qty_raw)
                avg_entry_raw = getattr(ap, "avg_entry_price", None)
                if avg_entry_raw is None or float(avg_entry_raw) <= 0:
                    skip_reasons.append(f"{sym}: avg_entry_price missing/invalid")
                    skipped_count += 1
                    continue
                avg_entry = float(avg_entry_raw)
                cur_price_raw = getattr(ap, "current_price", None)
                if cur_price_raw is None or float(cur_price_raw) <= 0:
                    skip_reasons.append(f"{sym}: current_price missing/invalid")
                    skipped_count += 1
                    continue
                cur_price = float(cur_price_raw)
                pos_value_raw = getattr(ap, "market_value", None)
                if pos_value_raw is None:
                    skip_reasons.append(f"{sym}: market_value missing")
                    skipped_count += 1
                    continue
                try:
                    pos_value = float(pos_value_raw)
                except (ValueError, TypeError):
                    skip_reasons.append(f"{sym}: market_value not numeric")
                    skipped_count += 1
                    continue
                if pos_value <= 0:
                    skip_reasons.append(f"{sym}: market_value <= 0")
                    skipped_count += 1
                    continue
                pnl_raw = getattr(ap, "unrealized_pl", None)
                pnl_pct_raw = getattr(ap, "unrealized_plpc", None)
                if pnl_raw is None or pnl_pct_raw is None:
                    skip_reasons.append(f"{sym}: PnL fields missing (pnl={pnl_raw}, pnl_pct={pnl_pct_raw})")
                    skipped_count += 1
                    continue
                try:
                    pnl = float(pnl_raw)
                    pnl_pct = float(pnl_pct_raw) * 100
                except (ValueError, TypeError) as e:
                    skip_reasons.append(f"{sym}: PnL not numeric ({e})")
                    skipped_count += 1
                    continue
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

                    # CRITICAL: Fail hard if ATR calculation failed - cannot import positions without risk limits
                    if stop_loss_price_retry is None:
                        cur.execute("RELEASE SAVEPOINT retry_sp")
                        raise RuntimeError(
                            f"[RECONCILIATION CRITICAL] Cannot import {sym}: ATR-based risk limits failed. "
                            f"Stop-loss price cannot be calculated. Cannot import positions without validated "
                            f"stop-loss calculations (risk management failure). "
                            f"Check technical_data_daily table for {sym} ATR data and retry."
                        )

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

                    cur.execute("RELEASE SAVEPOINT retry_sp")
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

        # CRITICAL: If any positions were skipped due to missing financial data, halt reconciliation
        # Do not silently accumulate orphaned positions — portfolio reconciliation depends on completeness
        if skipped_count > 0:
            raise RuntimeError(
                f"[RECONCILIATION CRITICAL] Cannot retry position imports — {skipped_count} positions "
                f"have missing critical financial data (qty, prices, PnL). Cannot reconcile portfolio "
                f"with incomplete position data. Failed symbols: {skip_reasons[:5]}. "
                f"Reconciliation halted to prevent orphaned positions. "
                f"Check Alpaca data completeness and retry."
            )

        # Issue #11: Log skip summary for audit trail
        logger.info(
            f"[RECONCILIATION] Retry import: {retried} succeeded, {skipped_count} skipped. "
            f"Skips: {skip_reasons[:10]}"  # First 10 skip reasons
        )
        cur.execute(
            "SELECT COUNT(DISTINCT symbol) FROM alpaca_import_failures "
            "WHERE resolved = FALSE AND failed_at > NOW() - INTERVAL '1 day'"
        )
        failure_row = cur.fetchone()
        if failure_row is None:
            raise RuntimeError("Query for alpaca import failures returned None — database error or connection lost")
        failure_count = failure_row[0]
        if failure_count > 5:
            try:
                notify(
                    severity="warning",
                    title=f"Alpaca Import Failures ({failure_count})",
                    message=">5 failed imports in last 24h. Positions may be orphaned.",
                    details={"failure_count": failure_count},
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as alert_e:
                # CRITICAL: Fail fast when alert system is down — operators must be notified of import failures
                raise RuntimeError(
                    f"[RECONCILIATION ALERT CRITICAL] Failed to notify operators of {failure_count} "
                    f"position import failures: {alert_e}. Operator awareness is critical for orphaned "
                    f"position detection. Cannot proceed without alert system. Check notification service."
                ) from alert_e
        try:
            cur.execute(
                "DELETE FROM alpaca_import_failures WHERE resolved = TRUE AND resolved_at < NOW() - INTERVAL '7 days'"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            # CRITICAL: If cleanup fails, database may grow unbounded with stale failure records
            raise RuntimeError(
                f"[RECONCILIATION CLEANUP CRITICAL] Failed to clean old failure records from database: {e}. "
                f"Database may grow unbounded. Cleanup is required for data integrity. "
                f"Check database connection and retry."
            ) from e
        return retried

    def compute_analytics_metrics(self, cur: Any) -> dict[str, Any]:
        """Compute analytics metrics (Information Coefficient, expectancy, Sharpe ratio).

        Returns dict with analytics results. If not implemented, returns dict with
        valid=False flags and implementation requirements.
        """
        return {
            "ic": {
                "valid": False,
                "data_unavailable": True,
                "implementation_required": True,
                "ic": None,
                "trade_count": None,
                "alert": (
                    "[ANALYTICS_METRICS] NOT IMPLEMENTED: compute_analytics_metrics() requires implementation. "
                    "Information Coefficient (IC) computation is REQUIRED for "
                    "performance dashboard and algorithmic monitoring. Cannot assess strategy edge without actual metrics."
                ),
            },
            "expectancy": {
                "valid": False,
                "data_unavailable": True,
                "implementation_required": True,
                "expectancy": None,
                "win_rate": None,
                "kelly_fraction": None,
                "alert": (
                    "Expectancy computation is CRITICAL for position sizing and risk management. "
                    "Implement analytics that compute: "
                    "(1) Information Coefficient (price prediction accuracy vs market), "
                    "(2) Expectancy (expected return per trade), "
                    "(3) Win rate (winning trades / total closed trades), "
                    "(4) Kelly Fraction (optimal position sizing), "
                    "(5) Sharpe ratio (risk-adjusted returns) — all required for dashboard."
                ),
            },
        }

    def compute_closed_trade_metrics(self, cur: Any) -> dict[str, Any]:
        """Compute closed trade metrics (win rate, R-multiples, profit factor).

        Returns dict with closed trade metrics. If not implemented, returns dict with
        valid=False flag and implementation requirements.
        """
        return {
            "valid": False,
            "data_unavailable": True,
            "implementation_required": True,
            "reason": (
                "[CLOSED_TRADE_METRICS] NOT IMPLEMENTED: compute_closed_trade_metrics() requires implementation. "
                "Closed trade analysis (win rate, R-multiples, profit factor) is REQUIRED for "
                "algorithmic performance evaluation and risk analysis. Cannot assess edge without actual closed trade metrics. "
                "Implement metrics that compute: "
                "(1) Win rate (winning trades / total closed trades), "
                "(2) Profit factor (gross profit / gross loss, must be > 1.0 for profitability), "
                "(3) Average R-multiple (average trade profit / initial risk, expected value), "
                "(4) Best and worst trade (max gain, max loss), "
                "(5) Consecutive win/loss streaks (longest win/loss sequence). "
                "All metrics required for dashboard monitoring and edge analysis."
            ),
            "win_rate": None,
            "profit_factor": None,
            "avg_r_multiple": None,
            "best_trade": None,
            "worst_trade": None,
            "max_consecutive_wins": None,
            "max_consecutive_losses": None,
        }

    def check_partial_fills(self, cur: Any) -> dict[str, Any]:
        """Check for partial fills that haven't been reconciled with Alpaca.

        Detects when orders were only partially filled but the local DB thinks
        they're fully filled. This catches the case when Alpaca fills part of an
        order and then network fails before we can sync.

        Returns: dict with reconciliation status and any detected drift
        """
        try:
            orders = self.broker.fetch_closed_orders()
            if not orders:
                logger.debug("No closed orders found for partial fill check")
                return {"mismatches": 0, "message": "No closed orders to check"}

            # Check each order against our DB records
            mismatches = []
            for order in orders:
                if "symbol" not in order or "filled_qty" not in order or "status" not in order:
                    # CRITICAL: Alpaca API contract violation — cannot reconcile fill status without required fields
                    raise RuntimeError(
                        f"[PARTIAL_FILL_CHECK CRITICAL] Alpaca API returned malformed order (missing required fields). "
                        f"Cannot reconcile fills: {order}. Partial fill detection disabled. "
                        f"API contract violated — check Alpaca API response structure."
                    )
                symbol = order["symbol"]
                alpaca_filled_qty = float(order["filled_qty"])
                order_status = order["status"]

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

                # Validate quantity data integrity
                if db_qty is None:
                    logger.error(
                        f"[RECONCILIATION] Database quantity NULL for {symbol} (trade_id {db_trade_id}). "
                        f"Cannot reconcile fill without known position size. Manual intervention required."
                    )
                    continue

                # Check for mismatch
                db_qty_int = int(db_qty)
                alpaca_filled_int = int(alpaca_filled_qty)

                if alpaca_filled_int > 0 and db_qty_int != alpaca_filled_int:
                    # Quantity drift detected - Alpaca has different fill than DB
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
                        # CRITICAL: Fail fast when alert system is down — partial fill corrections must be audited
                        raise RuntimeError(
                            f"[PARTIAL_FILL_ALERT CRITICAL] Failed to notify operator of fill correction "
                            f"for {symbol}: {e}. Partial fill notification is required for audit trail. "
                            f"Cannot proceed without operator awareness. Check notification service."
                        ) from e

            return {
                "checked": len(orders),
                "mismatches": len(mismatches),
                "message": f"Checked {len(orders)} orders; corrected {len(mismatches)} partial fills",
                "details": mismatches,
            }

        except (
            ValueError,
            requests.RequestException,
            json.JSONDecodeError,
            psycopg2.DatabaseError,
        ) as e:
            # CRITICAL: Partial fill detection failure — cannot reconcile fill status
            raise RuntimeError(
                f"[PARTIAL_FILL_CHECK FAILED] {type(e).__name__}: {e}. "
                f"Cannot reconcile fill status — algorithm cannot proceed without fill validation. "
                f"Partial fills undetected could lead to position quantity mismatches. Check broker connection."
            ) from e

    def check_pending_reconciliations(self, cur: Any) -> dict[str, Any]:
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
                        "estimated_price": float(est_price) if est_price is not None else None,
                        "current_exit_price": float(exit_price) if exit_price is not None else None,
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
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to check pending reconciliations: {e}", exc_info=True)
            raise RuntimeError(
                f"[RECONCILIATION] Cannot check pending reconciliations due to data error: {e}. "
                f"Position reconciliation is critical for accurate portfolio reporting. "
                f"Reconciliation check must fail explicitly rather than return incomplete data."
            ) from e
        except ZeroDivisionError as e:
            logger.error(f"[RECONCILIATION] Division by zero in pending reconciliation check: {e}", exc_info=True)
            raise RuntimeError(
                "[RECONCILIATION] Variance calculation failed with division by zero. "
                "This indicates missing or invalid price data in pending trade reconciliations. "
                "Check database consistency and retry."
            ) from e

    def _fetch_account(self) -> Any:
        """Fetch account data from broker via BrokerAdapter."""
        return self.broker.fetch_account()

    def _fetch_initial_capital(self, cur: Any) -> float:
        """Get the actual initial capital from broker account history (fail-fast).

        CRITICAL: Does NOT fall back to stale database snapshots. Initial capital is
        required for accurate cumulative return calculation. Stale data (days/months old)
        would severely distort P&L metrics and mask performance issues.

        Raises ValueError if broker history unavailable — reconciliation must fail fast
        rather than use potentially months-old snapshot data.
        """
        try:
            initial_val = self.broker.fetch_initial_capital()
            if initial_val and initial_val > 0:
                logger.info(f"Initial capital from broker history: ${initial_val:,.2f}")
                return initial_val
        except Exception as e:
            raise ValueError(
                f"CRITICAL: Cannot fetch initial capital from Alpaca broker history: {e}. "
                "Initial capital is required for accurate cumulative return calculation. "
                "Check: (1) Is Alpaca API reachable? (2) Does account have portfolio history? "
                "(3) Are credentials valid? Reconciliation halts without live broker data "
                "(stale database snapshots would corrupt P&L metrics)."
            ) from e

        raise ValueError(
            "CRITICAL: Broker returned no portfolio history. "
            "Initial capital cannot be determined from Alpaca. "
            "Reconciliation requires live broker history for accurate P&L — cannot proceed."
        )

    def validate_pnl(self, broker_equity: float, local_equity: float) -> dict[str, Any]:
        """Validate that local P&L matches Alpaca P&L within tolerance.

        Args:
            broker_equity: Equity reported by Alpaca
            local_equity: Equity calculated from local positions and cash

        Returns:
            Dict with validation results: {
                'valid': bool,
                'broker_equity': float,
                'local_equity': float,
                'variance_pct': float,
                'variance_dollars': float,
                'status': 'ok'|'alert'|'critical',
                'message': str
            }
        """
        if broker_equity is None or local_equity is None:
            return {
                "valid": False,
                "broker_equity": broker_equity,
                "local_equity": local_equity,
                "variance_pct": None,
                "variance_dollars": None,
                "status": "error",
                "message": "Cannot validate P&L: missing Alpaca or local equity data",
            }

        if broker_equity <= 0 or local_equity <= 0:
            return {
                "valid": False,
                "broker_equity": broker_equity,
                "local_equity": local_equity,
                "variance_pct": None,
                "variance_dollars": None,
                "status": "error",
                "message": "Cannot validate P&L: equity values must be positive",
            }

        variance_dollars = broker_equity - local_equity
        if broker_equity <= 0:
            raise ValueError("CRITICAL: Broker equity must be positive for variance calculation")
        variance_pct = (variance_dollars / broker_equity) * 100.0

        threshold = 0.1  # 0.1% tolerance

        if abs(variance_pct) <= threshold:
            status = "ok"
            message = f"P&L validated: Alpaca ${broker_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%)"
            valid = True
        elif abs(variance_pct) <= 1.0:
            status = "alert"
            message = f"P&L variance ALERT: Alpaca ${broker_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%, ${variance_dollars:+,.2f})"
            valid = False
        else:
            status = "critical"
            message = f"P&L MISMATCH CRITICAL: Alpaca ${broker_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%, ${variance_dollars:+,.2f}) - verify position prices and trade exit prices"
            valid = False

        return {
            "valid": valid,
            "broker_equity": broker_equity,
            "local_equity": local_equity,
            "variance_pct": variance_pct,
            "variance_dollars": variance_dollars,
            "status": status,
            "message": message,
        }


if __name__ == "__main__":
    from algo.infrastructure import get_config

    config = get_config()
    reconciliation = DailyReconciliation(cast(dict[str, Any], config))

    result = reconciliation.run_daily_reconciliation()
    logger.info(f"Result: {result}")
