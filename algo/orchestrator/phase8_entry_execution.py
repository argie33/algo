#!/usr/bin/env python3

"""PHASE 8: ENTRY EXECUTION - Transform signals into positions with strict validation.

Core responsibility: Execute buy signals from Phase 7 while enforcing multiple safety gates
and data quality checks. Phase 8 transforms qualified signals into actual positions with
rigorous risk management.

CONSTRAINT VALIDATION STRATEGY (AUDIT ISSUE #15):
Phase 8 receives exposure constraints from Phase 5 (ExposurePolicy tier settings).
These constraints must be validated BEFORE any trade execution:
- All required keys present (halt_new_entries, max_new_positions_today, max_concentration_pct, regime)
- All values have correct types (bool, int, float, string)
- All values within valid ranges (concentration 0-100%, regime = confirmed_uptrend/uptrend_under_pressure/caution/correction)
- If invalid: Phase 8 halts with clear error message
See: _validate_constraints_for_phase8() for implementation.

HALT FLAG PROPAGATION (AUDIT ISSUE #7):
When Phase 7 halts (due to missing signal data):
- qualified_trades is empty or None
- Phase 8 gracefully handles this (no entries, not fatal)
- Phase 7 status propagates to Phase 8's risk checks via executor.get_result(7)

DATA QUALITY VALIDATION (AUDIT ISSUE #4):
Before any trade execution:
- Technical data: ATR >= 0.01 (not frozen), SMA_50 > 0 (valid data)
- Prices: entry_price > 0, stop_loss > 0 and < entry_price
- Quantities: must be positive integers
Invalid data skipped per-signal with logging, not fatal.

POSITION SYNC VALIDATION (AUDIT ISSUE #3):
Position synchronization from trades to algo_positions:
- Validates: entry_price NOT NULL and > 0, quantity > 0
- Prevents corrupted records
See: algo/orchestration/position_sync.py for implementation.

EXECUTION PIPELINE for each qualified signal from Phase 7:

1. Check halt flag before any entry
2. Check exposure constraints from Phase 5 (ExposurePolicy tier)
3. Run liquidity checks (ADV, dollar volume, price history age)
4. Compute true ATR (max of H-L, |H-prev_C|, |L-prev_C|) anchored to run_date
5. Compute SMA_50 anchored to run_date
6. Stop loss: min(SMA_50 - ATR, entry - 1.2*ATR) - lower stop = more room for the trade
7. Use PositionSizer for regime-aware, drawdown-adjusted sizing
8. Run PreTradeChecks (size cap, duplicate prevention, minimum order)
9. Execute trade

CRITICAL DATA FRESHNESS ASSUMPTIONS (Session 2026-08-01):
Phase 1 validates price_daily and market_exposure_daily freshness at orchestrator start.
But Phase 8 may run HOURS later. Between Phase 1 and Phase 8:
- Market may close early (half-day)
- Data pipeline may stall after Phase 1 completes
- EOD loaders (load_market_status_daily at 4:05 PM) may fail for afternoon runs

Phase 8 should NOT assume data from Phase 1 is still valid:
- Morning run: Phase 1 at 9:00 AM, Phase 8 at 1:00 PM → price data is TODAY's, OK
- Afternoon run: Phase 1 at 1:00 PM, Phase 8 at 3:00 PM → price_daily may lack today's close
- Evening run: Phase 1 at 5:00 PM, Phase 8 at 5:30 PM → price_daily may lack today's EOD

Recommendation: Add re-validation in Phase 8 for afternoon/evening runs (see _calculate_current_total_risk_pct).

TIMEZONE REQUIREMENT: run_date parameter is always ET (Eastern Time), not UTC.
Market trading hours are 9:30 AM - 4:00 PM ET. Do NOT convert run_date to UTC or query
CURRENT_DATE/CURRENT_TIMESTAMP directly for trading decisions. All database queries should
use the run_date parameter or query price_daily MAX(date) to align with ET-based trading.
"""

import logging
import os
import time
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import psycopg2

from algo.infrastructure.market_calendar import MarketCalendar
from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase_data_contract import ExposureConstraints, QualifiedTrade
from algo.orchestrator.phase_result import PhaseResult
from algo.orchestrator.phase8_preentry_health_check import PreEntryHealthValidator
from algo.risk import LiquidityChecks
from algo.trading.exceptions import DatabaseError
from algo.trading.executor import TradeExecutor
from algo.trading.position_sizer import PositionSizer
from algo.trading.pretrade_checks import PreTradeChecks
from utils.db.context import DatabaseContext
from utils.infrastructure import EASTERN_TZ
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)

# ISSUE 15 FIX: Define valid constraint values for Phase 8 validation
# CRITICAL FIX: Must match the real regime taxonomy (see phase5_exposure_policy.py VALID_REGIMES
# for why - the old "expansion"/"correction"/"caution" list never matched actual data).
VALID_REGIMES = ["confirmed_uptrend", "uptrend_under_pressure", "caution", "correction"]

# CRITICAL: Maximum allowed risk per position (20%)
# Used in stop loss calculation and risk capping logic
MAX_RISK_ALLOWED = 0.20


def _validate_constraints_for_phase8(exposure_constraints: ExposureConstraints | Any) -> None:
    """AUDIT ISSUE #15 FIX: Validate exposure constraints before using in Phase 8 entry execution.

    Ensures all required constraint fields have valid values. Fail-fast if invalid.
    This validation is CRITICAL because exposure constraints control position sizing,
    concentration limits, and entry blocking - incorrect values could lead to oversized
    positions or entries outside policy.

    RATIONALE: Data integrity first. Phase 5 (ExposurePolicy) generates these constraints
    from market regime, volatility, and drawdown metrics. If Phase 5 produces invalid
    constraints due to data corruption or logic error, Phase 8 must catch it BEFORE
    attempting any trades, not after position sizing causes damage.

    Accepts both ExposurePolicyConstraints dataclass and dict for backwards compatibility.

    Validation checkpoints:
    1. Constraint dict/dataclass exists and is proper type
    2. All required keys/attributes are present
    3. Each value has correct type
    4. Each value is within valid range
    5. Enum values (regime) are from allowed list

    If any check fails, Phase 8 halts with clear error message explaining which field
    failed and why. Operator can then investigate Phase 5 output.

    Raises:
        TypeError: If exposure_constraints is not a dict or dataclass
        ValueError: If any constraint is invalid or missing (includes all details)
    """
    from algo.risk import ExposurePolicyConstraints

    # Convert dataclass to dict if needed for uniform validation
    if isinstance(exposure_constraints, ExposurePolicyConstraints):
        constraints_dict = exposure_constraints.to_dict()
    elif isinstance(exposure_constraints, dict):
        constraints_dict = cast(dict[str, Any], exposure_constraints)
    else:
        raise TypeError(f"exposure_constraints must be dict or ExposurePolicyConstraints, got {type(exposure_constraints).__name__}")

    errors = []
    tier_name = constraints_dict.get("tier_name", "UNKNOWN_TIER")

    # CHECKPOINT 1: All required keys must be present
    # These fields are mandatory for Phase 8 to make safe trading decisions
    required_keys = ["halt_new_entries", "max_new_positions_today", "max_concentration_pct", "regime"]
    for key in required_keys:
        if key not in constraints_dict:
            errors.append(f"Missing required key: {key}")

    # CHECKPOINT 2-5: Validate individual field values
    # Each validation includes type check and range check (if applicable)

    if "halt_new_entries" in constraints_dict:
        # AUDIT ISSUE #15: bool type required (not truthy/falsy string)
        val = constraints_dict.get("halt_new_entries")
        if not isinstance(val, bool):
            errors.append(f"halt_new_entries must be bool, got {type(val).__name__}")

    if "max_new_positions_today" in constraints_dict:
        # AUDIT ISSUE #15: int >= 0 required (prevents negative or fractional positions)
        val = constraints_dict.get("max_new_positions_today")
        if not isinstance(val, int) or val < 0:
            errors.append(f"max_new_positions_today must be int >= 0, got {val}")

    if "max_concentration_pct" in constraints_dict:
        # AUDIT ISSUE #15: percentage must be 0-100 (valid range for concentration)
        # Allows 0% (no single-stock limit) to 100% (entire portfolio in one stock, not recommended)
        val = constraints_dict.get("max_concentration_pct")
        if not isinstance(val, (int, float)) or not (0.0 <= val <= 100.0):
            errors.append(f"max_concentration_pct must be 0.0-100.0, got {val}")

    if "regime" in constraints_dict:
        # AUDIT ISSUE #15: regime must be from defined set (see VALID_REGIMES above)
        # Maps to market conditions and position sizing tier in ExposurePolicy
        regime = constraints_dict.get("regime", "").lower()
        if regime not in VALID_REGIMES:
            errors.append(f"regime must be one of {VALID_REGIMES}, got '{regime}'")

    # CRITICAL: Check for contradictory constraints (HIGH ISSUE #1 FIX)
    # Contradictory constraints indicate configuration error that would cause unexpected behavior
    if constraints_dict.get("halt_new_entries") is False:
        # If entries are NOT halted, at least one entry constraint must allow entries
        max_positions = constraints_dict.get("max_new_positions_today", 0)
        max_concentration = constraints_dict.get("max_concentration_pct", 0.0)

        if max_positions == 0:
            errors.append(
                f"Contradictory [{tier_name}]: halt_new_entries=False but max_new_positions_today=0. "
                "Either halt entries (halt_new_entries=True) or allow entries (max_new_positions_today > 0). "
                f"Investigate ExposurePolicy tier {tier_name} in Phase 5."
            )

        if max_concentration == 0:
            errors.append(
                f"Contradictory [{tier_name}]: halt_new_entries=False but max_concentration_pct=0.0. "
                "Either halt entries (halt_new_entries=True) or allow positions (max_concentration_pct > 0). "
                f"Investigate ExposurePolicy tier {tier_name} in Phase 5."
            )

    # If any validation failed, halt with comprehensive error message
    if errors:
        error_msg = f"Invalid exposure constraints from tier [{tier_name}]: {'; '.join(errors)}"
        logger.error(f"[PHASE 8] {error_msg}")
        raise ValueError(error_msg)

    # AUDIT TRAIL: Log successful constraint validation for monitoring and audit
    logger.info(
        f"[PHASE 8 AUDIT] Constraint validation passed [{tier_name}]: "
        f"halt_new_entries={constraints_dict.get('halt_new_entries')}, "
        f"max_new_positions={constraints_dict.get('max_new_positions_today')}, "
        f"max_concentration={constraints_dict.get('max_concentration_pct')}%, "
        f"regime={constraints_dict.get('regime')}"
    )


def _calculate_dynamic_stop_loss(entry_price: float, atr: float, sma_50: float) -> float:
    """Calculate stop loss with dynamic ATR multiplier based on volatility.

    CRITICAL FIX: Applies the same dynamic logic consistently across all stop-loss calculations
    (precheck and main execution). Ensures high-volatility stocks are treated fairly and don't
    get rejected for wider stops when a tighter multiplier would fit within risk limits.

    Progressive tightening based on volatility:
    - Normal (ATR < 5% of price): entry - 1.2*ATR
    - High (ATR 5-10% of price): entry - 0.8*ATR
    - Extreme (ATR >= 10% of price): entry - 0.5*ATR

    This ensures high-volatility stocks (ETFs, penny stocks, earnings runners) can still
    be traded without hitting the 20% max risk limit due to wide ATR multipliers.

    Then applies support-level validation (SMA_50 - ATR) as a floor.

    Args:
        entry_price: Stock entry price
        atr: Average True Range (volatility indicator)
        sma_50: 50-day simple moving average

    Returns:
        Calculated stop loss price (always > 0 and < entry_price)
    """
    if entry_price <= 0:
        raise ValueError(f"Invalid entry_price={entry_price} for stop-loss calculation. Must be > 0.")
    if atr < 0:
        raise ValueError(f"Invalid atr={atr} for stop-loss calculation. Must be >= 0.")

    atr_ratio = atr / entry_price

    # Progressive multiplier based on volatility
    if atr_ratio >= 0.10:  # Extreme volatility: ATR >= 10% of price
        atr_multiplier = 0.5  # Very tight: entry - 0.5*ATR
    elif atr_ratio >= 0.05:  # High volatility: ATR 5-10% of price
        atr_multiplier = 0.8  # Tight: entry - 0.8*ATR
    else:  # Normal volatility: ATR < 5% of price
        atr_multiplier = 1.2  # Standard: entry - 1.2*ATR

    volatility_stop = entry_price - atr_multiplier * atr
    risk_with_volatility_stop = (entry_price - volatility_stop) / entry_price

    # If even the tight volatility stop is too wide, cap it at MAX_RISK_ALLOWED
    if risk_with_volatility_stop > MAX_RISK_ALLOWED:
        stop_loss = entry_price * (1 - MAX_RISK_ALLOWED)
    else:
        # Use support-level stop (SMA_50 - ATR) if it's tighter than volatility stop
        support_stop = sma_50 - atr
        support_risk = (entry_price - support_stop) / entry_price

        # Only use support_stop if it's valid and fits within risk limits
        if support_stop > 0 and support_stop < entry_price and support_risk <= MAX_RISK_ALLOWED:
            stop_loss = min(volatility_stop, support_stop)
        else:
            stop_loss = volatility_stop

    return max(stop_loss, 0.01)  # Ensure stop is never negative or zero


def _calculate_pre_entry_concentration_impact(
    qualified_signals: list[QualifiedTrade],
    sizer: PositionSizer,
    portfolio_value: Decimal,
    merged_technical_data: dict[str, dict[str, Any]],
    run_date: _date,
) -> tuple[float, list[str]]:
    """Calculate total concentration impact of ALL pending signals BEFORE any entries.

    CRITICAL FIX (Session 2026-08-05): Pre-entry concentration check was disabled due to
    using a simplified formula that produced impossible values (e.g., 588% concentration).
    This fix implements the CORRECT calculation using actual PositionSizer logic:
    - Regime-aware multipliers
    - Drawdown reductions
    - Max position size caps
    - Tier-specific concentration limits

    Args:
        qualified_signals: List of QualifiedTrade signals to be entered
        sizer: PositionSizer instance (has actual config with regime multipliers, drawdown, caps)
        portfolio_value: Current portfolio value (Decimal)
        merged_technical_data: Dict of {symbol: {atr_14, sma_50, close}}
        run_date: Trading date

    Returns:
        (total_concentration_pct, blocked_symbols) tuple where:
        - total_concentration_pct: Sum of concentration % across all pending signals
        - blocked_symbols: List of signals that would exceed individual limits

    This calculates concentration WITHOUT executing orders - it simulates what PositionSizer
    WOULD calculate for each signal, accumulates the concentration, and returns the total.
    """
    if portfolio_value <= 0:
        raise ValueError(f"Invalid portfolio_value={portfolio_value} for concentration calculation. Must be > 0.")

    total_concentration = 0.0
    blocked_symbols = []
    signal_positions = []

    for signal in qualified_signals:
        symbol = signal.get("symbol")
        if not symbol:
            continue

        try:
            # Get technical data needed for position sizing
            tech_data = merged_technical_data.get(str(symbol), {})
            atr_val = tech_data.get("atr_14") or tech_data.get("atr")
            sma_50_val = tech_data.get("sma_50")
            close_val = tech_data.get("close")

            if not (atr_val and sma_50_val and close_val):
                logger.warning(
                    f"[CONCENTRATION CHECK] {symbol}: Incomplete technical data. Skipping from pre-entry concentration calc."
                )
                continue

            entry_price = float(close_val)
            atr = float(atr_val)
            sma_50 = float(sma_50_val)

            # Calculate stop loss using dynamic ATR multiplier (same as main execution)
            stop_loss = _calculate_dynamic_stop_loss(entry_price, atr, sma_50)

            if entry_price <= 0 or atr < 0 or sma_50 <= 0 or stop_loss <= 0:
                logger.warning(
                    f"[CONCENTRATION CHECK] {symbol}: Invalid technical data. Skipping from concentration calc."
                )
                continue

            # Call PositionSizer to get ACTUAL position sizing
            # Use enforce_total_risk_limit=False to get position size without checking the 4% portfolio risk limit
            # (we only care about concentration here, not total risk)
            position_result = sizer.calculate_position_size(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
                portfolio_value=portfolio_value,
                enforce_total_risk_limit=False,  # Don't check 4% limit here - we're just sizing
            )

            # If PositionSizer returned 0 shares (blocked), track it
            if position_result.get("shares", 0) == 0:
                reason = position_result.get("reason", "unknown")
                blocked_symbols.append(f"{symbol}({reason})")
                continue

            # Calculate concentration for this position
            shares = position_result.get("shares", 0)
            if shares > 0:
                position_value = Decimal(shares) * Decimal(str(entry_price))
                concentration_pct = float((position_value / portfolio_value) * Decimal(100))
                total_concentration += concentration_pct
                signal_positions.append(
                    {"symbol": symbol, "shares": shares, "concentration_pct": concentration_pct}
                )

                logger.info(
                    f"[CONCENTRATION CHECK] {symbol}: {shares} shares @ ${entry_price:.2f} = "
                    f"{concentration_pct:.2f}% concentration"
                )

        except Exception as e:
            raise RuntimeError(
                f"[PHASE 8 CRITICAL] {symbol}: Could not calculate concentration - {e}. "
                f"Cannot enforce position sizing without concentration calculation. "
                f"Cannot enter position without this safety check."
            )

    if signal_positions:
        breakdown = ", ".join(f"{p['symbol']}:{p['concentration_pct']:.1f}%" for p in signal_positions[:5])
        more = "..." if len(signal_positions) > 5 else ""
        logger.info(
            f"[CONCENTRATION CHECK] Pending signals total concentration: {total_concentration:.2f}%. "
            f"Breakdown: {breakdown}{more}"
        )

    return total_concentration, blocked_symbols


