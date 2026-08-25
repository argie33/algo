#!/usr/bin/env python3
from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

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

Does NOT itself validate account buying power or margin requirements (found stale/
inaccurate 2026-08-24 - the docstring here previously claimed both, but no such check
exists in run_all() below; confirmed via full-file grep). `portfolio_value` passed in is
TOTAL account equity (position_sizer.py's get_portfolio_value(), cash + open positions'
market value), not available cash/buying power - the max_position_size_pct check here caps
position size relative to total equity, it does not itself verify enough uncommitted cash
exists to fill the order.

Traced 2026-08-24: the practical cumulative-exposure concern this docstring's claim was
gesturing at IS covered, just in position_sizer.py rather than here -
PositionSizer.size_position()'s max_total_invested_pct check (line ~1130) computes
total_invested = get_active_positions_value() [a fresh DB query, so it reflects any
positions already entered earlier in the same Phase 8 run] + this candidate's position
value, and rejects if that would exceed the configured percentage of total equity. So the
system does prevent over-committing capital across a run; this file just isn't where that
enforcement lives. A hard dollar-for-dollar buying-power/margin check - distinct from the
total-invested-pct cap, which is sized as a percentage of equity, not a check against
actual settled cash - was reactive-only (Alpaca's own order-time rejection was the only
backstop) until 2026-08-25: phase8_entry_execution.py now fetches real Alpaca
`buying_power` once per run (execution_mode=="auto" only, reusing the same fetch_account()
call the PDT check already makes) and proactively rejects/decrements against it per
candidate in the main entry loop, rather than here - same reactive-vs-proactive shape as
the PDT gap fixed the day before (see
pdt_day_trade_limit_reactive_only_not_proactively_enforced_20260824 in memory).
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

                logger.debug(f"[PRETRADE EARNINGS] {symbol} on {eval_date}: {result}")

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

                    # Log the rejection (this is important for debugging why trades are losing)
                    logger.info(f"[PRETRADE EARNINGS BLOCK] {symbol}: {reason}")
                    return (False, reason)
            except ValueError as e:
                # Log the error (not just swallow it)
                logger.error(f"[PRETRADE EARNINGS ERROR] {symbol}: {e}")
                return (False, f"Earnings blackout check failed: {e}")

        try:
            max_position_pct = Decimal(str(self.config["max_position_size_pct"])) / Decimal(100)
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e
        max_position_value = Decimal(str(portfolio_value)) * max_position_pct

        # Add 1% tolerance to account for rounding errors during position sizing calculations
        # (share count * current price may round up due to shares needing whole numbers)
        rounding_tolerance = max_position_value * Decimal("0.01")

        position_value_dec = Decimal(str(position_value))
        if position_value_dec > max_position_value + rounding_tolerance:
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
                    "SELECT trade_id FROM algo_trades WHERE symbol = %s AND status = ANY(%s) LIMIT 1",
                    (symbol, list(open_statuses)),
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

                    # CRITICAL FIX: Only apply cooldown to STOP-OUT or TIME-BASED exits.
                    # Regular closes (manual, concentration limits, profit takes) shouldn't be penalized
                    # with a re-entry cooldown - only the edge cases where the position was forced out
                    # due to risk or time constraints. This allows legitimate re-entry after normal closes
                    # while still preventing flip-flop trading after adverse exit conditions.
                    cur.execute(
                        """
                        SELECT t.exit_reason
                        FROM algo_trades t
                        WHERE t.status = 'closed'
                          AND t.symbol = %s
                        ORDER BY t.exit_date DESC, t.id DESC
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    exit_reason_row = cur.fetchone()
                    exit_reason = exit_reason_row[0] if exit_reason_row else None

                    # Skip cooldown if exit was NOT a stop-out or time-based exit
                    if exit_reason is not None:
                        is_stop_out = "STOP" in exit_reason.upper() or "TIME" in exit_reason.upper()
                        if not is_stop_out:
                            logger.debug(
                                f"[PRE-TRADE] {symbol}: Exit reason '{exit_reason}' is not a stop-out; "
                                f"skipping re-entry cooldown (cooldown only applies after adverse exits)"
                            )
                            return True, None

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
                        from utils.db.timezone_utils import get_db_timezone

                        naive_tz = get_db_timezone()
                        closed_at = closed_at.replace(tzinfo=naive_tz)

                    minutes_since_close = (datetime.now(timezone.utc) - closed_at).total_seconds() / 60

                    # CRITICAL: reentry_cooldown_minutes must be explicitly configured
                    # This prevents flip-flop trading (re-entering position immediately after stop-out)
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
                            f"Position {symbol} stopped out {minutes_since_close:.0f}m ago, "
                            f"cooldown {reentry_cooldown_minutes}m required (closed_at={closed_at}). "
                            f"Re-entry blocked to prevent flip-flop trading after adverse exits.",
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

        # CORRELATION-BASED DIVERSIFICATION (2026-08-25 fix): sector/industry caps above only
        # catch concentration within GICS-style taxonomy - two names in different sectors can
        # still move nearly in lockstep (e.g. high-beta growth names across sectors during a
        # risk-off day), so a book could clear every sector/industry check while still holding
        # several near-duplicate return streams. This is a supplementary check (fails OPEN on
        # insufficient price history, unlike the sector/industry check above), not a
        # replacement for the primary taxonomy-based control.
        try:
            with DatabaseContext("read") as cur:
                corr_ok, corr_reason = self._check_correlation_concentration(symbol, cur)
                if not corr_ok:
                    return (False, corr_reason)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(
                f"[PRE-TRADE] {symbol}: correlation-diversification check unavailable ({e}) - "
                f"failing open (sector/industry caps above remain the primary control)."
            )

        # PORTFOLIO-BETA CAP (2026-08-25 fix): algo/risk/var.py's beta_exposure() already
        # documents "Beta exposure > 2.0 -> WARNING" as this system's own convention, but it
        # only ever fired as a Phase 9 (end-of-cycle) REPORT - nothing previously stopped an
        # entry from being the one that pushes the book over that exact threshold. Same
        # fail-open shape as the correlation check above (stability_metrics.beta coverage is
        # still filling in for some symbols) and reuses var.py's own 2.0 convention rather than
        # inventing a new number.
        try:
            with DatabaseContext("read") as cur:
                beta_ok, beta_reason = self._check_portfolio_beta(
                    symbol, position_value_dec, Decimal(str(portfolio_value)), cur
                )
                if not beta_ok:
                    return (False, beta_reason)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[PRE-TRADE] {symbol}: portfolio-beta check unavailable ({e}) - failing open.")

        logger.info(
            f"[PRE-TRADE] {symbol}: position ${position_value:.2f}, "
            f"portfolio ${portfolio_value:.2f}, {side} order approved"
        )
        return (True, None)

    def _check_correlation_concentration(self, symbol: str, cur: PsycopgCursor[Any]) -> tuple[bool, str | None]:
        """Block a new entry whose daily-return correlation with any currently open position
        exceeds max_position_correlation, over the trailing correlation_lookback_days.

        Supplements (does not replace) the sector/industry position caps above: two names in
        different sectors/industries can still move nearly in lockstep (e.g. high-beta growth
        names across sectors during a risk-off day), so a book could pass every taxonomy check
        while still holding several near-duplicate return streams.

        Fails OPEN (returns True, treats as "no correlation data available", never raises) when
        there are no open positions, or when a pair lacks correlation_min_overlap_days of
        overlapping real price history - unlike the sector/industry check, this is a
        supplementary control, and this codebase's own documented data-maturity gap
        (position_sizer.py's get_data_maturity_multiplier: real full-universe price history is
        still filling in) means blocking entries over a data gap here would be overly
        aggressive for a non-primary check.
        """
        cur.execute("SELECT symbol FROM algo_positions WHERE status = %s", ("open",))
        open_symbols = [r[0] for r in cur.fetchall() if r[0] != symbol]
        if not open_symbols:
            return True, None

        try:
            lookback_days = int(self.config["correlation_lookback_days"])
            min_overlap_days = int(self.config["correlation_min_overlap_days"])
            max_corr = float(self.config["max_position_correlation"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        all_symbols = [symbol, *open_symbols]
        cur.execute(
            """
            SELECT symbol, date, close FROM price_daily
            WHERE symbol = ANY(%s) AND date >= CURRENT_DATE - (%s || ' days')::interval
              AND close IS NOT NULL AND close > 0
            ORDER BY symbol, date
            """,
            (all_symbols, lookback_days),
        )
        closes_by_symbol: dict[str, dict[Any, float]] = {}
        for row_symbol, row_date, row_close in cur.fetchall():
            closes_by_symbol.setdefault(row_symbol, {})[row_date] = float(row_close)

        candidate_closes = closes_by_symbol.get(symbol)
        if not candidate_closes or len(candidate_closes) < min_overlap_days + 1:
            return True, None

        worst_corr: float | None = None
        worst_symbol: str | None = None
        for open_symbol in open_symbols:
            open_closes = closes_by_symbol.get(open_symbol)
            if not open_closes:
                continue
            # Aligned on shared calendar dates only - a reasonable approximation for actively
            # traded equities over a short (default 60d) window, not a full trading-calendar
            # reconciliation; an occasional missing day on one side just slightly widens that
            # one return's window rather than corrupting the whole series.
            common_dates = sorted(set(candidate_closes) & set(open_closes))
            if len(common_dates) < min_overlap_days + 1:
                continue
            candidate_returns = [
                candidate_closes[common_dates[i]] / candidate_closes[common_dates[i - 1]] - 1
                for i in range(1, len(common_dates))
            ]
            open_returns = [
                open_closes[common_dates[i]] / open_closes[common_dates[i - 1]] - 1 for i in range(1, len(common_dates))
            ]
            corr = _pearson_correlation(candidate_returns, open_returns)
            if corr is not None and (worst_corr is None or corr > worst_corr):
                worst_corr, worst_symbol = corr, open_symbol

        if worst_corr is not None and worst_corr >= max_corr:
            return False, (
                f"Correlation {worst_corr:.2f} with open position {worst_symbol} exceeds "
                f"{max_corr:.2f} limit (over {lookback_days}d lookback) - diversification check"
            )
        return True, None

    def _check_portfolio_beta(
        self, symbol: str, position_value: Decimal, portfolio_value: Decimal, cur: PsycopgCursor[Any]
    ) -> tuple[bool, str | None]:
        """Block a new entry that would push the position-value-weighted portfolio beta above
        max_portfolio_beta, reusing the same 2.0 convention var.py's beta_exposure() already
        documents for its (previously report-only) WARNING threshold.

        Fails OPEN (never blocks) when the candidate's own beta is unavailable, or when ANY
        currently open position lacks a beta reading - deliberately does not silently drop
        unknown-beta positions from a partial weighted average, since that could understate or
        overstate the true portfolio beta in either direction depending on which positions
        happen to be missing data. stability_metrics.beta coverage, like the correlation
        check's price-history requirement, is still filling in for some symbols (this
        codebase's own documented data-maturity gap - position_sizer.py's
        get_data_maturity_multiplier).
        """
        cur.execute("SELECT beta FROM stability_metrics WHERE symbol = %s AND data_unavailable IS NOT TRUE", (symbol,))
        row = cur.fetchone()
        if row is None or row[0] is None:
            return True, None
        candidate_beta = float(row[0])

        cur.execute("SELECT symbol, quantity, current_price FROM algo_positions WHERE status = %s", ("open",))
        open_positions = [r for r in cur.fetchall() if r[1] is not None and r[2] is not None]
        if not open_positions:
            # No existing book to weight against - candidate's own beta alone can't breach a
            # portfolio-level cap by definition (assuming a sane max_portfolio_beta >= 1.0).
            return True, None

        cur.execute(
            "SELECT symbol, beta FROM stability_metrics WHERE symbol = ANY(%s) AND data_unavailable IS NOT TRUE",
            ([p[0] for p in open_positions],),
        )
        beta_by_symbol = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

        missing = [p[0] for p in open_positions if p[0] not in beta_by_symbol]
        if missing:
            return True, None

        existing_value = sum(Decimal(str(qty)) * Decimal(str(price)) for _, qty, price in open_positions)
        existing_weighted_beta = sum(
            Decimal(str(qty)) * Decimal(str(price)) * Decimal(str(beta_by_symbol[pos_symbol]))
            for pos_symbol, qty, price in open_positions
        )
        total_value = existing_value + position_value
        if total_value <= 0:
            return True, None

        portfolio_beta_after = float(
            (existing_weighted_beta + position_value * Decimal(str(candidate_beta))) / total_value
        )

        try:
            max_portfolio_beta = float(self.config["max_portfolio_beta"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        if portfolio_beta_after > max_portfolio_beta:
            return False, (
                f"Entry would push portfolio beta to {portfolio_beta_after:.2f}, exceeding "
                f"{max_portfolio_beta:.2f} limit (candidate beta {candidate_beta:.2f}) - risk-management check"
            )
        return True, None


def _pearson_correlation(returns_a: list[float], returns_b: list[float]) -> float | None:
    """Pearson correlation between two equal-length return series.

    Returns None (caller must treat as "no signal", not "zero correlation") when the series
    are too short or either has zero variance (a flat/constant series has undefined
    correlation, not a real 0.0 reading).
    """
    if len(returns_a) != len(returns_b) or len(returns_a) < 2:
        return None
    import numpy as np

    a = np.asarray(returns_a, dtype=float)
    b = np.asarray(returns_b, dtype=float)
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])
