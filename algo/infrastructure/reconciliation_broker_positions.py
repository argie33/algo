#!/usr/bin/env python3
"""BROKER-CONNECTED RECONCILIATION: position sync + open-position analysis

Pure extract-method split of `DailyReconciliation.run_daily_reconciliation()` (see that
module's class docstring for the overall contract). This file covers the position-facing
steps of the execution_mode=="auto" (self.broker is not None) branch:

1. `_sync_broker_positions_and_pending` - steps 1b/1b2/1b2b/1b3: sync broker positions into
   the DB, reconcile actual fill prices, fall back to price_daily EOD close for whatever
   couldn't be resolved against the broker, and log any trades still stuck pending Phase 7
   price reconciliation.
2. `_fetch_and_analyze_open_positions` - the algo_trades-sourced open-position query (with
   its entry_price fallback/validation) plus the PositionAnalyzer pass over the result.

NO BEHAVIOR CHANGE: every method here is a verbatim relocation of code that used to live
inline in run_daily_reconciliation()'s `with DatabaseContext("write") as cur:` block -
control flow, thresholds, SQL, and log messages are unchanged. Comments documenting
non-obvious business logic (fix-history notes, bug-found dates) moved verbatim with the
code they describe.

Mixed into DailyReconciliation via multiple inheritance - every `self.` call here
(sync_positions, reconcile_exit_fills, resolve_local_pending_exits,
check_pending_reconciliations - all still defined directly on DailyReconciliation in
reconciliation.py) resolves normally through the instance regardless of which file defines it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date_type
from typing import Any

from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.position_analyzer import PositionAnalyzer
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


@dataclass
class BrokerPositionState:
    """Result of `_fetch_and_analyze_open_positions`: the raw open-position rows plus the
    PositionAnalyzer aggregate over them. One field per named local variable the original
    inline code carried forward into the cash/equity/concentration/snapshot-insert steps
    further down run_daily_reconciliation().
    """

    positions: list[Any]
    total_position_value: Any  # Decimal, from PositionAnalyzer
    unrealized_pnl: Any  # Decimal, from PositionAnalyzer
    unrealized_pnl_pct: float | None
    winning_count: int
    losing_count: int
    breakeven_count: int


class BrokerPositionSyncMixin:
    """Mixin providing the position-sync and open-position-analysis steps of the
    broker-connected (execution_mode=="auto") branch of run_daily_reconciliation()."""

    def _sync_broker_positions_and_pending(self, cur: PsycopgCursor[Any], reconcile_date: _date_type | None) -> None:
        # 1b. Sync broker positions into our DB (imports any external positions)
        sync_result = self.sync_positions(cur)  # type: ignore[attr-defined]
        logger.info("\n1b. Position Sync:")
        logger.info(f"   {sync_result['message']}")
        if sync_result.get("orphan_symbols"):
            logger.info(f"   Orphans flagged: {', '.join(sync_result['orphan_symbols'][:5])}")

        # 1b2. Reconcile actual fill prices with DB exit records
        fill_result = self.reconcile_exit_fills(cur, reconcile_date)  # type: ignore[attr-defined]
        logger.info("\n1b2. Exit Fill Reconciliation:")
        logger.info(f"   {fill_result['message']}")

        # 1b2b. Fall back to price_daily EOD close for whatever reconcile_exit_fills()
        # couldn't resolve (no broker configured, or a live Alpaca call failed) - see
        # resolve_local_pending_exits()'s docstring. Only touches rows still NULL after
        # the broker attempt above, and only ever uses genuine price_daily data, so this
        # is safe to run unconditionally in every environment: it's a no-op wherever the
        # broker path already succeeded.
        local_fallback_result = self.resolve_local_pending_exits(cur)  # type: ignore[attr-defined]
        if local_fallback_result["resolved"] > 0:
            logger.info("\n1b2b. Local-Mode Exit Fallback:")
            logger.info(f"   {local_fallback_result['message']}")

        # 1b3. Check for trades pending Phase 7 price reconciliation
        pending_result = self.check_pending_reconciliations(cur)  # type: ignore[attr-defined]
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

    def _fetch_and_analyze_open_positions(self, cur: PsycopgCursor[Any]) -> BrokerPositionState:
        # FIXED: Read from algo_trades (source of truth) instead of algo_positions (stale).
        # algo_positions drifts over time; algo_trades is authoritative for open positions.
        # CRITICAL: Fall back to algo_positions.avg_entry_price if algo_trades.entry_price is NULL.
        # This handles backlog of positions created before entry_price was consistently populated.
        # (migration 1104 tried adding a separate algo_positions.entry_price column for this
        # fallback instead, but was never applied to RDS -- production kept crashing with
        # "column ap.entry_price does not exist" every Phase 9 run. avg_entry_price already
        # exists and is the more meaningful cost-basis fallback anyway, so use it directly
        # instead of depending on another migration actually landing.)
        # When price_daily has no entry, current_price must be NULL to indicate missing data.
        # This prevents position_value from being calculated incorrectly (showing 0% gain/loss).
        # BUG FOUND 2026-08-25 (real-money-readiness goal session, sweep for the same
        # bug class as phase1_data_freshness.py's orphaned-position fix): this hand-
        # rolled ('open', 'filled', 'active', 'partially_filled') list silently
        # omitted 'pending'/'paper_pending' from TradeStatus.all_open() - a
        # paper_pending trade (recorded as a real committed position while Alpaca was
        # unreachable, per that status's own definition) was excluded from this
        # position-value/unrealized-P&L reconciliation query with no error, just a
        # quietly incomplete portfolio total. Use TradeStatus.all_open() directly
        # (the single source of truth) instead of a second hand-copied subset.
        cur.execute(
            """
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol) symbol, close as current_price
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            open_trades AS (
                -- CRITICAL FIX (real-money-readiness audit): this used to be a
                -- one-row-per-symbol DISTINCT-ON query ordered by trade_date DESC, which
                -- keeps only the MOST RECENT algo_trades row per symbol. A pyramided
                -- (scaled-in) position - 2+ open algo_trades rows for the same symbol, a real,
                -- supported case per position_sizer.py - silently dropped every earlier leg's
                -- quantity/entry_price. That understated unrealized_pnl/winning_count here and,
                -- via _compute_broker_snapshot_metrics, the concentration/Herfindahl metrics
                -- written to algo_portfolio_snapshots - meaning the concentration circuit-
                -- breaker could be blind to a symbol's true aggregate size. Aggregate all open
                -- legs per symbol instead: sum quantity, cost-basis-weighted average entry
                -- price (matches PositionAnalyzer's own cost-basis-weighted P&L% convention),
                -- one current_price per symbol (same latest_prices join for every leg).
                SELECT at.symbol,
                    SUM(at.entry_quantity) as quantity,
                    SUM(at.entry_quantity * at.entry_price) / NULLIF(SUM(at.entry_quantity), 0) as avg_entry_price,
                    'trade_price' as entry_price_source,
                    MAX(lp.current_price) as current_price,
                    SUM(at.entry_quantity) * MAX(lp.current_price) as position_value
                FROM algo_trades at
                LEFT JOIN latest_prices lp ON at.symbol = lp.symbol
                WHERE at.status = ANY(%s)
                  AND at.exit_date IS NULL
                  AND at.entry_price IS NOT NULL
                  AND at.entry_price > 0
                GROUP BY at.symbol
            )
            SELECT symbol, quantity, avg_entry_price, entry_price_source, current_price, position_value
            FROM open_trades
            WHERE avg_entry_price IS NOT NULL AND avg_entry_price > 0
            ORDER BY symbol
            """,
            (list(TradeStatus.all_open()),),
        )

        positions = cur.fetchall()

        # FAIL-FAST: All trades must have explicit entry_price for accurate P&L
        # Do NOT fall back to position.avg_entry_price (different calculation, corrupts P&L)
        if not positions:
            logger.warning(
                "[RECONCILIATION] No open trades with valid entry_price found. "
                "Either all trades closed or entry_price data missing. P&L calculation skipped for this run."
            )

        # CRITICAL VALIDATION: Check for invalid entry prices that would break P&L calculations
        invalid_entry_prices = []
        for pos in positions:
            symbol = pos[0]
            quantity = pos[1]
            avg_entry_price = pos[2]
            entry_source = pos[3]  # entry_price_source (new column)
            if avg_entry_price is None or float(avg_entry_price) <= 0:
                invalid_entry_prices.append(
                    {
                        "symbol": symbol,
                        "quantity": quantity,
                        "entry_price": avg_entry_price,
                        "entry_price_source": entry_source,
                    }
                )

        if invalid_entry_prices:
            logger.critical(
                f"[RECONCILIATION CRITICAL] {len(invalid_entry_prices)} positions have invalid entry_price (NULL or 0): "
                f"{invalid_entry_prices[:5]}. "
                f"P&L calculations will fail. Check: (1) algo_trades.entry_price, "
                f"(2) algo_positions.entry_price, (3) position creation logic."
            )
            raise ValueError(
                f"CRITICAL: {len(invalid_entry_prices)} positions have invalid entry_price. "
                f"Cannot calculate position values and P&L without entry price. "
                f"See logs for details. May require manual backfill from trade history."
            )

        # Analyze positions using PositionAnalyzer service
        analysis = PositionAnalyzer.analyze_positions(positions)
        PositionAnalyzer.log_position_analysis(analysis, logger)

        return BrokerPositionState(
            positions=positions,
            total_position_value=analysis["total_position_value"],
            unrealized_pnl=analysis["unrealized_pnl"],
            unrealized_pnl_pct=analysis["unrealized_pnl_pct"],
            winning_count=analysis["winning_count"],
            losing_count=analysis["losing_count"],
            breakeven_count=analysis["breakeven_count"],
        )