def _calculate_current_total_risk_pct(max_risk_limit_pct: float = 4.0) -> tuple[float, float]:
    """Calculate total open risk as percentage of portfolio.

    PROACTIVE RISK CHECK: Used by Phase 8 to verify entry won't exceed risk limit BEFORE executing.
    This is defensive - we check before entering, not after.

    CRITICAL FIX (Session 2026-08-01): Validates that all open trades have complete data
    (entry_price, stop_loss_price, quantity) before calculating risk. Missing data would cause
    SUM() to return NULL, yielding FALSE LOW risk and allowing entries beyond safe limits.

    Returns:
        (current_risk_pct, available_risk_pct) where available = limit - current

    Raises:
        RuntimeError: If portfolio value or risk calculation fails, or if data completeness issues detected
    """
    try:
        with DatabaseContext("read") as cur:
            # CRITICAL FIX: Validate that ALL open trades have required data for risk calculation
            # Use t.trade_id (text) not t.id (integer) since trade_ids_arr is text array
            cur.execute("""
                SELECT COUNT(*) as incomplete_count,
                       STRING_AGG(DISTINCT p.symbol, ', ') as symbols_with_issues
                FROM algo_positions p
                LEFT JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
                WHERE p.status = 'open'
                  AND (t.entry_price IS NULL
                       OR p.current_stop_price IS NULL
                       OR p.quantity IS NULL
                       OR p.quantity = 0)
            """)
            validation = cur.fetchone()
            incomplete_count = validation[0] if validation else 0
            if incomplete_count and incomplete_count > 0:
                symbols_with_issues = validation[1] if len(validation) > 1 and validation[1] else "unknown"
                raise RuntimeError(
                    f"[RISK CHECK CRITICAL] {incomplete_count} open trade(s) have incomplete data: {symbols_with_issues}. "
                    f"Cannot calculate risk: missing entry_price, stop_loss_price, or quantity. "
                    f"Data corruption detected - manual intervention required before entries can proceed."
                )

            # Get current open positions and calculate total risk
            cur.execute("""
                SELECT
                    SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * p.quantity)) as total_risk_dollars,
                    COUNT(*) as open_count
                FROM algo_positions p
                JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
                WHERE p.status = 'open'
                  AND t.entry_price IS NOT NULL
                  AND p.current_stop_price IS NOT NULL
                  AND p.quantity IS NOT NULL
                  AND p.quantity > 0
            """)
            result = cur.fetchone()
            if result is None or len(result) < 2:
                raise RuntimeError(
                    "[ENTRY EXECUTION] Risk calculation query returned no rows or incomplete result. "
                    "This indicates database failure. Check: (1) database connectivity, (2) algo_positions table exists"
                )
            # SUM returns NULL when no matching rows; COUNT returns 0 or actual count
            total_risk_dollars = float(result[0]) if result[0] is not None else 0.0
            open_count = result[1] if result[1] is not None else 0

            # Get portfolio value
            cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
            pf_row = cur.fetchone()
            if not pf_row or not pf_row[0]:
                raise RuntimeError("Portfolio value unavailable - cannot calculate risk")

            portfolio_value = float(pf_row[0])
            current_risk_pct = (total_risk_dollars / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
            available_risk_pct = max_risk_limit_pct - current_risk_pct

            # MEDIUM FIX: Add bounds checking for risk percentages
            # Ensure percentages stay within 0-100% range to prevent calculation errors
            if current_risk_pct < 0 or current_risk_pct > 100:
                logger.critical(
                    f"[RISK CHECK INVALID] Risk percentage {current_risk_pct:.2f}% outside valid range [0,100]. "
                    f"Portfolio value: {portfolio_value}, Total risk: {total_risk_dollars}. "
                    f"This indicates a data integrity issue or calculation error."
                )
                # Clamp to valid range to prevent cascading errors
                current_risk_pct = max(0.0, min(100.0, current_risk_pct))

            if available_risk_pct < 0:
                logger.warning(
                    f"[RISK CHECK] Available capacity {available_risk_pct:.2f}% is negative. "
                    f"Current risk {current_risk_pct:.2f}% exceeds limit {max_risk_limit_pct}%."
                )

            logger.info(
                f"[RISK CHECK] Total open risk: {current_risk_pct:.2f}% ({open_count} positions), "
                f"Available capacity: {available_risk_pct:.2f}% (limit: {max_risk_limit_pct}%)"
            )

            return current_risk_pct, available_risk_pct
    except RuntimeError:
        raise
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[RISK CHECK] Failed to calculate total open risk (DB error): {e}")
        raise RuntimeError(f"Risk calculation failed (DB): {e}") from e
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"[RISK CHECK] Failed to calculate total open risk (data error): {e}")
        raise RuntimeError(f"Risk calculation failed (data): {e}") from e
    except Exception as e:
        logger.error(f"[RISK CHECK] Failed to calculate total open risk (unexpected): {e}")
        raise RuntimeError(f"Risk calculation failed: {e}") from e


# algo_signal_rejections.rejection_reason is VARCHAR(200). Callers pass through full
# exception messages (some wrapped/re-wrapped across several layers - confirmed live
# 2026-07-27 at 320 chars for a single wrapped ValueError), so truncate defensively rather
# than let a StringDataRightTruncation from the audit INSERT itself crash the entire
# orchestrator run for every remaining symbol. The full untruncated message is always
# captured first via logger.error/logger.info at the call site, so nothing is lost from
# the operational logs - only the DB audit row is shortened.
_REJECTION_REASON_MAX_LEN = 200

# TradeExecutor.execute_trade() returns these statuses from its pre-submission validation
# checks (CheckHandlerRegistry in check_handler_strategies.py, plus the direct
# duplicate-position check in executor_entry_handler.py) - all fire before an order is ever
# attempted, exactly matching this function's own "skipped" definition below ("signals
# filtered out by policy before an order was ever attempted"). Confirmed live 2026-07-27:
# 2 signals correctly blocked by the 5-day reentry-reset rule (reentry_cooldown) for symbols
# closed earlier the same session were counted as failed_count instead, corrupting
# success_rate's attempted=executed+failed denominator and marking Phase 8 "degraded" - and
# the whole run "degraded" - on a day where every risk gate worked exactly as designed,
# indistinguishable from a real broker/DB outage in the final report.
_POLICY_REJECTION_STATUSES = {
    "duplicate",
    "duplicate_signal",
    "duplicate_position",
    "pending_trade_exists",
    "reentry_cooldown",
    "reentry_blocked",
}


def _cleanup_orphaned_positions() -> int:
    """Clean up corrupted/orphaned positions with missing critical data or zero quantity.

    AUDIT ISSUE #6: Positions with data corruption can occur when:
    - Phase 6 exit clears the position (quantity→0) but status update fails
    - Trade data is corrupted upstream and critical fields (entry_price, stop_loss) not set
    - Position was created but corresponding trade insertion failed

    These corrupted positions:
    - Shouldn't exist in the 'open' state (they're unmanageable)
    - Will fail risk validation and halt Phase 8 entry execution
    - Should be cleaned up proactively before risk checks run

    This function closes positions with:
    1. quantity=0 (fully exited but still marked open)
    2. NULL entry_price, stop_loss_price, or quantity (incomplete/corrupted data)
    3. Zero quantity (degenerate case of data corruption)

    Returns:
        Number of positions cleaned up
    """
    try:
        with DatabaseContext("write") as cur:
            # Find all corrupted positions (quantity=0, NULL fields, or zero quantity)
            cur.execute(
                """
                SELECT COUNT(*) FROM algo_positions
                WHERE status = 'open'
                  AND (quantity = 0
                       OR quantity IS NULL
                       OR entry_price IS NULL
                       OR stop_loss_price IS NULL)
                """
            )
            result = cur.fetchone()
            orphaned_count = result[0] if result else 0

            if orphaned_count > 0:
                # Mark all corrupted positions as closed
                cur.execute(
                    """
                    UPDATE algo_positions
                    SET status = 'closed',
                        closed_at = CURRENT_TIMESTAMP,
                        exit_reason = 'Phase8_cleanup_data_corruption'
                    WHERE status = 'open'
                      AND (quantity = 0
                           OR quantity IS NULL
                           OR entry_price IS NULL
                           OR stop_loss_price IS NULL)
                    """
                )
                logger.warning(
                    f"[PHASE 8 CLEANUP DATA CORRUPTION] Closed {orphaned_count} corrupted positions. "
                    f"These had missing or NULL critical fields (quantity, entry_price, stop_loss_price). "
                    f"Data corruption detected and cleaned up to prevent Phase 8 halt."
                )
                return orphaned_count
            return 0
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[PHASE 8 CLEANUP] Failed to clean up corrupted positions (DB error): {e}")
        # Don't fail Phase 8 over cleanup failure - log and continue
        return 0
    except Exception as e:
        logger.error(f"[PHASE 8 CLEANUP] Failed to clean up corrupted positions: {e}")
        # Don't fail Phase 8 over cleanup failure - log and continue
        return 0


