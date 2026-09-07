#!/usr/bin/env python3
"""
Position Sizer - Calculates trade size based on risk management rules

Rules:
- Base risk: 0.75% of portfolio per trade
- Drawdown defense: reduce risk at -5%, -10%, -15%, -20%
- Max position size: 8% of portfolio
- Max concentration: 50% in single position
- Max positions: 12 concurrent
"""

from __future__ import annotations

import decimal
import logging
import os
import time
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure import get_alpaca_timeout
from algo.infrastructure.market_calendar import MarketCalendar
from algo.trading.exceptions import (
    ConfigurationError,
    DatabaseError,
    DataUnavailableError,
    PortfolioValueError,
)
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

PORTFOLIO_SNAPSHOT_LOCK_ID = 2147483647

# A degraded-but-200-OK Alpaca /v2/account response (stale cache, wrong account payload,
# a decimal-place shift on their side) is otherwise indistinguishable from a real value -
# no HTTP error to retry on, no exception to catch. Bound any single fetch against the last
# known-good snapshot: a real trading account cannot lose >90% or gain >10x in one fetch
# (circuit_breaker.py's own 20% portfolio-drawdown halt would have already stopped trading
# long before a real loss got anywhere near this floor), so anything outside this band is
# treated as a broker-side data error, not a real portfolio move.
ALPACA_EQUITY_MIN_RATIO_VS_LAST_SNAPSHOT = Decimal("0.10")
ALPACA_EQUITY_MAX_RATIO_VS_LAST_SNAPSHOT = Decimal("10")


