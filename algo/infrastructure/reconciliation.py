#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
from datetime import date as _date_type
from datetime import datetime, timezone
from typing import Any, cast

import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
from algo.infrastructure.audit_logger import TradeAuditLogger
from algo.infrastructure.broker_adapter import BrokerAdapter
from algo.infrastructure.reconciliation_broker_positions import BrokerPositionSyncMixin
from algo.infrastructure.reconciliation_broker_snapshot import BrokerSnapshotMixin
from algo.infrastructure.reconciliation_exit_fills import ExitFillReconciliationMixin
from algo.infrastructure.reconciliation_fill_and_account import FillAndAccountValidationMixin
from algo.infrastructure.reconciliation_paper_mode import PaperModeReconciliationMixin
from algo.infrastructure.reconciliation_shared import compute_adjusted_drawdown
from algo.reporting import notify
from utils.db import DatabaseContext
from utils.trade_metrics import backfill_all_trade_metrics

logger = logging.getLogger(__name__)

# Re-exported for backward compatibility - tests/unit/test_capital_flow_adjusted_drawdown.py
# and other call sites import these by these names from this module. The implementations
# now live in reconciliation_shared.py so reconciliation_paper_mode.py and
# reconciliation_broker_snapshot.py can both use them without an import cycle back here.
_compute_adjusted_drawdown = compute_adjusted_drawdown


class DailyReconciliation(
    PaperModeReconciliationMixin,
    BrokerPositionSyncMixin,
    BrokerSnapshotMixin,
    ExitFillReconciliationMixin,
    FillAndAccountValidationMixin,
):
    """Daily reconciliation and portfolio snapshot creation.

    Uses broker adapter for position sync, analytics, and price auditing.

    Split via pure extract-method refactor (2026-09-05) across five mixins:
    PaperModeReconciliationMixin (reconciliation_paper_mode.py, the self.broker is None /
    LOCAL_MODE DB-only fallback), BrokerPositionSyncMixin (reconciliation_broker_positions.py,
    broker position sync + open-position analysis), BrokerSnapshotMixin
    (reconciliation_broker_snapshot.py, concentration/drawdown/return metrics + the
    portfolio-snapshot INSERT), ExitFillReconciliationMixin (reconciliation_exit_fills.py,
    broker-fill exit-price matching, the LOCAL_MODE price_daily fallback, staleness auditing,
    and the pending-reconciliation report), and FillAndAccountValidationMixin
    (reconciliation_fill_and_account.py, entry-fill drift detection, broker account/initial-
    capital fetch, and broker-vs-local P&L variance validation). run_daily_reconciliation()
    itself keeps the top-level control flow (dry_run gate, broker-account fetch/validation,
    cash-vs-execution-mode branching) and a handful of literal call sites/conditions several
    regression tests scan for by source text - see that method's own docstring for which
    lines must stay there.
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


if __name__ == "__main__":
    from algo.infrastructure import get_config

    config = get_config()
    reconciliation = DailyReconciliation(cast(dict[str, Any], config))

    result = reconciliation.run_daily_reconciliation()
    logger.info(f"Result: {result}")
# test
