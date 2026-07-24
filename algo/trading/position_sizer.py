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
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any, cast

import psycopg2
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
            "vix_caution_threshold",
            "vix_max_threshold",
            "vix_caution_risk_reduction",
        ]
        missing_keys = [k for k in required_config_keys if k not in config or config[k] is None]
        if missing_keys:
            raise ConfigurationError(
                f"CRITICAL: PositionSizer config missing required keys: {', '.join(missing_keys)}. "
                f"Cannot proceed with position sizing without explicit risk configuration."
            )

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
                cur.execute("""
                    SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots
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
                        "Phase 7 (reconciliation) must run daily. Last successful Phase 7 run: {snapshot_date}"
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

    def _fetch_live_alpaca_equity(self) -> Decimal:
        execution_mode = self.config.get("execution_mode", "paper")

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
        # session - scope the DB-snapshot fallback to execution_mode == "paper" only. Auto mode
        # now correctly reaches the real Alpaca API call below regardless of whether the
        # configured Alpaca account itself is live or Alpaca's own paper-trading endpoint (that
        # is controlled by credentials/base URL, a separate concern from execution_mode).
        if execution_mode == "paper":
            try:
                from utils.db.context import DatabaseContext

                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
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
            from config.credential_manager import get_credential_manager as _get_cm

            _creds = _get_cm().get_alpaca_credentials()
            key = _creds.get("key")
            secret = _creds.get("secret")
        except (ImportError, AttributeError, ValueError) as e:
            logger.error(f"[POSITION_SIZER] Alpaca credentials unavailable in live mode: {type(e).__name__}")
            raise RuntimeError(f"Live mode requires Alpaca credentials: {e}") from e

        base = os.getenv("APCA_API_BASE_URL")
        if not base:
            try:
                from config.api_endpoints import get_alpaca_base_url

                base = get_alpaca_base_url()
            except (ImportError, AttributeError) as cfg_e:
                raise ValueError(f"Alpaca config unavailable: {cfg_e}") from cfg_e
        if not key or not secret:
            raise RuntimeError("CRITICAL: Alpaca credentials not found. Cannot fetch portfolio value.")

        max_retries = self.config.get("alpaca_portfolio_fetch_retries", 3)
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
                        return Decimal(str(pv))

                    if "equity" in data and data["equity"] is not None:
                        pv = data["equity"]
                        return Decimal(str(pv))

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

            cur.execute("""
                SELECT
                    MAX(adjusted_equity) as peak,
                    (SELECT adjusted_equity FROM algo_portfolio_snapshots
                     WHERE adjusted_equity IS NOT NULL
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
            exposure_pct, data_date, data_unavailable, reason = row[0], row[1], row[2], row[3]
            # GOVERNANCE ENFORCEMENT: Fail-fast if data marked unavailable
            if data_unavailable is True:
                raise ValueError(
                    f"Market exposure marked unavailable (reason: {reason or 'unknown'}). "
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

    def get_phase_size_multiplier(self) -> float:
        """Stage-2 phase mult: always 1.0 (DB schema has no late/climax phase column)."""
        return 1.0

    def get_position_size_multiplier_from_regime(self, signal_date: _date | None = None) -> float:
        """Get position size multiplier from current market regime.

        Fail-fast  -" if regime cannot be determined, raises exception. Position sizing
        must account for current market regime to avoid inappropriate sizing.
        """
        try:
            from algo.orchestration import RegimeManager

            regime_mgr = RegimeManager()
            regime_mult = regime_mgr.get_position_size_multiplier(signal_date)
            if regime_mult is None:
                raise ValueError("Regime multiplier is None")
            return regime_mult
        except ValueError:
            raise
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Could not load RegimeManager: {e}") from e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Regime multiplier calculation failed: {type(e).__name__}: {e}") from e

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

    def get_active_positions_capital_pct(self) -> Decimal:
        """Get total capital invested as % of portfolio.

        Raises ValueError if portfolio_value is invalid or database unavailable.
        """
        portfolio_value = self.get_portfolio_value()
        if portfolio_value <= 0:
            raise ValueError(f"Invalid portfolio value for capital calculation: {portfolio_value}")

        def fetch_capital_pct(cur: PsycopgCursor[Any]) -> Decimal:
            cur.execute("""
                SELECT SUM(position_value) FROM algo_positions WHERE status = 'open'
            """)
            result = cur.fetchone()
            if result is None:
                raise ValueError("Position capital query returned None")
            total_value = Decimal(str(result[0])) if result[0] is not None else Decimal(0)
            return total_value / portfolio_value * Decimal(100)

        result: Decimal | int | float = self._with_cursor(fetch_capital_pct)
        if result is not None:
            return cast(Decimal, result)
        raise RuntimeError("Could not fetch capital percentage from database. Cannot calculate safe position size.")

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
        across all positions and scales position size down if we're running low on 4% limit capacity.
        This prevents individual position sizing from pushing aggregate risk over 4%.

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
        except (ZeroDivisionError, TypeError) as e:
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
        and scales position size down if aggregate risk would exceed 4% limit.

        Raises RuntimeError/ValueError for all error conditions. Let caller handle exceptions.
        Only returns success dict or explicit sizing denial (no_room, drawdown_halt, concentration, etc).
        """
        assert symbol and isinstance(symbol, str), f"Symbol must be non-empty string, got {symbol}"
        entry_dec = Decimal(str(entry_price))
        assert entry_dec > 0, f"Entry price must be > 0, got {entry_price}"
        stop_dec = Decimal(str(stop_loss_price))
        assert stop_dec > 0, f"Stop loss must be > 0, got {stop_loss_price}"
        assert stop_dec < entry_dec, f"Stop {stop_dec} must be < entry {entry_dec}"

        if portfolio_value is None:
            portfolio_value = self.get_portfolio_value()
        pv_dec = Decimal(str(portfolio_value))
        assert pv_dec > 0, f"Portfolio value must be > 0, got {portfolio_value}"

        risk_adjustment = self.get_risk_adjustment()
        assert risk_adjustment is not None, "Risk adjustment cannot be None"
        assert Decimal(str(risk_adjustment)) >= 0, f"Risk adjustment must be >= 0, got {risk_adjustment}"

        active_positions = self.get_position_count()
        assert isinstance(active_positions, int), f"Active positions must be int, got {type(active_positions)}"
        active_position_value = self.get_active_positions_value()

        max_positions_val = self.config.get("max_positions")
        if max_positions_val is None:
            raise ValueError("[POSITION_SIZER] Config missing required 'max_positions' key")
        try:
            max_positions = int(max_positions_val)
        except (ValueError, TypeError) as e:
            raise ValueError(f"[POSITION_SIZER] max_positions must be integer, got {type(max_positions_val).__name__}: {max_positions_val}") from e
        if max_positions <= 0:
            raise ValueError(f"[POSITION_SIZER] max_positions must be > 0, got {max_positions}")

        tolerance_buffer = max(1, int(max_positions * 0.15))
        hard_limit = max_positions + tolerance_buffer

        if active_positions >= hard_limit:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "no_room",
                "reason": f"{active_positions} open positions >= {hard_limit} hard limit (target {max_positions})",
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
        exposure_mult = self.get_market_exposure_multiplier()
        phase_mult = self.get_phase_size_multiplier()
        vix_mult = self.get_vix_caution_multiplier()
        regime_mult = self.get_position_size_multiplier_from_regime(signal_date)

        adjusted_risk_pct = (
            base_risk_pct
            * risk_adjustment
            * exposure_mult
            * Decimal(str(phase_mult))
            * vix_mult
            * Decimal(str(regime_mult))
        )
        risk_dollars = (portfolio_value * adjusted_risk_pct).quantize(Decimal("0.01"), ROUND_HALF_UP)

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

        if entry_price <= 0 or stop_loss_price >= entry_price:
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
        has_safety_reduction = exposure_mult < 0.8 or vix_mult < 1.0 or risk_adjustment < 1.0
        if adjusted_risk_pct < min_risk_floor and not has_safety_reduction:
            adjusted_risk_pct = min_risk_floor
            risk_dollars = portfolio_value * adjusted_risk_pct

        risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
        if risk_per_share <= 0:
            raise ValueError(
                f"[POSITION SIZER CRITICAL] Invalid risk_per_share={risk_per_share}: "
                f"stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). "
                f"Cannot size position with invalid stop price. This indicates corrupted position data."
            )
        shares = int((risk_dollars / risk_per_share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        base_shares = shares  # pre-cap share count from risk-based sizing alone, for algo_position_sizing_audit

        if shares < 1:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "too_small",
                "reason": f"Position too small: risk_dollars=${risk_dollars:.2f}, risk_per_share=${risk_per_share:.2f}",
            }

        position_value = Decimal(shares) * Decimal(str(entry_price))
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
        max_position_value = portfolio_value * max_position_pct

        if position_value > max_position_value:
            # ROUND_DOWN, not ROUND_HALF_UP: this caps position_value to a hard ceiling
            # (max_position_size_pct), so rounding the share count up can let the capped
            # position_value exceed max_position_value by up to half a share's value,
            # silently breaching the limit this branch exists to enforce.
            shares = int((max_position_value / Decimal(str(entry_price))).quantize(Decimal(1), rounding=ROUND_DOWN))
            position_value = Decimal(shares) * Decimal(str(entry_price))
            risk_dollars = risk_per_share * Decimal(shares)

        if portfolio_value <= 0:
            raise ValueError(
                f"CRITICAL: Portfolio value invalid ({portfolio_value}) - cannot calculate position sizing. "
                f"Position sizing requires current portfolio value > 0."
            )
        try:
            position_pct_of_portfolio = position_value / Decimal(str(portfolio_value)) * Decimal(100)
        except (ValueError, TypeError, decimal.InvalidOperation) as e:
            raise ValueError(
                f"CRITICAL: Position value calculation failed ({position_value}): {e}. "
                f"Cannot calculate position sizing without valid values."
            ) from e
        max_conc_val = self.config.get("max_concentration_pct")
        if max_conc_val is None:
            raise ValueError("CRITICAL: max_concentration_pct config missing. Cannot enforce concentration limit.")
        max_concentration = Decimal(str(max_conc_val))

        if position_pct_of_portfolio > max_concentration:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "concentration",
                "reason": f"Position would be {position_pct_of_portfolio:.1f}% > {max_concentration:.0f}% portfolio",
            }

        total_invested = Decimal(str(active_position_value)) + position_value
        max_inv_val = self.config.get("max_total_invested_pct")
        if max_inv_val is None:
            raise ValueError("CRITICAL: max_total_invested_pct config missing. Cannot enforce total investment limit.")
        max_invested_pct = Decimal(str(max_inv_val))
        if portfolio_value > 0 and (total_invested / Decimal(str(portfolio_value)) * Decimal(100)) > max_invested_pct:
            return {
                "shares": 0,
                "position_size_pct": 0,
                "risk_dollars": 0,
                "status": "no_room",
                "reason": f"Total invested would be {(total_invested / Decimal(str(portfolio_value)) * Decimal(100)):.0f}% > {max_invested_pct:.0f}%",
            }

        cascade_multiplier = (
            risk_adjustment * exposure_mult * Decimal(str(phase_mult)) * vix_mult * Decimal(str(regime_mult))
        )
        multipliers = {
            "risk_adjustment": float(risk_adjustment),
            "exposure_mult": float(exposure_mult),
            "phase_mult": float(phase_mult),
            "vix_mult": float(vix_mult),
            "regime_mult": float(regime_mult),
        }
        multiplier_reasons = {
            "risk_adjustment": f"drawdown-based risk adjustment: {multipliers['risk_adjustment']:.2f}x",
            "exposure_mult": f"market exposure multiplier: {multipliers['exposure_mult']:.2f}x",
            "phase_mult": f"stage/phase multiplier: {multipliers['phase_mult']:.2f}x",
            "vix_mult": f"VIX caution multiplier: {multipliers['vix_mult']:.2f}x",
            "regime_mult": f"market regime multiplier: {multipliers['regime_mult']:.2f}x",
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
            "reason": f"{shares} shares @ ${entry_price:.2f} = ${float(position_value):.2f} ({float(position_pct_of_portfolio):.1f}%)",
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
        (risk_adjustment/exposure_mult/phase_mult/vix_mult/regime_mult, computed above) was always
        computed here, just never persisted. Left the table permanently empty, which made
        lambda/api/routes/risk_dashboard.py's comprehensive risk dashboard 503 unconditionally
        (its position_sizing_stats section raises when the table has zero rows) and the dedicated
        /position-sizing-audit forensics endpoint return nothing. Fires on every "ok" sizing
        decision (not just executed trades), matching algo_signal_rejections' convention of
        auditing every real decision the pipeline makes, not only ones a downstream check later acts on.
        Best-effort: a logging failure must not block position sizing or trade entry.
        """
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
