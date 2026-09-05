#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import math
from datetime import date as _date_type
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import psycopg2
import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
from algo.infrastructure.audit_logger import TradeAuditLogger
from algo.infrastructure.broker_adapter import BrokerAdapter
from algo.infrastructure.reconciliation_broker_positions import BrokerPositionSyncMixin
from algo.infrastructure.reconciliation_broker_snapshot import BrokerSnapshotMixin
from algo.infrastructure.reconciliation_paper_mode import PaperModeReconciliationMixin
from algo.infrastructure.reconciliation_shared import compute_adjusted_drawdown
from algo.reporting import notify
from utils.db import DatabaseContext
from utils.trade_metrics import backfill_all_trade_metrics
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)

# Re-exported for backward compatibility - tests/unit/test_capital_flow_adjusted_drawdown.py
# and other call sites import these by these names from this module. The implementations
# now live in reconciliation_shared.py so reconciliation_paper_mode.py and
# reconciliation_broker_snapshot.py can both use them without an import cycle back here.
_compute_adjusted_drawdown = compute_adjusted_drawdown


class DailyReconciliation(PaperModeReconciliationMixin, BrokerPositionSyncMixin, BrokerSnapshotMixin):
    """Daily reconciliation and portfolio snapshot creation.

    Uses broker adapter for position sync, analytics, and price auditing.

    Split via pure extract-method refactor (2026-09-05) across three mixins:
    PaperModeReconciliationMixin (reconciliation_paper_mode.py, the self.broker is None /
    LOCAL_MODE DB-only fallback), BrokerPositionSyncMixin (reconciliation_broker_positions.py,
    broker position sync + open-position analysis), and BrokerSnapshotMixin
    (reconciliation_broker_snapshot.py, concentration/drawdown/return metrics + the
    portfolio-snapshot INSERT). run_daily_reconciliation() itself keeps the top-level control
    flow (dry_run gate, broker-account fetch/validation, cash-vs-execution-mode branching) and
    a handful of literal call sites/conditions several regression tests scan for by source
    text - see that method's own docstring for which lines must stay there.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config: dict[str, Any] = config
        self.trading_client: bool | None = None  # Kept for backward compat
        self.broker: BrokerAdapter | None = None  # Allow None for paper trading without credentials

        # Initialize broker adapter (abstracted from Alpaca-specific implementation)

        # CRITICAL: execution_mode governs whether entry execution actually sends orders to
        # Alpaca. executor.py's _submit_and_validate_order() only calls the Alpaca order API
        # for execution_mode == "auto" - "paper"/"dry"/"review" all create LOCAL-only fake
        # fills (alpaca_order_id="LOCAL-{trade_id}") that Alpaca never sees. Reconciliation
        # previously decided whether to trust the broker purely on whether credentials were
        # present/valid at that moment, so whenever Alpaca happened to be reachable it treated
        # the REAL Alpaca account - a completely different, unrelated position/equity history -
        # as ground truth for these LOCAL-only positions, and sync_positions() closed them out
        # (they're correctly "not found" at the broker, since they were never sent there),
        # fabricating near-zero P&L that corrupted portfolio_value/drawdown. Whether Alpaca is
        # reachable must not change reconciliation's source of truth for a mode that never
        # talks to it - gate on execution_mode, not on credential/API availability.
        execution_mode = config.get("execution_mode")
        if execution_mode is None:
            raise ValueError(
                "[RECONCILIATION INIT] Config missing required 'execution_mode' key. "
                "Trading mode must be explicitly set. Check algo_config table has execution_mode row."
            )
        if execution_mode != "auto":
            logger.warning(
                f"[RECONCILIATION] execution_mode={execution_mode!r} does not submit orders to Alpaca "
                "(only 'auto' does). Reconciliation will use database-only state regardless of "
                "Alpaca credential/API availability, so it never treats the unrelated real broker "
                "account as ground truth for locally-simulated positions."
            )
            self.broker = None
            self.trading_client = False
            return

        try:
            self.broker = AlpacaBrokerAdapter(config)
            self.audit_logger = TradeAuditLogger()
            self.trading_client = True  # Signals credentials are available
        except (KeyError, ValueError, AttributeError) as e:
            # CRITICAL FIX: Reconciliation MUST validate position state against broker
            # even in paper mode. Without broker verification, we cannot detect:
            # - Positions that failed to execute (never sent to broker)
            # - Orphaned positions at broker not in our database
            # - Fill price/quantity mismatches that corrupt P&L calculations
            # Skipping reconciliation in ANY mode corrupts portfolio_value and drawdown metrics
            # that circuit_breaker and daily loss checks depend on for position management.
            #
            # FAIL-FAST: If broker initialization fails, halt and surface the error.
            # Do not fall back to fabricated portfolio_value (DB-only reconstruction outside
            # LOCAL_MODE corrupts equity curve used by live circuit breaker checks).
            is_paper_trading = config.get("alpaca_paper_trading")
            if is_paper_trading is None:
                raise ValueError(
                    "[RECONCILIATION INIT] Config missing required 'alpaca_paper_trading' key. "
                    "Trading mode must be explicitly set. "
                    "Check: (1) algo_config table has alpaca_paper_trading row, "
                    "(2) AlgoConfig.get() returns complete config dict"
                ) from e

            # All modes require reconciliation - credentials are mandatory
            logger.critical(
                f"[CRITICAL] Reconciliation broker adapter initialization failed: {e}. "
                "Reconciliation requires Alpaca credentials to verify position state. "
                "Set APCA_API_KEY_ID and APCA_API_SECRET_KEY environment variables. "
                "Halt to prevent incorrect portfolio calculations that would corrupt risk management."
            )
            raise ValueError(
                f"Reconciliation initialization failed: {e}. "
                f"Alpaca credentials required for position verification in all trading modes."
            ) from e

    def run_daily_reconciliation(
        self, reconcile_date: _date_type | None = None, dry_run: bool = False
    ) -> dict[str, Any]:
        """Run full daily reconciliation. If dry_run=True, skip Alpaca API calls and return mock data.

        CRITICAL SAFETY: dry_run mode must be explicitly enabled via ORCHESTRATOR_DRY_RUN environment variable
        to prevent accidental trading with mock portfolio values if the flag is misconfigured.

        PAPER TRADING: If broker is None (credentials missing but paper trading enabled),
        return success with no positions to allow orchestrator to continue with signal generation.
        """
        # If broker not available (credentials missing for paper trading), use database state.
        # This DB-only fallback fabricates a portfolio_value from config + open positions, which is
        # only safe as a local-dev convenience when there's no broker to compare against. Persisting
        # it to algo_portfolio_snapshots outside LOCAL_MODE corrupts the historical equity curve that
        # circuit_breaker.py's drawdown/weekly-loss checks read live from this same table (see
        # migration 1112) -- so outside LOCAL_MODE this must fail closed instead, matching the
        # no-DB-only-fallback rule already enforced below for _fetch_account() returning None.
        if self.broker is None:
            import os

            if os.getenv("LOCAL_MODE") != "true":
                logger.critical(
                    "[RECONCILIATION] Broker unavailable (no Alpaca credentials) outside LOCAL_MODE. "
                    "Refusing to fabricate a portfolio snapshot from initial_capital_paper_trading + "
                    "DB positions -- this would silently corrupt algo_portfolio_snapshots with a fake "
                    "equity value that circuit breaker checks later treat as real broker truth."
                )
                try:
                    notify(
                        "critical",
                        title="Reconciliation Halted",
                        message="Broker credentials unavailable outside LOCAL_MODE - reconciliation "
                        "requires live account data and cannot fall back to a fabricated DB-only value.",
                    )
                except Exception as e:
                    logger.error(f"Failed to send critical notification (will still raise): {e}", exc_info=True)
                raise ValueError(
                    "Broker credentials unavailable outside LOCAL_MODE - cannot fabricate a portfolio "
                    "snapshot. Set APCA_API_KEY_ID/APCA_API_SECRET_KEY, or run with LOCAL_MODE=true for "
                    "the dev-only DB fallback."
                )

            logger.warning(
                "[RECONCILIATION] Broker not available - using database portfolio state (paper trading mode). "
                "Orchestrator will continue with signal generation and exit execution."
            )

            # Resolve any trades stuck NULL/pending broker-fill reconciliation using real EOD
            # price_daily data - see resolve_local_pending_exits() docstring. Must run before the
            # realized-P&L read below so a newly-resolved trade counts in this same run.
            with DatabaseContext("write") as resolve_cur:
                resolve_result = self.resolve_local_pending_exits(resolve_cur)
                if resolve_result["resolved"] > 0:
                    logger.info(f"[RECONCILIATION] {resolve_result['message']}")

                # BUG FOUND 2026-08-24 (goal session): backfill_all_trade_metrics() (MFE/MAE/
                # R-multiple/duration) was wired into run_daily_reconciliation() by an earlier
                # fix this same day (see mfe_mae_never_computed_wired_into_reconciliation_20260824
                # in memory) - but only into the execution_mode=="auto" branch further down this
                # method, past the `if self.broker is None: ... return result` this whole branch
                # ends with. Every paper/dry/local-mode run (which is 100% of what local dev, and
                # this system's entire pre-live-money verification phase, actually executes) took
                # THIS branch and returned before ever reaching that call - so mfe_pct/mae_pct
                # stayed permanently NULL for every paper trade despite the "fix" being live on
                # main, confirmed via a live DB check (algo_trades: 0/66+ closed trades across
                # 2026-08-12 through today have a non-NULL mfe_pct going back to before the fix
                # even existed). Idempotent (see backfill_all_trade_metrics()'s own docstring),
                # safe to call unconditionally here too, mirroring the auto-mode call site.
                backfill_result = backfill_all_trade_metrics(resolve_cur)
                if "total_updated" in backfill_result:
                    logger.info(
                        f"[RECONCILIATION] Paper mode: backfilled MFE/MAE/R-multiple/duration for "
                        f"{backfill_result['total_updated']} trade(s)"
                    )

            # The remainder of this branch (querying position/realized-P&L state, rolling the
            # baseline portfolio value forward, writing the snapshot, and the final
            # post-commit verification) is a pure extract-method move into
            # PaperModeReconciliationMixin (reconciliation_paper_mode.py) - see that file's
            # docstring. No behavior change.
            return self._finish_paper_mode_reconciliation(reconcile_date)

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

            # Get execution mode from config for cash calculation logic
            execution_mode = self.config.get("execution_mode")
            if execution_mode is None:
                raise ValueError(
                    "[RECONCILIATION CRITICAL] execution_mode config missing. "
                    "Cannot determine trading mode (live vs paper). "
                    "Set explicit execution_mode in algo_config table."
                )

            # NOTE (added 2026-08-11, after two separate sessions independently "fixed" bugs in
            # this section that turned out to be unreachable): everything from here to the end
            # of this try block only ever executes when execution_mode == "auto". __init__ sets
            # self.broker = None for any other execution_mode (paper/dry/review/anything else),
            # and the `if self.broker is None:` branch near the top of this method always
            # returns before reaching this point - grep this file for "self.broker =" to confirm
            # there is no other assignment site. So execution_mode is provably "auto" for the
            # rest of this try block; any "paper mode" / "dry mode" branching below describes
            # what WOULD happen if this were reached from those modes, which structurally cannot
            # occur. Verified empirically: constructing DailyReconciliation(execution_mode="dry")
            # and mocking _fetch_account shows it is never called. Don't "fix" a dry/paper-mode
            # bug here without first checking this invariant still holds - it's very easy to
            # spend real effort correctly following this codebase's execution_mode allowlist
            # convention on a branch that can never run.
            #
            # 1. Fetch broker account (required - no fallback to stale DB data)
            account_data = self._fetch_account()
            if not account_data:
                import os

                # In local test mode with auth failure, fall back to DB portfolio state
                if os.getenv("LOCAL_MODE") == "true":
                    logger.warning(
                        "[RECONCILIATION] Broker account fetch failed in LOCAL_MODE - "
                        "falling back to database portfolio state (paper trading mode)"
                    )
                    # Recursively call the paper trading mode section by using broker=None path
                    # Re-invoke the broker=None block above by setting broker to None temporarily
                    saved_broker = self.broker
                    self.broker = None
                    try:
                        return self.run_daily_reconciliation(reconcile_date, dry_run)
                    finally:
                        self.broker = saved_broker
                else:
                    logger.critical(
                        "Broker account fetch failed - reconciliation cannot proceed without live account data"
                    )
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

                # CRITICAL FIX: In paper mode, broker may not return real cash (returns error dict).
                # Calculate actual remaining cash from portfolio_value - position_value if cash is missing.
                # This ensures accurate cash calculation instead of showing initial capital.
                if cash is None and pv is not None:
                    # Defer cash calculation until after we've computed total_position_value
                    logger.debug("[PAPER MODE] Cash not available from broker, will compute from portfolio - positions")

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

                # CRITICAL FIX: Allow cash to be None in paper mode, calculate after position_value computed
                # Live mode requires real cash from broker, but paper mode can compute it from portfolio - positions
                # BUG FOUND 2026-08-11: "dry" mode is equally a no-real-broker local mode (same
                # allowlist distinction already fixed in executor.py's credential-fetch handling
                # and phase2_circuit_breakers.py's leniency check) - a bare `!= "paper"` here
                # missed it, so a None cash value in dry mode incorrectly raised this fatal
                # "Live mode: Broker cash is missing" halt instead of the paper-mode-equivalent
                # graceful compute-from-portfolio path.
                if cash is None and execution_mode not in ("paper", "dry"):
                    logger.critical(
                        "Live mode: Broker cash is missing - reconciliation cannot proceed without live cash value"
                    )
                    try:
                        notify(
                            "critical",
                            title="Reconciliation Halted",
                            message="Live mode: Broker cash missing - reconciliation requires live cash value for position sizing. Cannot use stale DB cache.",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send critical notification (will still raise): {e}", exc_info=True)
                    raise ValueError("Live mode: Broker cash required for reconciliation - cannot proceed")

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
                self._sync_broker_positions_and_pending(cur, reconcile_date)

                # 1c. Compute MAE/MFE metrics for recently closed trades (E3 analytics)
                # BUG FOUND 2026-08-24: this step only ever READ mfe_pct/mae_pct (via the
                # AVG() query below) - nothing wrote them. The only writer,
                # utils.trade_metrics.update_trade_metrics(), was never called from any
                # production code path (executor_exit_handler.py sets exit_r_multiple/
                # trade_duration_days directly via SQL at close time but never mfe_pct/
                # mae_pct), so every closed trade's mfe_pct/mae_pct stayed permanently NULL
                # and the TUI/API always rendered "--" for them. backfill_all_trade_metrics()
                # is idempotent (only touches rows with a NULL metric) so it's safe to run
                # on every reconciliation pass.
                backfill_result = backfill_all_trade_metrics(cur)
                if "total_updated" in backfill_result:
                    logger.info(
                        f"   Backfilled MFE/MAE/R-multiple/duration for {backfill_result['total_updated']} trade(s)"
                    )
                mae_result = self.compute_closed_trade_metrics(cur)
                logger.info("\n1c. MAE/MFE Metrics:")
                logger.info(f"   {mae_result['reason']}")

                # 1d. Compute analytics metrics: IC and expectancy (E4-E5)
                analytics = self.compute_analytics_metrics(cur)
                self._log_analytics_metrics(analytics)

                position_state = self._fetch_and_analyze_open_positions(cur)
                total_position_value = position_state.total_position_value
                unrealized_pnl = position_state.unrealized_pnl

                # 3. Calculate metrics
                # Values already validated at initial broker fetch; keep as Decimal for precision
                # Use broker's authoritative portfolio_value for the snapshot (includes live prices).
                # Our DB position_value sum may lag - Broker is the ground truth for drawdown math.
                from decimal import Decimal

                # CRITICAL FIX: In paper mode, ALWAYS compute cash as portfolio_value - position_value
                # Alpaca returns cash = $100k (initial capital) but doesn't update it as positions change
                # Real remaining cash = portfolio - positions
                # BUG FOUND 2026-08-11: follow-up to this same session's fix a few lines up (the
                # cash-is-None check now also exempts "dry" mode from the fatal halt) - but
                # without also exempting it HERE, a None cash in dry mode fell through to the
                # `else` branch below and called Decimal(str(None)), crashing with
                # decimal.InvalidOperation instead of computing cash the same way paper mode
                # does. "dry" is equally a no-real-broker local mode (same allowlist distinction
                # as executor.py's credential-fetch handling).
                if execution_mode in ("paper", "dry"):
                    # Paper mode: Compute actual remaining cash from portfolio and positions
                    # pv is a float (from the broker adapter's JSON response); total_position_value
                    # is a Decimal (from PositionAnalyzer, for precision) - must align types before subtracting.
                    if total_position_value is None:
                        raise ValueError(
                            "Paper mode reconciliation requires total_position_value from PositionAnalyzer - got None. "
                            "Cannot proceed without complete position analysis."
                        )
                    # Ensure both are Decimals to prevent float/Decimal type errors
                    cash_computed = Decimal(str(pv)) - total_position_value
                    logger.info(
                        f"[PAPER MODE] Computed cash: ${float(Decimal(str(pv))):,.2f} (portfolio) - ${float(total_position_value):,.2f} (positions) = ${float(cash_computed):,.2f}"
                    )
                    cash_dec = cash_computed
                else:
                    # Live mode: Use actual cash from broker
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

                metrics = self._compute_broker_snapshot_metrics(cur, reconcile_date, total_equity_dec, position_state)

                self._write_broker_snapshot(cur, reconcile_date, cash_dec, total_equity_dec, position_state, metrics)

            self._audit_and_log_broker_snapshot(reconcile_date, cash_dec, total_equity_dec, position_state, metrics)

            return {
                "success": True,
                # CRITICAL FIX: phase4_reconciliation.py::run() unconditionally requires a
                # "reason" key on this dict (raises RuntimeError if absent) - this broker-
                # connected path (only reached when execution_mode == "auto", real trading)
                # never set one, unlike the self.broker is None DB-fallback path above which
                # does. Every paper-mode test run takes that fallback path instead (broker is
                # forced None for any execution_mode != "auto"), so this was completely
                # invisible until the moment execution_mode switches to "auto" - at which
                # point Phase 4 would crash with "reason field missing" on its very first
                # successful reconciliation, every time, since this is the normal success
                # return, not an edge case.
                "reason": "Reconciliation completed successfully",
                "portfolio_value": float(total_equity_dec),
                "positions": len(position_state.positions),
                "unrealized_pnl": float(unrealized_pnl),
                "position_value": float(total_position_value),
                "cash_remaining": float(cash_dec),
                "cumulative_return_pct": metrics.cumulative_return_pct,
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
            # Same missing-"reason" gap as the success path above - this exception handler's
            # own error dict was masking real broker-reconciliation failures behind a generic
            # "reason field missing" RuntimeError from phase4_reconciliation.py instead of the
            # actual error captured here.
            return {"success": False, "error": str(e), "reason": str(e)}

    def reconcile_exit_fills(self, cur: PsycopgCursor[Any], reconcile_date: _date_type | None) -> dict[str, Any]:
        """Update DB trade exit prices with actual Alpaca fill prices.

        Phase 4 marks trades 'closed' immediately using the last known market price
        when placing market exit orders before market open. This reconciles those
        estimated prices with actual Alpaca fill prices after market opens.
        """
        try:
            if not self.broker:
                return {"updated": 0, "message": "No broker available (paper trading mode)", "no_broker": True}
            if reconcile_date is None:
                reconcile_date = datetime.now(timezone.utc).date()
            since = datetime.now(timezone.utc) - timedelta(days=2)
            orders = self.broker.fetch_closed_orders(since=since)
            if not orders:
                logger.debug(
                    "No closed orders returned from broker in exit fill reconciliation. "
                    "This is expected if: (1) No orders were placed in the last 2 days, "
                    "(2) All orders were already reconciled. Otherwise, broker API may be unavailable."
                )
                return {"updated": 0, "message": "No closed orders to reconcile", "no_orders_available": True}

            updated = 0

            for order in orders:
                if order.get("status") != "filled" or order.get("side") != "sell":
                    continue
                symbol = order.get("symbol")
                filled_price_str = order.get("filled_avg_price")
                if not symbol or not filled_price_str:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled sell order missing symbol or filled_price: {order}"
                    )
                # ORDER-ID CORRELATION FIX (2026-09-05, financial-integrity finding): matching
                # by client_order_id (exact) instead of symbol+date proximity (see module docstring
                # note above reconcile_exit_fills - actually see the fix commit message for the
                # full incident writeup). No match here means this fill isn't one of our trades
                # still awaiting reconciliation (already reconciled, or a foreign/manual order) -
                # skip it rather than guessing which trade it belongs to.
                client_order_id = order.get("client_order_id")
                if not client_order_id:
                    continue
                try:
                    filled_price = float(filled_price_str)
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled price not numeric '{filled_price_str}' for {symbol}"
                    ) from e
                # BUG FOUND 2026-08-10 (NaN-comparison-guard class): float() accepts "nan"/"inf"
                # strings without raising, so a malformed filled_avg_price from the broker JSON
                # would silently pass this `<= 0` check and get written into algo_trades.exit_price.
                if math.isnan(filled_price) or math.isinf(filled_price) or filled_price <= 0:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled price invalid {filled_price} for {symbol} - must be > 0"
                    )

                cur.execute("SAVEPOINT reconcile_fill")
                try:
                    cur.execute(
                        """
                        SELECT trade_id, entry_price, stop_loss_price, entry_quantity
                        FROM algo_trades
                        WHERE pending_exit_client_order_id = %s
                          AND symbol = %s
                          AND status = 'closed'
                    """,
                        (client_order_id, symbol),
                    )

                    row = cur.fetchone()
                    if row is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        logger.debug(
                            f"[RECONCILIATION] {symbol} fill (client_order_id={client_order_id}) does not match any trade still awaiting reconciliation - skipping."
                        )
                        continue

                    trade_id, entry_price, stop_loss_price, entry_qty = row
                    if entry_price is None or stop_loss_price is None or entry_qty is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) missing entry_price, stop_loss_price, or entry_qty - cannot reconcile"
                        )

                    try:
                        entry_price = float(entry_price)
                        stop_loss_price = float(stop_loss_price)
                        # float (not int): algo_trades.entry_quantity is NUMERIC(18,4) - real
                        # fractional-share entries exist in this DB. int() truncation here fed
                        # a too-small cost basis/risk denominator into original_cost_basis/
                        # original_risk_dollars below for multi-leg fills - same bug class
                        # already fixed in executor_exit_handler.py's _compute_cumulative_pnl
                        # (the synchronous exit path this function mirrors for async fills).
                        entry_qty = float(entry_qty)
                    except (ValueError, TypeError) as e:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has non-numeric price/qty - cannot reconcile"
                        ) from e

                    if (
                        math.isnan(entry_price)
                        or math.isinf(entry_price)
                        or math.isnan(stop_loss_price)
                        or math.isinf(stop_loss_price)
                        or math.isnan(entry_qty)
                        or math.isinf(entry_qty)
                        or entry_price <= 0
                        or stop_loss_price <= 0
                        or entry_qty <= 0
                    ):
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid prices/qty (entry={entry_price}, stop={stop_loss_price}, qty={entry_qty}) - must be > 0"
                        )

                    # CRITICAL: use THIS order's actual filled quantity, not entry_qty (the
                    # original full position size). For a trade closed via multiple partial
                    # exits (T1/T2 profit-taking before a final stop/target exit), this order
                    # only sold the shares remaining at final-exit time - using entry_qty here
                    # would attribute the entire original position's P&L to just this leg's
                    # price, silently discarding what the earlier legs actually realized. This
                    # is the same financial-integrity bug class already found and fixed for the
                    # synchronous exit path (see executor_exit_handler.py's
                    # _compute_cumulative_pnl docstring, "2026-07-21 financial-integrity audit")
                    # - this reconciliation fallback path (for fills whose price wasn't known
                    # synchronously) never got the same fix.
                    filled_qty_str = order.get("filled_qty")
                    if not filled_qty_str:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Filled sell order missing filled_qty for {symbol}: {order}"
                        )
                    try:
                        filled_qty = float(filled_qty_str)
                    except (TypeError, ValueError) as e:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] filled_qty not numeric '{filled_qty_str}' for {symbol}"
                        ) from e
                    if math.isnan(filled_qty) or math.isinf(filled_qty) or filled_qty <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] filled_qty invalid {filled_qty} for {symbol} - must be > 0"
                        )

                    filled_dec = Decimal(str(filled_price))
                    entry_dec = Decimal(str(entry_price))
                    entry_qty_dec = Decimal(str(entry_qty))
                    leg_pnl_dollars_dec = ((filled_dec - entry_dec) * Decimal(str(filled_qty))).quantize(
                        Decimal("0.01"), ROUND_HALF_UP
                    )
                    risk = entry_price - stop_loss_price
                    if risk <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid risk={risk}: "
                            f"stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). "
                            f"Cannot compute R-multiple with invalid stop price."
                        )

                    # Fold in any earlier partial-exit legs' realized P&L (mirrors
                    # executor_exit_handler.py's _compute_cumulative_pnl exactly).
                    cur.execute(
                        """
                        SELECT COALESCE(SUM((details->>'pnl_dollars')::numeric), 0)
                        FROM algo_audit_log
                        WHERE action_type LIKE 'exit_%%'
                          AND (details->>'trade_id') = %s
                          AND (details->>'full_exit')::boolean = false
                        """,
                        (trade_id,),
                    )
                    prior_partial_pnl_row = cur.fetchone()
                    prior_partial_pnl_dec = (
                        Decimal(str(prior_partial_pnl_row[0])) if prior_partial_pnl_row else Decimal(0)
                    )

                    if prior_partial_pnl_dec == 0:
                        # No prior partial legs - simple single-leg case, same formula as before.
                        pnl_dollars = float(leg_pnl_dollars_dec)
                        pnl_pct = float(
                            ((filled_dec - entry_dec) / entry_dec * Decimal(100)).quantize(
                                Decimal("0.01"), ROUND_HALF_UP
                            )
                        )
                        exit_r_multiple = float(
                            ((filled_dec - entry_dec) / Decimal(str(risk))).quantize(Decimal("0.01"), ROUND_HALF_UP)
                        )
                    else:
                        cumulative_pnl_dec = (prior_partial_pnl_dec + leg_pnl_dollars_dec).quantize(
                            Decimal("0.01"), ROUND_HALF_UP
                        )
                        original_cost_basis = entry_dec * entry_qty_dec
                        original_risk_dollars = Decimal(str(risk)) * entry_qty_dec
                        pnl_dollars = float(cumulative_pnl_dec)
                        pnl_pct = float(
                            (cumulative_pnl_dec / original_cost_basis * Decimal(100)).quantize(
                                Decimal("0.01"), ROUND_HALF_UP
                            )
                        )
                        exit_r_multiple = float(
                            (cumulative_pnl_dec / original_risk_dollars).quantize(Decimal("0.01"), ROUND_HALF_UP)
                        )
                        logger.info(
                            f"[RECONCILIATION MULTI_LEG] {symbol} trade {trade_id}: cumulative P&L across all "
                            f"legs ${pnl_dollars:.2f} (prior partial legs: ${float(prior_partial_pnl_dec):.2f}, "
                            f"final leg: ${float(leg_pnl_dollars_dec):.2f})"
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
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT reconcile_fill")
                    except psycopg2.DatabaseError as rollback_err:
                        if "does not exist" not in str(rollback_err):
                            raise
                        logger.warning(
                            f"[RECONCILIATION] Savepoint missing (transaction may be aborted), skipping rollback for {symbol}"
                        )
                    logger.error(
                        f"[RECONCILIATION] Exit fill reconciliation failed for {symbol}: {e}. "
                        f"Trade exit price could not be reconciled with Alpaca fill price. "
                        f"Skipping this trade but continuing reconciliation (partial reconciliation detected)."
                    )

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
            logger.error(
                f"[RECONCILIATION CRITICAL] Exit fill reconciliation failed: {e}. "
                "Cannot reconcile trade exit prices with actual Alpaca fill prices. "
                "This prevents accurate P&L calculation and risk reporting. "
                "Reconciliation must fail explicitly rather than silently skip exit price validation."
            )
            raise ValueError(
                f"CRITICAL: Exit fill reconciliation failed: {e}. "
                "Cannot reconcile exit prices with broker fills. "
                "Reconciliation requires accurate exit prices for P&L validation."
            ) from e

    def resolve_local_pending_exits(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """LOCAL_MODE-only: resolve trades stuck with NULL P&L pending broker fill reconciliation.

        reconcile_exit_fills() (above) is the only code path that ever resolves an
        estimated_exit_price into a real fill price, and it requires self.broker to be set AND a
        successful live Alpaca call - both unavailable in local dev (no broker, or placeholder
        credentials that can never authenticate). Without this, any trade closed by
        phase9_reconciliation.py's _record_closed_positions_exits() stays profit_loss_dollars=NULL
        forever, permanently invisible to win_rate/consecutive_losses/realized P&L in local dev.

        Uses price_daily's real EOD close for the exit symbol/date as the fill price - this is
        genuine market data (not fabricated), consistent with governance's real-data-only rule,
        unlike the fixed bug where a stale current_price silently produced a fake $0.00 P&L.

        Resolves trades whose exit_date has an actual close on file (today or earlier). If price_daily
        close is available for exit_date, uses it to calculate P&L. For same-day trades where
        entry_price = estimated_exit_price (no price movement), can use the estimate if price_daily
        data hasn't loaded yet. Otherwise leaves trade pending for next run.
        """
        cur.execute("""
            SELECT trade_id, symbol, entry_price, stop_loss_price, entry_quantity, exit_date,
                   estimated_exit_price
            FROM algo_trades
            WHERE status = 'closed'
              AND profit_loss_dollars IS NULL
              AND estimated_exit_price IS NOT NULL
              AND exit_date <= CURRENT_DATE
            """)
        pending = cur.fetchall()
        if not pending:
            return {"resolved": 0, "message": "No local-mode pending exits to resolve"}

        resolved = 0
        for trade_id, symbol, entry_price, stop_loss_price, entry_qty, exit_date, estimated_exit_price in pending:
            if entry_price is None or stop_loss_price is None or entry_qty is None:
                logger.warning(
                    f"[LOCAL EXIT RESOLUTION] {trade_id} ({symbol}) missing entry_price/stop_loss_price/"
                    "entry_quantity - cannot resolve, leaving pending"
                )
                continue

            # Always prefer price_daily's real close for exit_date over estimated_exit_price -
            # the estimate was itself derived from algo_positions.current_price at close time,
            # which is only as fresh as the last price sync before the position closed (see
            # _record_closed_positions_exits's comment above). For same-day trades in particular,
            # that sync often ran before the morning loader landed today's close, so blindly
            # trusting the estimate reproduces the exact "stale current_price -> fake $0.00 P&L"
            # bug this function exists to fix. Only fall back to the estimate when price_daily
            # genuinely has no close yet for exit_date (e.g. resolving before today's data loads).
            cur.execute(
                """
                SELECT close FROM price_daily
                WHERE symbol = %s AND date = %s AND (data_unavailable IS NOT TRUE)
                """,
                (symbol, exit_date),
            )
            price_row = cur.fetchone()
            if price_row is not None and price_row[0] is not None:
                fill_price = Decimal(str(price_row[0]))
                price_source = f"price_daily EOD close for {exit_date}"
            elif exit_date == datetime.now(timezone.utc).date() and entry_price == estimated_exit_price:
                fill_price = Decimal(str(estimated_exit_price))
                price_source = "estimated_exit_price (no price_daily close for today yet)"
                logger.debug(
                    f"[LOCAL EXIT RESOLUTION] Same-day close for {trade_id} ({symbol}): "
                    f"using estimated_exit_price ${float(fill_price):.2f}"
                )
            else:
                logger.debug(
                    f"[LOCAL EXIT RESOLUTION] No price_daily close yet for {symbol} on {exit_date} "
                    f"- leaving {trade_id} pending"
                )
                continue

            # CRITICAL FIX: For multi-leg exits, sum prior partial exit P&L with this final leg's P&L.
            # When a position closes via multiple partial exits (T1/T2 profit-taking before final
            # stop/target), each exit fills at a different price. This function receives fill_price
            # for the FINAL leg only, but must report total realized P&L across ALL legs.
            # Without this, multi-leg exits would report only the final leg's P&L (or loss),
            # discarding every dollar from earlier legs - exact same bug that was already fixed
            # in reconcile_exit_fills() and executor_exit_handler.py's _compute_cumulative_pnl.
            #
            # Prior partial leg data comes from algo_audit_log's JSONB 'details' column (this
            # table has no top-level trade_id/event_type/amount/quantity columns - see migration
            # 094a_create_algo_audit_log_table.py - only action_type and details JSONB). Exit
            # legs are logged by executor_exit_handler.py as action_type='exit_{stage}' with
            # details containing trade_id/pnl_dollars/shares_exited/full_exit (see its
            # _compute_cumulative_pnl and reconcile_exit_fills() above for the identical query).
            prior_pnl_dollars = Decimal("0")
            prior_exit_qty = Decimal("0")
            cur.execute(
                """
                SELECT COALESCE(SUM((details->>'pnl_dollars')::numeric), 0),
                       COALESCE(SUM((details->>'shares_exited')::numeric), 0)
                FROM algo_audit_log
                WHERE action_type LIKE 'exit_%%'
                  AND (details->>'trade_id') = %s
                  AND (details->>'full_exit')::boolean = false
                """,
                (trade_id,),
            )
            audit_row = cur.fetchone()
            if audit_row:
                prior_pnl_dollars = Decimal(str(audit_row[0])) if audit_row[0] is not None else Decimal("0")
                prior_exit_qty = Decimal(str(audit_row[1])) if audit_row[1] is not None else Decimal("0")

            # Calculate P&L for THIS leg only (not cumulative yet)
            entry_dec = Decimal(str(entry_price))
            qty_dec = Decimal(str(entry_qty))
            # This leg's P&L: (fill_price - entry_price) * remaining_qty
            # remaining_qty = entry_qty - prior_exit_qty (amount of position resolved by this exit)
            this_leg_qty = qty_dec - prior_exit_qty
            this_leg_pnl = (fill_price - entry_dec) * this_leg_qty if this_leg_qty > 0 else Decimal("0")
            # Cumulative P&L: prior legs + this leg
            cumulative_pnl = prior_pnl_dollars + this_leg_pnl

            # Risk/reward based on TOTAL realized P&L, not just this leg
            # R multiple = total_pnl / (risk_per_share * total_entry_qty)
            risk_per_share = float(entry_price) - float(stop_loss_price)
            if risk_per_share > 0:
                total_risk = Decimal(str(risk_per_share)) * qty_dec
                exit_r_multiple = float((cumulative_pnl / total_risk).quantize(Decimal("0.01"), ROUND_HALF_UP))
            else:
                exit_r_multiple = None

            # P&L % based on total realized P&L relative to total position cost
            pnl_pct = float(
                (cumulative_pnl / (entry_dec * qty_dec) * Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
            )
            pnl_dollars = float(cumulative_pnl.quantize(Decimal("0.01"), ROUND_HALF_UP))

            cur.execute(
                """
                UPDATE algo_trades
                SET exit_price = %s, profit_loss_dollars = %s, profit_loss_pct = %s,
                    exit_r_multiple = %s, exit_price_reconciled_at = CURRENT_TIMESTAMP,
                    reconciliation_note = %s, updated_at = CURRENT_TIMESTAMP
                WHERE trade_id = %s
                """,
                (
                    float(fill_price),
                    pnl_dollars,
                    pnl_pct,
                    exit_r_multiple,
                    f"[LOCAL_MODE] Resolved via {price_source} (no live broker available to confirm actual fill)",
                    trade_id,
                ),
            )
            resolved += 1
            logger.info(
                f"[LOCAL EXIT RESOLUTION] {trade_id} ({symbol}): resolved P&L ${pnl_dollars:+.2f} "
                f"({pnl_pct:+.2f}%) using {exit_date} close ${float(fill_price):.2f}"
            )

        return {"resolved": resolved, "message": f"Resolved {resolved} local-mode pending exit(s)"}

    def audit_stale_estimated_prices(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Audit for trades with estimated exit prices that haven't been reconciled to the
        broker's actual fill price yet.

        executor_exit_handler.py writes estimated_exit_price + status='closed' immediately on
        exit (PENDING_FILL_RECONCILIATION) when the real fill price isn't known synchronously;
        exit_price_reconciled_at is set once a later reconciliation pass confirms the real fill.
        A row that stays unreconciled too long means P&L/exit_r_multiple are still computed from
        a guess, not the broker's actual fill - this audit surfaces that before it goes unnoticed.

        In paper trading mode, reconciliation never happens (no real broker fills), so estimated
        prices are expected to remain unreconciled indefinitely. Skip audit in paper mode.

        BUG FOUND 2026-08-11: "dry" mode is equally a no-real-broker-fills local mode (same
        allowlist distinction already fixed elsewhere tonight, e.g. executor.py's
        credential-fetch handling) - a bare `== "paper"` here missed it, so dry mode ran this
        audit and could raise false ALERT/CRITICAL status for exit prices that will never
        reconcile in dry mode either.

        Returns dict: {'status': 'OK'|'ALERT'|'CRITICAL', 'message': str, 'stale_trade_count': int,
        'stale_trades': list[dict]}.
        """
        # Skip audit in paper/dry trading mode - broker reconciliation never happens, so
        # unreconciled estimated prices are expected and harmless. Only audit in live mode
        # where real fills matter.
        is_paper_mode = self.config.get("execution_mode") in ("paper", "dry")
        if is_paper_mode:
            return {
                "status": "OK",
                "message": "Paper trading mode: exit price reconciliation skipped (no real broker fills)",
                "stale_trade_count": 0,
                "stale_trades": [],
            }

        stale_threshold = timedelta(hours=2)
        critical_threshold = timedelta(hours=24)

        cur.execute("""SELECT trade_id, symbol, estimated_exit_price, exit_time
               FROM algo_trades
               WHERE estimated_exit_price IS NOT NULL
                 AND exit_price_reconciled_at IS NULL
               ORDER BY exit_time ASC""")
        rows = cur.fetchall()

        if not rows:
            return {
                "status": "OK",
                "message": "No unreconciled estimated exit prices.",
                "stale_trade_count": 0,
                "stale_trades": [],
            }

        now = datetime.now(timezone.utc)
        stale_trades: list[dict[str, Any]] = []
        max_age = timedelta(0)
        for trade_id, symbol, estimated_exit_price, exit_time in rows:
            if exit_time is None:
                # No exit_time recorded - can't compute age, but flag it as data quality issue
                age = critical_threshold + timedelta(seconds=1)
            else:
                # algo_trades.exit_time is a `timestamp without time zone` column written via
                # SQL CURRENT_TIMESTAMP, so a naive value here is in the DB session's local
                # wall-clock timezone (utils/bulk_insert_manager.py's documented convention),
                # not UTC - confirmed live this session's actual `SHOW timezone` is
                # America/Chicago, 5+ hours off UTC. Mislabeling it as UTC via
                # .replace(tzinfo=timezone.utc) silently inflated age by that offset, which
                # exceeds the 2h stale_threshold below on its own - every unreconciled exit
                # price would falsely alert as stale regardless of true age. Same bug class
                # already fixed in algo/risk/market_exposure.py's cache-age check,
                # algo/trading/pretrade_checks.py's re-entry cooldown, and
                # algo/monitoring/position_monitor.py's stale-order check.
                if exit_time.tzinfo:
                    exit_time_utc = exit_time
                else:
                    from utils.db.timezone_utils import get_db_timezone

                    naive_tz = get_db_timezone()
                    exit_time_utc = exit_time.replace(tzinfo=naive_tz)
                age = now - exit_time_utc
            if age >= stale_threshold:
                stale_trades.append(
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "estimated_exit_price": float(estimated_exit_price),
                        "exit_time": exit_time.isoformat() if exit_time else None,
                        "age_hours": round(age.total_seconds() / 3600, 1),
                    }
                )
                max_age = max(max_age, age)

        if not stale_trades:
            return {
                "status": "OK",
                "message": f"{len(rows)} unreconciled estimated exit price(s), all under {stale_threshold}.",
                "stale_trade_count": 0,
                "stale_trades": [],
            }

        status = "CRITICAL" if max_age >= critical_threshold else "ALERT"
        symbols = ", ".join(f"{t['symbol']}({t['age_hours']}h)" for t in stale_trades[:10])
        message = (
            f"[STALE_PRICE_AUDIT] {len(stale_trades)} trade(s) still on estimated exit price "
            f"past the {stale_threshold} threshold: {symbols}" + ("..." if len(stale_trades) > 10 else "")
        )
        return {
            "status": status,
            "message": message,
            "stale_trade_count": len(stale_trades),
            "stale_trades": stale_trades,
        }

    def sync_positions(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sync broker positions via BrokerAdapter."""
        if not self.broker:
            return {"synced": 0, "message": "No broker available (paper trading mode)", "no_broker": True}
        return self.broker.sync_positions(cur)

    def compute_analytics_metrics(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Compute analytics metrics (Information Coefficient, expectancy).

        Delegates to ReconciliationAnalytics for actual computation.

        Returns dict with ic and expectancy results.
        """
        from algo.infrastructure.reconciliation_analytics import ReconciliationAnalytics

        analytics = ReconciliationAnalytics()
        return analytics.compute_analytics_metrics(cur)

    def compute_closed_trade_metrics(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Compute closed trade metrics (win rate, R-multiples, profit factor).

        Delegates to ReconciliationAnalytics for actual computation.

        Returns dict with closed trade metrics including MAE/MFE.
        """
        from algo.infrastructure.reconciliation_analytics import ReconciliationAnalytics

        analytics = ReconciliationAnalytics()
        return analytics.compute_closed_trade_metrics(cur)

    def check_partial_fills(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Check for partial fills that haven't been reconciled with Alpaca.

        Detects when orders were only partially filled but the local DB thinks
        they're fully filled. This catches the case when Alpaca fills part of an
        order and then network fails before we can sync.

        Returns: dict with reconciliation status and any detected drift
        """
        try:
            if not self.broker:
                return {"mismatches": 0, "message": "No broker available (paper trading mode)", "no_broker": True}
            orders = self.broker.fetch_closed_orders()
            if not orders:
                logger.debug(
                    "No closed orders returned from broker in partial fill check. "
                    "This is expected if: (1) No orders were placed recently, "
                    "(2) All recent orders are still open/pending. Otherwise, broker API may be unavailable."
                )
                return {"mismatches": 0, "message": "No closed orders to check", "no_orders_available": True}

            # Check each order against our DB records
            mismatches = []
            for order in orders:
                if "symbol" not in order or "filled_qty" not in order or "status" not in order:
                    # CRITICAL: Alpaca API contract violation - cannot reconcile fill status without required fields
                    raise RuntimeError(
                        f"[PARTIAL_FILL_CHECK CRITICAL] Alpaca API returned malformed order (missing required fields). "
                        f"Cannot reconcile fills: {order}. Partial fill detection disabled. "
                        f"API contract violated - check Alpaca API response structure."
                    )
                symbol = order["symbol"]
                alpaca_filled_qty = float(order["filled_qty"])
                order_status = order["status"]

                if not symbol or alpaca_filled_qty <= 0:
                    continue

                # CRITICAL FIX: fetch_closed_orders() has no side filter (status=[filled,
                # partially_filled] only) - it returns both buy and sell orders. This function
                # exists to catch entry-fill drift (DB entry_quantity vs Alpaca's actual filled
                # buy order), but without a side check, a partial-exit SELL order (T1/T2 partial
                # profit-taking - see executor_exit_handler.py's full_exit=False path) for a
                # still-open trade would match here too, since the trade's status stays in
                # TradeStatus.all_open() until the final leg closes it. Its filled_qty is the
                # (smaller, expected) exit quantity, not the original entry quantity - matching
                # it here would silently shrink entry_quantity to the partial-exit size, and
                # entry_quantity later feeds original_cost_basis/original_risk_dollars for the
                # trade's final pnl_pct/exit_r_multiple in reconcile_exit_fills() (~line 1613,
                # 1713-1722), corrupting reported P&L% and R-multiple for every trade that used a
                # partial exit. reconcile_exit_fills() itself already filters to side == "sell"
                # for the opposite (exit) purpose (~line 1572) - mirror that here for entries.
                if order.get("side") != "buy":
                    continue

                # Find corresponding trade in our DB
                #
                # CRITICAL FIX: this hardcoded list omitted 'pending'/'paper_pending' - exactly
                # the two statuses a trade sits in when "Alpaca fills part of an order and then
                # network fails before we can sync" (this function's own docstring), i.e. the
                # precise desync this check exists to catch. A trade stuck at 'pending' in our
                # DB while Alpaca's own closed-orders feed already shows it filled would never
                # match this WHERE clause, so the mismatch would go undetected. Use
                # TradeStatus.all_open() so every live status is covered.
                open_trade_statuses = TradeStatus.all_open()
                status_placeholders = ", ".join(["%s"] * len(open_trade_statuses))
                cur.execute(
                    f"""
                    SELECT trade_id, entry_quantity, status
                    FROM algo_trades
                    WHERE symbol = %s AND status IN ({status_placeholders})
                    ORDER BY trade_date DESC LIMIT 1
                """,
                    (symbol, *open_trade_statuses),
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

                # Check for mismatch. CRITICAL FIX: this used to compare int(db_qty) !=
                # int(alpaca_filled_qty), truncating fractional shares before comparing - this
                # system actively trades fractional shares (order_manager.py), so a genuine
                # sub-1-share drift (e.g. db_qty=10.9, alpaca_filled_qty=10.1) truncated to
                # int(10.9)=10 == int(10.1)=10 and was silently classified as "no mismatch".
                # Unlike the equivalent bug already fixed in alpaca_sync_manager.py (where the
                # DB correction ran unconditionally and only the alert was gated), HERE the
                # comparison gates the correction UPDATE itself (see below) - so this
                # truncation didn't just miss an alert, it left algo_trades.entry_quantity
                # silently wrong for any sub-1-share entry-fill drift, with no way for a later
                # reconciliation pass to ever catch it (int(10.9) always equals int(10.1)).
                qty_mismatch = alpaca_filled_qty > 0 and abs(float(db_qty) - alpaca_filled_qty) > 1e-6

                if qty_mismatch:
                    # Quantity drift detected - Alpaca has different fill than DB
                    mismatches.append(
                        {
                            "symbol": symbol,
                            "trade_id": db_trade_id,
                            "db_quantity": float(db_qty),
                            "alpaca_filled": alpaca_filled_qty,
                            "alpaca_status": order_status,
                        }
                    )

                    # Correct the DB quantity to match Alpaca (source of truth). algo_trades.
                    # entry_quantity is numeric(_, 4) - write the precise fractional value, not
                    # the truncated int (which would itself re-introduce the same precision loss
                    # this fix removes from the comparison).
                    cur.execute(
                        "UPDATE algo_trades SET entry_quantity = %s, updated_at = CURRENT_TIMESTAMP WHERE trade_id = %s",
                        (alpaca_filled_qty, db_trade_id),
                    )
                    logger.warning(
                        f"[PARTIAL_FILL] Corrected {symbol} quantity: DB had {db_qty}, Alpaca filled {alpaca_filled_qty}"
                    )

                    try:
                        # strict=True: notify() otherwise swallows every delivery failure
                        # internally and just logs, which made the except clause below
                        # non-functional for its actual purpose (see the comment there) -
                        # it could never see a psycopg2 error notify() had already caught
                        # and discarded itself.
                        notify(
                            severity="warning",
                            title="Partial Fill Detected and Corrected",
                            message=f"{symbol}: Quantity corrected from {db_qty} to {alpaca_filled_qty} to match Alpaca.",
                            symbol=symbol,
                            details={
                                "symbol": symbol,
                                "db_quantity": float(db_qty),
                                "alpaca_filled": alpaca_filled_qty,
                            },
                            strict=True,
                        )
                    except Exception as e:
                        # CRITICAL FIX: this used to re-raise, which propagates out of this
                        # loop, out of the single `with DatabaseContext("write") as cur:`
                        # block that phase4_reconciliation.py opens around the whole
                        # check_partial_fills() call - rolling back the UPDATE just made
                        # above (which corrects a genuinely stale DB quantity to match
                        # Alpaca, the source of truth) AND every other symbol's correction
                        # already applied earlier in this same loop/transaction. A flaky
                        # alert channel would silently discard real, already-verified
                        # data-integrity corrections instead of just failing to announce
                        # them. Same bug class as the entry/exit notification-rollback
                        # fixes (executor_entry_handler.py, executor_exit_handler.py) -
                        # log-and-continue so the correction survives regardless of
                        # whether the operator alert lands.
                        logger.error(
                            f"[PARTIAL_FILL_ALERT] Failed to notify operator of fill correction "
                            f"for {symbol} (non-blocking, correction already applied): {e}"
                        )

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
            # Handle Alpaca 401/auth errors: return a structured auth_unavailable=True result
            # rather than raising, so the caller (phase4_reconciliation.py) can distinguish
            # this from a generic reconciliation failure. NOTE (2026-08-10 audit): the
            # `mismatches: 0` here does NOT mean "checked and clean" - phase4_reconciliation.py
            # explicitly documents and enforces this ("The 0 mismatches means 'not checked',
            # not 'checked and clean'") by fail-fasting on `auth_unavailable=True` regardless
            # of the mismatches count (see its own FAIL-FAST block). Also NOTE: __init__ only
            # ever constructs a real `self.broker` when execution_mode == "auto" - this branch
            # can only be reached in that mode (paper/dry/review short-circuit earlier via the
            # `if not self.broker` check above), so despite the "paper mode" wording below,
            # this is exclusively a live-mode signal; the fail-fast caller behavior is what
            # actually keeps this safe, not this comment's description of when it fires.
            error_str = str(e).lower()
            if "401" in str(e) or "unauthorized" in error_str or "alpaca" in error_str:
                logger.warning(
                    "[PARTIAL_FILL_CHECK] Alpaca broker authentication failed (401). "
                    "Reporting auth_unavailable=True; caller must fail-fast on this in "
                    "live/auto mode rather than treat it as a clean check."
                )
                return {"mismatches": 0, "message": "Broker auth unavailable", "auth_unavailable": True}
            # CRITICAL: Partial fill detection failure - cannot reconcile fill status
            raise RuntimeError(
                f"[PARTIAL_FILL_CHECK FAILED] {type(e).__name__}: {e}. "
                f"Cannot reconcile fill status without valid broker connection."
            ) from e

    def check_pending_reconciliations(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
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
                stuck_message = (
                    f"RECONCILIATION STUCK: {len(stuck)} trades with estimated exit prices "
                    "stuck > 1 day without Alpaca price reconciliation. "
                    f"Examples: {stuck_examples}"
                )
                logger.critical(stuck_message)
                # BUG FOUND 2026-09-01 (real-money-readiness pass): this only ever reached
                # logger.critical() - unlike every other CRITICAL condition in this same
                # file (broker cash missing/negative, account fetch failure, portfolio_value
                # missing, all of which call notify() a few hundred lines above/below this
                # one), a stuck reconciliation never reached a real alert channel. Effect:
                # profit_loss_dollars/portfolio_value/drawdown get silently computed off a
                # stale ESTIMATED exit price indefinitely, with no operator ever notified -
                # same "computed but never delivered" bug class already found and fixed for
                # Phase 9's VaR/concentration/beta alerts (commit 5ac092eea).
                try:
                    notify(
                        "critical",
                        title="Trade Reconciliation Stuck",
                        message=stuck_message,
                    )
                except Exception as e:
                    logger.error(f"Failed to send stuck-reconciliation notification (non-blocking): {e}", exc_info=True)

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
        if not self.broker:
            return {"error": "No broker available (paper trading mode)"}
        try:
            return self.broker.fetch_account()
        except ValueError as e:
            # Handle Alpaca 401/auth errors gracefully in paper mode
            error_str = str(e).lower()
            if "401" in str(e) or "unauthorized" in error_str or "alpaca" in error_str:
                logger.warning(
                    "[RECONCILIATION] Alpaca broker authentication failed (401). "
                    "Gracefully falling back to database portfolio state in paper mode."
                )
                return None  # Return None to trigger DB fallback in run_daily_reconciliation
            # Re-raise other ValueErrors
            raise

    def _fetch_initial_capital(self, cur: PsycopgCursor[Any]) -> float:
        """Get the actual initial capital from broker account history (fail-fast).

        CRITICAL: Does NOT fall back to stale database snapshots. Initial capital is
        required for accurate cumulative return calculation. Stale data (days/months old)
        would severely distort P&L metrics and mask performance issues.

        Raises ValueError if broker history unavailable - reconciliation must fail fast
        rather than use potentially months-old snapshot data.
        """
        try:
            if not self.broker:
                raise ValueError("No broker available in paper trading mode")
            initial_val = self.broker.fetch_initial_capital()
            # Check if dict (error marker) or float (valid data)
            if isinstance(initial_val, dict):
                # CRITICAL: Validate error field exists when dict is returned (fail-fast if missing)
                error_reason = initial_val.get("error")
                if error_reason is None:
                    raise ValueError(
                        f"CRITICAL: Broker returned dict (error marker) but missing required 'error' field. "
                        f"Cannot determine what went wrong. This indicates API contract violation. Response: {initial_val}"
                    )
                raise ValueError(
                    f"CRITICAL: Broker returned empty portfolio history (error: {error_reason}). "
                    "Initial capital cannot be determined from Alpaca. "
                    "Reconciliation requires live broker history for accurate P&L - cannot proceed."
                )
            if initial_val and initial_val > 0:
                logger.info(f"Initial capital from broker history: ${initial_val:,.2f}")
                return initial_val
        except ValueError:
            raise
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
            "Reconciliation requires live broker history for accurate P&L - cannot proceed."
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
# test
