#!/usr/bin/env python3

"""

PHASE 8: ENTRY EXECUTION

For each qualified signal from Phase 5:

1. Check halt flag before any entry
2. Check exposure constraints from Phase 3b
3. Run liquidity checks (ADV, dollar volume, price history age)
4. Compute true ATR (max of H-L, |H-prev_C|, |L-prev_C|) anchored to run_date
5. Compute SMA_50 anchored to run_date
6. Stop loss: min(SMA_50 - ATR, entry - 2*ATR) - lower stop = more room for the trade
7. Use PositionSizer for regime-aware, drawdown-adjusted sizing
8. Run PreTradeChecks (size cap, duplicate prevention, minimum order)
9. Execute trade

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

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from algo.trading.executor import TradeExecutor
from algo.trading.position_sizer import PositionSizer
from algo.trading.pretrade_checks import PreTradeChecks
from utils.db.context import DatabaseContext
from utils.infrastructure import EASTERN_TZ
from utils.infrastructure.market_timing import MARKET_CLOSE_TIME, MARKET_OPEN_TIME

logger = logging.getLogger(__name__)


def _calculate_current_total_risk_pct(max_risk_limit_pct: float = 4.0) -> tuple[float, float]:
    """Calculate total open risk as percentage of portfolio.

    PROACTIVE RISK CHECK: Used by Phase 8 to verify entry won't exceed risk limit BEFORE executing.
    This is defensive - we check before entering, not after.

    Returns:
        (current_risk_pct, available_risk_pct) where available = limit - current

    Raises:
        RuntimeError: If portfolio value or risk calculation fails
    """
    try:
        with DatabaseContext("read") as cur:
            # Get current open positions and calculate total risk
            cur.execute("""
                SELECT
                    SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * p.quantity)) as total_risk_dollars,
                    COUNT(*) as open_count
                FROM algo_positions p
                JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE p.status = 'open'
            """)
            result = cur.fetchone()
            total_risk_dollars = float(result[0]) if result and result[0] else 0.0
            open_count = result[1] if result and result[1] else 0

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

            logger.info(
                f"[RISK CHECK] Total open risk: {current_risk_pct:.2f}% ({open_count} positions), "
                f"Available capacity: {available_risk_pct:.2f}% (limit: {max_risk_limit_pct}%)"
            )

            return current_risk_pct, available_risk_pct
    except Exception as e:
        logger.error(f"[RISK CHECK] Failed to calculate total open risk: {e}")
        raise RuntimeError(f"Risk calculation failed: {e}") from e


def _log_signal_rejection(
    symbol: str,
    rejection_stage: str,
    rejection_reason: str,
    run_date: _date,
    entry_price: float | None = None,
    risk_pct: float | None = None,
) -> None:
    """Log signal rejection to audit table."""
    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                """INSERT INTO algo_signal_rejections
                   (rejection_date, symbol, rejection_stage, rejection_reason, entry_price, risk_pct)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (run_date, symbol, rejection_stage, rejection_reason, entry_price, risk_pct),
            )
    except Exception as e:
        logger.error(f"[AUDIT] CRITICAL: Failed to log signal rejection for {symbol}: {e}. Audit trail incomplete.")
        raise RuntimeError(f"Signal rejection audit logging failed for {symbol}: {e}") from e


