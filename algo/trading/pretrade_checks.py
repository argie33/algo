#!/usr/bin/env python3
from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import psycopg2

from algo.risk import EarningsBlackout
from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.trading import TradeStatus

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

"""
Pre-Trade Checks - Hard stops before order execution.

Validates:
- Earnings blackout window (Issue #11 fix)
- Account buying power
- Margin requirements
- Duplicate position prevention
- Exchange/symbol status
- Order size limits
- Sector/industry concentration limits (Issue #2 fix)
"""

logger = logging.getLogger(__name__)


class PreTradeChecks:
    """Validation layer before executing trades."""

    def __init__(
        self,
        config: AlgoConfig | dict[str, Any],
        alpaca_base_url: str | None = None,
        alpaca_key: str | None = None,
        alpaca_secret: str | None = None,
    ):
        """Initialize pre-trade checks with configuration."""
        self.config = config
        self.alpaca_base_url = alpaca_base_url
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret

    def run_all(
        self,
        symbol: str,
        position_value: float,
        portfolio_value: float,
        side: str = "BUY",
        eval_date: _date | None = None,
    ) -> tuple[bool, str | None]:
        """
        Run all pre-trade validation checks.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            position_value: Total position value (shares * price)
            portfolio_value: Current portfolio value
            side: 'BUY' or 'SELL'
            eval_date: Date to evaluate for earnings blackout (default: today)

        Returns:
            (passed: bool, reason: str or None)
            - If passed: (True, None)
            - If failed: (False, "reason for failure")
        """
        if eval_date is None:
            # Eastern Time, not system-local date.today() - eval_date feeds
            # EarningsBlackout.run()'s exact trading-day-based window arithmetic (a
            # documented hard gate), so a server running in a different timezone (UTC in
            # AWS, or anything not America/New_York) could evaluate the blackout window
            # against the wrong calendar day near midnight, off-by-one-trading-day in
            # exactly the boundary cases that matter most. Same bug class fixed 2026-07-21
            # in algo/trading/tca.py's record_fill() and multiple prior sessions elsewhere
            # in this codebase (see git history: "N more date.today()-instead-of-Eastern-
            # Time instances").
            eval_date = datetime.now(EASTERN_TZ).date()

        # Issue #11: Earnings blackout check (hard gate, must pass before any entry)
        if side == "BUY":
            try:
                earnings_check = EarningsBlackout(config=self.config)
                result = earnings_check.run(symbol, eval_date)
                if result is None or not isinstance(result, dict):
                    raise ValueError(
                        f"Earnings blackout check returned invalid result: {type(result).__name__}. "
                        f"Expected dict with 'pass' and 'reason' fields."
                    )
                pass_check = result.get("pass")
                if pass_check is not True:
                    reason = result.get("reason")
                    if reason is None:
                        raise ValueError("Earnings check failed but 'reason' field is missing")
                    return (False, reason)
            except ValueError as e:
                return (False, f"Earnings blackout check failed: {e}")

        try:
            max_position_pct = Decimal(str(self.config["max_position_size_pct"])) / Decimal(100)
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e
        max_position_value = Decimal(str(portfolio_value)) * max_position_pct

        position_value_dec = Decimal(str(position_value))
        if position_value_dec > max_position_value:
            max_value_str = f"{float(max_position_value):.2f}"
            return (
                False,
                f"Position ${position_value:.2f} exceeds max ${max_value_str} ({float(max_position_pct * Decimal(100)):.1f}% of portfolio)",
            )

        try:
            with DatabaseContext("read") as cur:
                # Check 1: Position currently open in algo_positions
                cur.execute(
                    "SELECT symbol FROM algo_positions WHERE symbol = %s AND status = %s LIMIT 1",
                    (symbol, "open"),
                )
                if cur.fetchone():
                    return (False, f"Position already open for {symbol}")

                # Check 1b: Also check algo_trades for open positions (constraint is at algo_trades level)
                # CRITICAL: Database constraint algo_trades_symbol_live_status_idx (migration 1158;
                # supersedes migration 007's status='open'-only index, which never fired for a live
                # fill - see phase8_entry_execution.py's duplicate-gate comment) prevents duplicate
                # non-terminal trades per symbol at the algo_trades table level. Must check here to
                # prevent validation passing when algo_positions and algo_trades are out of sync.
                open_statuses = TradeStatus.all_open()
                cur.execute(
                    f"SELECT trade_id FROM algo_trades WHERE symbol = %s "
                    f"AND status IN ({', '.join(['%s'] * len(open_statuses))}) LIMIT 1",
                    (symbol, *open_statuses),
                )
                if cur.fetchone():
                    return (False, f"Already have open/pending trade for {symbol} in algo_trades")

                # Check 2: Position recently closed (same trading day) - prevent flip-flop entries
                # ISSUE: Without this check, Phase 6 can exit a position and Phase 8 can immediately
                # re-enter it in the same orchestrator run. Re-entry within a few minutes indicates
                # a signal stale issue (buy_sell_daily signal wasn't invalidated after exit).
                # Allow up to 30 minutes (configurable) between close and re-entry to prevent
                # rapid flip-flop trading that increases costs and undermines risk management.
                cur.execute(
                    """
                    SELECT position_id, closed_at FROM algo_positions
                    WHERE symbol = %s AND status = %s AND closed_at IS NOT NULL
                    ORDER BY closed_at DESC LIMIT 1
                    """,
                    (symbol, "closed"),
                )
                recently_closed_row = cur.fetchone()
                if recently_closed_row:
                    pos_id, closed_at = recently_closed_row
                    if closed_at is None:
                        raise ValueError(
                            f"[PRE-TRADE CRITICAL] {symbol}: Position {pos_id} marked closed but closed_at is NULL. "
                            "Cannot evaluate flip-flop cooldown period without close timestamp. "
                            "This indicates database data corruption. Blocking entry to prevent uncontrolled re-entries."
                        )

                    # closed_at is written via SQL `CURRENT_TIMESTAMP`/NOW() into a `timestamp
                    # without time zone` column, so a naive value here is in the DB session's
                    # local wall-clock timezone (utils/bulk_insert_manager.py's documented
                    # convention), not necessarily UTC - confirmed live this session's actual
                    # `SHOW timezone` is America/Chicago, 5+ hours off UTC. Mislabeling it as
                    # UTC via .replace(tzinfo=timezone.utc) silently inflated minutes_since_close
                    # by that offset, which made the flip-flop cooldown below a no-op (a position
                    # closed seconds ago would compute as hours stale, always clearing any
                    # realistic cooldown) - defeating the exact same-run re-entry protection this
                    # check exists for. Same fix as algo/risk/market_exposure.py's cache-age
                    # check and lambda/api/routes/utils.py's normalize_to_utc_datetime: resolve
                    # the real session timezone dynamically instead of assuming UTC.
                    if closed_at.tzinfo is None:
                        cur.execute("SHOW timezone")
                        naive_tz = ZoneInfo(cur.fetchone()[0])
                        closed_at = closed_at.replace(tzinfo=naive_tz)

                    minutes_since_close = (datetime.now(timezone.utc) - closed_at).total_seconds() / 60

                    # CRITICAL: reentry_cooldown_minutes must be explicitly configured
                    # This prevents flip-flop trading (re-entering position immediately after close)
                    # CRITICAL FIX: previously branched on isinstance(self.config, dict) and used
                    # getattr(self.config, "reentry_cooldown_minutes", None) for the non-dict
                    # (real AlgoConfig) case - but AlgoConfig has no such attribute (it stores
                    # values in self._config, exposed via __getitem__/.get(), not per-key Python
                    # attributes), so getattr() always silently returned None regardless of what
                    # was actually configured. Confirmed live 2026-07-27: this made the check
                    # permanently, universally broken (always "config missing") for every real
                    # orchestrator run, not just a missing-seed issue - every other self.config
                    # access in this file already uses subscript/.get() access, which works
                    # correctly for both a plain dict and AlgoConfig.
                    reentry_cooldown_minutes = self.config.get("reentry_cooldown_minutes")

                    if reentry_cooldown_minutes is None:
                        raise ValueError(
                            "[PRE-TRADE CRITICAL] reentry_cooldown_minutes config missing. "
                            "Cannot determine flip-flop prevention period. "
                            "Set explicit reentry_cooldown_minutes in algo_config table (recommended: 30-60 minutes)."
                        )

                    try:
                        reentry_cooldown_minutes = int(reentry_cooldown_minutes)
                        if reentry_cooldown_minutes < 0:
                            raise ValueError("reentry_cooldown_minutes must be non-negative")
                    except (ValueError, TypeError) as e:
                        raise ValueError(
                            f"[PRE-TRADE CRITICAL] reentry_cooldown_minutes is invalid ({reentry_cooldown_minutes}): {e}"
                        ) from e

                    if minutes_since_close < reentry_cooldown_minutes:
                        return (
                            False,
                            f"Position {symbol} closed {minutes_since_close:.0f}m ago, "
                            f"cooldown {reentry_cooldown_minutes}m required (closed_at={closed_at}). "
                            f"Re-entry blocked to prevent flip-flop trading.",
                        )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"[PRE-TRADE] Database error checking duplicate/recent position for {symbol}: {e}")
            raise ValueError(f"Cannot validate duplicate/recent position check for {symbol}: {e}") from e

        try:
            min_order_size = Decimal(str(self.config["min_order_size_dollars"]))
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e
        if position_value_dec < min_order_size:
            min_value_str = f"{float(min_order_size):.2f}"
            return (
                False,
                f"Position value ${position_value:.2f} below minimum ${min_value_str}",
            )

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol FROM stock_symbols WHERE symbol = %s LIMIT 1",
                    (symbol,),
                )
                if not cur.fetchone():
                    return (False, f"Symbol {symbol} not found in universe")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise ValueError(f"Symbol validation unavailable for {symbol}: {e}") from None

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT sector, industry FROM company_profile WHERE symbol = %s LIMIT 1",
                    (symbol,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(
                        f"[PRE-TRADE CRITICAL] {symbol}: company_profile not found. "
                        f"Cannot evaluate sector/industry concentration limits (required risk controls). "
                        f"Blocking entry - load_company_profile must run fresh for all symbols."
                    )

                sector, industry = row

                try:
                    max_sector_positions = int(self.config["max_positions_per_sector"])
                    max_industry_positions = int(self.config["max_positions_per_industry"])
                except KeyError as e:
                    raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

                cur.execute(
                    """SELECT COUNT(*) FROM algo_positions ap
                       LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
                       WHERE ap.status = %s AND cp.sector = %s""",
                    ("open", sector),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(f"Sector count query failed for {sector}")
                sector_count = row[0]
                if sector_count >= max_sector_positions:
                    return (
                        False,
                        f"Sector {sector} at limit ({sector_count}/{max_sector_positions} positions)",
                    )

                cur.execute(
                    """SELECT COUNT(*) FROM algo_positions ap
                       LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
                       WHERE ap.status = %s AND cp.industry = %s""",
                    ("open", industry),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(f"Industry count query failed for {industry}")
                industry_count = row[0]
                if industry_count >= max_industry_positions:
                    return (
                        False,
                        f"Industry {industry} at limit ({industry_count}/{max_industry_positions} positions)",
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"[PRE-TRADE] Database error checking sector/industry concentration for {symbol}: {e}")
            raise ValueError(f"Cannot validate sector/industry limits for {symbol}: {e}") from e

        logger.info(
            f"[PRE-TRADE] {symbol}: position ${position_value:.2f}, "
            f"portfolio ${portfolio_value:.2f}, {side} order approved"
        )
        return (True, None)