def _log_signal_rejection(
    symbol: str,
    rejection_stage: str,
    rejection_reason: str,
    run_date: _date,
    entry_price: float | None = None,
    risk_pct: float | None = None,
) -> None:
    """Log signal rejection to audit table AND mark signal as rejected in algo_signals.

    CRITICAL FIX (Session 2026-08-03): Previously, rejected signals were logged to
    algo_signal_rejections but left marked as signal_active=TRUE in algo_signals,
    causing the dashboard to show rejected signals as "active". This function now:
    1. Logs rejection to algo_signal_rejections (audit trail)
    2. Updates algo_signals to set execution_status='rejected' (dashboard visibility)
    3. Preserves rejection_reason for quick lookup in dashboard queries
    """
    if len(rejection_reason) > _REJECTION_REASON_MAX_LEN:
        rejection_reason = rejection_reason[: _REJECTION_REASON_MAX_LEN - 3] + "..."
    try:
        with DatabaseContext("write") as cur:
            # 1. Log to audit table (existing behavior)
            cur.execute(
                """INSERT INTO algo_signal_rejections
                   (rejection_date, symbol, rejection_stage, rejection_reason, entry_price, risk_pct)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (run_date, symbol, rejection_stage, rejection_reason, entry_price, risk_pct),
            )

            # 2. NEW: Mark signal as rejected in algo_signals so dashboard knows this signal was rejected
            # This ensures the dashboard query (WHERE execution_status='executed') excludes rejected signals
            rejection_reason_short = f"{rejection_stage}: {rejection_reason}"
            cur.execute(
                """UPDATE algo_signals
                   SET execution_status = 'rejected',
                       rejection_reason = %s,
                       updated_at = NOW()
                   WHERE symbol = %s AND signal_date = %s""",
                (rejection_reason_short, symbol, run_date),
            )
            if cur.rowcount == 0:
                logger.warning(
                    f"[AUDIT] Signal {symbol} rejected ({rejection_stage}) but not found in algo_signals. "
                    f"May not have been persisted yet. Audit trail recorded in algo_signal_rejections."
                )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[AUDIT] CRITICAL: Failed to log signal rejection for {symbol} (DB error): {e}. Audit trail incomplete.")
        raise RuntimeError(f"Signal rejection audit logging failed for {symbol} (DB): {e}") from e
    except Exception as e:
        logger.error(f"[AUDIT] CRITICAL: Failed to log signal rejection for {symbol}: {e}. Audit trail incomplete.")
        raise RuntimeError(f"Signal rejection audit logging failed for {symbol}: {e}") from e


def _persist_signals_to_database(qualified_trades: list[QualifiedTrade], run_date: _date, dry_run: bool) -> int:
    """Persist Phase 7 generated signals to algo_signals table for dashboard display.

    CRITICAL FIX: Signals were being generated but never saved, causing:
    - Dashboard to show no signals
    - Historical signal count stuck at 3 (from prior run)
    - No signal audit trail

    This insertion makes signals visible to:
    - Dashboard signal panel
    - Signal quality analysis
    - Historical backtesting reports
    """
    if not qualified_trades:
        return 0

    inserted_count = 0
    skipped_count = 0

    try:
        with DatabaseContext("write") as cur:
            for signal_data in qualified_trades:
                # Extract required fields from Phase 7 signal data
                symbol = signal_data.get("symbol")
                if not symbol:
                    logger.warning("[PERSIST SIGNALS] Skipping signal with no symbol")
                    skipped_count += 1
                    continue

                # Explicitly validate required financial fields (fail-fast governance)
                if "entry_price" not in signal_data or signal_data["entry_price"] is None:
                    logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: missing entry_price")
                    skipped_count += 1
                    continue
                # CRITICAL FIX: Session 345 - Validate type conversion (handles NaN/Infinity/non-numeric)
                try:
                    from utils.type_conversion import safe_float

                    entry_price = safe_float(signal_data["entry_price"], f"{symbol}.entry_price", allow_none=False)
                except (ValueError, TypeError) as e:
                    logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: invalid entry_price: {e}")
                    skipped_count += 1
                    continue

                # CRITICAL: Signal quality score is MANDATORY for audit trail and Phase 7 filtering
                # Don't persist signals without explicit quality assessment
                signal_quality_score = None
                if "composite_score" in signal_data and signal_data["composite_score"] is not None:
                    try:
                        signal_quality_score = safe_float(
                            signal_data["composite_score"], f"{symbol}.composite_score", allow_none=False
                        )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: invalid composite_score: {e}")
                        skipped_count += 1
                        continue
                elif "signal_quality_score" in signal_data and signal_data["signal_quality_score"] is not None:
                    try:
                        signal_quality_score = safe_float(
                            signal_data["signal_quality_score"], f"{symbol}.signal_quality_score", allow_none=False
                        )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: invalid signal_quality_score: {e}")
                        skipped_count += 1
                        continue

                # CRITICAL VALIDATION: signal_quality_score cannot be None
                # Each signal must have explicit quality assessment for audit and filtering
                if signal_quality_score is None:
                    logger.warning(
                        f"[PERSIST SIGNALS] Skipping {symbol}: missing signal quality score. "
                        f"Signal must have explicit quality assessment. "
                        f"Fail-fast: signal quality is required for audit trail and Phase 7 filtering."
                    )
                    skipped_count += 1
                    continue

                if "risk_score" not in signal_data or signal_data["risk_score"] is None:
                    logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: missing risk_score")
                    skipped_count += 1
                    continue
                try:
                    risk_score = safe_float(signal_data["risk_score"], f"{symbol}.risk_score", allow_none=False)
                except (ValueError, TypeError) as e:
                    logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: invalid risk_score: {e}")
                    skipped_count += 1
                    continue

                cur.execute(
                    """
                    INSERT INTO algo_signals (
                        signal_date, symbol, source_table, source_timeframe, raw_signal,
                        entry_price, entry_stage, signal_active,
                        signal_quality_score, risk_score, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                    ON CONFLICT (signal_date, symbol, source_timeframe) DO UPDATE SET
                        updated_at = NOW(),
                        raw_signal = EXCLUDED.raw_signal,
                        entry_price = EXCLUDED.entry_price,
                        signal_quality_score = EXCLUDED.signal_quality_score,
                        risk_score = EXCLUDED.risk_score
                """,
                    (
                        run_date,
                        symbol,
                        "phase7_signal_generation",
                        "daily",
                        "BUY",
                        entry_price,
                        "entry",
                        True,
                        signal_quality_score,
                        risk_score,
                    ),
                )
                # Validate that signal was actually inserted/updated
                if cur.rowcount < 1:
                    logger.error(f"[PERSIST SIGNALS] Failed to insert signal for {symbol}: rowcount={cur.rowcount}")
                    raise RuntimeError(f"[PERSIST SIGNALS] Signal insert returned no rows for {symbol} on {run_date}")
                inserted_count += 1

        if skipped_count:
            logger.warning(
                f"[PERSIST SIGNALS] Inserted {inserted_count}/{len(qualified_trades)} signals for {run_date} "
                f"({skipped_count} skipped - see warnings above)"
            )
        else:
            logger.info(f"[PERSIST SIGNALS] Inserted {inserted_count} signals for {run_date}")
        return inserted_count
    except psycopg2.DatabaseError as e:
        logger.error(f"[PERSIST SIGNALS] Database error: {e}", exc_info=True)
        raise RuntimeError(f"[PHASE 8] Failed to persist entry signals: {e}") from e


def _batch_fetch_technical_data(
    symbols_with_precomputed: dict[str, dict[str, Any]], run_date: _date, period: int = 14
) -> dict[str, dict[str, float | None]]:
    """Batch-fetch missing ATR and SMA_50 data, using pre-computed values from Phase 5 when available.



    Args:

        symbols_with_precomputed: Dict mapping symbol -> {pre-computed fields from Phase 5}

        run_date: Trading date

        period: ATR period (default 14)



    Returns dict keyed by symbol with {atr, sma_50, close} values.



    ISSUE #8 FIX: Reuses Phase 5's SMA_50 and ATR computations instead of recomputing.

    Only fetches missing data (symbols with no phase5_precomputed values).

    """

    if not symbols_with_precomputed:
        # Phase 5 didn't run or produced no candidates (e.g., circuit breaker halted entry)
        # This is not an error-it means no entries are allowed. Return empty dict (no candidates to process).
        logger.warning(
            "[PHASE8] No precomputed technical data available for entry execution. "
            "Phase 5 likely halted or produced no candidates. No entries will be executed this run."
        )
        return {}

    # Separate symbols that have precomputed values from those that don't

    precomputed_by_symbol = {}

    symbols_needing_fetch = []

    for symbol, data in symbols_with_precomputed.items():
        has_atr = data.get("atr_14") is not None

        has_sma = data.get("sma_50") is not None

        has_close = data.get("close") is not None

        if has_atr and has_sma and has_close:
            # All values precomputed in Phase 5

            precomputed_by_symbol[symbol] = {
                "atr": float(data["atr_14"]),
                "sma_50": float(data["sma_50"]),
                "close": float(data["close"]),
            }

        else:
            # Missing at least one value � fetch from DB

            symbols_needing_fetch.append(symbol)

    if not symbols_needing_fetch:
        # All data precomputed in Phase 5, no DB fetch needed

        return cast(dict[str, dict[str, float | None]], precomputed_by_symbol)

    # Fetch missing data only for symbols that lack precomputed values
    # Use SQL parameter markers (%s) for safe parameterized queries
    symbol_placeholders = ",".join(["%s"] * len(symbols_needing_fetch))

    result: dict[str, dict[str, float | None]] = cast(dict[str, dict[str, float | None]], precomputed_by_symbol.copy())

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                f"""WITH latest_prices AS (
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM price_daily
                    WHERE symbol IN ({symbol_placeholders}) AND date <= %s
                    ORDER BY symbol, date DESC
                ),
                sma_50_data AS (
                    SELECT symbol, AVG(close) AS sma_50
                    FROM (
                        SELECT symbol, close,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE symbol IN ({symbol_placeholders}) AND date <= %s
                    ) t
                    WHERE rn <= 50
                    GROUP BY symbol
                ),
                atr_data AS (
                    SELECT symbol, AVG(tr) AS atr
                    FROM (
                        SELECT symbol,
                               GREATEST(high - low,
                                       ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY date)),
                                       ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY date))) AS tr,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE symbol IN ({symbol_placeholders}) AND date <= %s
                    ) t
                    WHERE tr IS NOT NULL AND rn <= %s
                    GROUP BY symbol
                )
                SELECT lp.symbol, atr.atr, sma.sma_50, lp.close
                FROM latest_prices lp
                INNER JOIN sma_50_data sma ON sma.symbol = lp.symbol
                INNER JOIN atr_data atr ON atr.symbol = lp.symbol""",
                [
                    *symbols_needing_fetch,
                    run_date,
                    *symbols_needing_fetch,
                    run_date,
                    *symbols_needing_fetch,
                    run_date,
                    period,
                ],
            )

            rows = cur.fetchall()

            for row in rows:
                try:
                    # DictCursor returns dict-like row objects; unpack safely
                    if isinstance(row, dict):
                        row_symbol = row.get('symbol')
                        atr = row.get('atr')
                        sma_50 = row.get('sma_50')
                        close = row.get('close')
                    else:
                        # Fallback for tuple-based cursor (shouldn't happen with DictCursor, but be defensive)
                        if len(row) < 4:
                            raise IndexError(f"Row has {len(row)} columns, expected 4")
                        row_symbol, atr, sma_50, close = row
                except (IndexError, TypeError, ValueError) as e:
                    logger.critical(
                        f"[PHASE 8 CRITICAL] Failed to unpack technical data row: {e}. "
                        f"Row type: {type(row).__name__}, Row value: {row}"
                    )
                    raise

                if row_symbol is None:
                    logger.warning("[PHASE 8] Skipping row with no symbol")
                    continue
                if atr is None or sma_50 is None or close is None:
                    logger.warning(
                        f"[PHASE 8] Symbol {row_symbol}: Technical data incomplete (ATR={atr}, SMA_50={sma_50}, close={close}). "
                        f"Skipping this symbol. Check technical_data_daily table for completeness."
                    )
                    # CRITICAL FIX: Skip this symbol instead of halting all entry execution
                    # One symbol with bad technical data should not block entries for all other symbols
                    continue

                # CRITICAL FIX: Session 345 - Validate type conversions (handles NaN/Infinity)
                try:
                    from utils.type_conversion import safe_float

                    atr_float = safe_float(atr, f"{symbol}.atr", allow_none=False)
                    sma_50_float = safe_float(sma_50, f"{row_symbol}.sma_50", allow_none=False)
                    close_float = safe_float(close, f"{row_symbol}.close", allow_none=False)
                except (ValueError, TypeError) as e:
                    logger.error(f"[ENTRY EXECUTION] {row_symbol}: Technical data type conversion failed: {e}")
                    raise ValueError(f"Technical data validation failed for {row_symbol}: {e}") from e

                result[row_symbol] = cast(
                    dict[str, float | None],
                    {
                        "atr": atr_float,
                        "sma_50": sma_50_float,
                        "close": close_float,
                    },
                )

            return result

    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(f"Batch fetch technical data failed: {e}") from e


def _check_price_data_freshness(run_date: _date) -> tuple[bool, str]:
    """Validate price_daily data is fresh enough for Phase 8 entry execution.

    CRITICAL DATA FRESHNESS GUARD (Phase 8 revalidation):
    Phase 1 validates price freshness at orchestrator start (9:00 AM), but Phase 8
    may run HOURS later (1-5 PM). Between Phase 1 and Phase 8:
    - Price loader may fail (network issue, data source down)
    - EOD loaders may stall (4:05 PM market_status/market_exposure updates)
    - Morning price_daily could be STALE by afternoon/evening runs

    MARKET-HOURS-AWARE FRESHNESS:
    During INTRADAY hours (9:30 AM - 4:00 PM ET), today's close is NOT published yet.
    We expect the previous trading day's close, which is appropriate for technical analysis.
    Only after market close (4:00 PM+) do we expect today's data.

    Returns:
        (is_fresh, message) - is_fresh=True if price_daily is current for the market phase
    """
    from datetime import datetime as dt, timedelta as td
    from utils.infrastructure import EASTERN_TZ as _TZ_LOCAL

    try:
        # Determine market context (matching Phase 1 logic)
        now_et = dt.now(_TZ_LOCAL)
        is_market_open = now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30)
        is_after_market_close = now_et.hour >= 16

        # Determine expected price date based on market context
        if is_after_market_close:
            # EOD context: expect today's close
            expected_price_date = run_date
        elif is_market_open:
            # INTRADAY context: expect previous trading day's close
            prev_date = run_date - td(days=1)
            from algo.infrastructure.market_calendar import MarketCalendar
            if MarketCalendar.is_trading_day(prev_date):
                expected_price_date = prev_date
            else:
                # Find the most recent trading day before today
                expected_price_date = prev_date
                while expected_price_date > run_date - td(days=10):
                    if MarketCalendar.is_trading_day(expected_price_date):
                        break
                    expected_price_date -= td(days=1)
        else:
            # MORNING context (before 9:30 AM): expect previous trading day's close
            prev_date = run_date - td(days=1)
            from algo.infrastructure.market_calendar import MarketCalendar
            if MarketCalendar.is_trading_day(prev_date):
                expected_price_date = prev_date
            else:
                expected_price_date = prev_date
                while expected_price_date > run_date - td(days=10):
                    if MarketCalendar.is_trading_day(expected_price_date):
                        break
                    expected_price_date -= td(days=1)

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT MAX(date) as latest_price_date
                FROM price_daily
            """)
            result = cur.fetchone()
            if not result or result[0] is None:
                # No price data yet (test scenario or pre-load state)
                logger.debug("[PHASE 8 PRICE CHECK] No price_daily data yet - allowing Phase 8 to proceed")
                return True, "No price data yet - deferring validation to technical data fetch"

            latest_price_date = result[0]

            # Price data must be >= expected_price_date (accounting for market context)
            if latest_price_date < expected_price_date:
                return False, (
                    f"price_daily is stale: max(date)={latest_price_date} is BEFORE expected_date={expected_price_date}. "
                    f"Price loader may have failed between Phase 1 and Phase 8. "
                    f"Cannot execute entries on stale prices."
                )

            logger.info(f"[PHASE 8 PRICE CHECK] price_daily is current: max(date)={latest_price_date} >= expected={expected_price_date} (context: {'EOD' if is_after_market_close else 'INTRADAY' if is_market_open else 'MORNING'})")
            return True, f"Price data is fresh (max_date={latest_price_date})"

    except Exception as e:
        return False, f"Could not verify price freshness: {e}"


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
    qualified_trades: list[QualifiedTrade] | None = None,
    exposure_constraints: ExposureConstraints | None = None,
    check_halt_flag: Callable[..., Any] | None = None,
    executor: Any = None,
) -> PhaseResult:
    """Execute Phase 8: Entry Execution.

    DEPENDENCY VALIDATION: Phase 8 requires data from Phase 7 (qualified trades)
    and Phase 5 (exposure constraints). If executor is provided, dependencies are
    fetched via validated contract. Otherwise, data must be passed directly (legacy API).
    """
    validate_phase_config(config, "phase_8_entry_execution")

    if "execution_mode" not in config:
        raise ValueError(
            "[PHASE 8] Config missing 'execution_mode'. "
            "Trading mode must be explicit ('paper', 'dry', 'review', or 'auto'). "
            "Check algo_config table has this key."
        )
    execution_mode = config["execution_mode"]
    # CRITICAL FIX: This whitelist only accepted "paper"/"auto", but "dry" and "review" are
    # two other fully-supported execution_mode values - algo.orchestration.orchestrator.py's
    # own startup VALID_EXECUTION_MODES set and algo.trading.executor_strategies.py's
    # create_execution_mode_strategy() both already register/accept all 4 (DryExecutionMode
    # and ReviewExecutionMode are real, working strategies). Setting execution_mode to "dry"
    # or "review" - both legitimate pre-live-trading testing modes - would pass Orchestrator
    # startup validation cleanly, then crash here with ValueError the moment Phase 8 ran.
    if execution_mode not in ("paper", "dry", "review", "auto"):
        raise ValueError(
            f"[PHASE 8] Invalid execution_mode='{execution_mode}'. "
            "Must be 'paper' (paper trading), 'dry' (local-only, no Alpaca calls), "
            "'review' (pending orders for manual approval), or 'auto' (live trading)."
        )

    if "alpaca_paper_trading" not in config:
        raise ValueError(
            "[PHASE 8] Config missing 'alpaca_paper_trading'. "
            "Trading mode must be explicit (paper vs live). "
            "Check algo_config table has this key."
        )
    alpaca_paper_trading = config["alpaca_paper_trading"]

    phase_start = time.time()

    logger.info("[PHASE 8] Starting entry execution")

    # CRITICAL GUARD: Enforce market hours (9:30 AM - 4:00 PM ET, 9:30 AM - 1:00 PM ET on
    # NYSE/NASDAQ early-close days). Entries executed outside market hours will be queued as
    # pre-market/after-hours orders and may fill at unexpected prices or not fill at all.
    # Risk: duplicate orders on next run.
    # MUST use MarketCalendar.is_market_open() (early-close aware), not a raw comparison
    # against the fixed MARKET_OPEN_TIME/MARKET_CLOSE_TIME constants - those ignore early
    # closes entirely, which would let this guard wave entries through from 1-4 PM ET on a
    # day the market has already closed.
    # CRITICAL FIX: Always check market hours, even in dry-run, so testing can verify
    # the guard works correctly on early-close days and outside market hours.

    # TEST MODE: Allow override for testing outside market hours (PHASE_8_TEST_MODE=true or ALLOW_OUTSIDE_MARKET_HOURS=true)
    test_mode = os.environ.get('PHASE_8_TEST_MODE', 'false').lower() == 'true'
    allow_outside_hours = os.environ.get('ALLOW_OUTSIDE_MARKET_HOURS', 'false').lower() == 'true'

    # CRITICAL FIX (Session 30): Import EASTERN_TZ at function level to ensure availability
    # Previous: UnboundLocalError "cannot access local variable 'EASTERN_TZ'" due to scope shadowing
    # This ensures we always have access to the timezone regardless of outer scope
    from utils.infrastructure import EASTERN_TZ as _EASTERN_TZ
    now_dt = datetime.now(_EASTERN_TZ)
    now_et = now_dt.time()
    is_market_open = MarketCalendar.is_market_open(now_dt)

    logger.info(
        f"[PHASE 8 MARKET HOURS CHECK] Current time: {now_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} ET, "
        f"is_market_open={is_market_open}, test_mode={test_mode}, allow_outside_hours={allow_outside_hours}"
    )

    if not is_market_open and not test_mode and not allow_outside_hours:
        close_time = "1:00 PM" if MarketCalendar.is_early_close(now_dt.date()) else "4:00 PM"
        msg = (
            f"[PHASE 8 MARKET HOURS GUARD] Cannot execute entries outside market hours. "
            f"Current time: {now_et.strftime('%H:%M:%S')} ET, "
            f"market hours: 9:30 AM - {close_time} ET. Skipping Phase 8."
        )
        logger.warning(msg)
        log_phase_result_fn(8, "entry_execution", "blocked", msg)
        result = PhaseResult(
            8,
            "entry_execution",
            "blocked",
            {"entered": 0},
            False,  # halted=False: guard is just blocking entries, not halting orchestration
            msg,
        )
        return result

    # CRITICAL FIX (Session 32): Market-open exclusion (9:30-10:30 AM) hard cutoff
    # Previous: Guard at line 2089 only fired if current_time_et was 09:30-10:30
    # Problem: Morning runs at 09:03 AM passed because check was FALSE (before 09:30)
    # Result: All 5 market-open false breakouts entered at 09:03-09:12, stopped out 3 hours later (62.5% loss rate)
    # FIX: Hard cutoff - skip Phase 8 entirely if current_time_et < 10:30 AM ET
    # This prevents ALL market-open entries regardless of when orchestrator runs
    from datetime import time as dt_time
    market_open_exclusion_enabled = config.get("market_open_exclusion_enabled", False)
    if market_open_exclusion_enabled and not test_mode and not allow_outside_hours:
        market_open_end = dt_time(10, 30)  # 10:30 AM ET
        if now_et < market_open_end:
            msg = (
                f"[PHASE 8 MARKET-OPEN EXCLUSION] Blocking entries during high-volatility market open window. "
                f"Current time: {now_et.strftime('%H:%M:%S')} ET. "
                f"Entries allowed only after 10:30 AM ET (60-minute window after 9:30 AM market open). "
                f"Reason: Market-open false breakouts cause 62.5% loss rate within 3 hours."
            )
            logger.warning(msg)
            log_phase_result_fn(8, "entry_execution", "blocked", msg)
            result = PhaseResult(
                8,
                "entry_execution",
                "blocked",
                {"entered": 0},
                False,  # halted=False: guard is blocking entries, not halting orchestration
                msg,
            )
            return result

    if test_mode:
        logger.warning("[PHASE 8 TEST MODE] Market hours guard BYPASSED for testing")

    # CRITICAL GUARD: Check for pending/recent orders that may still be filling
    # If orders from prior run are still pending, executing new entries risks duplicates
    # NOTE: Skip this guard in paper mode since there are no real pending orders in simulation
    if execution_mode != "paper":
        try:
            with DatabaseContext("read") as cur:
                # Check for positions created in the last 10 minutes (indicates recent fills or pending orders)
                # If we just created positions very recently, the orders may still be in flight
                cur.execute(
                    """
                    SELECT COUNT(*) as recent_position_count
                    FROM algo_positions
                    WHERE entry_date = %s
                    AND created_at > NOW() - INTERVAL '10 minutes'
                    AND status = 'open'
                    """,
                    (run_date,),
                )
                result = cur.fetchone()
                recent_count = result[0] if result else 0

                if recent_count > 0:
                    msg = (
                        f"[PHASE 8 PENDING ORDERS GUARD] Blocking Phase 8: {recent_count} positions "
                        f"created in last 10 min (orders may still be pending/filling). Re-run in 5 minutes."
                    )
                    logger.warning(msg)
                    log_phase_result_fn(8, "entry_execution", "blocked", msg)
                    result = PhaseResult(
                        8,
                        "entry_execution",
                        "blocked",
                        {"entered": 0},
                        False,  # halted=False: guard worked but didn't halt orchestration
                        msg,
                    )
                    return result
        except Exception as e:
            msg = (
                f"[PHASE 8 CRITICAL] Could not verify pending orders status: {e}. "
                f"Cannot safely execute new entries without knowing if prior orders are still pending. "
                f"Risk of order duplication or conflicts. Must halt and investigate."
            )
            logger.critical(msg, exc_info=True)
            log_phase_result_fn(8, "entry_execution", "halt", msg)
            raise RuntimeError(msg) from e
    else:
        logger.info("[PHASE 8 PENDING ORDERS GUARD] Skipping in paper mode (no real pending orders)")

    # SIGNAL FRESHNESS GUARD: algo/risk/stale_signal_circuit_breaker.py was written
    # ("ROOT CAUSE #4 fix") specifically to catch entries placed off stale signals -
    # buy_sell_daily generated from price data older than the threshold, or lagging behind
    # price_daily entirely - but was never actually called from anywhere in the orchestrator.
    # Phase 1 validates price_daily/market_health/market_exposure freshness but explicitly
    # excludes buy_sell_daily (not generated yet at that point in the run); nothing downstream
    # ever checked whether the signals Phase 8 is about to trade on are themselves fresh
    # relative to the price data they were computed from. Block (not halt orchestration)
    # entries this run if stale, matching the market-hours/pending-orders guards above.
    try:
        from algo.risk.stale_signal_circuit_breaker import StaleSignalCircuitBreaker

        signals_fresh, freshness_msg = StaleSignalCircuitBreaker.check_signal_freshness()
        if not signals_fresh:
            msg = f"[PHASE 8 SIGNAL FRESHNESS GUARD] Blocking Phase 8: {freshness_msg}"
            logger.critical(msg)
            log_phase_result_fn(8, "entry_execution", "blocked", msg)
            result = PhaseResult(
                8,
                "entry_execution",
                "blocked",
                {"entered": 0},
                False,  # halted=False: guard is just blocking entries, not halting orchestration
                msg,
            )
            return result
    except RuntimeError as e:
        msg = (
            f"[PHASE 8 CRITICAL] Could not verify signal freshness: {e}. "
            f"Cannot safely execute new entries without knowing if signals are stale. Must halt and investigate."
        )
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(8, "entry_execution", "halt", msg)
        raise RuntimeError(msg) from e

    # PRICE DATA FRESHNESS GUARD: Re-validate that price_daily is fresh for afternoon/evening runs
    # Phase 1 validates at 9:00 AM, but Phase 8 may run at 1-5 PM. Price loader may fail between phases.
    # Without this check: trades execute on stale morning prices (risk: wrong entry prices, no intraday updates)
    price_fresh, price_msg = _check_price_data_freshness(run_date)
    if not price_fresh:
        msg = f"[PHASE 8 PRICE FRESHNESS GUARD] Blocking Phase 8: {price_msg}"
        logger.critical(msg)
        log_phase_result_fn(8, "entry_execution", "blocked", msg)
        result = PhaseResult(
            8,
            "entry_execution",
            "blocked",
            {"entered": 0},
            False,  # halted=False: guard is just blocking entries, not halting orchestration
            msg,
        )
        return result

    # SESSION 396 FIX: PROACTIVE RISK ENFORCEMENT
    # Phase 8 now ALWAYS runs (always_run=True) to enforce proactive risk checks
    # even when Phase 2 circuit breaker has halted earlier phases.
    # Proactive check: Block ALL entries if total risk >= 4% BEFORE attempting trades
    #
    # If Phase 7 (signals) or Phase 5 (exposure) are unavailable, that's OK:
    # Phase 8 will still run its risk guard and gracefully skip to reconciliation.
    # This prevents cascade failures where Phase 2 halt → Phase 5 skip → Phase 7 halt → Phase 8 halt.

    qualified_trades_from_executor = None
    exposure_constraints_from_executor = None

    if executor is not None:
        try:
            # Try to get Phase 7 signals (optional - empty signals = skip entries, not fatal)
            phase7_result = executor.get_result(7)
            if phase7_result and phase7_result.ok:
                # CRITICAL: Require explicit "qualified_trades" key in data.
                # If missing, Phase 7 failed to properly construct result - must not silently treat as []
                if "qualified_trades" not in phase7_result.data:
                    raise ValueError(
                        "[PHASE 8 DATA INTEGRITY] Phase 7 returned status='ok' but missing 'qualified_trades' key. "
                        "This indicates Phase 7 did not properly populate result data. "
                        f"Phase 7 data keys: {list(phase7_result.data.keys())}"
                    )
                qualified_trades_from_executor = cast(list[QualifiedTrade], phase7_result.data["qualified_trades"])
                if qualified_trades_from_executor is None:
                    raise ValueError(
                        "[PHASE 8 DATA INTEGRITY] Phase 7 returned 'qualified_trades'=None. "
                        "Must be a list (empty or with signals), not None."
                    )

                # CRITICAL FIX: Phase 7 lock contention handling
                # Phase 7 gracefully degrades when signal quality score batch loader has lock contention:
                # - Batch pre-computation may fail (lock_contention=True flag set)
                # - BUT inline scorer always runs and computes signal_quality_score for each candidate
                # - Candidates are still valid and safe to trade on (inline scores are reliable)
                # This is safe degradation, not a data quality issue.
                lock_contention = phase7_result.data.get("lock_contention", False)
                if lock_contention:
                    logger.warning(
                        f"[PHASE 8] Phase 7 reported lock contention on signal quality scores table. "
                        f"Batch pre-computation skipped, but {len(qualified_trades_from_executor)} candidates have "
                        f"inline-computed scores (RSI/MACD/Minervini/Weinstein). This is safe degradation mode."
                    )

                logger.info(f"[PHASE 8] Retrieved {len(qualified_trades_from_executor)} signals from Phase 7")
                # DEBUG: Log what signal_quality_score values we received
                if qualified_trades_from_executor:
                    logger.info(f"[PHASE 8 DEBUG] Top 5 received signals signal_quality_score values:")
                    for i, sig in enumerate(qualified_trades_from_executor[:5]):
                        logger.info(f"  {i+1}. {sig.get('symbol')}: sqs={sig.get('signal_quality_score')}, trend={sig.get('trend_template_score')}, base_q={sig.get('base_quality')}")
            elif phase7_result and phase7_result.halted:
                logger.warning(
                    f"[PHASE 8] Phase 7 halted: {phase7_result.error or 'unknown'}. "
                    f"No signals available, but Phase 8 will still run proactive risk check."
                )
            else:
                logger.info("[PHASE 8] Phase 7 unavailable - proceeding with proactive risk check only")

            # Try to get Phase 5 exposure constraints (also optional for proactive checks)
            phase5_result = executor.get_result(5)
            if phase5_result:
                # CRITICAL FIX: Extract constraints from Phase 5 regardless of status.
                # When Phase 5 halts due to missing market data or policy error, it returns
                # halt_constraints with safe defaults (max_concentration_pct=0, halt_new_entries=True).
                # Phase 8 MUST use these halt constraints, not ignore them.
                exposure_constraints_from_executor = cast(ExposureConstraints | None, phase5_result.data.get("constraints"))

                # CHECKPOINT 1: Validate Phase 5 constraints have ALL required fields (around line 685-710)
                # If any required field is missing, use safe defaults instead
                required_fields = ["halt_new_entries", "max_new_positions_today", "max_concentration_pct"]
                if exposure_constraints_from_executor:
                    missing_in_phase5 = [k for k in required_fields if k not in exposure_constraints_from_executor]
                    if missing_in_phase5:
                        logger.warning(
                            f"[PHASE 8 CONSTRAINT VALIDATION] Phase 5 constraints incomplete at extraction point "
                            f"(missing: {missing_in_phase5}). Using safe halt defaults instead."
                        )
                        # Fail-fast: Log which keys are missing for diagnostics
                        for missing_key in missing_in_phase5:
                            logger.error(f"[PHASE 8] CONSTRAINT MISSING: '{missing_key}' required for entry validation")
                        exposure_constraints_from_executor = None  # Trigger safe defaults below
                    else:
                        constraint_keys = list(exposure_constraints_from_executor.keys())
                        if phase5_result.ok:
                            logger.info(f"[PHASE 8] Retrieved exposure constraints from Phase 5: {constraint_keys}")
                        else:
                            logger.warning(
                                f"[PHASE 8] Phase 5 halted ({phase5_result.status}), "
                                f"using halt constraints: {constraint_keys}"
                            )
                else:
                    logger.warning(
                        f"[PHASE 8] Phase 5 returned {phase5_result.status} but constraints dict is empty. "
                        f"This is a data contract violation - Phase 5 must always return constraints."
                    )
        except ValueError as val_e:
            raise RuntimeError(f"[PHASE 8] Invalid exposure constraints data: {val_e}") from val_e
        except Exception as e:
            logger.warning(f"[PHASE 8] Could not fetch Phase 7/5 data: {e}. Proceeding with available data.")

    # CRITICAL FIX: Apply safe defaults OUTSIDE try-except block so they ALWAYS run
    # even if an exception occurs when fetching Phase 5/7 data.
    # Previously, exceptions could skip the safe defaults, leaving exposure_constraints_from_executor=None
    # which would cause Phase 8 to halt with "missing max_concentration_pct" later.
    # Also prioritize exposure_constraints parameter if provided (used when executor unavailable)
    if exposure_constraints_from_executor is None and exposure_constraints is not None:
        # Use the parameter if it was passed and executor data is unavailable
        exposure_constraints_from_executor = exposure_constraints
        logger.info("[PHASE 8] Using exposure_constraints parameter (executor data unavailable)")

    if exposure_constraints_from_executor is None:
        # CRITICAL FIX: Phase 5 unavailability should halt Phase 8, not silently degrade
        # Entry sizing requires exposure policy constraints from Phase 5
        # Without them, we cannot safely calculate position sizes or enforce limits
        logger.critical(
            "[PHASE 8 CRITICAL] Exposure constraints unavailable - Phase 5 was skipped, halted, or errored. "
            "Cannot proceed with entry execution without valid exposure policy. Phase 8 must halt."
        )
        return PhaseResult(
            8,
            "entry_execution",
            "halted",
            {"entered": 0, "failed": 0},
            True,  # halted=True: this is critical and must halt orchestration
            "Phase 5 (exposure_policy) did not provide constraints. Phase 8 requires Phase 5 output to execute entries safely.",
        )

        # CHECKPOINT 3: Validate safe defaults have all required fields (fallback path)
        required_fields = ["halt_new_entries", "max_new_positions_today", "max_concentration_pct"]
        safe_defaults_dict = exposure_constraints_from_executor
        missing_in_defaults = [k for k in required_fields if k not in safe_defaults_dict]
        if missing_in_defaults:
            error_msg = (
                f"[PHASE 8 CRITICAL] Safe default constraints incomplete: missing {missing_in_defaults}. "
                f"Cannot proceed - default constraints must have all required fields."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

    # Override with executor data if available, else use passed-in data
    if qualified_trades_from_executor is not None:
        qualified_trades = qualified_trades_from_executor
    if exposure_constraints_from_executor is not None:
        exposure_constraints = exposure_constraints_from_executor

    # SESSION 396 FIX: Handle missing signals gracefully (Phase 7 may be halted)
    # Phase 8 can still run proactive risk checks even without signals
    if qualified_trades is None:
        qualified_trades = []
        logger.info(
            "[PHASE 8] No qualified trades from Phase 7 (None). "
            "Phase 8 will still run proactive risk check and proceed with market cleanup if needed."
        )

    if not qualified_trades:
        logger.info("[PHASE 8] No qualified trades from Phase 7 (empty list)")
        # Don't return here - continue to run proactive risk check
        # This allows Phase 8's proactive risk enforcement to run even without new signals

    # CRITICAL: Clean up orphaned positions before risk calculation
    # Positions with quantity=0 but status='open' will cause risk validation to fail
    # AUDIT ISSUE #6: Proactive cleanup prevents Phase 8 failures from prior Phase 6 exit issues
    if not dry_run:
        cleanup_count = _cleanup_orphaned_positions()
        if cleanup_count > 0:
            logger.warning(f"[PHASE 8] Cleaned up {cleanup_count} orphaned positions during initialization")

    # CRITICAL: Persist signals to database (previously missing - this caused zero signals in dashboard)
    # This is the essential link between Phase 7 signal generation and dashboard display
    try:
        _persisted = _persist_signals_to_database(qualified_trades, run_date, dry_run)
        logger.info(f"[PHASE 8] Persisted {_persisted}/{len(qualified_trades)} signals to database")
    except Exception as e:
        logger.critical(
            f"[PHASE 8] CRITICAL: Failed to persist signals to database: {e}. Dashboard will not show trades.",
            exc_info=True,
        )
        raise RuntimeError(f"Signal persistence failed (dashboard sync broken): {e}") from e

    # Halt flag check before any trades
    # SESSION 396 FIX: When halt flag is set (circuit breaker triggered), Phase 8 should
    # gracefully skip entries without failing. This is expected behavior - it means the
    # circuit breaker prevented new positions due to existing risk or market conditions.
    # Circuit breaker active - entries blocked. This is a safety guard, not a failure.
    if check_halt_flag and check_halt_flag():
        msg = "[PHASE 8] Circuit breaker active (halt flag set) - entries blocked to protect portfolio"
        logger.warning(msg)
        log_phase_result_fn(8, "entry_execution", "blocked", msg)
        return PhaseResult(
            8,
            "entry_execution",
            "blocked",
            {"entered": 0},
            False,  # halted=False: guard is blocking entries, not halting orchestration
            msg,
        )

    # CRITICAL FIX 2026-08-01: Ensure exposure_constraints always has required fields
    # Either Phase 5 provided them, or safe defaults were applied earlier.
    # As a final safety check, ensure all required fields exist before proceeding.
    required_constraint_keys = [
        "halt_new_entries",
        "max_new_positions_today",
        "max_concentration_pct",
    ]

    # CRITICAL: Convert dataclass to dict for downstream compatibility
    # exposure_constraints may be ExposurePolicyConstraints dataclass or dict
    from algo.risk import ExposurePolicyConstraints

    if isinstance(exposure_constraints, ExposurePolicyConstraints):
        exposure_constraints_dict = exposure_constraints.to_dict()
    else:
        exposure_constraints_dict = cast(dict[str, Any], exposure_constraints or {})

    # CRITICAL: Exposure constraints are REQUIRED - fail-fast if entirely missing
    if not exposure_constraints_dict:
        msg = (
            "[PHASE 8 CRITICAL] Exposure constraints not available (Phase 5 may have halted). "
            "Cannot execute trades without market exposure analysis from Phase 5 (Exposure Policy). "
            "Position sizing requires valid exposure constraints. "
            "Using safe halt defaults: halt_new_entries=True, max_concentration_pct=0."
        )
        logger.critical(msg)
        log_phase_result_fn(8, "entry_execution", "blocked", msg)
        # CRITICAL: Apply safe defaults instead of halting
        # Phase 8 can continue with conservative constraints to prevent unguarded trades
        exposure_constraints_dict = {
            "halt_new_entries": True,
            "max_new_positions_today": 0,
            "max_concentration_pct": 0.0,
        }

    # Validate that all required fields exist - apply defaults for any missing fields
    missing_keys = [k for k in required_constraint_keys if k not in exposure_constraints_dict]

    if missing_keys:
        # CRITICAL FIX: Apply defaults for missing fields instead of halting
        # This ensures Phase 8 never fails due to incomplete constraints.
        # Missing fields are filled with conservative defaults that block new entries.
        logger.warning(
            f"[PHASE 8] Exposure constraints incomplete from Phase 5: missing keys {missing_keys}. "
            f"Available fields: {list(exposure_constraints_dict.keys())}. "
            f"Applying conservative defaults for missing fields to prevent unguarded trades."
        )

        # Fill in missing constraint fields with safe defaults
        constraint_defaults = {
            "halt_new_entries": True,
            "max_new_positions_today": 0,
            "max_concentration_pct": 0.0,
        }
        for key in missing_keys:
            if key in constraint_defaults:
                exposure_constraints_dict[key] = constraint_defaults[key]
                logger.warning(f"[PHASE 8] Applied default for missing constraint '{key}': {constraint_defaults[key]}")

    # Add diagnostic logging
    if exposure_constraints_dict:
        logger.info(
            f"[PHASE 8 DIAGNOSTIC] Exposure constraints status: "
            f"has {len(exposure_constraints_dict)} fields, requires {len(required_constraint_keys)}. "
            f"Fields present: {list(exposure_constraints_dict.keys())}"
        )

    # Use dict for subsequent operations
    exposure_constraints = cast(ExposureConstraints, exposure_constraints_dict)

    # ISSUE 15 FIX: Validate constraints before using in Phase 8
    try:
        _validate_constraints_for_phase8(exposure_constraints)
    except ValueError as e:
        error_msg = f"[PHASE 8 CRITICAL] Constraint validation failed: {e}. Cannot proceed with trade execution."
        logger.critical(error_msg)
        log_phase_result_fn(8, "entry_execution", "halt", error_msg)
        raise RuntimeError(error_msg) from e

    # CRITICAL: Verify data freshness before executing trades

    # Trades execute on EOD (after market close), so expect:
    # - If today is a trading day: same-day data
    # - If today is not a trading day: most recent trading day's data (within 10 days)

    try:
        from datetime import timedelta as td

        with DatabaseContext("read") as cur:
            cur.execute("""SELECT MAX(date) as latest_price_date FROM price_daily""")

            result = cur.fetchone()
            if result is None:
                raise ValueError("Price data freshness query returned no results - price_daily table may be empty")

            latest_price_date = result[0]
            if latest_price_date is None:
                # In dry-run/test mode, price_daily may be empty. Skip freshness check instead of crashing.
                if dry_run:
                    logger.warning(
                        "[PHASE 8] Price data unavailable in dry-run mode (price_daily is empty). "
                        "Skipping price freshness validation (acceptable for testing)."
                    )
                    latest_price_date = run_date  # Assume data is fresh for testing purposes
                else:
                    raise ValueError("Price data freshness query returned NULL - price_daily table may have no valid dates")

            # Determine expected last trading day - allow previous trading day's data
            # Phase 8 may run intraday (9 AM, 1 PM, 3 PM) before EOD data is available,
            # so we require prices to be at most 1 trading day old (not necessarily same-day).
            most_recent_trading_day = run_date
            if not MarketCalendar.is_trading_day(most_recent_trading_day):
                most_recent_trading_day = most_recent_trading_day - td(days=1)
                while most_recent_trading_day > run_date - td(days=10):
                    if MarketCalendar.is_trading_day(most_recent_trading_day):
                        break
                    most_recent_trading_day -= td(days=1)
                if not MarketCalendar.is_trading_day(most_recent_trading_day):
                    raise ValueError(f"No trading day found within 10 days of {run_date}")
            # Find previous trading day as minimum acceptable price date
            expected_price_date = most_recent_trading_day - td(days=1)
            while expected_price_date > most_recent_trading_day - td(days=10):
                if MarketCalendar.is_trading_day(expected_price_date):
                    break
                expected_price_date -= td(days=1)
            if not MarketCalendar.is_trading_day(expected_price_date):
                raise ValueError(f"No previous trading day found within 10 days of {most_recent_trading_day}")

            if latest_price_date is None or latest_price_date < expected_price_date:
                msg = (
                    f"[PHASE 8 CRITICAL] Price data is not current (latest: {latest_price_date}, "
                    f"expected: {expected_price_date}, run_date: {run_date}). "
                    f"Cannot execute trades without current market data. "
                    f"EOD price loader may not have completed - check data_loader_status and CloudWatch logs."
                )

                logger.critical(msg)

                log_phase_result_fn(8, "entry_execution", "halt", msg)

                return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, msg)

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[PHASE 8 CRITICAL] Data freshness check failed: {e}"

        logger.critical(msg)

        log_phase_result_fn(8, "entry_execution", "halt", msg)

        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, msg)

    # exposure_constraints validated above - guaranteed to exist and have all required fields
    # Additional fields may be present (tier_name, risk_multiplier) but are not required for entry execution

    # Check for halt flag set by exposure policy
    # exposure_constraints validated above - always exists and has required keys
    if exposure_constraints["halt_new_entries"]:
        # FAIL-FAST: halt_reason MUST be present when halt_new_entries is True
        if "halt_reason" not in exposure_constraints:
            raise RuntimeError(
                "[PHASE 8 CRITICAL] Exposure policy set halt_new_entries=True but halt_reason missing. "
                "Cannot determine why trading is halted. Exposure constraints data incomplete."
            )

        reason = exposure_constraints["halt_reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeError(
                "[PHASE 8 CRITICAL] Exposure policy halted entries but halt_reason is empty/None/whitespace. "
                f"Cannot determine why trading is halted. Got: {type(reason).__name__} = {reason!r}. "
                "Halt reason must be non-empty string."
            )

        logger.warning(f"[PHASE 8] {reason}")

        log_phase_result_fn(8, "entry_execution", "halt", reason)

        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, reason)

    max_entries = exposure_constraints["max_new_positions_today"]

    logger.info(
        f"[PHASE 8] Processing {len(qualified_trades)} qualified signals"
        + (f" (cap: {max_entries}/day)" if max_entries else "")
    )

    # Log paper trading mode info (execution_mode and alpaca_paper_trading already validated above)
    if execution_mode == "paper" or alpaca_paper_trading:
        logger.info(
            f"[PHASE 8] Paper trading mode active (execution_mode={execution_mode}, "
            f"alpaca_paper_trading={alpaca_paper_trading}). Trades will execute against paper account."
        )

    trade_executor = TradeExecutor(config=config)

    # Wire tier's max_concentration_pct into sizer so correction/caution limits are respected.

    # Each ExposurePolicy tier defines its own concentration ceiling (20%/16%/12%/10%).
    # exposure_constraints validated above - always exists
    tier_max_conc = exposure_constraints["max_concentration_pct"]

    # CRITICAL: config must be present. Position sizing parameters (base_risk_pct, max_positions,
    # VIX thresholds, drawdown reductions) are non-negotiable for risk management. Empty dict
    # fallback bypasses all position sizing safety gates. Must fail-fast if config is missing.
    if config is None:
        error_msg = (
            "[PHASE 8] CRITICAL: Position sizing configuration is None. "
            "Cannot apply position size limits (base_risk_pct, max_positions), VIX reductions, "
            "or drawdown position size adjustments. Entry execution failed."
        )
        logger.error(error_msg)
        log_phase_result_fn(8, "entry_execution", "halt", error_msg)
        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    # CRITICAL: Validate max_position_size_pct is configured - this is the hard cap on individual positions
    # CRITICAL FIX (Session Date): max_position_size_pct must be present in config. This is the baseline
    # position sizing constraint that prevents any single position from exceeding this % of portfolio.
    # Without it, position sizer cannot enforce hard position size limits.
    if "max_position_size_pct" not in config or config["max_position_size_pct"] is None:
        error_msg = (
            "[PHASE 8] CRITICAL: max_position_size_pct configuration missing. "
            "Cannot enforce hard limit on individual position size. "
            "Every position must have a maximum size (e.g., 6-8% of portfolio). "
            "Set max_position_size_pct in algo_config table before trading."
        )
        logger.critical(error_msg)
        log_phase_result_fn(8, "entry_execution", "halt", error_msg)
        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    # Fall back to a COPY of `config` (not `{}`) when it lacks .to_dict() - an empty dict here
    # would silently discard every actually-configured risk key (base_risk_pct, max_positions,
    # VIX thresholds) rather than the still-fail-closed PositionSizer.__init__ requiring them.
    # Must be a copy, not `config` itself: the max_concentration_pct assignment just below
    # would otherwise mutate the caller's original config dict in place.
    sizer_config = config.to_dict() if hasattr(config, "to_dict") else dict(config)

    if tier_max_conc is not None:
        sizer_config["max_concentration_pct"] = tier_max_conc

        logger.info(f"[PHASE 8] Position sizer: max_concentration_pct={tier_max_conc:.0f}% (from tier)")

    sizer = PositionSizer(config=sizer_config)

    liquidity = LiquidityChecks(config=config)

    # Fetch portfolio value for Phase 8 entry sizing
    # CRITICAL FIX (Session 12): Phase 6 (exit execution) runs BEFORE Phase 8 (entry execution) in the
    # orchestrator pipeline. Using a stale snapshot causes positions to be sized too large after Phase 6
    # has closed positions. Use the LATEST snapshot (which reflects current state), not the run_date snapshot.
    portfolio_value = None
    portfolio_value_source = None

    # Primary: Use LATEST portfolio snapshot (not stale start-of-day snapshot)
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT total_portfolio_value, snapshot_date
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """
            )
            result = cur.fetchone()
            if result and len(result) > 0 and result[0] is not None:
                portfolio_value = Decimal(str(result[0]))
                portfolio_value_source = f"latest_snapshot ({result[1]})"
                logger.info(f"[PHASE 8] Portfolio value: ${portfolio_value:,.0f} (from latest snapshot, date={result[1]})")
            else:
                raise ValueError("No portfolio snapshot available")
    except Exception as db_err:
        logger.warning(f"[PHASE 8] Latest snapshot unavailable: {db_err}. Trying Alpaca API...")

        # Secondary: Try Alpaca API (live, current value)
        try:
            portfolio_value = sizer.get_portfolio_value()
            portfolio_value_source = "alpaca_api"
            logger.info(f"[PHASE 8] Portfolio value: ${portfolio_value:,.0f} (from Alpaca API)")
        except RuntimeError as api_err:
            # Tertiary: Use configured fallback ONLY in paper mode
            if execution_mode == "paper":
                initial_capital = config.get("initial_capital_paper_trading")
                if not initial_capital or initial_capital <= 0:
                    error_msg = (
                        f"[PHASE 8 HALT] Cannot determine portfolio value. "
                        f"Tried: latest snapshot, Alpaca API. "
                        f"Configured fallback invalid: initial_capital_paper_trading={initial_capital}. "
                        f"Cannot proceed with trading without reliable portfolio value."
                    )
                    logger.critical(error_msg)
                    log_phase_result_fn(8, "entry_execution", "halt", error_msg)
                    return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)
                portfolio_value = Decimal(str(initial_capital))
                portfolio_value_source = "configured_fallback"
                logger.warning(
                    f"[PHASE 8] Using configured paper trading capital ${portfolio_value:,.0f} "
                    f"(latest snapshot and API unavailable). "
                    f"Position sizing may be inaccurate. Snapshot error: {db_err}. API error: {api_err}"
                )
            else:
                # Live mode: never use fallback, fail-fast
                error_msg = (
                    f"[PHASE 8 HALT] Cannot determine portfolio value (live mode). "
                    f"Snapshot error: {db_err}. API error: {api_err}"
                )
                logger.critical(error_msg)
                log_phase_result_fn(8, "entry_execution", "halt", error_msg)
                return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    if portfolio_value is None or portfolio_value <= 0:
        error_msg = (
            f"[PHASE 8 HALT] Invalid portfolio value: {portfolio_value} "
            f"(source: {portfolio_value_source}). Cannot execute trades."
        )
        logger.critical(error_msg)
        log_phase_result_fn(8, "entry_execution", "halt", error_msg)
        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    # CRITICAL: Get Alpaca credentials - FAIL LOUD if missing and trades are queued
    # Previously: silent fallback would skip trades without any indication (WRONG!)
    # Now: explicit validation with actionable error messages
    alpaca_key = None
    alpaca_secret = None

    try:
        from algo.config.credential_manager import get_credential_manager

        creds = get_credential_manager().get_alpaca_credentials()

        # CRITICAL FIX: Explicit field-by-field validation with clear error messages
        # Previously: generic "credentials not available" message didn't say which field failed
        # Now: explicit validation shows operator exactly which field is missing
        if not creds:
            raise ValueError(
                "[PHASE 8 CRITICAL] Credential manager returned None. "
                "Alpaca credentials not available in Secrets Manager or environment."
            )

        if not isinstance(creds, dict):
            raise ValueError(
                f"[PHASE 8 CRITICAL] Credential manager returned invalid type {type(creds).__name__}. "
                f"Expected dict with 'key' and 'secret' fields."
            )

        # Validate each field explicitly
        alpaca_key = creds.get("key")
        alpaca_secret = creds.get("secret")

        if not alpaca_key or not isinstance(alpaca_key, str):
            raise ValueError(
                f"[PHASE 8 CRITICAL] Missing or invalid 'key' field in Alpaca credentials. "
                f"Got: {type(alpaca_key).__name__}. Expected: string. "
                f"Check ALPACA_API_KEY_ID in Secrets Manager or environment variable."
            )

        if not alpaca_secret or not isinstance(alpaca_secret, str):
            raise ValueError(
                f"[PHASE 8 CRITICAL] Missing or invalid 'secret' field in Alpaca credentials. "
                f"Got: {type(alpaca_secret).__name__}. Expected: string. "
                f"Check ALPACA_API_SECRET_KEY in Secrets Manager or environment variable."
            )

        logger.info("[PHASE 8] Alpaca credentials loaded successfully")
    except (RuntimeError, ValueError, KeyError, ImportError) as e:
        # FAIL-FAST: Credentials are required for trade execution
        # No graceful degradation for local/paper mode - if we have trades to execute,
        # credentials MUST be available. Missing credentials is a hard error.
        if len(qualified_trades) > 0:
            error_msg = (
                f"[PHASE 8 CRITICAL] Alpaca credentials not available: {e}\n"
                f"Cannot execute {len(qualified_trades)} qualified trades without credentials.\n"
                f"\nTO FIX:\n"
                f"1. LOCAL DEV: Run: source scripts/setup_local_alpaca_credentials.sh\n"
                f"2. AWS DEPLOYMENT: Set GitHub Secrets:\n"
                f"   - ALPACA_API_KEY_ID (e.g., PK_PAPER_xxxxx)\n"
                f"   - ALPACA_API_SECRET_KEY\n"
                f"   See: https://github.com/argie33/algo/settings/secrets/actions\n"
                f"3. Then run: terraform apply (or push to main for GitHub Actions)"
            )
            logger.critical(error_msg)
            log_phase_result_fn(8, "entry_execution", "halt", error_msg)
            return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)
        else:
            logger.warning(f"[PHASE 8] No trades queued, skipping credential check: {e}")

    pretrade = PreTradeChecks(
        config=config,
        alpaca_base_url=os.getenv("APCA_API_BASE_URL"),
        alpaca_key=alpaca_key,
        alpaca_secret=alpaca_secret,
    )

    executed_count = 0

    skipped_count = 0

    failed_count = 0

    # entries_executed/success_rate/avg_entry_price/symbols_entered: the health dashboard
    # (dashboard/panels/health.py, Phase 8 detail row) reads these exact keys, but this
    # phase's PhaseResult.data only ever carried entered/skipped/failed/
    # execution_rejection_rate - that section of the panel always rendered nothing.
    entered_symbols: list[str] = []
    entered_prices: list[float] = []

    # PROACTIVE RISK CHECK: Before entering positions, verify we won't exceed 4% risk limit
    # CRITICAL FIX 2026-08-01: Add position count limit check (was missing - allowed 17 positions)
    # Check position count BEFORE allowing entries
    #
    # CRITICAL FIX: this was hardcoded to 15 instead of reading the real, admin-editable
    # "max_positions" config key (algo/infrastructure/config_schema.py: int, range 1-100,
    # default 15; actively consumed by algo/trading/position_sizer.py and
    # algo/infrastructure/config/main.py for the same purpose). Same divergence risk as the
    # max_total_risk_pct guard fixed just above: if an admin ever changed this config value,
    # this pre-check would silently keep enforcing the old hardcoded 15 instead of the real
    # configured limit.
    try:
        config_max_positions = config.get("max_positions")
        if config_max_positions is None:
            raise ValueError("[PHASE 8] Config missing 'max_positions'. Required for position count check.")
        max_positions = int(config_max_positions)

        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open' AND quantity != 0")
            result = cur.fetchone()
            if result is None or len(result) < 1:
                raise RuntimeError("[PHASE 8] Query to count open positions returned NULL or incomplete")
            current_position_count = result[0] if result[0] is not None else 0

        # CRITICAL FIX (Session 35): Previous logic blocked entries if position_count >= max_positions,
        # even though daily rotations (close some, enter new) should be allowed.
        # New logic: Only block if we can't enter ANY new positions. Allow entries up to max limit.
        available_slots = max_positions - current_position_count
        if available_slots <= 0:
            msg = (
                f"[PHASE 8 POSITION LIMIT] Currently holding {current_position_count} positions "
                f"(limit: {max_positions}). Must close positions before entering new trades."
            )
            logger.warning(msg)
            log_phase_result_fn(8, "entry_execution", "blocked", msg)
            return PhaseResult(
                8,
                "entry_execution",
                "blocked",
                {"entered": 0},
                False,
                msg,
            )

        # Cap daily entries by available slots (can't exceed max_positions)
        max_entries_allowed = min(max_entries, available_slots)
        if max_entries_allowed < max_entries:
            logger.info(
                f"[PHASE 8 POSITION LIMIT] Available slots: {available_slots} of {max_positions}. "
                f"Reducing daily entries from {max_entries} to {max_entries_allowed}."
            )
            max_entries = max_entries_allowed
    except Exception as e:
        msg = (
            f"[PHASE 8 CRITICAL] Position count check failed: {e}. "
            f"Cannot verify position limit. Must halt to prevent exceeding the configured position limit."
        )
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(8, "entry_execution", "halt", msg)
        raise RuntimeError(msg) from e

    # This is defensive - stops entries BEFORE they would push us over the limit
    # (vs circuit breaker which stops AFTER we've exceeded it)
    try:
        # CRITICAL FIX: this guard hardcoded 4.0 instead of reading max_total_risk_pct from
        # config - the same admin-editable value algo/risk/circuit_breaker.py's CB4
        # (_check_total_risk) enforces. If that config were ever changed, this pre-check
        # would silently diverge from the real limit: either blocking entries too early
        # (config raised above 4%) or, worse, letting Phase 8 submit real orders past a
        # lowered limit until CB4 catches it after the fact. Reading the same config key
        # keeps this defensive guard and the actual circuit breaker in lockstep.
        config_max_risk_pct = config.get("max_total_risk_pct")
        if config_max_risk_pct is None:
            raise ValueError("[PHASE 8] Config missing 'max_total_risk_pct'. Required for risk pre-check.")
        max_risk_limit_pct = float(config_max_risk_pct)
        current_risk_pct, available_capacity_pct = _calculate_current_total_risk_pct(
            max_risk_limit_pct=max_risk_limit_pct
        )
        if available_capacity_pct < 0.3:  # Less than 0.3% room left (rounding safety)
            msg = (
                f"[PHASE 8 RISK GUARD] Total open risk {current_risk_pct:.2f}% >= {max_risk_limit_pct:.0f}% limit. "
                f"Available capacity: {available_capacity_pct:.2f}%. "
                f"Cannot enter new positions - risk already at limit. Close positions to trade."
            )
            logger.warning(msg)
            log_phase_result_fn(8, "entry_execution", "blocked", msg)
            return PhaseResult(
                8,
                "entry_execution",
                "blocked",
                {"entered": 0},
                False,  # halted=False: guard worked but didn't halt orchestration
                msg,
            )
        elif available_capacity_pct < 1.0:
            logger.warning(
                f"[PHASE 8 RISK GUARD] Current risk {current_risk_pct:.2f}%, "
                f"only {available_capacity_pct:.2f}% capacity available. "
                f"Will size positions conservatively to stay within limit."
            )
    except Exception as e:
        msg = (
            f"[PHASE 8 CRITICAL] Risk pre-check failed: {e}. "
            f"Cannot proceed without verifying current risk position. "
            f"Position sizing safety gate failed. Must halt to prevent accidental overexposure."
        )
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(8, "entry_execution", "halt", msg)
        raise RuntimeError(msg) from e

    # ISSUE #8 FIX: Build a dict with precomputed technical data from Phase 5 signals
    # to avoid redundant SMA_50/ATR calculations in Phase 6.
    # VALIDATION: Only store actual values; track which signals lack precomputed data (data_unavailable markers).
    symbols_with_precomputed = {}

    for sig in qualified_trades:
        symbol = sig.get("symbol")

        if not symbol:
            raise RuntimeError(
                "[PHASE 8] Signal missing required 'symbol' field. "
                "Cannot process trade without stock symbol. "
                "Verify Phase 7 (qualified trades) produces valid signals."
            )

        # Extract precomputed technical indicators from Phase 5 signal
        # These are OPTIONAL (Phase 5 may not have computed all values if data was unavailable)
        sma_50 = sig.get("sma_50")  # None if Phase 5 marked data_unavailable
        atr_14 = sig.get("atr_14")  # None if Phase 5 marked data_unavailable
        close = sig.get("close")  # None if Phase 5 marked data_unavailable

        symbols_with_precomputed[symbol] = {
            "sma_50": sma_50,
            "atr_14": atr_14,
            "close": close,
        }

    technical_data = _batch_fetch_technical_data(symbols_with_precomputed, run_date)

    def _is_valid_numeric(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    # Merge precomputed + fetched technical data
    merged_technical_data = {}
    for sym, precomp_data in symbols_with_precomputed.items():
        sma_50 = precomp_data.get("sma_50")
        atr_14 = precomp_data.get("atr_14")
        close = precomp_data.get("close")

        # Fill in missing values from batch fetch
        if technical_data.get(sym):
            fetched = technical_data[sym]
            sma_50 = sma_50 if sma_50 is not None else fetched.get("sma_50")
            atr_14 = atr_14 if atr_14 is not None else fetched.get("atr")
            close = close if close is not None else fetched.get("close")

        # Store merged result
        merged_technical_data[sym] = {"sma_50": sma_50, "atr_14": atr_14, "close": close}

    # Validate merged data
    precomputed_count = 0
    for sym, data in merged_technical_data.items():
        sma_50 = data.get("sma_50")
        atr_14 = data.get("atr_14")
        close = data.get("close")

        # FAIL-FAST: Technical data is required for ALL trading modes (paper and live).
        # No graceful degradation for paper mode - using synthetic defaults masks
        # data quality issues and causes wrong position sizing. Backtests/paper runs
        # must reveal data gaps before live trading.
        missing_fields = []
        if sma_50 is None:
            missing_fields.append("SMA_50")
        if atr_14 is None:
            missing_fields.append("ATR_14")
        if close is None:
            missing_fields.append("close")

        if missing_fields:
            raise RuntimeError(
                f"[PHASE 8] {sym}: Required technical data missing (fields: {', '.join(missing_fields)}). "
                f"SMA_50={sma_50}, ATR_14={atr_14}, close={close}. "
                f"Cannot execute trade without complete technical indicators (trading mode={execution_mode})."
            )

        # Type check only if values present
        if sma_50 is not None and not _is_valid_numeric(sma_50):
            logger.warning(f"[PHASE 8] {sym}: SMA_50={sma_50} has type {type(sma_50).__name__}")
        if atr_14 is not None and not _is_valid_numeric(atr_14):
            logger.warning(f"[PHASE 8] {sym}: ATR_14={atr_14} has type {type(atr_14).__name__}")
        if close is not None and not _is_valid_numeric(close):
            logger.warning(f"[PHASE 8] {sym}: close={close} has type {type(close).__name__}")

        precomputed_count += 1

    # CHECKPOINT 2: Final constraint validation before trade execution loop (around line 1402)
    # Fail-fast if any required constraint field is still missing after all processing
    required_constraint_keys = ["halt_new_entries", "max_new_positions_today", "max_concentration_pct"]
    missing_keys_final = [k for k in required_constraint_keys if k not in exposure_constraints]
    if missing_keys_final:
        error_msg = (
            f"[PHASE 8 CRITICAL] Constraint validation failed before trade loop: "
            f"missing keys {missing_keys_final}. "
            f"Available fields: {list(exposure_constraints.keys())}. "
            f"Cannot proceed with trade execution without complete constraints."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    # ISSUE 2: Explicit halt flag check before inline scorer/trade execution loop
    # If halt is set, skip qualified_trades processing entirely to prevent unguarded entries
    if check_halt_flag and check_halt_flag():
        logger.warning("[PHASE 8] Halt flag set - skipping inline scorer and trade execution loop")
        qualified_trades = []

    # ISSUE 4 FIX: Data quality edge cases validation - validate ATR and SMA before trade processing
    # AUDIT TRAIL: Log successful validation passes for audit trail and monitoring
    # Check technical data quality for all symbols in qualified_trades
    validated_trades: list[QualifiedTrade] = []
    data_quality_failures: dict[str, str] = {}

    for signal in qualified_trades:
        symbol = signal.get("symbol")
        if not symbol:
            logger.warning("[PHASE 8] Signal missing symbol - skipping")
            data_quality_failures[symbol or "unknown"] = "missing_symbol"
            continue

        # CRITICAL FIX (Session 27 + Session 31): Block all entries before 10:30 AM ET
        # Root cause: Pre-market and early market entries (09:03-09:04 AM) caused 75% losses
        # Analysis: Pre-market signals are stale (from yesterday's EOD), market open 9:30-10:30 AM is high-volatility
        # Solution: Enforce absolute 10:30 AM ET minimum - no entries anytime before then
        from datetime import time as dt_time
        current_time_et = datetime.now(_EASTERN_TZ).time()
        earliest_entry_time = dt_time(10, 30)  # 10:30 AM ET - MINIMUM entry time

        if current_time_et < earliest_entry_time:
            logger.info(
                f"[PHASE 8 EARLY MARKET EXCLUSION] {symbol}: Skipping entry at {current_time_et}. "
                f"Pre-market and early market (before 10:30 AM ET) entries cause high losses due to stale signals "
                f"and false breakouts. Entries allowed only after 10:30 AM ET."
            )
            data_quality_failures[symbol] = "early_market_open_exclusion"
            continue

        tech = merged_technical_data.get(str(symbol))
        if not tech:
            logger.error(f"[PHASE 8] {symbol}: Technical data not found in cache - skipping")
            data_quality_failures[symbol] = "technical_data_not_found"
            continue

        atr = tech.get("atr_14")
        sma_50 = tech.get("sma_50")

        # AUDIT ISSUE #4: Validate ATR >= 0.01 (minimum 1 cent volatility)
        # WHY: ATR < 0.01 indicates frozen/stale data or penny stock with zero recent movement
        # RATIONALE: Prevents position sizing errors on stocks with no volatility
        if atr is not None and float(atr) < 0.01:
            logger.error(f"[PHASE 8 DATA QUALITY] {symbol}: Invalid ATR {atr} (must be >= 0.01) - skipping trade")
            data_quality_failures[symbol] = f"invalid_atr_{atr}"
            continue

        # AUDIT ISSUE #4: Validate SMA_50 > 0
        # WHY: SMA_50 <= 0 is impossible for positive prices; indicates data corruption
        # RATIONALE: Catches corrupted technical data before position sizing
        if sma_50 is not None and float(sma_50) <= 0:
            logger.error(f"[PHASE 8 DATA QUALITY] {symbol}: Invalid SMA_50 {sma_50} (must be > 0) - skipping trade")
            data_quality_failures[symbol] = f"invalid_sma50_{sma_50}"
            continue

        # AUDIT TRAIL: Trade passed all data quality checks
        logger.info(f"[PHASE 8 DATA QUALITY] {symbol}: Technical data validated (ATR={atr:.2f}, SMA_50={sma_50:.2f})")
        validated_trades.append(signal)

    # Log data quality metrics
    if data_quality_failures:
        logger.warning(
            f"[PHASE 8 AUDIT] Data quality validation: {len(validated_trades)} passed, "
            f"{len(data_quality_failures)} rejected. Failures: {data_quality_failures}"
        )

    # CRITICAL FIX: Deduplicate signals by symbol
    # If Phase 7 generated multiple signals for the same symbol in a single run,
    # keep only the highest-quality one (by composite_score). Attempting to enter
    # multiple positions for the same symbol causes idempotent duplicate failures.
    # This can happen if multiple technical patterns trigger for same symbol.
    signal_by_symbol: dict[str | None, QualifiedTrade] = {}
    duplicate_signals_removed = 0
    for signal in validated_trades:
        symbol = signal.get("symbol")
        composite_score = signal.get("composite_score", 0)

        if symbol in signal_by_symbol:
            # Keep the signal with higher composite_score
            existing_score = signal_by_symbol[symbol].get("composite_score", 0)
            if composite_score > existing_score:
                logger.info(
                    f"[PHASE 8 DEDUP] {symbol}: Keeping signal with score {composite_score:.1f} "
                    f"(previous: {existing_score:.1f})"
                )
                signal_by_symbol[symbol] = signal
                duplicate_signals_removed += 1
            else:
                logger.info(
                    f"[PHASE 8 DEDUP] {symbol}: Skipping duplicate signal with score {composite_score:.1f} "
                    f"(keeping previous: {existing_score:.1f})"
                )
                duplicate_signals_removed += 1
        else:
            signal_by_symbol[symbol] = signal

    if duplicate_signals_removed:
        logger.warning(
            f"[PHASE 8 DEDUP] Removed {duplicate_signals_removed} duplicate signals. "
            f"Processing {len(signal_by_symbol)} unique symbols."
        )

    # Use deduplicated signals for processing
    validated_trades = list(signal_by_symbol.values())

    # Use validated trades for execution
    qualified_trades = validated_trades

    # CRITICAL FIX: PRE-ENTRY CONCENTRATION LIMIT VALIDATION (Session 2026-08-05)
    # Check total concentration impact BEFORE entering ANY signals.
    # Previously: Signals were processed individually, checking only current open positions.
    # Problem: Signals 1-14 would pass, each at <15% concentration, but collectively
    # they would violate the limit if entered sequentially (no lookahead of other signals).
    # Solution: Calculate concentration impact of ALL pending signals before any entries
    # using ACTUAL PositionSizer logic (not simplified estimation).
    #
    # This correctly accounts for:
    #   - Regime-aware multipliers
    #   - Drawdown reductions
    #   - Max position size caps
    #   - Tier-specific concentration limits
    if qualified_trades and exposure_constraints.get("max_concentration_pct", 0) > 0:
        try:
            tier_max_conc_val = float(exposure_constraints.get("max_concentration_pct", 100.0))

            # Instead of all-or-nothing rejection, intelligently rank signals by quality
            # and enter as many as fit within concentration limit
            # This prevents wasting high-quality signals when some would fit

            # Sort signals by composite_score descending (best first)
            sorted_signals = sorted(
                qualified_trades,
                key=lambda s: float(s.get("composite_score", 0)),
                reverse=True
            )

            # Calculate cumulative concentration to find how many fit
            qualified_trades_that_fit = []
            cumulative_conc = 0.0
            skipped_reason_counts: dict[str, int] = {}

            for signal in sorted_signals:
                symbol = signal.get("symbol")
                if not symbol:
                    skipped_reason_counts['missing_symbol'] = skipped_reason_counts.get('missing_symbol', 0) + 1
                    continue

                try:
                    tech_data = merged_technical_data.get(str(symbol), {})
                    atr_val = tech_data.get("atr_14") or tech_data.get("atr")
                    sma_50_val = tech_data.get("sma_50")
                    close_val = tech_data.get("close")

                    if not (atr_val and sma_50_val and close_val):
                        skipped_reason_counts['missing_tech_data'] = skipped_reason_counts.get('missing_tech_data', 0) + 1
                        continue

                    entry_price = float(close_val)
                    atr = float(atr_val)
                    sma_50 = float(sma_50_val)
                    stop_loss = _calculate_dynamic_stop_loss(entry_price, atr, sma_50)

                    if entry_price <= 0 or atr < 0 or sma_50 <= 0 or stop_loss <= 0:
                        skipped_reason_counts['invalid_price_data'] = skipped_reason_counts.get('invalid_price_data', 0) + 1
                        continue

                    # Get position size from sizer
                    position_result = sizer.calculate_position_size(
                        symbol=symbol,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        portfolio_value=portfolio_value,
                        enforce_total_risk_limit=False,
                    )

                    shares = position_result.get("shares", 0)
                    if shares == 0:
                        skipped_reason_counts['sizer_zero_shares'] = skipped_reason_counts.get('sizer_zero_shares', 0) + 1
                        continue

                    position_value = Decimal(shares) * Decimal(str(entry_price))
                    conc_pct = float((position_value / portfolio_value) * Decimal(100))

                    # Check if adding this signal would exceed the limit
                    if cumulative_conc + conc_pct <= tier_max_conc_val:
                        cumulative_conc += conc_pct
                        qualified_trades_that_fit.append(signal)
                    else:
                        # This and all remaining signals don't fit
                        skipped_reason_counts['exceeds_limit'] = skipped_reason_counts.get('exceeds_limit', 0) + 1
                        break

                except (ValueError, TypeError, KeyError, AttributeError) as e:
                    logger.debug(f"[PHASE 8 CONCENTRATION] {symbol}: Skipping from concentration calc due to data error: {type(e).__name__}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"[PHASE 8 CONCENTRATION] {symbol}: Unexpected error in concentration calculation: {type(e).__name__}: {e}. Skipping.")
                    continue

            # If some but not all signals fit, update the list and log
            if len(qualified_trades_that_fit) < len(qualified_trades):
                skip_summary = ", ".join(f"{k}:{v}" for k, v in sorted(skipped_reason_counts.items())) if skipped_reason_counts else "none"
                logger.info(
                    f"[PHASE 8 CONCENTRATION] {len(qualified_trades_that_fit)} of {len(qualified_trades)} "
                    f"signals fit within {tier_max_conc_val:.0f}% concentration limit. "
                    f"Total concentration would be: {cumulative_conc:.1f}%. "
                    f"Proceeding with {len(qualified_trades_that_fit)} highest-quality signals. "
                    f"(Skipped: {skip_summary})"
                )
                qualified_trades = qualified_trades_that_fit
            elif len(qualified_trades_that_fit) == 0:
                skip_summary = ", ".join(f"{k}:{v}" for k, v in sorted(skipped_reason_counts.items())) if skipped_reason_counts else "unknown"
                msg = (
                    f"[PHASE 8 PRE-ENTRY CONCENTRATION] No signals fit within {tier_max_conc_val:.0f}% "
                    f"concentration limit. Evaluated {len(qualified_trades)} signals. "
                    f"Skipped: {skip_summary}. "
                    f"Rejecting ALL trades to maintain concentration policy. Blocked by individual limits: []"
                )
                logger.warning(msg)
                log_phase_result_fn(8, "entry_execution", "blocked", msg)
                return PhaseResult(
                    8,
                    "entry_execution",
                    "blocked",
                    {"entered": 0, "skipped": len(qualified_trades)},
                    False,
                    msg,
                )

        except Exception as conc_check_err:
            logger.warning(
                f"[PHASE 8] Pre-entry concentration check failed: {conc_check_err}. "
                f"Proceeding without lookahead (per-trade enforcement still active)."
            )

    # ALL-OR-NOTHING TRANSACTION SAFETY (Session 2026-08-03):
    # Pre-flight validation: If we detect issues that would cause partial execution,
    # reject all trades upfront rather than executing some and failing on others.
    # Partial execution (trades 1-3 succeed, trade 4 fails) is unrecoverable - the broker
    # won't cancel orders that are already placed.
    if qualified_trades and not dry_run:
        try:
            # DatabaseContext already imported at top of module
            with DatabaseContext("read") as cur:
                cur.execute("SELECT 1")
        except Exception as db_test_err:
            error_msg = f"[PHASE 8] Database connectivity check failed before trade execution: {db_test_err}. Rejecting all trades to prevent partial execution."
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from db_test_err

        # Pre-flight validation pass: test position sizing and pretrade checks
        # for all trades before executing any. This catches issues upfront that would
        # cause partial execution if discovered mid-loop.
        validation_failures = []
        for preflight_signal in qualified_trades:
            preflight_symbol = preflight_signal.get("symbol")
            if not preflight_symbol:
                validation_failures.append("missing_symbol")
                continue

            try:
                # Validate position sizing would work for this trade
                preflight_entry = float(preflight_signal.get("entry_price", 0) or 0)
                if preflight_entry <= 0:
                    validation_failures.append(f"{preflight_symbol}:invalid_entry_price")
                    continue

                # Validate data available for sizing
                if str(preflight_symbol) not in merged_technical_data:
                    validation_failures.append(f"{preflight_symbol}:missing_tech_data")
                    continue

                preflight_tech = merged_technical_data[str(preflight_symbol)]
                if not preflight_tech.get("atr_14") or not preflight_tech.get("sma_50"):
                    validation_failures.append(f"{preflight_symbol}:incomplete_tech_data")
                    continue

            except Exception as preflight_err:
                validation_failures.append(f"{preflight_symbol}:validation_error:{str(preflight_err)[:50]}")
                continue

        if validation_failures:
            error_msg = (
                f"[PHASE 8 CRITICAL] All-or-nothing validation failed for {len(validation_failures)} trades. "
                f"Rejecting all trades to prevent partial execution. "
                f"Issues: {validation_failures[:3]}" +
                (f"... and {len(validation_failures)-3} more" if len(validation_failures) > 3 else "")
            )
            logger.critical(error_msg)
            log_phase_result_fn(8, "entry_execution", "halt", error_msg)
            raise RuntimeError(error_msg)

    # ISSUE 14 FIX: Track per-trade execution with resource cleanup
    successfully_entered = 0
    failed_entries = []

    for signal in qualified_trades:
        try:
            symbol = signal.get("symbol")

            if not symbol:
                raise RuntimeError(
                    "[PHASE 8] Signal missing symbol. "
                    "Cannot execute trade without stock symbol. "
                    "Verify signal_generation phase produced valid signals."
                )

            # Re-check halt flag each iteration - this loop can run for minutes

            if check_halt_flag and check_halt_flag():
                logger.warning(f"[PHASE 8] Halt flag set mid-loop at {symbol}, stopping")

                break

            # PRE-ENTRY HEALTH CHECK: Reject signals that fail 2+ health checks
            # Prevents 15% of entries that immediately exit at zero percent
            health_passes, failed_checks = PreEntryHealthValidator.validate(symbol, str(run_date))
            if not health_passes:
                health_reason = f"health_checks_failed: {','.join(failed_checks)}"
                logger.info(f"[PHASE 8] {symbol}: Pre-entry health validation failed: {health_reason}")
                _log_signal_rejection(
                    symbol, "health_validation", health_reason, run_date,
                    float(signal.get("entry_price", 0) or 0), None
                )
                skipped_count += 1
                continue

            # Liquidity: ADV, dollar volume, price history age

            entry_price_hint = signal.get("entry_price")
            if entry_price_hint is None:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: Signal missing entry_price. "
                    "Cannot run liquidity checks without entry price. "
                    "Verify Phase 5 signals include entry_price field."
                )

            liq_ok, liq_reason = liquidity.run_all(
                str(symbol),
                float(entry_price_hint),
                run_date,
            )

            if not liq_ok:
                # Same audit-trail gap as the sizer_blocked branch below: this was the only skip
                # path in the loop logging at debug (invisible by default) instead of info, and the
                # only one never writing to algo_signal_rejections.
                logger.info(f"[PHASE 8] {symbol}: liquidity - {liq_reason}")
                _log_signal_rejection(
                    symbol, "liquidity", liq_reason, run_date, float(entry_price_hint), None
                )

                skipped_count += 1

                continue

            # Fetch technical data from merged cache
            if str(symbol) not in merged_technical_data:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: technical data not in batch cache. "
                    f"Cannot execute trade without technical indicators. "
                    f"This indicates an upstream data quality issue - technical indicators not loaded for this symbol."
                )
            tech_data = merged_technical_data[str(symbol)]

            # Extract technical indicators - CRITICAL: Must have all values for position sizing
            atr = tech_data.get("atr_14")
            sma_50 = tech_data.get("sma_50")
            close = tech_data.get("close")

            # FAIL-FAST: Technical data is required for stop-loss calculation and position sizing
            # Do NOT use synthetic/approximated values - they mask data quality issues and can cause
            # wrong position sizing (especially ATR which directly affects stop loss placement).
            if close is None or atr is None or sma_50 is None:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: Incomplete technical data "
                    f"(ATR={atr}, SMA_50={sma_50}, close={close}). "
                    "Cannot execute entry without complete data. "
                    "This indicates upstream loader failure or data cache corruption."
                )

            entry_price = float(close)
            atr = float(atr)
            sma_50 = float(sma_50)

            # VALIDATION: Technical indicators must be positive (sanity check for data corruption)
            if entry_price <= 0 or atr < 0 or sma_50 <= 0:
                errors = []
                if entry_price <= 0:
                    errors.append(f"entry_price={entry_price}")
                if atr < 0:
                    errors.append(f"ATR={atr}")
                if sma_50 <= 0:
                    errors.append(f"SMA_50={sma_50}")
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: Corrupted technical data ({', '.join(errors)}). "
                    "Cannot proceed with trade execution."
                )

            # Stop loss: Dynamic tightening based on volatility.
            # Use helper function to calculate with consistent ATR multiplier logic across all paths
            stop_loss = _calculate_dynamic_stop_loss(entry_price, atr, sma_50)

            # AUDIT FIX (Session 276): Validate stop placement against recent support levels
            # In extended rallies, SMA_50 - ATR can sit far above chart support, leading to
            # mathematically correct but technically unsound stop placement.
            # Get 52-week low as reference support level
            try:
                with DatabaseContext("read") as cur_support:
                    cur_support.execute(
                        """
                        SELECT MIN(low) as support_52w
                        FROM price_daily
                        WHERE symbol = %s AND date >= %s - INTERVAL '365 days'
                        """,
                        (symbol, run_date),
                    )
                    support_row = cur_support.fetchone()
                    if support_row and support_row[0]:
                        support_52w = float(support_row[0])
                        # CRITICAL: Stop loss MUST be above recent support
                        # Allow minimal slack (0.5%) above support to avoid false fills
                        min_stop_above_support = support_52w * 1.005
                        if stop_loss <= support_52w:
                            adjusted_stop = min_stop_above_support
                            adjusted_risk = (entry_price - adjusted_stop) / entry_price

                            # CRITICAL: Cap stop at MAX_RISK_ALLOWED even after support adjustment
                            # to prevent support-based adjustment from violating risk limits
                            if adjusted_risk > MAX_RISK_ALLOWED:
                                adjusted_stop = entry_price * (1 - MAX_RISK_ALLOWED)
                                logger.warning(
                                    f"[PHASE 8] {symbol}: Support-adjusted stop ${min_stop_above_support:.2f} "
                                    f"would risk {adjusted_risk*100:.1f}%, exceeds {MAX_RISK_ALLOWED*100:.0f}% limit. "
                                    f"Capping at ${adjusted_stop:.2f}."
                                )
                            else:
                                logger.info(
                                    f"[PHASE 8] {symbol}: Stop loss ${stop_loss:.2f} "
                                    f"below 52-week support ${support_52w:.2f}. "
                                    f"Adjusting to ${min_stop_above_support:.2f} (0.5% above support)."
                                )

                            stop_loss = adjusted_stop
            except (psycopg2.DatabaseError, ValueError, TypeError) as e:
                logger.error(
                    f"[PHASE 8 CRITICAL] {symbol}: Could not validate stop loss against "
                    f"support: {type(e).__name__}: {e}"
                )
                _log_signal_rejection(
                    symbol,
                    "stop_loss_validation_failed",
                    f"Cannot verify stop loss against support levels - {type(e).__name__}",
                    run_date,
                )
                # Sibling rejection paths below (negative stop, low risk_pct, etc.) all
                # increment skipped_count - this one didn't, so a symbol rejected here
                # silently vanished from total_evaluated/execution_rejection_rate instead
                # of showing up as a skip.
                skipped_count += 1
                continue

            # EDGE CASE FIX: Stop loss can become negative when ATR is very large
            # (extreme volatility). This is invalid - cannot short at negative price.
            if stop_loss <= 0:
                logger.info(
                    f"[PHASE 8] {symbol}: Stop loss negative (${stop_loss:.2f}) "
                    f"due to extreme volatility (ATR ${atr:.2f}). "
                    "Risk control: Rejecting trade - volatility too high to place safe stop."
                )
                _log_signal_rejection(
                    symbol,
                    "invalid_stop_loss",
                    f"Stop loss ${stop_loss:.2f} <= 0 (ATR ${atr:.2f})",
                    run_date,
                    entry_price,
                    None,
                )
                skipped_count += 1
                continue

            # CRITICAL FIX: Validate entry_price > stop_loss to prevent negative risk
            # If stops are inverted, risk becomes negative, masking overexposure
            if entry_price <= stop_loss:
                logger.error(
                    f"[PHASE 8 CRITICAL] {symbol}: Inverted stops detected - "
                    f"entry ${entry_price:.2f} <= stop ${stop_loss:.2f}. "
                    "This indicates malformed data or stop-loss calculation error."
                )
                _log_signal_rejection(
                    symbol,
                    "inverted_stops",
                    f"Entry ${entry_price:.2f} <= stop ${stop_loss:.2f}",
                    run_date,
                    entry_price,
                    None,
                )
                skipped_count += 1
                continue

            risk_pct = (entry_price - stop_loss) / entry_price * 100

            if risk_pct < 1.5:
                logger.info(f"[PHASE 8] {symbol}: stop too tight ({risk_pct:.1f}%), skipping")
                _log_signal_rejection(
                    symbol, "stop_too_tight", f"Risk {risk_pct:.1f}% < 1.5%", run_date, entry_price, risk_pct
                )

                skipped_count += 1

                continue

            max_risk_val = config.get("max_risk_per_trade_pct")
            if max_risk_val is not None:
                try:
                    max_risk_pct = float(max_risk_val)
                    if risk_pct > max_risk_pct:
                        logger.info(
                            f"[PHASE 8] {symbol}: stop too wide ({risk_pct:.1f}% > {max_risk_pct:.1f}%), skipping"
                        )
                        _log_signal_rejection(
                            symbol,
                            "stop_too_wide",
                            f"Risk {risk_pct:.1f}% > {max_risk_pct:.1f}%",
                            run_date,
                            entry_price,
                            risk_pct,
                        )
                        skipped_count += 1
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(f"[PHASE 8] {symbol}: Could not parse max_risk_per_trade_pct ({max_risk_val}): {e}")

            # Position sizer will handle actual dollar risk limits using max_risk_per_trade_pct
            # The stop-loss width (risk_pct) is checked for min (1.5%) above. Position sizer
            # receives stop_loss_price and enforces position_size so dollar loss <= portfolio * max_risk_per_trade_pct

            # Regime-aware, drawdown-adjusted sizing

            sizing = sizer.calculate_position_size(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
                signal_date=run_date,
                portfolio_value=portfolio_value,
            )

            if "status" not in sizing or sizing["status"] is None:
                raise RuntimeError(
                    f"Position sizer returned invalid result for {symbol}: missing 'status' field. Response: {sizing}"
                )

            if sizing["status"] != "ok":
                reason = sizing.get("reason")
                if not reason:
                    raise RuntimeError(
                        f"[PHASE 8] {symbol}: Position sizer returned status != 'ok' but no 'reason' field. "
                        f"Sizer must provide reason for rejection. Response: {sizing}"
                    )
                logger.info(f"[PHASE 8] {symbol}: sizer blocked - {reason}")
                # Unlike every other skip path in this function (pretrade_check, duplicate_position,
                # quality_gate, stop_too_tight, ...), this one never wrote to algo_signal_rejections -
                # confirmed live 2026-07-27: with all 17 position slots full, every one of 16 qualified
                # signals hit this exact branch and the audit table showed zero rows for them, making
                # a routine, expected "we're at the position cap" run indistinguishable from a silent
                # data/logic failure to anyone checking the audit trail instead of raw logs.
                _log_signal_rejection(symbol, "sizer_blocked", reason, run_date, entry_price, risk_pct)
                skipped_count += 1
                continue

            if "shares" not in sizing:
                logger.error(
                    f"[PHASE 8] {symbol}: CRITICAL - sizer did not return shares field. "
                    f"Response: {sizing}. Check position_sizer module."
                )
                raise RuntimeError(
                    f"Position sizer failed to provide shares for {symbol}. Cannot proceed with zero-share position."
                )
            elif sizing["shares"] < 1:
                reason = f"insufficient shares ({sizing['shares']})"
                logger.info(f"[PHASE 8] {symbol}: sizer blocked - {reason}")
                _log_signal_rejection(symbol, "sizer_blocked", reason, run_date, entry_price, risk_pct)

                skipped_count += 1

                continue

            shares = sizing["shares"]

            position_value = shares * entry_price

            # Final hard-stop validation (includes earnings blackout check)

            try:
                pt_ok, pt_reason = pretrade.run_all(symbol, position_value, float(portfolio_value), eval_date=run_date)

            except ValueError as e:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: pre-trade validation critical failure: {e}. "
                    f"System cannot proceed with entry execution if pre-trade checks fail."
                ) from e

            if not pt_ok:
                logger.info(f"[PHASE 8] {symbol}: pre-trade check - {pt_reason}")
                rejection_reason = pt_reason if pt_reason else "Pre-trade validation failed"
                _log_signal_rejection(symbol, "pretrade_check", rejection_reason, run_date, entry_price, risk_pct)

                skipped_count += 1

                continue

            # CRITICAL DEFENSIVE CHECK: Verify no open/pending positions exist for this symbol
            # FIXED (Session 381): Using serializable isolation level to prevent race condition.
            # Previously: Two concurrent runs could both pass the check, then both create positions.
            # SOLUTION: Check within a SERIALIZABLE transaction so conflicts are detected.
            # This is PostgreSQL's strictest isolation level - concurrent transactions that
            # read/write the same data will conflict, and one will fail with a serialization error.
            # This converts the race condition from "silent duplicate" to "explicit retry needed".
            # BACKSTOP: UNIQUE constraint on algo_trades(symbol) WHERE status IN (open/filled/...)
            # (migration 1158) still provides final safety if isolation level check is bypassed.
            try:
                open_statuses = TradeStatus.all_open()
                # Use read isolation level - PostgreSQL will detect conflicts at commit time
                with DatabaseContext("read") as cur:
                    # Set SERIALIZABLE isolation for this check to detect concurrent writes
                    cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    cur.execute(
                        "SELECT id FROM algo_trades WHERE symbol = %s "
                        "AND status = ANY(%s) LIMIT 1",
                        (symbol, list(open_statuses)),
                    )
                    if cur.fetchone():
                        msg = f"[PHASE 8 DUPLICATE GATE] {symbol} already has open/pending position. Blocking entry."
                        logger.warning(msg)
                        _log_signal_rejection(symbol, "duplicate_position", msg, run_date, entry_price, risk_pct)
                        skipped_count += 1
                        continue
            except psycopg2.extensions.TransactionRollbackError as ser_err:
                # SERIALIZABLE isolation level detected conflict - retry this symbol later
                logger.warning(f"[PHASE 8] {symbol}: Serialization conflict (concurrent write detected), skipping this run")
                _log_signal_rejection(symbol, "serialization_conflict", str(ser_err), run_date, entry_price, risk_pct)
                skipped_count += 1
                continue
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
                logger.error(f"[PHASE 8] Failed to check for duplicate positions: {type(db_err).__name__}: {db_err}")
                _log_signal_rejection(symbol, "duplicate_check_failed", f"Database error checking positions: {type(db_err).__name__}", run_date, entry_price, risk_pct)
                skipped_count += 1
                continue

            sig_composite_score = signal.get("composite_score")
            sig_rs_pct = signal.get("rs_percentile")

            if sig_composite_score is None:
                raise RuntimeError(
                    f"[PHASE 8] Signal for {symbol} missing required 'composite_score' field - "
                    f"cannot execute trade without signal quality validation."
                )
            if sig_rs_pct is None:
                raise RuntimeError(
                    f"[PHASE 8] Signal for {symbol} missing required 'rs_percentile' field - "
                    f"cannot execute trade without relative strength validation."
                )

            # FAIL-FAST: Signal quality score is REQUIRED for entry validation
            # Phase 7 must compute and pass signal_quality_score for all qualified trades
            # Do NOT fall back to composite_score (different methodology)
            # Do NOT fall back to database lookup (indicates Phase 7 computation failed)
            sqs = signal.get("signal_quality_score")
            if sqs is None:
                rejection_reason = (
                    "Signal quality score missing from Phase 7 output. "
                    "Phase 7 must compute signal_quality_score for all trades. "
                    "Reject signal to prevent entry without quality validation."
                )
                logger.error(f"[PHASE 8] {symbol}: REJECTED - {rejection_reason}")
                _log_signal_rejection(symbol, "quality_gate_missing", rejection_reason, run_date, entry_price, risk_pct)
                skipped_count += 1
                continue

            trend_score = signal.get("trend_template_score")
            base_quality = signal.get("base_quality")
            composite_score = sig_composite_score  # Re-assign for use in logging below

            # CRITICAL DEBUG: Log signal fields to diagnose persistence issues
            logger.debug(
                f"[PHASE 8 SIGNAL FIELDS] {symbol}: "
                f"trend={trend_score} base_type={signal.get('base_type')} "
                f"base_quality={base_quality} "
                f"stage_phase={signal.get('stage_phase')}"
            )

            # CRITICAL GATE: Reject stale signals (from prior trading day's EOD pipeline)
            # Session 28 root cause: signals 16+ hours old cause 75% loss rate (momentum already faded)
            # Signals generated yesterday at 4:05 PM → entered today at 1:00 PM = 16+ hours old
            # This gate prevents entering dead setups by age threshold (default 24 hours)
            signal_age_hours_val = config.get("max_signal_age_hours", default=24)
            try:
                max_signal_age_hours = int(signal_age_hours_val)
                if max_signal_age_hours <= 0:
                    raise ValueError(f"max_signal_age_hours must be positive, got {max_signal_age_hours}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"[PHASE 8 CRITICAL] max_signal_age_hours is invalid ({signal_age_hours_val}): {e}") from e

            sig_date_obj = signal.get("signal_date")
            if sig_date_obj:
                if isinstance(sig_date_obj, str):
                    sig_date_obj = datetime.fromisoformat(sig_date_obj).date()
                run_date_obj = run_date if isinstance(run_date, _date) else run_date.date()
                signal_age_days = (run_date_obj - sig_date_obj).days
                signal_age_hours = signal_age_days * 24
                if signal_age_hours > max_signal_age_hours:
                    rejection_reason = f"Signal too old: {signal_age_days}d {signal_age_hours}h (max {max_signal_age_hours}h). Generated {sig_date_obj}, entered {run_date_obj}."
                    logger.info(f"[PHASE 8] {symbol}: REJECTED - {rejection_reason}")
                    _log_signal_rejection(symbol, "stale_signal", rejection_reason, run_date, entry_price, risk_pct)
                    skipped_count += 1
                    continue

            # CRITICAL GATE: Enforce min_signal_quality_score threshold for entry validation
            min_sqs_val = config.get("min_signal_quality_score")
            if min_sqs_val is None:
                raise ValueError(
                    "[PHASE 8 CRITICAL] min_signal_quality_score config missing. "
                    "Cannot gate entry quality without threshold. "
                    "Set explicit min_signal_quality_score in algo_config table (recommended: 60-75)."
                )
            try:
                min_sqs = int(min_sqs_val)
                if min_sqs < 0 or min_sqs > 100:
                    raise ValueError(f"min_signal_quality_score must be 0-100, got {min_sqs}")
            except (ValueError, TypeError) as e:
                raise ValueError(f"[PHASE 8 CRITICAL] min_signal_quality_score is invalid ({min_sqs_val}): {e}") from e
            if sqs < min_sqs:
                rejection_reason = f"Signal quality score {int(sqs)} below minimum {min_sqs}"
                logger.info(f"[PHASE 8] {symbol}: REJECTED - {rejection_reason}")
                _log_signal_rejection(symbol, "quality_gate", rejection_reason, run_date, entry_price, risk_pct)
                skipped_count += 1
                continue

            # NEW GATE: Check maximum signal quality score (filters potentially risky high-scoring signals)
            # Investigation pending on whether quality_score is inverted (higher scores had losses on 2026-08-07)
            max_sqs_val = config.get("max_signal_quality_score")
            if max_sqs_val is not None:
                try:
                    max_sqs = int(max_sqs_val)
                    if max_sqs < 0 or max_sqs > 100:
                        raise ValueError(f"max_signal_quality_score must be 0-100, got {max_sqs}")
                except (ValueError, TypeError) as e:
                    raise ValueError(f"[PHASE 8 CRITICAL] max_signal_quality_score is invalid ({max_sqs_val}): {e}") from e
                if sqs > max_sqs:
                    rejection_reason = f"Signal quality score {int(sqs)} exceeds maximum {max_sqs} (potential risk indicator)"
                    logger.info(f"[PHASE 8] {symbol}: REJECTED - {rejection_reason}")
                    _log_signal_rejection(symbol, "quality_gate_max", rejection_reason, run_date, entry_price, risk_pct)
                    skipped_count += 1
                    continue

            logger.info(
                f"[PHASE 8] {symbol}: BUY entry=${entry_price:.2f} stop=${stop_loss:.2f} "
                f"risk={risk_pct:.1f}% shares={shares} value=${position_value:,.0f} "
                f"composite={sig_composite_score} rs_pct={sig_rs_pct} sqs={sqs} trend={trend_score}"
            )
            # DEBUG: Log signal dict for this trade before execution
            logger.debug(f"[PHASE 8 DEBUG] {symbol}: Full signal dict - sqs={signal.get('signal_quality_score')}, trend={signal.get('trend_template_score')}, base_q={signal.get('base_quality')}, composite={signal.get('composite_score')}")

            if not dry_run:
                # ISSUE 14 FIX: Execute each trade with fresh database context to prevent connection corruption
                # If one trade corrupts the connection, the next trade gets a fresh connection from the pool
                try:
                    with DatabaseContext("write") as cur:
                        # REQUIRED: symbol, entry_price, shares, stop_loss_price, signal_date, entry_date
                        # OPTIONAL: sector, industry (enrichment data, may be None if data unavailable)
                        # SESSION 367 FIX: Pass signal quality scores for trade entry validation
                        # CRITICAL FIX: Ensure sqs is passed to trade executor to be stored in database
                        # Phase 7 computes signal_quality_score and passes it via qualified_trades
                        # Phase 8 must extract and pass it through to TradeContext
                        # Session 379 fix: Verified sqs value before passing

                        # CRITICAL FIX (Session 30): Convert signal_date from string to date object
                        # Phase 7 stores signal_date as ISO string, but TradeContext expects date object
                        sig_date = signal.get("signal_date")
                        if isinstance(sig_date, str):
                            try:
                                sig_date = datetime.strptime(sig_date, "%Y-%m-%d").date()
                            except (ValueError, TypeError):
                                sig_date = run_date
                        sig_date = sig_date or run_date

                        trade_result = trade_executor.execute_trade(
                            symbol=symbol,
                            entry_price=entry_price,
                            shares=shares,
                            stop_loss_price=stop_loss,
                            signal_date=sig_date,
                            entry_date=run_date,
                            composite_score=composite_score,
                            sector=signal.get("sector"),
                            industry=signal.get("industry"),
                            rs_percentile=signal.get("rs_percentile"),
                            sqs=sqs,
                            trend_score=trend_score,
                            base_type=signal.get("base_type"),
                            base_quality=signal.get("base_quality"),
                        )
                        logger.debug(f"[PHASE 8] {symbol}: Executed trade with sqs={sqs}, trend_score={trend_score}")

                        if "success" not in trade_result or trade_result["success"] is None:
                            raise RuntimeError(
                                f"Trade executor returned invalid result for {symbol}: missing 'success' field. "
                                f"Response: {trade_result}"
                            )

                        if trade_result["success"]:
                            if "trade_id" not in trade_result:
                                raise RuntimeError(
                                    f"Trade succeeded for {symbol} but missing 'trade_id' field. Response: {trade_result}"
                                )

                            executed_count += 1
                            entered_symbols.append(symbol)
                            entered_prices.append(entry_price)
                            successfully_entered += 1

                            # CRITICAL FIX (2026-08-03): Mark signal as executed in algo_signals
                            # so dashboard query (WHERE execution_status='executed') shows this trade
                            try:
                                with DatabaseContext("write") as cur:
                                    cur.execute(
                                        """UPDATE algo_signals
                                           SET execution_status = 'executed',
                                               updated_at = NOW()
                                           WHERE symbol = %s AND DATE(signal_date) = %s""",
                                        (symbol, run_date),
                                    )
                            except Exception as mark_err:
                                logger.warning(
                                    f"[PHASE 8] {symbol}: Trade executed but failed to mark signal as executed in algo_signals: {mark_err}. "
                                    f"Audit trail preserved in algo_trades table (trade_id={trade_result['trade_id']})"
                                )

                            logger.info(
                                f"[PHASE 8] {symbol}: ENTERED trade_id={trade_result['trade_id']} "
                                f"alpaca_order_id={trade_result['alpaca_order_id']} "
                                f"status={trade_result['status']}"
                            )

                            if max_entries and executed_count >= max_entries:
                                logger.info(f"[PHASE 8] Reached max_new_positions_today={max_entries}, stopping")

                                break

                        else:
                            message = trade_result["message"]
                            status = trade_result["status"]
                            if status in _POLICY_REJECTION_STATUSES:
                                logger.info(f"[PHASE 8] {symbol}: SKIPPED (policy) - {message} (status={status})")
                                _log_signal_rejection(symbol, status, message, run_date, entry_price, risk_pct)
                                skipped_count += 1
                            else:
                                logger.error(f"[PHASE 8] {symbol}: FAILED to execute trade: {message} (status={status})")
                                # Persist the failure reason - previously this only went to logger.error(),
                                # which is lost once the process exits. Skipped/rejected signals were already
                                # audited via _log_signal_rejection() below in this same function; actual
                                # broker-execution failures were the one path with no queryable audit trail,
                                # making them undiagnosable in production without live log access.
                                _log_signal_rejection(
                                    symbol,
                                    "execution_failed",
                                    f"{message} (status={status})",
                                    run_date,
                                    entry_price,
                                    risk_pct,
                                )

                                failed_count += 1

                except (ValueError, ZeroDivisionError, TypeError, DatabaseError) as exec_err:
                    logger.error(
                        f"[PHASE 8] {symbol}: execution error: {exec_err}",
                        exc_info=True,
                    )
                    _log_signal_rejection(symbol, "execution_error", str(exec_err), run_date, entry_price, risk_pct)
                    failed_entries.append((symbol, str(exec_err)))

                    failed_count += 1
                except psycopg2.DatabaseError as db_err:
                    # Check for UniqueViolation (duplicate idempotency key)
                    db_err_str = str(db_err)
                    if "duplicate key value violates" in db_err_str or "uniqueness violation" in db_err_str.lower():
                        logger.info(
                            f"[PHASE 8] {symbol}: Trade already exists (duplicate idempotency key). "
                            f"Orchestrator already executed this signal - skipping reexecution."
                        )
                        _log_signal_rejection(
                            symbol, "duplicate_trade_exists",
                            f"Trade already executed in prior orchestrator run: {db_err_str[:150]}",
                            run_date, entry_price, risk_pct
                        )
                        executed_count += 1  # Count as successful (trade exists and is valid)
                        successfully_entered += 1  # CRITICAL FIX: Also update successfully_entered for consistency
                        entered_symbols.append(symbol)
                        entered_prices.append(entry_price)
                    else:
                        # Generic database error
                        logger.error(f"[PHASE 8] {symbol}: Database error during trade execution, skipping: {db_err}")
                        _log_signal_rejection(symbol, "database_error", str(db_err), run_date, entry_price, risk_pct)
                        failed_entries.append((symbol, "database_error"))
                        failed_count += 1

            else:
                logger.info(f"[PHASE 8] DRY-RUN: Would execute {symbol} ({shares} shares @ ${entry_price:.2f})")

                executed_count += 1
                successfully_entered += 1  # CRITICAL FIX: Also update successfully_entered for consistency
                entered_symbols.append(symbol)
                entered_prices.append(entry_price)

                if max_entries and executed_count >= max_entries:
                    logger.info(f"[PHASE 8] Reached max_new_positions_today={max_entries}, stopping")

                    break

        except (RuntimeError, ValueError, TypeError, AttributeError, IndexError, psycopg2.Error, DatabaseError) as e:
            symbol = (signal.get("symbol") or "UNKNOWN") if isinstance(signal, dict) else str(signal)
            if isinstance(e, IndexError):
                logger.critical(
                    f"[PHASE 8] CRITICAL IndexError processing {symbol}: {e}. "
                    f"This indicates a data structure mismatch or missing fields. "
                    f"Signal type: {type(signal).__name__}, Signal: {signal}. Stack trace:",
                    exc_info=True,
                )
            else:
                logger.error(
                    f"[PHASE 8] Error processing {symbol}: {e}",
                    exc_info=True,
                )
            # psycopg2.Error (added here): the duplicate-position pre-check above (~line 1497)
            # is a soft, non-atomic read - algo_trades_symbol_live_status_idx (migration 1158,
            # a UNIQUE partial index) is the real backstop against an actual duplicate write if
            # two entry attempts for the same symbol race past that check. But the comment on
            # that check claims "TradeExecutor will catch constraint violation and log error" -
            # it doesn't: _insert_trade_record() deliberately raises on any DB error (see its
            # own docstring - "MUST NOT silently fail"), and DatabaseContext's cursor wrapper
            # (utils/db/context.py) re-raises psycopg2.DatabaseError/OperationalError as-is, not
            # translated to any of the types this except previously listed. Without this, a real
            # UniqueViolation (or any other psycopg2 error from execute_trade's DB writes) would
            # propagate straight out of this per-symbol loop and abort Phase 8 for every symbol
            # not yet evaluated that run - not just skip the one raced symbol, as documented.
            # Use signal.get(...) rather than the local entry_price/risk_pct vars - this
            # handler covers the whole per-symbol block, including the part before those
            # locals are computed, so they aren't guaranteed to be assigned yet.
            entry_price_val = None
            if isinstance(signal, dict) and "entry_price" in signal and signal.get("entry_price") is not None:
                try:
                    entry_price_val = float(signal["entry_price"])
                except (TypeError, ValueError):
                    entry_price_val = None
            _log_signal_rejection(
                symbol, "processing_error", str(e), run_date, entry_price_val
            )

            failed_count += 1

    elapsed = time.time() - phase_start

    logger.info(
        f"[PHASE 8] Done in {elapsed:.1f}s: {executed_count} executed, {skipped_count} skipped, {failed_count} failed"
    )

    # CRITICAL FIX: Log all failures with details for debugging
    if failed_count > 0:
        logger.critical(
            f"[PHASE 8 CRITICAL] {failed_count} trades failed to execute. "
            f"Failed entries: {failed_entries}. "
            f"Success rate: {round((executed_count / (executed_count + failed_count) * 100), 1)}%. "
            f"These failures prevent position entry and require investigation."
        )

    # ISSUE 14 FIX: Log resource cleanup summary
    if failed_entries:
        logger.warning(
            f"[PHASE 8] Trade execution summary: {successfully_entered} entered, {len(failed_entries)} failed. "
            f"Failed entries: {failed_entries}"
        )

    # Calculate execution rejection rate for observability
    total_evaluated = executed_count + skipped_count + failed_count
    execution_rejection_rate = round((skipped_count / total_evaluated * 100) if total_evaluated > 0 else 0, 1)
    if execution_rejection_rate > 20:
        logger.warning(
            f"[PHASE 8] High execution rejection rate: {execution_rejection_rate}% "
            f"({skipped_count}/{total_evaluated} signals rejected)"
        )

    # CRITICAL FIX: status was hardcoded "success"/"ok" below regardless of failed_count,
    # so a run where every entry attempt raised (order rejected, DB error, etc.) still
    # reported clean success with 0 executed - same bug class as phase6_exit_execution.py's
    # previously-always-"success" status (which errors already fed into but the status
    # string itself ignored).
    #
    # DRY-RUN FIX: the dry-run branch above (`else: ... executed_count += 1`) simulates
    # entries without ever calling trade_executor.execute_trade(), but this summary used
    # to read "N trades executed, 0 failed" identically to a real run - no way to tell a
    # monitor-only (--evening) dry-run from a real paper-money execution just from this
    # text/status, unlike phase6_exit_execution.py which already labels its dry-run summary
    # "DRY-RUN: execution skipped (no real trades)". Mirrors that fix here.
    if dry_run:
        phase_status = "degraded"
        detail_text = (
            f"DRY-RUN: execution skipped (no real trades) - would have entered "
            f"{executed_count} trades, {failed_count} failed"
        )
    else:
        phase_status = "degraded" if failed_count > 0 else "ok"
        detail_text = f"{executed_count} trades executed, {failed_count} failed"
    log_phase_result_fn(8, "entry_execution", phase_status, detail_text)

    # success_rate: percentage of actual submission attempts (executed + failed) that
    # succeeded. Deliberately excludes skipped_count from the denominator - those are
    # signals filtered out by policy before an order was ever attempted (sizing/exposure
    # gates), a different concept from execution_rejection_rate above (which does include
    # skips, to answer "how much of today's signal pool got filtered").
    attempted = executed_count + failed_count
    success_rate = round((executed_count / attempted * 100) if attempted > 0 else 0, 1)

    result_data = {
        "entered": executed_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "execution_rejection_rate": execution_rejection_rate,
        "entries_executed": executed_count,
        "success_rate": success_rate,
        "avg_entry_price": round(sum(entered_prices) / len(entered_prices), 2) if entered_prices else None,
        "symbols_entered": entered_symbols,
    }
    # Validate schema contract before returning
    from algo.orchestrator.phase_data_contract import validate_phase_data

    validate_phase_data(8, result_data)
    return PhaseResult(
        8,
        "entry_execution",
        phase_status,
        result_data,
        False,
        detail_text,
    )