def _persist_signals_to_database(qualified_trades: list[dict[str, Any]], run_date: _date, dry_run: bool) -> int:
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

                if "composite_score" in signal_data and signal_data["composite_score"] is not None:
                    try:
                        signal_quality_score = safe_float(signal_data["composite_score"], f"{symbol}.composite_score", allow_none=False)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: invalid composite_score: {e}")
                        skipped_count += 1
                        continue
                elif "signal_quality_score" in signal_data and signal_data["signal_quality_score"] is not None:
                    try:
                        signal_quality_score = safe_float(signal_data["signal_quality_score"], f"{symbol}.signal_quality_score", allow_none=False)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: invalid signal_quality_score: {e}")
                        skipped_count += 1
                        continue
                else:
                    logger.warning(f"[PERSIST SIGNALS] Skipping {symbol}: missing signal quality score")
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
        raise


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
                f"""

                WITH latest_prices AS (

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

                        SELECT

                            symbol,

                            GREATEST(

                                high - low,

                                ABS(high - LAG(close) OVER (PARTITION BY symbol ORDER BY date)),

                                ABS(low - LAG(close) OVER (PARTITION BY symbol ORDER BY date))

                            ) AS tr,

                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn

                        FROM price_daily

                        WHERE symbol IN ({symbol_placeholders}) AND date <= %s

                    ) t

                    WHERE tr IS NOT NULL AND rn <= %s

                    GROUP BY symbol

                )

                SELECT

                    lp.symbol,

                    atr.atr,

                    sma.sma_50,

                    lp.close

                FROM latest_prices lp

                INNER JOIN sma_50_data sma ON sma.symbol = lp.symbol

                INNER JOIN atr_data atr ON atr.symbol = lp.symbol

                """,
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
                symbol, atr, sma_50, close = row

                if atr is None or sma_50 is None or close is None:
                    raise ValueError(
                        f"Symbol {symbol}: Technical data incomplete from database query. "
                        f"ATR={atr}, SMA_50={sma_50}, close={close}. "
                        f"INNER JOIN should have excluded incomplete rows. Check technical data loader."
                    )

                # CRITICAL FIX: Session 345 - Validate type conversions (handles NaN/Infinity)
                try:
                    from utils.type_conversion import safe_float
                    atr_float = safe_float(atr, f"{symbol}.atr", allow_none=False)
                    sma_50_float = safe_float(sma_50, f"{symbol}.sma_50", allow_none=False)
                    close_float = safe_float(close, f"{symbol}.close", allow_none=False)
                except (ValueError, TypeError) as e:
                    logger.error(f"[ENTRY EXECUTION] {symbol}: Technical data type conversion failed: {e}")
                    raise ValueError(f"Technical data validation failed for {symbol}: {e}") from e

                result[symbol] = cast(
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


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
    qualified_trades: list[dict[str, Any]] | None = None,
    exposure_constraints: dict[str, Any] | None = None,
    check_halt_flag: Callable[..., Any] | None = None,
    executor: Any = None,
) -> PhaseResult:
    """Execute Phase 8: Entry Execution.

    DEPENDENCY VALIDATION: Phase 8 requires data from Phase 7 (qualified trades)
    and Phase 5 (exposure constraints). If executor is provided, dependencies are
    fetched via validated contract. Otherwise, data must be passed directly (legacy API).
    """

    phase_start = time.time()

    logger.info("[PHASE 8] Starting entry execution")

    # CRITICAL GUARD: Enforce market hours (9:30 AM - 4:00 PM ET)
    # Entries executed outside market hours will be queued as pre-market/after-hours orders
    # and may fill at unexpected prices or not fill at all. Risk: duplicate orders on next run.
    now_et = datetime.now(EASTERN_TZ).time()
    if not (MARKET_OPEN_TIME <= now_et < MARKET_CLOSE_TIME):
        msg = (
            f"[PHASE 8 MARKET HOURS GUARD] Cannot execute entries outside market hours. "
            f"Current time: {now_et.strftime('%H:%M:%S')} ET, "
            f"market hours: 9:30 AM - 4:00 PM ET. Skipping Phase 8."
        )
        logger.warning(msg)
        log_phase_result_fn(8, "entry_execution", "degraded", msg)
        return PhaseResult(
            8,
            "entry_execution",
            "degraded",
            {"entered": 0},
            False,
            msg,
        )

    # CRITICAL GUARD: Check for pending/recent orders that may still be filling
    # If orders from prior run are still pending, executing new entries risks duplicates
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
                return PhaseResult(
                    8,
                    "entry_execution",
                    "blocked",
                    {"entered": 0},
                    False,
                    msg,
                )
    except Exception as e:
        logger.error(f"[PHASE 8] Error checking for pending orders: {e}")
        # Don't halt on this check - log and continue

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
                qualified_trades_from_executor = phase7_result.data.get("qualified_trades")
                logger.info(f"[PHASE 8] Retrieved {len(qualified_trades_from_executor or [])} signals from Phase 7")
            elif phase7_result and phase7_result.halted:
                logger.warning(
                    f"[PHASE 8] Phase 7 halted: {phase7_result.error or 'unknown'}. "
                    f"No signals available, but Phase 8 will still run proactive risk check."
                )
            else:
                logger.info("[PHASE 8] Phase 7 unavailable - proceeding with proactive risk check only")

            # Try to get Phase 5 exposure constraints (also optional for proactive checks)
            phase5_result = executor.get_result(5)
            if phase5_result and phase5_result.ok:
                exposure_constraints_from_executor = phase5_result.data.get("constraints")
                logger.info("[PHASE 8] Retrieved exposure constraints from Phase 5")
            elif phase5_result and phase5_result.halted:
                logger.warning(
                    f"[PHASE 8] Phase 5 halted: {phase5_result.error or 'unknown'}. "
                    f"No exposure constraints available."
                )
            else:
                logger.info("[PHASE 8] Phase 5 unavailable - will use defaults for proactive checks")
        except Exception as e:
            logger.warning(f"[PHASE 8] Could not fetch Phase 7/5 data: {e}. Proceeding with available data.")

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
    # Report as "degraded" (success but suboptimal) not "halted" - Phase 8 ran but entries were blocked.
    if check_halt_flag and check_halt_flag():
        msg = "[PHASE 8] Circuit breaker active (halt flag set) - entries blocked to protect portfolio"
        logger.warning(msg)
        log_phase_result_fn(8, "entry_execution", "degraded", msg)
        return PhaseResult(8, "entry_execution", "degraded", {"entered": 0}, False, msg)

    # SESSION 396 FIX: GRACEFUL DEGRADATION WHEN DEPENDENCIES UNAVAILABLE
    # Phase 5 (exposure policy) may be unavailable due to earlier phase halts.
    # We can still run proactive risk checks and gracefully skip entries if constraints are missing.
    if not exposure_constraints:
        logger.warning(
            "[PHASE 8 DEGRADED] Exposure constraints not available (Phase 5 may have halted). "
            "Phase 8 will run proactive risk check only, no entries will be attempted."
        )
        # Continue to proactive risk check below - don't halt
    else:
        required_constraint_keys = [
            "halt_new_entries",
            "max_new_positions_today",
            "max_concentration_pct",
        ]
        missing_keys = [k for k in required_constraint_keys if k not in exposure_constraints]
        if missing_keys:
            logger.warning(
                f"[PHASE 8 DEGRADED] Exposure constraints missing keys: {missing_keys}. "
                f"Using defaults for proactive risk check."
            )
            # Don't halt - continue with proactive check using defaults

    # CRITICAL: Verify data freshness before executing trades

    # Trades execute on EOD (after market close), so expect:
    # - If today is a trading day: same-day data
    # - If today is not a trading day: most recent trading day's data (within 10 days)

    try:
        from datetime import timedelta as td

        from algo.infrastructure.market_calendar import MarketCalendar

        with DatabaseContext("read") as cur:
            cur.execute("""SELECT MAX(date) as latest_price_date FROM price_daily""")

            result = cur.fetchone()
            if result is None:
                raise ValueError("Price data freshness query returned no results - price_daily table may be empty")

            latest_price_date = result[0]

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
            # Find previous trading day as minimum acceptable price date
            expected_price_date = most_recent_trading_day - td(days=1)
            while expected_price_date > most_recent_trading_day - td(days=10):
                if MarketCalendar.is_trading_day(expected_price_date):
                    break
                expected_price_date -= td(days=1)

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

    # Validate that exposure_constraints has all fields needed for position sizing
    # CRITICAL: All required fields must be present; no silent defaults allowed
    required_fields = [
        "tier_name",
        "risk_multiplier",
        "max_new_positions_today",
        "halt_new_entries",
        "max_concentration_pct",  # Added by Phase 5 fallback
    ]

    missing_fields = [f for f in required_fields if f not in exposure_constraints]

    if missing_fields:
        msg = (
            f"[PHASE 8 CRITICAL] exposure_constraints missing required fields: {missing_fields}. "
            "Cannot size positions without complete constraints. "
            "Phase 5 (Exposure Policy) must provide complete constraint data."
        )

        logger.critical(msg)

        log_phase_result_fn(8, "entry_execution", "halt", msg)

        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, msg)

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

    # ISSUE #4 FIX: Check if paper mode is active before initializing TradeExecutor
    # CRITICAL FIX: Require explicit config - fail-fast if missing
    # No silent fallback to False (which would attempt live trading)
    if "execution_mode" not in config:
        raise ValueError(
            "[PHASE 8] Config missing 'execution_mode'. "
            "Trading mode must be explicit ('paper' or 'auto'). "
            "Check algo_config table has this key."
        )
    execution_mode_check = config["execution_mode"]

    if "alpaca_paper_trading" not in config:
        raise ValueError(
            "[PHASE 8] Config missing 'alpaca_paper_trading'. "
            "Trading mode must be explicit (paper vs live). "
            "Check algo_config table has this key."
        )
    alpaca_paper_trading = config["alpaca_paper_trading"]
    # "auto" is this system's real live-trading mode (see this session's other
    # execution_mode fixes) - this is log text only (no behavior gated on it), but
    # including "auto" made every live orchestrator run log the misleading "Paper trading
    # mode active... Trades will execute against paper account" message.
    if execution_mode_check == "paper" or alpaca_paper_trading:
        logger.info(
            f"[PHASE 8] Paper trading mode active (execution_mode={execution_mode_check}, "
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

    sizer_config = config.to_dict() if hasattr(config, "to_dict") else {}

    if tier_max_conc is not None:
        sizer_config["max_concentration_pct"] = tier_max_conc

        logger.info(f"[PHASE 8] Position sizer: max_concentration_pct={tier_max_conc:.0f}% (from tier)")

    sizer = PositionSizer(config=sizer_config)

    liquidity = LiquidityChecks(config=config)

    # Fetch portfolio value once - avoids one Alpaca API call per symbol
    # CRITICAL FIX: Use database snapshot for atomic value, not live Alpaca fetch
    # Prevents: stale value being used for position sizing if API times out and fallback activates
    execution_mode = config.get("execution_mode", "paper")
    portfolio_value = None
    portfolio_value_source = None

    # Primary: Try database snapshot (atomic, consistent across all trades)
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT total_portfolio_value, snapshot_date
                FROM algo_portfolio_snapshots
                WHERE snapshot_date = %s
                ORDER BY snapshot_date DESC LIMIT 1
            """,
                (run_date,),
            )
            result = cur.fetchone()
            if result and result[0] is not None:
                portfolio_value = Decimal(str(result[0]))
                portfolio_value_source = "database_snapshot"
                logger.info(f"[PHASE 8] Portfolio value: ${portfolio_value:,.0f} (from database snapshot)")
            else:
                raise ValueError("No portfolio snapshot available for today")
    except Exception as db_err:
        logger.warning(f"[PHASE 8] Database snapshot unavailable: {db_err}. Trying Alpaca API...")

        # Secondary: Try Alpaca API (may be stale/slow but more current than config)
        try:
            portfolio_value = sizer.get_portfolio_value()
            portfolio_value_source = "alpaca_api"
            logger.info(f"[PHASE 8] Portfolio value: ${portfolio_value:,.0f} (from Alpaca API)")
        except RuntimeError as api_err:
            # Tertiary: Use configured fallback ONLY in paper mode. "auto" is this system's
            # real live-trading mode (see this session's other execution_mode fixes:
            # 0f37d938d, 0d6ce501a, a2389bb48) - including it here meant that if both the
            # database snapshot AND the live Alpaca API were unavailable during real trading,
            # this would silently size positions off a static configured
            # initial_capital_paper_trading number instead of failing fast like the `else`
            # branch below (which this comment already describes as the intended live-mode
            # behavior, but which "auto" never actually reached).
            if execution_mode == "paper":
                initial_capital = config.get("initial_capital_paper_trading")
                if not initial_capital or initial_capital <= 0:
                    error_msg = (
                        f"[PHASE 8 HALT] Cannot determine portfolio value. "
                        f"Tried: database snapshot, Alpaca API. "
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
                    f"(database and API unavailable). "
                    f"Position sizing may be inaccurate. Database error: {db_err}. API error: {api_err}"
                )
            else:
                # Live mode: never use fallback, fail-fast
                error_msg = f"[PHASE 8 HALT] Cannot determine portfolio value (live mode). Database error: {db_err}. API error: {api_err}"
                logger.critical(error_msg)
                log_phase_result_fn(8, "entry_execution", "halt", error_msg)
                return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    if portfolio_value is None or portfolio_value <= 0:
        error_msg = f"[PHASE 8 HALT] Invalid portfolio value: {portfolio_value} (source: {portfolio_value_source}). Cannot execute trades."
        logger.critical(error_msg)
        log_phase_result_fn(8, "entry_execution", "halt", error_msg)
        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    # CRITICAL: Get Alpaca credentials - FAIL LOUD if missing and trades are queued
    # Previously: silent fallback would skip trades without any indication (WRONG!)
    # Now: explicit validation with actionable error messages
    alpaca_key = None
    alpaca_secret = None
    execution_mode = config.get("execution_mode", "paper")

    try:
        from config.credential_manager import get_credential_manager

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
    # This is defensive - stops entries BEFORE they would push us over the limit
    # (vs circuit breaker which stops AFTER we've exceeded it)
    try:
        current_risk_pct, available_capacity_pct = _calculate_current_total_risk_pct(max_risk_limit_pct=4.0)
        if available_capacity_pct < 0.3:  # Less than 0.3% room left (rounding safety)
            msg = (
                f"[PHASE 8 RISK GUARD] Total open risk {current_risk_pct:.2f}% >= 4% limit. "
                f"Available capacity: {available_capacity_pct:.2f}%. "
                f"Cannot enter new positions - risk already at limit. Close positions to trade."
            )
            logger.warning(msg)
            log_phase_result_fn(8, "entry_execution", "degraded", msg)
            return PhaseResult(8, "entry_execution", "degraded", {"entered": 0}, False, msg)
        elif available_capacity_pct < 1.0:
            logger.warning(
                f"[PHASE 8 RISK GUARD] Current risk {current_risk_pct:.2f}%, "
                f"only {available_capacity_pct:.2f}% capacity available. "
                f"Will size positions conservatively to stay within limit."
            )
    except Exception as e:
        logger.warning(f"[PHASE 8] Risk pre-check failed (will rely on circuit breaker): {e}")
        # Don't halt - circuit breaker will catch if we exceed limits
        pass

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
        if sma_50 is None or atr_14 is None or close is None:
            raise RuntimeError(
                f"[PHASE 8] {sym}: Required technical data missing. "
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

    logger.info(
        f"[PHASE 8] Technical data: {precomputed_count}/{len(symbols_with_precomputed)} symbols validated. "
        f"Merged from Phase 7 precomputed + batch fetch."
    )

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
                logger.debug(f"[PHASE 8] {symbol}: liquidity - {liq_reason}")

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
                    f"[PHASE 8] {symbol}: Incomplete technical data (ATR={atr}, SMA_50={sma_50}, close={close}). "
                    f"Cannot execute entry without complete data. This indicates upstream loader failure or data cache corruption."
                )

            entry_price = cast(float, close)
            atr = cast(float, atr)
            sma_50 = cast(float, sma_50)

            # VALIDATION: Technical indicators must be positive (sanity check for data corruption)
            if entry_price <= 0:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: entry_price={entry_price} is non-positive. "
                    "This indicates corrupted price data in technical_data_daily table. "
                    "Cannot proceed with trade execution."
                )

            if atr < 0:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: ATR={atr} is negative. "
                    "ATR cannot be negative. This indicates corrupted volatility data in technical_data_daily table."
                )

            if sma_50 <= 0:
                raise RuntimeError(
                    f"[PHASE 8] {symbol}: SMA_50={sma_50} is non-positive. "
                    "50-day moving average is corrupted. Cannot calculate valid stop loss levels."
                )

            # Stop loss: min() picks the LOWER (wider) stop, giving the trade more room.
            # SMA_50 - ATR = below moving-average support.
            # entry - 1.2*ATR = volatility-based floor (SESSION 372 FIX: tighter than 2.0*ATR).
            # REASON: 2.0*ATR was causing avg losses 1.57x larger than wins (risk/reward imbalance).
            # Tighter stop = smaller loss if wrong, better risk/reward profile.
            stop_loss = min(
                sma_50 - atr,
                entry_price - 1.2 * atr,
            )

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
                            logger.info(
                                f"[PHASE 8] {symbol}: Stop loss ${stop_loss:.2f} below 52-week support ${support_52w:.2f}. "
                                f"Adjusting to ${min_stop_above_support:.2f} (0.5% above support). "
                                f"Original formula (min(sma-atr, entry-2*atr)) produced technically unsound placement."
                            )
                            stop_loss = min_stop_above_support
            except Exception as e:
                logger.error(
                    f"[PHASE 8 CRITICAL] {symbol}: Could not validate stop loss against support: {type(e).__name__}: {e}"
                )
                _log_signal_rejection(
                    symbol,
                    "stop_loss_validation_failed",
                    f"Cannot verify stop loss against support levels - {type(e).__name__}",
                    run_date,
                )
                continue

            # EDGE CASE FIX: Stop loss can become negative when ATR is very large
            # (extreme volatility). This is invalid - cannot short at negative price.
            if stop_loss <= 0:
                logger.info(
                    f"[PHASE 8] {symbol}: Stop loss negative (${stop_loss:.2f}) due to extreme volatility (ATR ${atr:.2f}). "
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
                        logger.info(f"[PHASE 8] {symbol}: stop too wide ({risk_pct:.1f}% > {max_risk_pct:.1f}%), skipping")
                        _log_signal_rejection(
                            symbol, "stop_too_wide", f"Risk {risk_pct:.1f}% > {max_risk_pct:.1f}%", run_date, entry_price, risk_pct
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
                logger.info(f"[PHASE 8] {symbol}: sizer blocked - insufficient shares ({sizing['shares']})")

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

            composite_score = signal.get("composite_score")
            rs_pct = signal.get("rs_percentile")

            # DEBUG: Log all available keys in signal dict
            logger.debug(f"[PHASE 8] {symbol}: Available signal keys: {list(signal.keys())}")

            if composite_score is None:
                raise RuntimeError(
                    f"[PHASE 8] Signal for {symbol} missing required 'composite_score' field - "
                    f"cannot execute trade without signal quality validation."
                )
            if rs_pct is None:
                raise RuntimeError(
                    f"[PHASE 8] Signal for {symbol} missing required 'rs_percentile' field - "
                    f"cannot execute trade without relative strength validation."
                )

            # SESSION 367 FIX: Fetch signal quality scores (SQS & trend score) from signal_quality_scores table
            # These are computed by Phase 7's signal quality scorer and used for position validation
            sqs = signal.get("signal_quality_score")
            # CRITICAL FIX (Session 379): If signal_quality_score is not present, try composite_score as fallback
            # Phase 7 sets both fields, but composite_score might be more reliably populated
            if sqs is None:
                sqs = signal.get("composite_score")

            trend_score = signal.get("trend_template_score")

            # If not in signal dict, fetch from database (fallback for earlier Signal 7 runs)
            if sqs is None or trend_score is None:
                try:
                    with DatabaseContext("read") as cur_sqs:
                        cur_sqs.execute(
                            """
                            SELECT composite_sqs, trend_template_score
                            FROM signal_quality_scores
                            WHERE symbol = %s AND date = %s
                            LIMIT 1
                            """,
                            (symbol, run_date),
                        )
                        sqs_row = cur_sqs.fetchone()
                        if sqs_row:
                            sqs = sqs_row[0] if sqs is None else sqs
                            trend_score = sqs_row[1] if trend_score is None else trend_score
                except Exception as e:
                    logger.warning(f"[PHASE 8] {symbol}: Could not fetch signal quality scores: {e}. Proceeding with available data.")

            # CRITICAL GATE: Enforce min_signal_quality_score threshold for entry validation
            # CRITICAL FIX (Session 372): Reject NULL signal quality scores
            # - NULL means signal quality was never computed (upstream data incomplete)
            # - Accepting NULL bypasses the entire quality gate, causing losses
            # - Require explicit quality score for all entries (fail-closed principle)
            min_sqs = config.get("min_signal_quality_score", 60)
            if sqs is None:
                rejection_reason = f"Signal quality score unavailable (NULL) - cannot trade without quality validation"
                logger.info(f"[PHASE 8] {symbol}: REJECTED - {rejection_reason}")
                _log_signal_rejection(symbol, "quality_gate_null", rejection_reason, run_date, entry_price, risk_pct)
                skipped_count += 1
                continue
            if sqs < min_sqs:
                rejection_reason = f"Signal quality score {int(sqs)} below minimum {min_sqs}"
                logger.info(f"[PHASE 8] {symbol}: REJECTED - {rejection_reason}")
                _log_signal_rejection(symbol, "quality_gate", rejection_reason, run_date, entry_price, risk_pct)
                skipped_count += 1
                continue

            logger.info(
                f"[PHASE 8] {symbol}: BUY entry=${entry_price:.2f} stop=${stop_loss:.2f} "
                f"risk={risk_pct:.1f}% shares={shares} value=${position_value:,.0f} "
                f"composite={composite_score} rs_pct={rs_pct} sqs={sqs} trend={trend_score}"
            )

            # DEBUG: Verify what's actually in the signal dict
            logger.debug(
                f"[PHASE 8 DEBUG] {symbol}: sqs type={type(sqs).__name__}, value={sqs}. "
                f"Available signal keys: {list(signal.keys())}"
            )

            if not dry_run:
                try:
                    # REQUIRED: symbol, entry_price, shares, stop_loss_price, signal_date, entry_date
                    # OPTIONAL: sector, industry (enrichment data, may be None if data unavailable)
                    # SESSION 367 FIX: Pass signal quality scores for trade entry validation
                    # CRITICAL FIX: Ensure sqs is passed to trade executor to be stored in database
                    # Phase 7 computes signal_quality_score and passes it via qualified_trades
                    # Phase 8 must extract and pass it through to TradeContext
                    # Session 379 fix: Verified sqs value before passing
                    result = trade_executor.execute_trade(
                        symbol=symbol,
                        entry_price=entry_price,
                        shares=shares,
                        stop_loss_price=stop_loss,
                        signal_date=run_date,
                        entry_date=run_date,
                        composite_score=composite_score,
                        sector=signal.get("sector"),
                        industry=signal.get("industry"),
                        rs_percentile=signal.get("rs_percentile"),
                        sqs=sqs,
                        trend_score=trend_score,
                    )
                    logger.debug(f"[PHASE 8] {symbol}: Executed trade with sqs={sqs}, trend_score={trend_score}")

                    if "success" not in result or result["success"] is None:
                        raise RuntimeError(
                            f"Trade executor returned invalid result for {symbol}: missing 'success' field. "
                            f"Response: {result}"
                        )

                    if result["success"]:
                        if "trade_id" not in result:
                            raise RuntimeError(
                                f"Trade succeeded for {symbol} but missing 'trade_id' field. Response: {result}"
                            )

                        executed_count += 1
                        entered_symbols.append(symbol)
                        entered_prices.append(entry_price)

                        logger.info(
                            f"[PHASE 8] {symbol}: ENTERED trade_id={result['trade_id']} alpaca_order_id={result.get('alpaca_order_id')} status={result.get('status')}"
                        )

                        if max_entries and executed_count >= max_entries:
                            logger.info(f"[PHASE 8] Reached max_new_positions_today={max_entries}, stopping")

                            break

                    else:
                        message = result.get("message", "unknown error")
                        status = result.get("status", "unknown")
                        logger.error(f"[PHASE 8] {symbol}: FAILED to execute trade: {message} (status={status})")

                        failed_count += 1

                except (ValueError, ZeroDivisionError, TypeError) as exec_err:
                    logger.error(
                        f"[PHASE 8] {symbol}: execution error: {exec_err}",
                        exc_info=True,
                    )

                    failed_count += 1

            else:
                logger.info(f"[PHASE 8] DRY-RUN: Would execute {symbol} ({shares} shares @ ${entry_price:.2f})")

                executed_count += 1
                entered_symbols.append(symbol)
                entered_prices.append(entry_price)

                if max_entries and executed_count >= max_entries:
                    logger.info(f"[PHASE 8] Reached max_new_positions_today={max_entries}, stopping")

                    break

        except (RuntimeError, ValueError, TypeError, AttributeError) as e:
            logger.error(
                f"[PHASE 8] Error processing {signal.get('symbol', '?')}: {e}",
                exc_info=True,
            )

            failed_count += 1

    elapsed = time.time() - phase_start

    logger.info(
        f"[PHASE 8] Done in {elapsed:.1f}s: {executed_count} executed, {skipped_count} skipped, {failed_count} failed"
    )

    # Calculate execution rejection rate for observability
    total_evaluated = executed_count + skipped_count + failed_count
    execution_rejection_rate = round((skipped_count / total_evaluated * 100) if total_evaluated > 0 else 0, 1)
    if execution_rejection_rate > 20:
        logger.warning(
            f"[PHASE 8] High execution rejection rate: {execution_rejection_rate}% "
            f"({skipped_count}/{total_evaluated} signals rejected)"
        )

    log_phase_result_fn(8, "entry_execution", "success", f"{executed_count} trades executed")

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
        "ok",
        result_data,
        False,
        f"Executed {executed_count} trades (rejection rate: {execution_rejection_rate}%)",
    )