class PositionSizer:
    def __init__(self, config: dict[str, Any]) -> None:
        if config is None:
            raise ValueError("PositionSizer config cannot be None")
        if not isinstance(config, dict):
            raise TypeError(f"PositionSizer config must be a dict, got {type(config).__name__}")
        self.config = config

        required_config_keys = [
            "base_risk_pct",
            "max_positions",
            "risk_reduction_at_minus_5",
            "risk_reduction_at_minus_10",
            "risk_reduction_at_minus_15",
            # CRITICAL FIX: get_risk_adjustment() below reads risk_reduction_at_minus_20 for
            # the >= 20% drawdown circuit breaker (its own docstring even claims "Config keys
            # validated at init" - this key wasn't), but it was missing from this list, so a
            # missing/deleted DB row would pass construction silently and only raise KeyError
            # deep inside get_risk_adjustment() at the exact moment a portfolio hits a -20%
            # drawdown - the worst possible time for a validation gap to surface.
            "risk_reduction_at_minus_20",
            "vix_caution_threshold",
            "vix_max_threshold",
            "vix_caution_risk_reduction",
            # CRITICAL FIX (Session Date): max_position_size_pct and max_concentration_pct are
            # required for position sizing enforcement. max_position_size_pct is the hard cap
            # on individual positions (e.g. 6-8% of portfolio). max_concentration_pct is the
            # exposure-policy-driven limit (varies by market regime 10-20%). Missing either
            # means position sizing constraints cannot be enforced - must fail-fast.
            "max_position_size_pct",
            "max_concentration_pct",
            "max_total_invested_pct",
            # CRITICAL FIX 2026-08-06: max_total_risk_pct was hardcoded to 4% despite config
            # setting it to 8%. This caused Phase 8 to report 8% limit but sizer use 4%,
            # exhausting capacity immediately (3.99% actual vs 4% limit = $4 remaining).
            # Must read from config to stay in sync with circuit breaker and Phase 8.
            "max_total_risk_pct",
        ]
        missing_keys = [k for k in required_config_keys if k not in config or config[k] is None]
        if missing_keys:
            raise ConfigurationError(
                f"CRITICAL: PositionSizer config missing required keys: {', '.join(missing_keys)}. "
                f"Cannot proceed with position sizing without explicit risk configuration."
            )

        # Cache for get_data_maturity_multiplier(): a system-wide constant (same real/synthetic
        # split for every symbol - see that method's docstring), not per-symbol like
        # exposure_mult/vix_mult. Phase 8 constructs one PositionSizer per run and reuses it
        # across every symbol sized that run, so caching here avoids re-running an expensive
        # full-table price_daily GROUP BY once per symbol for a value that cannot change within
        # a single run.
        self._data_maturity_mult_cache: Decimal | None = None

    def _calculate_trading_days_elapsed(self, start_date: _date, end_date: _date) -> int:
        """Count the number of trading days elapsed between two dates (inclusive of start, exclusive of end).

        Uses MarketCalendar to determine trading days, avoiding false positives on weekends/holidays.
        For example: Friday to Monday = 1 trading day (Mon is a new trading day, Fri->Mon is only Fri's day).

        Args:
            start_date: Start date (e.g., snapshot_date)
            end_date: End date (e.g., current_date)

        Returns:
            Number of trading days elapsed (0 if same day, 1 if next trading day, etc.)
        """
        if start_date >= end_date:
            return 0

        trading_days = 0
        current = start_date

        # Iterate from start to end, counting trading days
        # Start from the day after start_date to count elapsed days
        current += timedelta(days=1)
        while current <= end_date:
            if MarketCalendar.is_trading_day(current):
                trading_days += 1
            current += timedelta(days=1)

        return trading_days

    def _with_cursor(self, operation: Callable[[Any], Any]) -> Any:
        """Execute an operation with a database cursor."""
        with DatabaseContext("read") as cur:
            return operation(cur)

    def get_portfolio_value(self) -> Decimal:
        """Get current portfolio value.

        Priority:
        1. Live Alpaca account (most accurate, for live trading)
        2. Latest portfolio snapshot (for paper mode / when Alpaca unavailable)

        CRITICAL: Does NOT fall back to default $100k. If neither is available,
        raises RuntimeError to fail-closed. Position sizing requires accurate
        portfolio value - guessing is worse than not trading.

        THREAD SAFETY: Uses PostgreSQL advisory lock to prevent race condition
        where Phase 6 (position sizing) reads while Phase 7 (reconciliation) updates.
        """
        try:
            alpaca_value = self._fetch_live_alpaca_equity()
            if alpaca_value is not None:
                logger.info(f"[PORTFOLIO] Using live Alpaca value: ${alpaca_value:,.2f}")
                return alpaca_value
        except RuntimeError as e:
            # CRITICAL: Never silently fall back to portfolio snapshot when Alpaca fails
            # Position sizing MUST use live portfolio value. Stale data is worse than not trading.
            logger.critical(
                f"[POSITION_SIZER] CRITICAL: Alpaca portfolio value unavailable: {e!s}. "
                f"Cannot proceed with position sizing using stale snapshot. Halting phase execution."
            )
            raise PortfolioValueError(
                f"Portfolio value fetch failed and fallback snapshot is stale. "
                f"Alpaca unavailable: {str(e)[:200]}. Position sizing halted."
            ) from e

        def fetch_snapshot(cur: PsycopgCursor[Any]) -> Any:
            cur.execute("SELECT pg_advisory_lock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))
            cur.fetchone()
            try:
                # CRITICAL FIX 2026-08-09: bound by CURRENT_DATE - an unbounded "latest
                # snapshot" query picks up any stray future-dated row (e.g. a leftover
                # local --date simulation snapshot in the shared dev DB) ahead of the
                # real current one. Live-reproduced: a leftover 2026-08-11 test snapshot
                # outranked the real current snapshot in this exact query (see
                # algo/risk/circuit_breaker.py and phase8_entry_execution.py for the
                # same bug class, fixed there by binding to the caller's run_date - this
                # function has no run_date in scope, so CURRENT_DATE is the correct bound).
                cur.execute("""
                    SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= CURRENT_DATE
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                return cur.fetchone()
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))

        try:
            result = self._with_cursor(fetch_snapshot)
            if result is not None and result[0] is not None:
                snapshot_value = Decimal(str(result[0]))
                snapshot_date = result[1]
                if snapshot_date is None:
                    raise PortfolioValueError(
                        "Portfolio snapshot date is NULL. Cannot calculate staleness without timestamp. "
                        "Check that Phase 7 reconciliation is updating portfolio snapshots."
                    )
                # FIXED (Session 281): Use trading day logic instead of calendar days
                # Calendar days false-positive on weekends (Fri snapshot = 3 calendar days old on Mon)
                # but only 2 trading days old (Fri + Mon = 2 trading days elapsed)
                # Eastern Time, not system-local date.today() - same bug class already fixed
                # elsewhere in this codebase this session (pretrade_checks.py, regime_manager.py).
                # A wrong "today" near the midnight-ET boundary could misjudge snapshot staleness
                # by a day either direction, feeding position sizing off a value that's either
                # spuriously halted or wrongly accepted as fresh.
                today_et = _datetime.now(EASTERN_TZ).date()
                calendar_age = (today_et - snapshot_date).days
                trading_age = self._calculate_trading_days_elapsed(snapshot_date, today_et)

                if trading_age <= 1:
                    logger.info(
                        f"[PORTFOLIO] Using snapshot from {trading_age}d ago (trading days, {calendar_age}d calendar): ${snapshot_value:,.2f}"
                    )
                    # Edge case: 0 days = current snapshot (normal case)
                    # Edge case: 1 day = yesterday's data (acceptable, position sizing proceeds)
                    if trading_age == 0:
                        logger.debug("[PORTFOLIO_SNAPSHOT] Using current trading day snapshot (latest available)")
                    elif trading_age == 1:
                        logger.warning(
                            "[PORTFOLIO_SNAPSHOT] Using yesterday's snapshot (Phase 7 may have missed today)"
                        )
                    return snapshot_value
                # CRITICAL: Snapshot is too stale. Stricter 1-trading-day threshold prevents position
                # sizing on multi-day-old data when Phase 7 fails. Better to halt than risk
                # thousands of dollars in wrong position sizes.
                # Log edge cases: negative age_days or very old data
                if trading_age < 0:
                    logger.critical(
                        f"[PORTFOLIO_SNAPSHOT CRITICAL] Snapshot date in future ({trading_age}d): {snapshot_date}. "
                        "Clock skew detected or snapshot timestamp corrupted."
                    )
                else:
                    logger.critical(
                        f"[PORTFOLIO_SNAPSHOT CRITICAL] Snapshot too stale ({trading_age}d old, trading days). "
                        f"Phase 7 (reconciliation) must run daily. Last successful Phase 7 run: {snapshot_date}"
                    )
                error_msg = (
                    f"Portfolio snapshot too stale ({trading_age}d old trading days, threshold 1 day). "
                    "Phase 7 must run daily. Position sizing halted."
                )
                logger.critical(error_msg)
                raise PortfolioValueError(error_msg)
        except PortfolioValueError:
            raise
        except DatabaseError as e:
            logger.error(f"Database error fetching portfolio snapshot: {e}")
            raise PortfolioValueError(f"Portfolio snapshot unavailable due to database error: {e}") from e
        except (ValueError, RuntimeError) as e:
            logger.error(f"Error processing portfolio snapshot: {e}")
            raise PortfolioValueError(f"Portfolio snapshot processing failed: {e}") from e

        # CRITICAL: No valid portfolio value available. Fail-closed.
        error_msg = (
            "CRITICAL: Portfolio value unavailable. "
            "Cannot execute trades without knowing account size. "
            "Check: (1) Is Alpaca API reachable? (2) Did Phase 7 run yesterday? "
            "(3) Is there a recent portfolio snapshot in the database? "
            "Phase 6 entry execution will be halted."
        )
        logger.critical(error_msg)
        raise PortfolioValueError(error_msg)

    def _last_known_portfolio_snapshot_value(self) -> Decimal | None:
        """Best-effort read of the most recent snapshot, for sanity-bounding a live Alpaca fetch.

        Deliberately does not take PORTFOLIO_SNAPSHOT_LOCK_ID (this is an advisory comparison,
        not the authoritative read) and swallows DB errors - the caller must not let a sanity
        check that can't complete block the primary fetch from succeeding.
        """
        try:

            def fetch(cur: PsycopgCursor[Any]) -> Any:
                cur.execute(
                    "SELECT total_portfolio_value FROM algo_portfolio_snapshots "
                    "WHERE snapshot_date <= CURRENT_DATE AND total_portfolio_value IS NOT NULL "
                    "ORDER BY snapshot_date DESC LIMIT 1"
                )
                return cur.fetchone()

            result = self._with_cursor(fetch)
            if result is not None and result[0] is not None:
                return Decimal(str(result[0]))
        except Exception as e:
            logger.debug(f"[POSITION_SIZER] Could not fetch last snapshot for equity sanity check: {e}")
        return None

    def _validate_alpaca_equity(self, raw_value: Any) -> Decimal:
        """Reject a live Alpaca equity/portfolio_value that is implausible on its face or
        wildly inconsistent with the last known snapshot - a degraded-but-200-OK broker
        response (stale cache, wrong account, decimal-shift bug) has no HTTP error or
        exception to catch it otherwise. See ALPACA_EQUITY_MIN/MAX_RATIO_VS_LAST_SNAPSHOT.
        """
        try:
            value = Decimal(str(raw_value))
        except (InvalidOperation, ValueError, TypeError) as e:
            raise RuntimeError(
                f"[POSITION_SIZER] CRITICAL: Alpaca returned a non-numeric portfolio value "
                f"({raw_value!r}): {e}. Treating as a degraded broker response, not a real value."
            ) from e

        if not value.is_finite() or value <= 0:
            raise RuntimeError(
                f"[POSITION_SIZER] CRITICAL: Alpaca returned an implausible portfolio value "
                f"({value}). A funded live account can never report zero, negative, NaN, or "
                f"infinite equity - treating as a degraded broker response, not a real value."
            )

        last_known = self._last_known_portfolio_snapshot_value()
        if last_known is not None and last_known > 0:
            ratio = value / last_known
            if ratio < ALPACA_EQUITY_MIN_RATIO_VS_LAST_SNAPSHOT or ratio > ALPACA_EQUITY_MAX_RATIO_VS_LAST_SNAPSHOT:
                raise RuntimeError(
                    f"[POSITION_SIZER] CRITICAL: Alpaca-reported equity (${value:,.2f}) is "
                    f"{ratio:.2f}x the last known portfolio snapshot (${last_known:,.2f}) - "
                    f"outside the [{ALPACA_EQUITY_MIN_RATIO_VS_LAST_SNAPSHOT}, "
                    f"{ALPACA_EQUITY_MAX_RATIO_VS_LAST_SNAPSHOT}] plausible band. Treating as a "
                    f"degraded broker response (stale cache / wrong account / data corruption), "
                    f"not a real portfolio move - no real trading day moves equity this much. "
                    f"If this is a genuine capital deposit/withdrawal, record it via "
                    f"scripts/record_capital_flow.py first so the snapshot baseline reflects it."
                )

        return value

    def _fetch_live_alpaca_equity(self) -> Decimal:
        execution_mode = self.config.get("execution_mode")
        if execution_mode is None:
            raise RuntimeError(
                "[POSITION_SIZER CRITICAL] execution_mode config missing. "
                "Cannot determine whether to fetch live Alpaca data or use paper mode snapshot. "
                "Set explicit execution_mode in algo_config table (values: 'auto' for live, 'paper' for sim)."
            )

        # CRITICAL: "auto" is this system's real live-trading mode (the only mode that
        # actually contacts the Alpaca API - confirmed via executor.py/_submit_and_validate_order,
        # which never sends real orders for paper/dry/review). Including "auto" here meant this
        # function - whose entire purpose is fetching LIVE Alpaca equity, and whose caller
        # (get_portfolio_value) documents "Priority 1: Live Alpaca account (most accurate, for
        # live trading)" - unconditionally skipped the real API call below (lines further down,
        # a fully-implemented retry-hardened /v2/account fetch) for every live trade and used a
        # potentially stale algo_portfolio_snapshots row instead (last written whenever Phase 9
        # reconciliation last ran, not reflecting same-day trading activity or capital flows).
        # Position sizing for real money was computed off stale data on every single live trade.
        # Same bug class, same fix, as executor_entry_handler.py's order-rejection fix this
        # session - scope the DB-snapshot fallback to paper/dry modes only. review/auto modes
        # now correctly reach the real Alpaca API call below regardless of whether the
        # configured Alpaca account itself is live or Alpaca's own paper-trading endpoint (that
        # is controlled by credentials/base URL, a separate concern from execution_mode).
        if execution_mode in ("paper", "dry"):
            try:
                from utils.db.context import DatabaseContext

                with DatabaseContext("read") as cur:
                    # CRITICAL FIX 2026-08-09: bound by CURRENT_DATE - see fetch_snapshot()
                    # above for why an unbounded "latest snapshot" query is unsafe.
                    cur.execute(
                        "SELECT total_portfolio_value FROM algo_portfolio_snapshots "
                        "WHERE snapshot_date <= CURRENT_DATE ORDER BY snapshot_date DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        logger.debug(f"[POSITION_SIZER] Paper mode: using portfolio snapshot value {row[0]}")
                        return Decimal(str(row[0]))
                # No snapshot - use configured initial capital
                initial_capital = self.config.get("initial_capital_paper_trading")
                if not initial_capital:
                    raise RuntimeError(
                        "[POSITION_SIZER] CRITICAL: No portfolio snapshot available and "
                        "initial_capital_paper_trading not configured. "
                        "Set initial_capital_paper_trading in algo_config table."
                    )
                logger.warning(
                    f"[POSITION_SIZER] No portfolio snapshot found. "
                    f"Using configured initial_capital_paper_trading=${initial_capital:.2f}"
                )
                return Decimal(str(initial_capital))
            except RuntimeError:
                raise
            except Exception as db_err:
                initial_capital = self.config.get("initial_capital_paper_trading")
                if not initial_capital:
                    raise RuntimeError(
                        f"[POSITION_SIZER] CRITICAL: Paper mode portfolio lookup failed ({db_err}) and "
                        "initial_capital_paper_trading not configured. "
                        "Set initial_capital_paper_trading in algo_config table."
                    ) from db_err
                logger.warning(
                    f"[POSITION_SIZER] Paper mode portfolio lookup failed: {db_err}. "
                    f"Using configured initial_capital_paper_trading=${initial_capital:.2f}"
                )
                return Decimal(str(initial_capital))

        # Live mode: attempt Alpaca API call
        key = None
        secret = None

        try:
            from algo.config.credential_manager import get_credential_manager as _get_cm

            _creds = _get_cm().get_alpaca_credentials()
            key = _creds.get("key")
            secret = _creds.get("secret")
        except (ImportError, AttributeError, ValueError) as e:
            logger.error(f"[POSITION_SIZER] Alpaca credentials unavailable in live mode: {type(e).__name__}")
            raise RuntimeError(f"Live mode requires Alpaca credentials: {e}") from e

        base = os.getenv("APCA_API_BASE_URL")
        if not base:
            try:
                from algo.config.api_endpoints import get_alpaca_base_url

                base = get_alpaca_base_url(execution_mode)
            except (ImportError, AttributeError) as cfg_e:
                raise ValueError(f"Alpaca config unavailable: {cfg_e}") from cfg_e
        if not key or not secret:
            raise RuntimeError("CRITICAL: Alpaca credentials not found. Cannot fetch portfolio value.")

        max_retries_val = self.config.get("alpaca_portfolio_fetch_retries")
        if max_retries_val is None:
            raise RuntimeError(
                "[POSITION_SIZER CRITICAL] alpaca_portfolio_fetch_retries config missing. "
                "Cannot determine retry policy for Alpaca API calls. "
                "Set explicit alpaca_portfolio_fetch_retries in algo_config table."
            )
        try:
            max_retries = int(max_retries_val)
            if max_retries <= 0:
                raise ValueError(f"max_retries must be positive, got {max_retries}")
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[POSITION_SIZER CRITICAL] alpaca_portfolio_fetch_retries is invalid ({max_retries_val}): {e}. "
                "Must be a positive integer."
            ) from e
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"{base}/v2/account",
                    headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                    timeout=get_alpaca_timeout(),
                )
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as e:
                        raise RuntimeError(f"Invalid JSON response from Alpaca portfolio API: {e}") from e

                    if "portfolio_value" in data and data["portfolio_value"] is not None:
                        pv = data["portfolio_value"]
                        return self._validate_alpaca_equity(pv)

                    if "equity" in data and data["equity"] is not None:
                        pv = data["equity"]
                        return self._validate_alpaca_equity(pv)

                    raise ValueError(
                        f"Portfolio value fields missing or null in Alpaca response. Expected 'portfolio_value' or 'equity', got: {list(data.keys())}"
                    )
                elif response.status_code in (429, 503):
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.debug(
                            f"Alpaca API rate limited/unavailable (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(
                        f"Alpaca API unavailable after {max_retries} attempts (status {response.status_code})"
                    )
                else:
                    raise RuntimeError(f"Alpaca portfolio API error (status {response.status_code})")
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.debug(
                        f"Alpaca API transient error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"Portfolio value retrieval failed after {max_retries} attempts: {e}") from e
            except RuntimeError:
                raise
            except requests.RequestException as e:
                raise RuntimeError(f"Alpaca API error: {type(e).__name__}: {e}") from e
        # Should never reach here (all paths raise or return above)
        raise RuntimeError("CRITICAL: Alpaca portfolio value retrieval exhausted all retries without a result.")

    def get_current_drawdown(self) -> Decimal:
        """Calculate current drawdown from peak.

        Fails fast  -" raises if any data missing. Position sizing requires accurate
        drawdown to adjust risk multiplier correctly. Guessing is worse than not trading.

        Uses adjusted_equity/cash-flow-adjusted peak (migration 1134), NOT raw
        total_portfolio_value. Raw equity moves for two different reasons: trading
        performance AND external capital flows (deposits/withdrawals). A withdrawal
        looks identical to a trading loss in the raw series - this is the same bug
        migration 1134 fixed in algo/risk/circuit_breaker.py's drawdown check; this
        method must use the same cash-flow-adjusted series so a withdrawal cannot
        trip the 5/10/15/20% risk-reduction tiers below (get_risk_adjustment) or
        the 20% halt as if it were a real trading loss.
        """

        def calc_drawdown(cur: PsycopgCursor[Any]) -> Decimal:
            cur.execute("SELECT COUNT(*) FROM algo_portfolio_snapshots WHERE adjusted_equity IS NOT NULL")
            count_result = cur.fetchone()
            if count_result is None or len(count_result) < 1 or count_result[0] is None or count_result[0] == 0:
                raise RuntimeError(
                    "No portfolio snapshots with adjusted_equity found. Phase 7 must run daily to maintain "
                    "drawdown tracking, and scripts/record_capital_flow.py must have backfilled adjusted_equity."
                )

            # CRITICAL FIX 2026-08-09: bound the "current" subquery by CURRENT_DATE - see
            # fetch_snapshot() above for why an unbounded "latest snapshot" query is
            # unsafe. MAX(adjusted_equity) for the peak stays unbounded (all-time high).
            cur.execute("""
                SELECT
                    MAX(adjusted_equity) as peak,
                    (SELECT adjusted_equity FROM algo_portfolio_snapshots
                     WHERE adjusted_equity IS NOT NULL AND snapshot_date <= CURRENT_DATE
                     ORDER BY snapshot_date DESC LIMIT 1) as current
                FROM algo_portfolio_snapshots
                WHERE adjusted_equity IS NOT NULL
            """)
            result = cur.fetchone()
            if result is None or len(result) < 2 or result[0] is None or result[1] is None:
                raise RuntimeError(
                    "Portfolio snapshot data inconsistent. Cannot calculate drawdown for position sizing."
                )

            peak = Decimal(str(result[0]))
            current = Decimal(str(result[1]))
            if peak == 0:
                raise RuntimeError("Peak adjusted equity is zero. Portfolio snapshots data is invalid.")

            drawdown_pct = ((peak - current) / peak) * Decimal(100)
            return max(Decimal(0), drawdown_pct)

        result: Decimal | int | float = self._with_cursor(calc_drawdown)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError(
            "Could not fetch drawdown from database. Cannot calculate risk adjustment for position sizing."
        )

    def get_risk_adjustment(self) -> Decimal:
        """Get risk adjustment factor based on drawdown.

        Combined with market_exposure_pct multiplier for dynamic risk:
            effective_risk = base_risk x dd_adjustment x (exposure_pct / 100)

        Config keys validated at init; assumes all risk thresholds are present.
        """
        dd = self.get_current_drawdown()

        if dd >= 20:
            val = self.config.get("risk_reduction_at_minus_20")
            if val is None:
                raise KeyError("[POSITION_SIZER] Config missing 'risk_reduction_at_minus_20'")
            risk_mult = Decimal(str(val))
            if risk_mult == 0:
                logger.critical(
                    "CIRCUIT BREAKER TRIGGERED: Portfolio drawdown >= 20%. "
                    "Position sizing halted. All entries blocked until recovery."
                )
            return risk_mult
        elif dd >= 15:
            val = self.config.get("risk_reduction_at_minus_15")
            if val is None:
                raise KeyError("[POSITION_SIZER] Config missing 'risk_reduction_at_minus_15'")
            return Decimal(str(val))
        elif dd >= 10:
            val = self.config.get("risk_reduction_at_minus_10")
            if val is None:
                raise KeyError("[POSITION_SIZER] Config missing 'risk_reduction_at_minus_10'")
            return Decimal(str(val))
        elif dd >= 5:
            val = self.config.get("risk_reduction_at_minus_5")
            if val is None:
                raise KeyError("[POSITION_SIZER] Config missing 'risk_reduction_at_minus_5'")
            return Decimal(str(val))
        else:
            return Decimal(1)

    def get_market_exposure_multiplier(self) -> Decimal:
        """Look up the most recent market exposure pct (0-100). Returns multiplier 0.0-1.0.

        Fail-fast  -" if data unavailable or stale (>1 day old). Position sizing requires
        current market exposure to avoid over-committing during risk-off periods.
        """

        def fetch_exposure(cur: PsycopgCursor[Any]) -> Decimal:
            # GOVERNANCE: Must check data_unavailable flag before using exposure data
            # Position size depends critically on accurate market exposure assessment
            cur.execute(
                "SELECT exposure_pct, date, data_unavailable, reason FROM market_exposure_daily ORDER BY date DESC LIMIT 1"
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                raise ValueError("Market exposure data unavailable. Phase must run daily to maintain this.")
            if len(row) < 4:
                raise ValueError(
                    f"Market exposure query returned {len(row)} columns instead of expected 4. "
                    f"Schema mismatch in market_exposure_daily table."
                )
            exposure_pct, data_date, data_unavailable, reason = row[0], row[1], row[2], row[3]
            # GOVERNANCE ENFORCEMENT: Fail-fast if data marked unavailable
            if data_unavailable:
                if not reason:
                    logger.critical(
                        f"[POSITION SIZER CRITICAL] Market exposure marked unavailable but reason field is empty. "
                        f"Reason value: {reason!r}. "
                        f"Cannot determine why market exposure is unavailable. Check market_exposure_daily loader."
                    )
                    raise ValueError(
                        "Market exposure marked unavailable but reason field missing or empty. "
                        "Cannot proceed with position sizing. Data quality issue in market exposure data."
                    )
                raise ValueError(
                    f"Market exposure marked unavailable (reason: {reason}). "
                    f"Cannot calculate safe position size without valid market exposure analysis."
                )
            # FIXED (Session 281): Use trading day logic instead of calendar days
            # Eastern Time, not system-local date.today() - see get_portfolio_value() above.
            today_et = _datetime.now(EASTERN_TZ).date()
            calendar_age = (today_et - data_date).days
            trading_age = self._calculate_trading_days_elapsed(data_date, today_et)
            if trading_age > 1:
                raise ValueError(
                    f"Market exposure data too stale: {trading_age} trading days old (max 1 day, {calendar_age}d calendar). "
                    f"Loader must run to provide fresh market exposure for position sizing."
                )
            return Decimal(str(exposure_pct)) / Decimal(100)

        result: Decimal | int | float = self._with_cursor(fetch_exposure)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError("Could not fetch market exposure from database. Cannot calculate safe position size.")

    def get_vix_caution_multiplier(self) -> Decimal:
        """Reduce risk if VIX is in caution zone (caution_threshold < VIX < max_threshold).

        Returns risk multiplier: 1.0 if VIX is normal, reduced multiplier if in caution zone.
        Fail-fast if data unavailable or stale (>1 day old), raises exception.

        VIX thresholds validated at init; assumes all config keys are present.
        """

        def fetch_vix(cur: PsycopgCursor[Any]) -> Decimal:
            cur.execute(
                "SELECT vix_level, date FROM market_health_daily WHERE vix_level IS NOT NULL ORDER BY date DESC LIMIT 1"
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                raise ValueError(
                    "VIX level unavailable from market_health_daily. Cannot adjust position size for volatility."
                )
            if len(row) < 2:
                raise ValueError(
                    f"VIX query returned {len(row)} columns instead of expected 2. "
                    f"Schema mismatch in market_health_daily table."
                )
            data_date = row[1]
            # Eastern Time, not system-local date.today() - see get_portfolio_value() above.
            today = _datetime.now(EASTERN_TZ).date()
            calendar_days_old = (today - data_date).days

            trading_days_old = 0
            if calendar_days_old > 0:
                check_date = data_date
                while check_date < today:
                    check_date += timedelta(days=1)
                    if MarketCalendar.is_trading_day(check_date):
                        trading_days_old += 1

            if trading_days_old > 1:
                raise ValueError(
                    f"VIX data too stale: {trading_days_old} trading days old (max 1 trading day). "
                    f"Volatility protection requires fresh VIX data from last trading day."
                )
            vix = Decimal(str(row[0]))
            caution_threshold_val = self.config.get("vix_caution_threshold")
            if caution_threshold_val is None:
                raise KeyError("[POSITION_SIZER] Config missing 'vix_caution_threshold'")
            max_threshold_val = self.config.get("vix_max_threshold")
            if max_threshold_val is None:
                raise KeyError("[POSITION_SIZER] Config missing 'vix_max_threshold'")
            caution_threshold = Decimal(str(caution_threshold_val))
            max_threshold = Decimal(str(max_threshold_val))
            if vix > caution_threshold and vix <= max_threshold:
                vix_reduction_val = self.config.get("vix_caution_risk_reduction")
                if vix_reduction_val is None:
                    raise KeyError("[POSITION_SIZER] Config missing 'vix_caution_risk_reduction'")
                return Decimal(str(vix_reduction_val))
            return Decimal(1)

        result: Decimal | int | float = self._with_cursor(fetch_vix)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError("Could not fetch VIX from database. Cannot calculate safe position size.")

    def get_data_maturity_multiplier(self) -> Decimal:
        """Discount risk while long-lookback technical indicators (roc_252d, beta,
        volatility_252d, max_drawdown_1y) are still substantially built on the
        pre-2026-05-26 bulk historical price_daily seed rather than real, incrementally
        loaded data.

        FOUND 2026-08-24 (real-money-readiness goal session): scripts/check_synthetic_price_data.py
        already documents that a one-time bulk seed covers ~90% of price_daily
        (2021-05-18 .. 2026-05-22), and full-universe real collection only began
        2026-07-16. As of this fix, only ~21 of the 252 real trading days a full-year
        lookback needs have accumulated. The only existing guard
        (ROC_OVERFLOW_SKIP/CLIP in loaders/load_technical_indicators.py) catches just the
        most extreme seed-period corruption - values large enough to overflow
        NUMERIC(14,4) (live-confirmed on BRID/CGTL/BYFC). Anything less extreme still
        silently drives momentum/trend scores and position sizing at full confidence
        today, with zero visibility anywhere in scoring or risk. No amount of re-fetching
        fixes this - it closes only as real trading days accumulate (~231 more needed).

        This is a SYSTEM-WIDE constant, not a per-symbol signal like exposure_mult/vix_mult:
        real full-universe collection began on one date for the whole universe, so every
        symbol's 252-day lookback has roughly the same real/synthetic split right now.

        Returns 1.0 (no discount) once REQUIRED_LOOKBACK_DAYS of real trading days have
        accumulated. Floored at 0.5 - discounts position size, never blocks entries
        outright, since seed-period data still carries real signal, just less trustworthy
        than fully-real data. Cached per-instance (see __init__) since Phase 8 reuses one
        PositionSizer across every symbol sized in a run.
        """
        if self._data_maturity_mult_cache is not None:
            return self._data_maturity_mult_cache

        required_lookback_days = 252
        floor_mult = Decimal("0.5")
        # Matches scripts/check_synthetic_price_data.py's _FULL_UNIVERSE_ROW_THRESHOLD - a
        # per-date row count in the same ballpark as the active universe, so an isolated
        # early backfill for a handful of symbols doesn't get counted as "full coverage".
        full_universe_row_threshold = 5000

        def fetch_maturity(cur: PsycopgCursor[Any]) -> Decimal:
            cur.execute(
                """
                SELECT MIN(date) FROM (
                    SELECT date FROM price_daily WHERE data_source IS NOT NULL
                    GROUP BY date HAVING COUNT(*) >= %s
                ) full_coverage_dates
                """,
                (full_universe_row_threshold,),
            )
            row = cur.fetchone()
            full_coverage_start = row[0] if row else None
            if full_coverage_start is None:
                # No real full-universe coverage detected at all yet - maximally conservative.
                return floor_mult

            today = _datetime.now(EASTERN_TZ).date()
            cur.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT date FROM price_daily
                    WHERE date > %s AND date <= %s AND data_source IS NOT NULL
                    GROUP BY date HAVING COUNT(*) >= %s
                ) full_coverage_dates
                """,
                (full_coverage_start - timedelta(days=1), today, full_universe_row_threshold),
            )
            row = cur.fetchone()
            real_trading_days = int(row[0]) if row and row[0] is not None else 0

            coverage_ratio = min(Decimal(1), Decimal(real_trading_days) / Decimal(required_lookback_days))
            return floor_mult + (Decimal(1) - floor_mult) * coverage_ratio

        result: Decimal = self._with_cursor(fetch_maturity)
        self._data_maturity_mult_cache = result
        return result

    def get_phase_size_multiplier(self) -> float:
        """Stage-2 phase mult: always 1.0 (DB schema has no late/climax phase column)."""
        return 1.0

    def get_active_positions_value(self) -> Decimal:

        def fetch_positions_value(cur: PsycopgCursor[Any]) -> Decimal:
            # Check for data integrity: all open positions must have non-NULL position_value
            cur.execute("""
                SELECT COUNT(*) as total_open, COUNT(position_value) as valid_values
                FROM algo_positions
                WHERE status = 'open'
            """)
            count_row = cur.fetchone()
            if count_row is None:
                raise ValueError("Position count query failed - cannot fetch position values")
            total_open, valid_values = count_row
            if total_open is None or valid_values is None:
                raise ValueError("Position count returned NULL - database state corrupted")
            if total_open > 0 and valid_values < total_open:
                raise ValueError(
                    f"Data integrity error: {total_open - valid_values} open positions have NULL position_value. "
                    "Cannot calculate portfolio exposure without complete position data."
                )

            # Now fetch the sum, which should never be NULL if we passed the check above
            cur.execute("""
                SELECT SUM(position_value) as total
                FROM algo_positions
                WHERE status = 'open'
            """)
            result = cur.fetchone()
            if result is None or len(result) < 1:
                raise ValueError("Position sum query returned no data")
            total = result[0]
            if total is None and total_open == 0:
                # Empty position table is OK - return 0
                return Decimal(0)
            if total is None:
                # This should never happen if our integrity check passed
                raise ValueError(
                    f"SUM(position_value) returned NULL for {total_open} open positions - database corruption"
                )
            return Decimal(str(total))

        try:
            result: Decimal | int | float = self._with_cursor(fetch_positions_value)
            if result is not None:
                return cast(Decimal, result)
            raise RuntimeError("Portfolio value query returned no data")
        except (RuntimeError, ValueError) as e:
            logger.error(f"Could not fetch position values: {e}")
            raise DataUnavailableError(f"Portfolio value unavailable - cannot calculate safe position size: {e}") from e
        except DatabaseError as e:
            logger.error(f"Database error fetching position values: {e}")
            raise DataUnavailableError(f"Portfolio value unavailable due to database error: {e}") from e

    def get_symbol_position_value(self, symbol: str) -> Decimal:
        """Sum of position_value across all open positions for one symbol.

        REAL-MONEY-READINESS FIX (2026-09-07 audit): max_position_size_pct and
        max_concentration_pct were both being checked against ONLY the new candidate
        trade's own position_value, never added to any EXISTING open position(s) in the
        same symbol. max_reentries_per_name allows pyramiding into a symbol across
        multiple entries (each individually capped at max_position_size_pct), so a fully
        pyramided position could reach several times the intended single-symbol
        concentration ceiling while every individual leg's own check still passed. This
        getter lets both caps be checked against the symbol's TOTAL exposure (existing +
        candidate), restoring the invariant those caps were designed to enforce, without
        changing any config value.
        """

        def fetch_symbol_position_value(cur: PsycopgCursor[Any]) -> Decimal:
            cur.execute(
                "SELECT SUM(position_value) FROM algo_positions WHERE status = 'open' AND symbol = %s",
                (symbol,),
            )
            result = cur.fetchone()
            if result is None or result[0] is None:
                # SUM() with no matching rows / NULL means no open positions for this
                # symbol - a genuine zero, not missing/ambiguous data.
                return Decimal(0)
            return Decimal(str(result[0]))

        try:
            result: Decimal | int | float = self._with_cursor(fetch_symbol_position_value)
            return cast(Decimal, result) if result is not None else Decimal(0)
        except (RuntimeError, ValueError) as e:
            logger.error(f"Could not fetch existing position value for {symbol}: {e}")
            raise DataUnavailableError(
                f"Existing position value for {symbol} unavailable - cannot safely size a pyramided entry: {e}"
            ) from e
        except DatabaseError as e:
            logger.error(f"Database error fetching existing position value for {symbol}: {e}")
            raise DataUnavailableError(
                f"Existing position value for {symbol} unavailable due to database error: {e}"
            ) from e

    def get_position_count(self) -> int:
        """Get count of active positions (Issue #26: Now checks capital, not just count).

        Fail-fast  -" if data unavailable, raises exception. Cannot size positions
        without knowing how many are already open.
        """

        def fetch_position_count(cur: PsycopgCursor[Any]) -> int:
            cur.execute("""
                SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'
            """)
            result = cur.fetchone()
            if result is None:
                raise ValueError("Position count query returned None")
            return cast(int, result[0])

        result: Decimal | int | float = self._with_cursor(fetch_position_count)
        if result is not None:
            return cast(int, result)
        raise RuntimeError("Could not fetch position count from database. Cannot calculate safe position size.")

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: Any,
        stop_loss_price: Any,
        signal_date: _date | None = None,
        portfolio_value: Any = None,
        enforce_total_risk_limit: bool = True,
    ) -> dict[str, Any]:
        """
        Calculate position size for a new trade.

        CRITICAL FIX (Session 393): When enforce_total_risk_limit=True, checks total open risk
        across all positions and scales position size down if we're running low on
        max_total_risk_pct's limit capacity (config-driven, not a fixed number - see the
        2026-08-06 fix below and [[t1_t2_t3_reason_hardcoded_r_multiple_stale_fixed_20260825]]
        in memory for why a specific percentage isn't restated here).
        This prevents individual position sizing from pushing aggregate risk over that limit.

        Args:
            portfolio_value: Pre-fetched portfolio value to skip Alpaca API call.
                             Pass this when calling in a loop to avoid N Alpaca calls.
            enforce_total_risk_limit: If True, check total risk and scale down if needed

        Returns:
        {
            'shares': number of shares,
            'position_size_pct': % of portfolio,
            'risk_dollars': dollar amount at risk,
            'status': 'ok' | 'no_room' | 'drawdown_halt' | 'risk_limit_scaled'
        }
        """
        try:
            return self._calculate_with_external_cursor(
                symbol,
                entry_price,
                stop_loss_price,
                signal_date,
                portfolio_value=portfolio_value,
                enforce_total_risk_limit=enforce_total_risk_limit,
            )
        except (DataUnavailableError, ConfigurationError, ValueError) as e:
            raise RuntimeError(f"Position sizing calculation failed: {type(e).__name__}: {e}") from e
        except (ZeroDivisionError, TypeError, InvalidOperation) as e:
            # BUG FOUND 2026-08-10 (via fuzzing with pathological inputs): decimal.InvalidOperation
            # (raised by e.g. a NaN Decimal used in an ordering comparison - `Decimal("nan") > 0`
            # raises, unlike float NaN which just returns False) is an ArithmeticError, not a
            # ValueError/ZeroDivisionError/TypeError - it fell through both except clauses above
            # uncaught, breaking this function's own documented contract ("Raises RuntimeError/
            # ValueError for all error conditions") for any NaN/Infinity-tainted price input.
            raise RuntimeError(f"Unexpected error in position sizing: {type(e).__name__}: {e}") from e

    def _calculate_with_external_cursor(
        self,
        symbol: str,
        entry_price: Any,
        stop_loss_price: Any,
        signal_date: _date | None = None,
        portfolio_value: Any = None,
        enforce_total_risk_limit: bool = True,
    ) -> dict[str, Any]:
        """Internal method for position calculation.

        CRITICAL FIX (Session 393): When enforce_total_risk_limit=True, checks total open risk
        and scales position size down if aggregate risk would exceed max_total_risk_pct's
        configured limit (not a fixed number - see the 2026-08-06 fix below).

        Raises RuntimeError/ValueError for all error conditions. Let caller handle exceptions.
        Only returns success dict or explicit sizing denial (no_room, drawdown_halt, concentration, etc).

        CRITICAL FIX: every validation below used to be a bare `assert`, which (1) raises
        AssertionError, not ValueError/RuntimeError as this docstring promises and as
        calculate_position_size's own except clause expects to catch and re-wrap - an
        AssertionError here propagated straight past Phase 8's per-symbol exception
        handlers (which catch ValueError/RuntimeError/TypeError/AttributeError, not
        AssertionError), aborting entry execution for every remaining symbol in the batch
        instead of cleanly skipping just this one bad-data symbol; and (2) is silently
        stripped entirely under `python -O`/`PYTHONOPTIMIZE=1`, which would let a
        zero/negative portfolio value or an inverted stop/entry (the single most basic
        long-only risk-management invariant) through with no validation at all. Converted
        to explicit checks so they're real, unconditional, correctly-typed validation.

        CRITICAL FIX (Session 64): Convert portfolio_value to Decimal BEFORE arithmetic.
        If caller passes float (from Alpaca API), Decimal arithmetic would fail with TypeError.
        This ensures all Decimal * float operations are prevented.
        """
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Symbol must be non-empty string, got {symbol!r}")

        # CRITICAL: Convert portfolio_value to Decimal before any arithmetic
        # Prevents: Decimal * float TypeError when multiplying max_position_pct
        if portfolio_value is not None:
            if not isinstance(portfolio_value, Decimal):
                try:
                    portfolio_value = Decimal(str(portfolio_value))
                except (ValueError, TypeError, InvalidOperation) as e:
                    raise ValueError(
                        f"Invalid portfolio_value: cannot convert {portfolio_value!r} to Decimal: {e}"
                    ) from e
        else:
            portfolio_value = self.get_portfolio_value()
        entry_dec = Decimal(str(entry_price))
        if not entry_dec > 0:
            raise ValueError(f"Entry price must be > 0, got {entry_price}")
        stop_dec = Decimal(str(stop_loss_price))
        if not stop_dec > 0:
            raise ValueError(f"Stop loss must be > 0, got {stop_loss_price}")
        if not stop_dec < entry_dec:
            raise ValueError(f"Stop {stop_dec} must be < entry {entry_dec}")

        if portfolio_value is None:
            portfolio_value = self.get_portfolio_value()
        pv_dec = Decimal(str(portfolio_value))
        if not pv_dec > 0:
            raise ValueError(f"Portfolio value must be > 0, got {portfolio_value}")

        risk_adjustment = self.get_risk_adjustment()
        if risk_adjustment is None:
            raise ValueError("Risk adjustment cannot be None")
        if not Decimal(str(risk_adjustment)) >= 0:
            raise ValueError(f"Risk adjustment must be >= 0, got {risk_adjustment}")

        active_positions = self.get_position_count()
        if not isinstance(active_positions, int):
            raise ValueError(f"Active positions must be int, got {type(active_positions)}")
        active_position_value = self.get_active_positions_value()

        max_positions_val = self.config.get("max_positions")
        if max_positions_val is None:
            raise ValueError("[POSITION_SIZER] Config missing required 'max_positions' key")
        try:
            max_positions = int(max_positions_val)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"[POSITION_SIZER] max_positions must be integer, got {type(max_positions_val).__name__}: {max_positions_val}"
            ) from e
        if max_positions <= 0:
            raise ValueError(f"[POSITION_SIZER] max_positions must be > 0, got {max_positions}")

        if active_positions >= max_positions:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "no_room",
                "reason": f"{active_positions} open positions >= {max_positions} position limit",
            }

        if risk_adjustment == 0:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "drawdown_halt",
                "reason": "Drawdown >= 20%, trading halted",
            }

        base_risk_val = self.config.get("base_risk_pct")
        if base_risk_val is None:
            raise KeyError("[POSITION_SIZER] Config missing 'base_risk_pct'")
        base_risk_pct = Decimal(str(base_risk_val)) / Decimal(100)
        # BUG FOUND 2026-08-24 (exposure-score audit): this cascade used to also multiply by
        # regime_mult (RegimeManager.get_position_size_multiplier(), REGIME_POSITION_SIZE_*
        # constants keyed by market_exposure_daily.regime). regime IS tier_for_exposure() of
        # the exact same market_exposure_daily.exposure_pct that exposure_mult already reads
        # continuously two lines below - regime_mult was a coarse re-bucketing of the same
        # signal exposure_mult already applies smoothly, so multiplying both compounded one
        # market read twice (e.g. exposure_pct=35% in "caution": 0.35 exposure_mult x 0.5
        # regime_mult = 0.175x combined, roughly half the intended single-application
        # reduction). Removed - exposure_mult alone is the documented, continuous mechanism
        # (see market_exposure.py's module docstring: "position_sizer.py's continuous
        # exposure_pct/100 multiplier"). get_position_size_multiplier_from_regime() is deleted
        # below since this was its only call site; RegimeManager itself is untouched (still
        # used for reporting/display and weight-optimization gating elsewhere).
        exposure_mult = self.get_market_exposure_multiplier()
        phase_mult = self.get_phase_size_multiplier()
        vix_mult = self.get_vix_caution_multiplier()
        data_maturity_mult = self.get_data_maturity_multiplier()

        adjusted_risk_pct = (
            base_risk_pct * risk_adjustment * exposure_mult * Decimal(str(phase_mult)) * vix_mult * data_maturity_mult
        )
        risk_dollars = (pv_dec * adjusted_risk_pct).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # NOTE (confirmed 2026-08-10, checked git history back to this file's first commit):
        # get_phase_size_multiplier() always returns 1.0 - "DB schema has no late/climax
        # phase column" per its own docstring - so phase_mult == 0.0 can never be true and
        # this branch (and the "phase_climax" status phase8_entry_execution.py's own comment
        # lists as a real possible rejection reason) is currently unreachable dead code, not a
        # silently-broken regression like _check_sector_drawdown was (that one had real
        # config/intent behind it that was simply never wired up - this one has never had the
        # underlying data to support it at all). Left in place as a real, deliberate
        # extension point for a future Stage-2 climax detector, not because anything here is
        # currently broken - do not "fix" it by inventing detection logic without a real data
        # source and product/strategy sign-off on what should trigger it.
        if phase_mult == 0.0:
            logger.warning(
                f"Position sizing halted for {symbol}: Stage-2 climax phase detected. "
                "No new entries until stock exits climax conditions."
            )
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "phase_climax",
                "reason": f"{symbol} in Stage-2 climax phase - skip entry",
            }

        # BUG FOUND 2026-08-10 (via fuzzing with pathological inputs): this used to compare
        # the raw entry_price/stop_loss_price parameters (type Any) directly against int 0,
        # instead of the already-validated entry_dec/stop_dec Decimals computed above. Every
        # real Phase 8 call site only ever passes float, so this was unreachable in current
        # production paths - but this function's own Any signature and its Decimal(str(x))
        # normalization pattern both imply string input is a supported contract, and a string
        # entry_price/stop_loss_price crashed here with an uncaught
        # "TypeError: '<=' not supported between instances of 'str' and 'int'" instead of the
        # clean {"status": "invalid", ...} result this branch exists to return. Also genuinely
        # redundant with the entry_dec/stop_dec ValueError checks above - kept as a second
        # guard, just now type-safe.
        if entry_dec <= 0 or stop_dec >= entry_dec:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "invalid",
                "reason": "Invalid entry or stop price",
            }

        min_risk_val = self.config.get("min_risk_pct_floor")
        if min_risk_val is None:
            raise ValueError("CRITICAL: min_risk_pct_floor config missing. Cannot enforce minimum position risk floor.")
        min_risk_floor = Decimal(str(min_risk_val)) / Decimal(100)
        has_safety_reduction = (
            exposure_mult < 0.8 or vix_mult < 1.0 or risk_adjustment < 1.0 or data_maturity_mult < 1.0
        )
        if adjusted_risk_pct < min_risk_floor and not has_safety_reduction:
            adjusted_risk_pct = min_risk_floor
            risk_dollars = pv_dec * adjusted_risk_pct

        risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
        if risk_per_share <= 0:
            raise ValueError(
                f"[POSITION SIZER CRITICAL] Invalid risk_per_share={risk_per_share}: "
                f"stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). "
                f"Cannot size position with invalid stop price. This indicates corrupted position data."
            )
        # ROUND_DOWN, not ROUND_HALF_UP: risk_dollars is a hard budget (adjusted_risk_pct *
        # portfolio_value), not a target - rounding the share count up here can push the
        # actual dollar risk of the position past that budget by up to half a share's worth
        # of risk_per_share. Same class of bug the max_position_size_pct cap below already
        # guards against with ROUND_DOWN (see its comment) - this is the risk-budget
        # equivalent of that same hard ceiling and needs the same rounding direction.
        shares = int((risk_dollars / risk_per_share).quantize(Decimal(1), rounding=ROUND_DOWN))
        base_shares = shares  # pre-cap share count from risk-based sizing alone, for algo_position_sizing_audit

        if shares < 1:
            raise ValueError(
                f"Position sizing resulted in zero shares. "
                f"risk_dollars=${risk_dollars:.2f}, risk_per_share=${risk_per_share:.2f}. "
                f"Cannot place a 0-share order at the broker. Review position_sizer configuration."
            )

        position_value = Decimal(shares) * Decimal(str(entry_price))

        # REAL-MONEY-READINESS FIX (2026-09-07 audit): fold in any EXISTING open
        # position value for this same symbol (prior pyramid legs) so the per-symbol
        # caps below bound the symbol's TOTAL exposure, not just this one candidate
        # trade in isolation - see get_symbol_position_value's docstring for the bug
        # this closes.
        existing_symbol_value = self.get_symbol_position_value(symbol)

        max_pos_pct_val = self.config.get("max_position_size_pct")
        if max_pos_pct_val is None:
            raise ValueError("CRITICAL: max_position_size_pct config missing. Cannot enforce position size cap.")
        try:
            max_position_pct = Decimal(str(max_pos_pct_val)) / Decimal(100)
            if max_position_pct <= 0 or max_position_pct > Decimal(1):
                raise ValueError(f"max_position_size_pct must be between 0 and 100, got {max_pos_pct_val}")
        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            raise ValueError(
                f"CRITICAL: max_position_size_pct config has invalid value '{max_pos_pct_val}': {e}"
            ) from None
        max_position_value = pv_dec * max_position_pct

        if existing_symbol_value + position_value > max_position_value:
            # ROUND_DOWN, not ROUND_HALF_UP: this caps position_value to a hard ceiling
            # (max_position_size_pct), so rounding the share count up can let the capped
            # position_value exceed max_position_value by up to half a share's value,
            # silently breaching the limit this branch exists to enforce.
            room_left = max_position_value - existing_symbol_value
            if room_left <= 0:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "no_room",
                    "reason": (
                        f"{symbol}: existing position(s) already at/over max_position_size_pct "
                        f"(${float(existing_symbol_value):,.2f} existing vs "
                        f"${float(max_position_value):,.2f} cap) - no room for another pyramid leg"
                    ),
                }
            shares = int((room_left / Decimal(str(entry_price))).quantize(Decimal(1), rounding=ROUND_DOWN))
            position_value = Decimal(shares) * Decimal(str(entry_price))
            risk_dollars = risk_per_share * Decimal(shares)

            # BUG FOUND 2026-08-10 (position-sizing boundary-condition audit): unlike the two
            # sibling scaling branches below (concentration-limit scale-down, total-risk-limit
            # scale-down), this cap never re-checked `shares < 1` after rounding down - a stock
            # priced above `max_position_size_pct * portfolio_value` (e.g. entry_price=$600,
            # max_position_value=$500 for a $10k portfolio at a 5% cap) rounds straight to 0
            # shares here, then falls through every remaining check (concentration/total-
            # invested/total-risk all trivially pass at position_value=0) to the function's
            # final `return {..., "status": "ok"}` - a 0-share result reported as success,
            # violating this function's own documented status contract ('ok' | 'no_room' |
            # 'drawdown_halt' | 'risk_limit_scaled', not "ok" meaning "zero shares"). Not
            # currently causing a live bad order - every one of Phase 8's 3 call sites already
            # independently re-checks `shares < 1` regardless of `status` before using the
            # result - but that safety is accidental (each caller happening to defensively
            # re-check), not a contract this function itself upholds. Matches the exact
            # landmine pattern found elsewhere today (docstring/behavior contradicting actual
            # code): fix the function's own contract rather than rely on every future caller
            # independently reinventing the same defensive check.
            if shares < 1:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "no_room",
                    "reason": (
                        f"Entry price ${entry_price} exceeds max position value "
                        f"${max_position_value:.2f} ({max_position_pct * 100:.1f}% of "
                        f"${pv_dec:.2f} portfolio) - cannot afford even 1 share within the cap"
                    ),
                }

        # OPTIONAL absolute-dollar per-trade backstop (added 2026-08-31 - see
        # absolute_dollar_backstop_missing_open_recommendation_20260831 in project memory for
        # the full finding). Every cap above is a PERCENTAGE of portfolio_value - if
        # portfolio_value were ever wrong (a bug upstream of _validate_alpaca_equity's relative
        # sanity check, or a bad snapshot that check can't itself catch), every percentage cap
        # would look "compliant" while authorizing an arbitrarily large real-dollar trade. This
        # is an independent ceiling that doesn't depend on portfolio_value at all - deliberately
        # OPT-IN (skipped entirely when unset, zero behavior change for anyone who hasn't
        # configured it) rather than a hardcoded guess, since the right dollar figure depends on
        # the account's real intended size, not something a code-correctness pass should invent.
        # Set absolute_max_dollars_per_trade in algo_config to activate.
        absolute_max_dollars_val = self.config.get("absolute_max_dollars_per_trade")
        if absolute_max_dollars_val is not None:
            try:
                absolute_max_dollars = Decimal(str(absolute_max_dollars_val))
            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                raise ValueError(
                    f"CRITICAL: absolute_max_dollars_per_trade config has invalid value "
                    f"'{absolute_max_dollars_val}': {e}"
                ) from None
            if absolute_max_dollars <= 0:
                raise ValueError(
                    f"CRITICAL: absolute_max_dollars_per_trade must be positive, got "
                    f"{absolute_max_dollars}. Set a real dollar ceiling or remove the config "
                    f"key entirely to disable this check."
                )
            if position_value > absolute_max_dollars:
                # Same ROUND_DOWN reasoning as the max_position_size_pct cap above - this is a
                # hard ceiling, not a target.
                shares = int(
                    (absolute_max_dollars / Decimal(str(entry_price))).quantize(Decimal(1), rounding=ROUND_DOWN)
                )
                position_value = Decimal(shares) * Decimal(str(entry_price))
                risk_dollars = risk_per_share * Decimal(shares)
                if shares < 1:
                    return {
                        "shares": 0,
                        "position_size_pct": 0,
                        "risk_dollars": 0,
                        "status": "no_room",
                        "reason": (
                            f"Entry price ${entry_price} exceeds absolute_max_dollars_per_trade "
                            f"${absolute_max_dollars:.2f} - cannot afford even 1 share within "
                            f"the absolute ceiling"
                        ),
                    }

        # OPTIONAL market-impact/participation-rate cap (added 2026-09-06, real-money-
        # readiness audit finding: every cap above sizes off portfolio_value alone - none of
        # them reference the STOCK's OWN trading volume, so a position sized well within every
        # portfolio-pct/absolute-dollar ceiling could still be a large, market-moving fraction
        # of a thinly-traded name's actual daily turnover. LiquidityChecks.run_all (algo/risk/
        # liquidity_checks.py) is a fixed-floor pass/fail gate on ADV (does this SYMBOL clear a
        # minimum bar at all) - it does not scale with how large the CANDIDATE POSITION itself
        # is, so a big-enough account can clear that floor by a wide margin while still sizing
        # a single trade as a large percentage of the stock's own 20-day average dollar volume,
        # risking real execution slippage and multi-day unwind risk on exit. Deliberately
        # OPT-IN (skipped entirely when unset, same convention as absolute_max_dollars_per_trade
        # just above) rather than a hardcoded guess - the right participation-rate ceiling is a
        # strategy/product decision (typical institutional practice caps at low single-digit
        # percent of ADV), not something a code-correctness pass should invent. Set
        # max_pct_of_adv_dollars in algo_config to activate. Only enforced when signal_date is
        # available (the historical ADV window is computed as-of that date, matching
        # liquidity_checks.py's own windowing) - Phase 8's preliminary concentration-prefilter
        # sizing pass doesn't pass signal_date and is skipped here, same as it already skips
        # LiquidityChecks entirely at that stage; the real, order-submitting sizing call always
        # passes signal_date and gets the real cap.
        max_pct_of_adv_val = self.config.get("max_pct_of_adv_dollars")
        if max_pct_of_adv_val is not None and signal_date is not None:
            try:
                max_pct_of_adv = Decimal(str(max_pct_of_adv_val)) / Decimal(100)
            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                raise ValueError(
                    f"CRITICAL: max_pct_of_adv_dollars config has invalid value '{max_pct_of_adv_val}': {e}"
                ) from None
            if max_pct_of_adv <= 0:
                raise ValueError(
                    f"CRITICAL: max_pct_of_adv_dollars must be positive, got {max_pct_of_adv_val}. "
                    f"Set a real percentage or remove the config key entirely to disable this check."
                )
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT AVG(volume * close) AS avg_dollar_vol
                    FROM (
                        SELECT volume, close FROM price_daily
                        WHERE symbol = %s
                          AND date >= %s
                          AND date < %s
                        ORDER BY date DESC
                        LIMIT 20
                    ) recent
                    """,
                    (symbol, signal_date - timedelta(days=25), signal_date),
                )
                adv_row = cur.fetchone()
            if adv_row is not None and adv_row[0] is not None:
                avg_dollar_vol = Decimal(str(adv_row[0]))
                max_adv_position_value = avg_dollar_vol * max_pct_of_adv
                if position_value > max_adv_position_value:
                    shares = int(
                        (max_adv_position_value / Decimal(str(entry_price))).quantize(Decimal(1), rounding=ROUND_DOWN)
                    )
                    position_value = Decimal(shares) * Decimal(str(entry_price))
                    risk_dollars = risk_per_share * Decimal(shares)
                    if shares < 1:
                        return {
                            "shares": 0,
                            "position_size_pct": 0,
                            "risk_dollars": 0,
                            "status": "no_room",
                            "reason": (
                                f"{symbol}: even 1 share would exceed max_pct_of_adv_dollars "
                                f"({max_pct_of_adv * 100:.1f}% of ${avg_dollar_vol:,.0f} 20-day "
                                f"avg dollar volume) - too thin to size a position at all"
                            ),
                        }
            # A missing/NULL ADV reading here (adv_row is None or avg_dollar_vol is NULL) is
            # NOT the same "block as a safety measure" case LiquidityChecks.run_all uses for
            # its own pass/fail gate - that gate's entire job is verifying tradability, so
            # missing data there must fail closed. This cap only refines a position that
            # ALREADY passed that gate (or is a candidate LiquidityChecks hasn't run against
            # yet in the prefilter pass) - silently skipping the refinement on missing data
            # leaves the position sized by every OTHER real cap above, not unsized/unguarded.

        if pv_dec <= 0:
            raise ValueError(
                f"CRITICAL: Portfolio value invalid ({pv_dec}) - cannot calculate position sizing. "
                f"Position sizing requires current portfolio value > 0."
            )
        try:
            # Includes existing_symbol_value (prior pyramid legs) - see get_symbol_position_value's
            # docstring - so this reflects the symbol's TOTAL concentration, not just this trade.
            position_pct_of_portfolio = (existing_symbol_value + position_value) / pv_dec * Decimal(100)
        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            raise ValueError(
                f"CRITICAL: Position value calculation failed ({position_value}): {e}. "
                f"Cannot calculate position sizing without valid values."
            ) from e
        # STRUCTURAL FINDING 2026-08-25 (real-money-readiness goal session, position-sizing
        # audit): live-confirmed via direct DB query, not just schema defaults -
        # algo_config.max_position_size_pct=4.75 and max_concentration_pct=50.0 (both stamped
        # with the IDENTICAL updated_at timestamp, 2026-06-03 - set once at initial seed, never
        # independently reasoned about together). Phase 8 overrides max_concentration_pct per
        # exposure-tier regime (algo/risk/exposure_policy.py EXPOSURE_TIERS: 10%/12%/22%/28%
        # across correction/caution/normal/aggressive), specifically so concentration risk
        # SHRINKS in risk-off regimes - but every one of those tier values (10-28%) is looser
        # than the STATIC 4.75% cap already enforced above (unconditionally, every call,
        # regardless of regime). Since position_value here is already capped to <=4.75% of
        # portfolio_value by the branch above, position_pct_of_portfolio below can never
        # exceed effective_limit (max_concentration_pct minus its own safety margin, always
        # >=9% for the tightest real tier) - the scale-down branch immediately below this
        # comment, and the entire regime-driven concentration dial it exists to enforce, is
        # currently UNREACHABLE dead code under real production config. This is a genuine
        # design bug (two caps that were each individually reasonable in isolation compose
        # such that the intended dynamic one has zero effect), not the earlier
        # get_phase_size_multiplier() dead-code case (which has no underlying data source at
        # all) - here both signals are real and live, they just never interact as designed.
        # Currently SAFE (the tighter static cap means no position can ever exceed 4.75%
        # regardless of regime - the failure mode is "the regime dial does nothing," not "a
        # position gets oversized"), so left unchanged rather than picking a new absolute
        # ceiling unilaterally for a live-money account - that specific number is a real
        # risk-tolerance/business decision, not something a code-correctness pass should
        # invent. Flagging precisely so a future session (or the user directly) can decide
        # deliberately: e.g. raise max_position_size_pct above the loosest tier (28%) so the
        # regime dial becomes the actual binding day-to-day constraint, or leave the static
        # cap authoritative and remove/simplify the now-decorative tier-driven branch instead.
        #
        # RESOLVED 2026-08-25 (same day, user directed: figure out what's best and act):
        # KEEP the static 4.75% cap authoritative. Do NOT raise max_position_size_pct.
        # Reasoning, not just caution:
        # 1. 4.75% is coherent with this system's own design, exactly not approximately:
        #    live-confirmed algo_config.max_positions=20 x 4.75% = 95.0%, which equals
        #    max_total_invested_pct (95.0%) exactly - a clean, deliberate-looking design
        #    relationship (a fully-invested, evenly-capped 20-name book exactly fills the
        #    total-invested ceiling with no slack). Raising max_position_size_pct to 28%
        #    (confirmed_uptrend's tier value) would let ONE position reach ~6x an
        #    equal-weighted 20-way share - a large, real increase in single-name concentration
        #    risk that breaks this exact relationship and cuts against this session's own
        #    diversification goal, with no new evidence to justify it.
        # 2. Rescaling EXPOSURE_TIERS' max_concentration_pct values DOWN instead (to nest
        #    under 4.75%) was considered and rejected too: those values carry their own real,
        #    independent, live-P&L-validated tuning history (see exposure_policy.py's
        #    "TUNING FIX (2026-08-02): Raised from 20% to 28%. Was forcing exits at winners.
        #    -2.43% avg return on forced exits" - a real, measured cost of a tighter cap).
        #    Rescaling them without equivalent new evidence would silently discard a decision
        #    that was already validated against real trading outcomes, for a different regime
        #    of the system (a different max_positions/portfolio-construction point in time)
        #    that no longer applies the same way - not something to do casually either.
        # 3. Could not arbitrate between these two real-but-conflicting numbers with a fresh
        #    backtest: same hard data-availability wall as
        #    regime_manager.py's get_adjusted_config() finding - see
        #    tests/unit/test_regime_adaptive_exits_backtest_infeasible_20260825.py. NOTE
        #    (2026-09-04 correction, see that test file's docstring): the regime-LABEL half of
        #    that finding was later found to be wrong (correction/caution regimes are common,
        #    66% of market history, once reconstructed from deeper price/VIX/credit-spread
        #    data instead of the shallow market_exposure_daily table) - but this decision here
        #    depends only on buy_sell_daily's shallow real-trade history (~83 days), which is
        #    still true and still the actual blocker. This #3 point is NOT reopened by that
        #    correction.
        # Net: the concentration branch below stays exactly as-is (correct, real defense-in-
        # depth code, just non-binding under today's numbers) - not simplified/removed either,
        # since it would activate correctly and immediately if either number is ever
        # independently retuned in the future. Monitored by
        # test_position_sizer_concentration_dial_inert_under_real_config_20260825.py.
        max_conc_val = self.config.get("max_concentration_pct")
        if max_conc_val is None:
            raise ValueError("CRITICAL: max_concentration_pct config missing. Cannot enforce concentration limit.")
        max_concentration = Decimal(str(max_conc_val))

        # CRITICAL FIX (Session 2026-08-05): Scale down position size if it exceeds concentration limit
        # instead of rejecting entirely. This allows us to capture the trade at a reduced size
        # rather than missing the opportunity entirely and creating forced-exit losses.
        # When another position closes between Phase 8 (entry) and Phase 6 (exit), the position
        # could violate limits on Phase 6 check. Instead of rejecting at entry time:
        # OLD: position would be 23%, limit is 20% → reject (0 shares)
        # NEW: position would be 23%, limit is 20% → scale to 19% and enter
        # Safety margin: max(1%, max_concentration * 0.05) - typically 1% for 20% limit
        safety_margin = Decimal(str(max(1.0, float(max_concentration) * 0.05)))
        effective_limit = max_concentration - safety_margin

        if position_pct_of_portfolio > effective_limit:
            # Scale down the position instead of rejecting it
            # Calculate maximum allowed NEW position value at effective limit, net of any
            # existing same-symbol exposure already counted toward that limit above.
            max_position_value_at_limit = pv_dec * (effective_limit / Decimal(100)) - existing_symbol_value
            scaled_shares = (
                int((max_position_value_at_limit / Decimal(str(entry_price))).quantize(Decimal(1), rounding=ROUND_DOWN))
                if max_position_value_at_limit > 0
                else 0
            )

            if scaled_shares < 1:
                # Can't scale down further - truly no room
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "concentration",
                    "reason": f"Position would exceed {effective_limit:.0f}% limit even at minimum size (margin: {safety_margin:.0f}%)",
                }

            # BUG FOUND 2026-08-23 (goal session: real-money-readiness position-sizer audit):
            # this branch used to `return` immediately with the scaled position - unlike the
            # max_position_size_pct cap just above it (which updates shares/position_value/
            # risk_dollars in place and falls through to the concentration/total-invested/
            # total-risk checks that follow), this was the ONLY scaling branch in the whole
            # function that skipped the remaining checks entirely. That meant a concentration-
            # scaled entry never went through the total_invested_pct check (line ~1119) OR the
            # enforce_total_risk_limit block (line ~1135) - the latter explicitly documented a
            # few lines below as "the single most important portfolio-level guardrail" (the
            # aggregate open-risk hard cap), specifically evaluated per-symbol because Phase 8
            # sizes multiple symbols per cycle and needs a live, cumulative check as it goes.
            # A symbol whose OWN concentration limit triggered scaling could still push the
            # portfolio's aggregate open risk past the configured cap, completely unchecked -
            # not currently exploited (no live incident found), but a real, structural gap in
            # the exact guardrail meant to prevent overexposure before using real money. Update
            # the working variables in place and let execution continue, matching the
            # max_position_size_pct branch's own established pattern, instead of returning early.
            original_pct_of_portfolio = position_pct_of_portfolio
            original_shares = shares
            shares = scaled_shares
            position_value = Decimal(shares) * Decimal(str(entry_price))
            position_pct_of_portfolio = (position_value / pv_dec) * Decimal(100)
            risk_dollars = risk_per_share * Decimal(shares)

            logger.info(
                f"[POSITION SIZER] {symbol}: Position scaled down to respect concentration limit. "
                f"Original: {original_pct_of_portfolio:.1f}% ({original_shares} shares). "
                f"Scaled: {position_pct_of_portfolio:.1f}% ({shares} shares). "
                f"Limit: {effective_limit:.0f}% (with {safety_margin:.0f}% safety margin). "
                f"Still subject to the total-invested/total-risk checks below."
            )

        total_invested = Decimal(str(active_position_value)) + position_value
        max_inv_val = self.config.get("max_total_invested_pct")
        if max_inv_val is None:
            raise ValueError("CRITICAL: max_total_invested_pct config missing. Cannot enforce total investment limit.")
        max_invested_pct = Decimal(str(max_inv_val))
        if pv_dec > 0 and (total_invested / pv_dec * Decimal(100)) > max_invested_pct:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "no_room",
                "reason": f"Total invested would be {(total_invested / pv_dec * Decimal(100)):.0f}% > {max_invested_pct:.0f}%",
            }

        # OPTIONAL absolute-dollar TOTAL EXPOSURE backstop - the total-exposure sibling of the
        # per-trade check above (see absolute_dollar_backstop_missing_open_recommendation_20260831
        # in project memory). Same reasoning: max_total_invested_pct is a percentage of
        # portfolio_value, so a wrong portfolio_value would make it look compliant regardless of
        # real dollar exposure. Deliberately opt-in (skipped when unset) for the same reason the
        # per-trade version is - the right ceiling depends on the account's real intended size.
        # Set absolute_max_total_exposure_dollars in algo_config to activate.
        absolute_max_exposure_val = self.config.get("absolute_max_total_exposure_dollars")
        if absolute_max_exposure_val is not None:
            try:
                absolute_max_exposure = Decimal(str(absolute_max_exposure_val))
            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                raise ValueError(
                    f"CRITICAL: absolute_max_total_exposure_dollars config has invalid value "
                    f"'{absolute_max_exposure_val}': {e}"
                ) from None
            if absolute_max_exposure <= 0:
                raise ValueError(
                    f"CRITICAL: absolute_max_total_exposure_dollars must be positive, got "
                    f"{absolute_max_exposure}. Set a real dollar ceiling or remove the config "
                    f"key entirely to disable this check."
                )
            if total_invested > absolute_max_exposure:
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "no_room",
                    "reason": (
                        f"Total invested (${total_invested:.2f}) would exceed "
                        f"absolute_max_total_exposure_dollars (${absolute_max_exposure:.2f}) - "
                        f"independent of any percentage-based limit"
                    ),
                }

        # SESSION 393 IMPLEMENTATION: Enforce total risk limit BEFORE returning success
        # Check if aggregate risk (current open + this new position) would exceed 4% limit
        if enforce_total_risk_limit:
            try:
                with DatabaseContext("read") as cur:
                    # FIX 2026-08-31 (/goal pre-real-money audit): was `p.quantity` (a
                    # position-level total) multiplied into EVERY fanned-out row of the
                    # JOIN - for a pyramided position (trade_ids_arr has 2+ open trades,
                    # a real, supported case per position_sync.py's own LINKED_TRADE_STATUSES
                    # handling), each constituent trade's row repeated the SAME full
                    # position quantity instead of that trade's own share count, summing to
                    # an inflated total. Concrete example: position qty=100 (60sh @ entry
                    # $50 + 40sh @ entry $52, stop=$45) used to compute
                    # (50-45)*100 + (52-45)*100 = $1,200 instead of the real
                    # 60*(50-45) + 40*(52-45) = $580 - the aggregate open-risk figure this
                    # file's own comment calls "the single most important portfolio-level
                    # guardrail" was overstated for any pyramided position (fails
                    # over-conservative - spuriously blocks/scales down otherwise-good new
                    # entries - not under-protective, but still wrong). algo_trades.quantity
                    # is the correct per-trade figure: verified it's actively decremented on
                    # partial exits (executor_exit_handler.py's partial-exit UPDATE, itself a
                    # documented prior fix in this same file's history) and trade_ids_arr is
                    # already scoped to TradeStatus.all_open() trades only
                    # (position_sync.py's LINKED_TRADE_STATUSES), so no additional t.status
                    # filter is needed here.
                    cur.execute("""
                        SELECT SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * t.quantity))
                        FROM algo_positions p
                        JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
                        WHERE p.status = 'open'
                    """)
                    result = cur.fetchone()
                    if result is None:
                        raise RuntimeError(
                            "[POSITION SIZER] Risk calculation query returned no rows. "
                            "Cannot compute aggregate risk without valid query result. "
                            "Check: (1) database connectivity, (2) algo_positions/algo_trades tables"
                        )
                    risk_sum = result[0]
                    # CRITICAL: this is the single most important portfolio-level guardrail
                    # (aggregate 4% open-risk hard cap) - kept in Decimal throughout, matching
                    # every other money/threshold computation in this file, instead of the
                    # float arithmetic previously used here (a precision-drift risk on exactly
                    # the check meant to be least tolerant of drift).
                    if risk_sum is None:
                        # SUM returns NULL when no matching rows, but query succeeded
                        current_risk_dollars = Decimal(0)
                    else:
                        current_risk_dollars = Decimal(str(risk_sum))

                    # Calculate aggregate risk after this position would be added
                    total_risk_after_entry = current_risk_dollars + risk_dollars
                    total_risk_pct = (total_risk_after_entry / pv_dec) * Decimal(100) if pv_dec > 0 else Decimal(0)

                    # Hard limit: read from config (was hardcoded to 4% but config sets 8%)
                    # CRITICAL FIX 2026-08-06: Use config value to stay in sync with Phase 8 and circuit breaker
                    max_risk_pct = Decimal(str(self.config["max_total_risk_pct"]))

                    if total_risk_pct > max_risk_pct:
                        # Risk limit would be exceeded - scale down position or block
                        available_capacity_dollars = (max_risk_pct / Decimal(100) * pv_dec) - current_risk_dollars

                        if available_capacity_dollars <= 0:
                            # No room left - block entry entirely
                            return {
                                "shares": 0,
                                "position_size_pct": 0,
                                "risk_dollars": 0,
                                "status": "risk_limit",
                                "reason": f"Total open risk {(current_risk_dollars / pv_dec * Decimal(100)):.2f}% already at/exceeds {max_risk_pct:.1f}% limit - no capacity for new position",
                            }
                        else:
                            # Scale down position to fit within available capacity.
                            # ROUND_DOWN, not ROUND_HALF_UP: available_capacity_dollars is the
                            # remaining room under the configured aggregate hard risk cap - rounding the
                            # scaled share count up can push risk_dollars (recomputed below from
                            # this share count) back past that cap, defeating the entire purpose
                            # of this scale-down branch. Same class of bug as the
                            # max_position_size_pct cap above.
                            scaled_shares = int(
                                (available_capacity_dollars / risk_per_share).quantize(Decimal(1), rounding=ROUND_DOWN)
                            )

                            if scaled_shares < 1:
                                # Can't fit even minimum position
                                return {
                                    "shares": 0,
                                    "position_size_pct": 0,
                                    "risk_dollars": 0,
                                    "status": "risk_limit_scaled_zero",
                                    "reason": f"Total open risk {(current_risk_dollars / pv_dec * Decimal(100)):.2f}% - available capacity ${available_capacity_dollars:.2f} insufficient for minimum position",
                                }

                            # Use scaled size
                            shares = scaled_shares
                            risk_dollars = risk_per_share * Decimal(shares)
                            position_value = Decimal(shares) * Decimal(str(entry_price))
                            position_pct_of_portfolio = position_value / pv_dec * Decimal(100)

                            logger.info(
                                f"[POSITION_SIZER] {symbol}: Risk-limited sizing applied. "
                                f"Current risk {(current_risk_dollars / pv_dec * Decimal(100)):.2f}%, "
                                # BUG FOUND 2026-08-25 (same class as
                                # [[t1_t2_t3_reason_hardcoded_r_multiple_stale_fixed_20260825]]):
                                # this line still hardcoded "4% limit" even though line 1227's
                                # threshold computation was already fixed 2026-08-06 to read
                                # max_risk_pct from config (live value: 8.0%) - the two sibling
                                # reason strings a few lines above (risk_limit/
                                # risk_limit_scaled_zero) already correctly use {max_risk_pct},
                                # only this log line was missed. Every risk-limited-scale-down
                                # since the 2026-08-06 fix logged the wrong percentage.
                                f"scaled from {base_shares} to {shares} shares to stay within {max_risk_pct:.1f}% limit"
                            )
            except Exception as e:
                # CRITICAL FIX: this used to log a warning and fall through to use the
                # unscaled, pre-risk-limit `shares`/`risk_dollars` computed above - the
                # comment justified it as "circuit breaker will catch it", but Phase 2
                # (circuit breakers) runs BEFORE Phase 8 (entry execution) in every
                # orchestrator cycle (see phase_registry.py phase_num ordering), so it
                # cannot retroactively catch an aggregate-risk breach created by that same
                # cycle's own entries - only the NEXT cycle's Phase 2 run would see it,
                # by which point the oversized positions are already open. Every other
                # validation failure in this exact function (missing config, invalid
                # portfolio value, query failures elsewhere) fails closed; this was the
                # one silent exception. A transient failure of just this one query should
                # not abort the whole entry batch (Phase 8 handles each symbol
                # independently), so this fails closed for this symbol only, not the run.
                logger.error(
                    f"[POSITION_SIZER] {symbol}: Could not enforce total open-risk limit ({e}). "
                    f"Blocking this entry rather than risking an unenforced aggregate-risk breach - "
                    f"Phase 2's circuit breaker only re-checks at the START of the NEXT cycle, not "
                    f"before this position would be opened."
                )
                return {
                    "shares": 0,
                    "position_size_pct": 0,
                    "risk_dollars": 0,
                    "status": "risk_check_unavailable",
                    "reason": f"Could not verify total open-risk limit for {symbol}: {e}",
                }

        # CRITICAL FIX: Convert ALL multipliers to Decimal BEFORE arithmetic (load-bearing rule: feedback_psycopg2_decimal_arithmetic)
        # Previously: mixed float * float * Decimal * float * Decimal → TypeError on float * Decimal
        # Fix: Convert all to Decimal first, then multiply together
        cascade_multiplier = (
            Decimal(str(risk_adjustment))
            * Decimal(str(exposure_mult))
            * Decimal(str(phase_mult))
            * Decimal(str(vix_mult))
            * Decimal(str(data_maturity_mult))
        )
        multipliers = {
            "risk_adjustment": float(risk_adjustment),
            "exposure_mult": float(exposure_mult),
            "phase_mult": float(phase_mult),
            "vix_mult": float(vix_mult),
            "data_maturity_mult": float(data_maturity_mult),
        }
        multiplier_reasons = {
            "risk_adjustment": f"drawdown-based risk adjustment: {multipliers['risk_adjustment']:.2f}x",
            "exposure_mult": f"market exposure multiplier: {multipliers['exposure_mult']:.2f}x",
            "phase_mult": f"stage/phase multiplier: {multipliers['phase_mult']:.2f}x",
            "vix_mult": f"VIX caution multiplier: {multipliers['vix_mult']:.2f}x",
            "data_maturity_mult": (
                f"historical data maturity multiplier: {multipliers['data_maturity_mult']:.2f}x "
                "(long-lookback indicators still partly built on the pre-2026-05-26 seed)"
            ),
        }
        self._record_sizing_audit(
            symbol=symbol,
            signal_date=signal_date,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            base_shares=base_shares,
            final_shares=shares,
            position_size_pct=position_pct_of_portfolio,
            cascade_multiplier=cascade_multiplier,
            multipliers=multipliers,
            reasons=multiplier_reasons,
        )

        return {
            "shares": shares,
            "position_size_pct": position_pct_of_portfolio,
            "risk_dollars": risk_dollars,
            "position_value": position_value,
            "status": "ok",
            # entry_dec (already-normalized Decimal), not the raw entry_price parameter (type
            # Any) - see the entry_dec/stop_dec fix above for why a string entry_price reaches
            # this far without raising: "%.2f"-style formatting of a raw str crashes with
            # "Unknown format code 'f' for object of type 'str'" instead of returning this
            # success result.
            "reason": f"{shares} shares @ ${entry_dec:.2f} = ${float(position_value):.2f} ({float(position_pct_of_portfolio):.1f}%)",
        }

    def _record_sizing_audit(
        self,
        symbol: str,
        signal_date: _date | None,
        entry_price: Any,
        stop_loss_price: Any,
        base_shares: int,
        final_shares: int,
        position_size_pct: Decimal,
        cascade_multiplier: Decimal,
        multipliers: dict[str, float],
        reasons: dict[str, str],
    ) -> None:
        """Persist the risk-multiplier cascade behind a sizing decision to algo_position_sizing_audit.

        This table's schema (base_shares/final_shares/cascade_multiplier/reasons_json) was added
        by migration but never written to - the exact multiplier cascade it exists to capture
        (risk_adjustment/exposure_mult/phase_mult/vix_mult, computed above) was always
        computed here, just never persisted. Left the table permanently empty, which made
        lambda/api/routes/risk_dashboard.py's comprehensive risk dashboard 503 unconditionally
        (its position_sizing_stats section raises when the table has zero rows) and the dedicated
        /position-sizing-audit forensics endpoint return nothing. Fires on every "ok" sizing
        decision (not just executed trades), matching algo_signal_rejections' convention of
        auditing every real decision the pipeline makes, not only ones a downstream check later acts on.
        Best-effort: a logging failure must not block position sizing or trade entry.
        """
        # Skip audit for hypothetical sizing (e.g., concentration checks). Audit requires signal_date
        # which is only available for real signals, not for what-if simulations during pre-entry checks.
        if signal_date is None:
            return

        try:
            import json

            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_position_sizing_audit (
                        symbol, signal_date, entry_price, stop_loss_price,
                        base_shares, final_shares, position_size_pct,
                        cascade_multiplier, multipliers_json, reasons_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        symbol,
                        signal_date,
                        float(entry_price),
                        float(stop_loss_price),
                        base_shares,
                        final_shares,
                        float(position_size_pct),
                        float(cascade_multiplier),
                        json.dumps(multipliers),
                        json.dumps(reasons),
                    ),
                )
        except Exception as e:
            logger.warning(f"[POSITION_SIZER] Failed to record sizing audit for {symbol}: {e}")
