#!/usr/bin/env python3

"""

PHASE 8: ENTRY EXECUTION

For each qualified signal from Phase 5:

1. Check halt flag before any entry
2. Check exposure constraints from Phase 3b
3. Run liquidity checks (ADV, dollar volume, price history age)
4. Compute true ATR (max of H-L, |H-prev_C|, |L-prev_C|) anchored to run_date
5. Compute SMA_50 anchored to run_date
6. Stop loss: min(SMA_50 - ATR, entry - 2*ATR) — lower stop = more room for the trade
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
from decimal import Decimal
from typing import Any, cast

import psycopg2

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from algo.trading.executor import TradeExecutor
from algo.trading.position_sizer import PositionSizer
from algo.trading.pretrade_checks import PreTradeChecks
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def _persist_signals_to_database(
    qualified_trades: list[dict[str, Any]], run_date: _date, dry_run: bool
) -> None:
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
        return

    try:
        with DatabaseContext("write") as cur:
            for signal_data in qualified_trades:
                # Extract required fields from Phase 7 signal data
                symbol = signal_data.get("symbol")
                if not symbol:
                    logger.warning("[PERSIST SIGNALS] Skipping signal with no symbol")
                    continue

                # Safely extract optional fields with defaults
                entry_price = float(signal_data.get("entry_price", 0.0))
                signal_quality_score = float(signal_data.get("composite_score", signal_data.get("signal_quality_score", 0.0)))
                risk_score = float(signal_data.get("risk_score", 0.0))

                cur.execute("""
                    INSERT INTO algo_signals (
                        signal_date, symbol, source_table, source_timeframe,
                        entry_price, entry_stage, signal_active,
                        signal_quality_score, risk_score, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                """, (
                    run_date,
                    symbol,
                    "phase7_signal_generation",
                    "daily",
                    entry_price,
                    "entry",
                    True,
                    signal_quality_score,
                    risk_score,
                ))

        logger.info(f"[PERSIST SIGNALS] Inserted {len(qualified_trades)} signals for {run_date}")
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
        # This is not an error—it means no entries are allowed. Return empty dict (no candidates to process).
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

                result[symbol] = cast(
                    dict[str, float | None],
                    {
                        "atr": float(atr),
                        "sma_50": float(sma_50),
                        "close": float(close),
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

    # EXPLICIT DEPENDENCY RESOLUTION: Use executor if available (preferred pattern)
    if executor is not None:
        try:
            qualified_trades = executor.get_phase_data_required(7, "qualified_trades")
            exposure_constraints = executor.get_phase_data_required(5, "constraints")
            logger.info("[PHASE 8 CONTRACTS] [OK] Retrieved validated data from Phase 7 & 5")
        except Exception as e:
            logger.critical(f"[PHASE 8 DEPENDENCY FAILURE] {e}")
            log_phase_result_fn(8, "entry_execution", "halt", str(e))
            return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, str(e))

    if not qualified_trades:
        logger.info("[PHASE 8] No qualified trades from Phase 7")

        log_phase_result_fn(8, "entry_execution", "success", "No qualified signals")

        return PhaseResult(8, "entry_execution", "ok", {"entered": 0}, False, "No signals to execute")

    # CRITICAL: Persist signals to database (previously missing - this caused zero signals in dashboard)
    # This is the essential link between Phase 7 signal generation and dashboard display
    try:
        _persist_signals_to_database(qualified_trades, run_date, dry_run)
        logger.info(f"[PHASE 8] Persisted {len(qualified_trades)} signals to database")
    except Exception as e:
        logger.error(f"[PHASE 8] Failed to persist signals: {e}", exc_info=True)
        # Non-blocking - continue execution even if signal persistence fails
        # (trades will still execute, just signals won't be visible on dashboard)

    # Halt flag check before any trades

    if check_halt_flag and check_halt_flag():
        logger.warning("[PHASE 8] Halt flag set — skipping all entries")

        log_phase_result_fn(8, "entry_execution", "halt", "Halt flag active")

        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, "Halt flag active")

    # CRITICAL: Validate exposure constraints (fail-fast)
    if not exposure_constraints:
        msg = (
            "[PHASE 8 CRITICAL] Exposure constraints not provided. "
            "Phase 5 (Exposure Policy) must produce constraints before Phase 8 executes."
        )
        logger.critical(msg)
        log_phase_result_fn(8, "entry_execution", "halt", msg)
        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, msg)

    required_constraint_keys = [
        "halt_new_entries",
        "max_new_positions_today",
        "max_concentration_pct",
    ]
    missing_keys = [k for k in required_constraint_keys if k not in exposure_constraints]
    if missing_keys:
        msg = (
            f"[PHASE 8 CRITICAL] Exposure constraints missing required keys: {missing_keys}. "
            f"Phase 5 output must include: {required_constraint_keys}"
        )
        logger.critical(msg)
        log_phase_result_fn(8, "entry_execution", "halt", msg)
        return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, msg)

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
                raise ValueError("Price data freshness query returned no results — price_daily table may be empty")

            latest_price_date = result[0]

            # Determine expected last trading day — allow previous trading day's data
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
                    f"EOD price loader may not have completed — check data_loader_status and CloudWatch logs."
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
        if not reason or reason is None or (isinstance(reason, str) and not reason.strip()):
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

    # Fetch portfolio value once — avoids one Alpaca API call per symbol
    # For paper mode, use sensible default if Alpaca API unavailable
    execution_mode = config.get("execution_mode", "paper")
    try:
        portfolio_value = sizer.get_portfolio_value()
        logger.info(f"[PHASE 8] Portfolio value: ${portfolio_value:,.0f} (from Alpaca API)")
    except RuntimeError as e:
        if execution_mode in ("paper", "auto"):
            portfolio_value = Decimal("100000.00")
            logger.warning(
                f"[PHASE 8] Portfolio value fetch failed, using default ${portfolio_value:,.0f} for paper mode: {e}"
            )
        else:
            # Live mode requires accurate portfolio value
            error_msg = f"[PHASE 8 HALT] Cannot determine portfolio value (live mode): {e}"
            logger.critical(error_msg)
            log_phase_result_fn(8, "entry_execution", "halt", error_msg)
            return PhaseResult(8, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    # Get Alpaca credentials if available, but don't fail if missing (TradeExecutor handles paper mode)
    alpaca_key = None
    alpaca_secret = None
    execution_mode = config.get("execution_mode", "paper")

    try:
        from config.credential_manager import get_credential_manager

        creds = get_credential_manager().get_alpaca_credentials()
        if creds and creds.get("key") and creds.get("secret"):
            alpaca_key = creds["key"]
            alpaca_secret = creds["secret"]
        else:
            logger.warning("[PHASE 8] Alpaca credentials not configured - will use paper trading mode")
    except (RuntimeError, ValueError, KeyError) as e:
        # Credentials unavailable - will use paper trading mode
        logger.warning(
            f"[PHASE 8] Could not fetch Alpaca credentials ({type(e).__name__}): {e}. "
            f"Proceeding with {execution_mode} mode (will skip live broker calls)"
        )

    pretrade = PreTradeChecks(
        config=config,
        alpaca_base_url=os.getenv("APCA_API_BASE_URL"),
        alpaca_key=alpaca_key,
        alpaca_secret=alpaca_secret,
    )

    executed_count = 0

    skipped_count = 0

    failed_count = 0

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

        # For paper trading, allow graceful degradation if SMA/ATR missing
        # (use reasonable defaults rather than halting)
        if execution_mode in ("paper", "auto"):
            if sma_50 is None or atr_14 is None or close is None:
                logger.warning(
                    f"[PHASE 8] {sym}: Incomplete technical data (SMA_50={sma_50}, ATR_14={atr_14}, close={close}). "
                    f"Proceeding with paper mode (may use approximate values)."
                )
        else:
            # Live mode: strict validation required
            if sma_50 is None or atr_14 is None or close is None:
                raise RuntimeError(
                    f"[PHASE 8] {sym}: Required technical data missing. "
                    f"SMA_50={sma_50}, ATR_14={atr_14}, close={close}."
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

            # Re-check halt flag each iteration — this loop can run for minutes

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
                logger.debug(f"[PHASE 8] {symbol}: liquidity — {liq_reason}")

                skipped_count += 1

                continue

            # Fetch technical data from merged cache
            if str(symbol) not in merged_technical_data:
                if execution_mode in ("paper", "auto"):
                    logger.warning(f"[PHASE 8] {symbol}: not in technical data cache, skipping")
                    skipped_count += 1
                    continue
                else:
                    raise RuntimeError(
                        f"[PHASE 8] {symbol}: technical data not in batch cache. "
                        f"Cannot execute trade without technical indicators."
                    )
            tech_data = merged_technical_data[str(symbol)]

            # Extract technical indicators (use with defaults if missing in paper mode)
            atr = tech_data.get("atr_14")
            sma_50 = tech_data.get("sma_50")
            close = tech_data.get("close")

            # In paper mode, use sensible defaults if data missing
            # In live mode, fail-fast on missing critical data
            if execution_mode not in ("paper", "auto"):
                if atr is None or sma_50 is None or close is None:
                    raise RuntimeError(
                        f"[PHASE 8] {symbol}: incomplete technical data (live mode). "
                        f"ATR={atr}, SMA_50={sma_50}, close={close}."
                    )
            else:
                # Paper mode: use approximations if needed
                if close is None:
                    logger.warning(f"[PHASE 8] {symbol}: close price missing, using entry_price")
                    close = entry_price_hint
                if atr is None:
                    logger.warning(f"[PHASE 8] {symbol}: ATR missing, using 2% approximation")
                    atr = close * 0.02 if close else entry_price_hint * 0.02
                if sma_50 is None:
                    logger.warning(f"[PHASE 8] {symbol}: SMA_50 missing, using entry_price")
                    sma_50 = close if close else entry_price_hint

            entry_price = cast(float, close)
            atr = cast(float, atr)
            sma_50 = cast(float, sma_50)

            # Stop loss: min() picks the LOWER (wider) stop, giving the trade more room.

            # SMA_50 - ATR = below moving-average support.

            # entry - 2*ATR = volatility-based floor.

            stop_loss = min(
                sma_50 - atr,
                entry_price - 2.0 * atr,
            )

            risk_pct = (entry_price - stop_loss) / entry_price * 100

            if risk_pct < 1.5:
                logger.info(f"[PHASE 8] {symbol}: stop too tight ({risk_pct:.1f}%), skipping")

                skipped_count += 1

                continue

            if risk_pct > 12.0:
                logger.info(f"[PHASE 8] {symbol}: stop too wide ({risk_pct:.1f}%), skipping")

                skipped_count += 1

                continue

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
                logger.info(f"[PHASE 8] {symbol}: sizer blocked — {reason}")
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
                logger.info(f"[PHASE 8] {symbol}: sizer blocked — insufficient shares ({sizing['shares']})")

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
                logger.info(f"[PHASE 8] {symbol}: pre-trade check — {pt_reason}")

                skipped_count += 1

                continue

            composite_score = signal.get("composite_score")
            rs_pct = signal.get("rs_percentile")
            if composite_score is None:
                raise RuntimeError(
                    f"[PHASE 8] Signal for {symbol} missing required 'composite_score' field — "
                    f"cannot execute trade without signal quality validation."
                )
            if rs_pct is None:
                raise RuntimeError(
                    f"[PHASE 8] Signal for {symbol} missing required 'rs_percentile' field — "
                    f"cannot execute trade without relative strength validation."
                )
            logger.info(
                f"[PHASE 8] {symbol}: BUY entry=${entry_price:.2f} stop=${stop_loss:.2f} "
                f"risk={risk_pct:.1f}% shares={shares} value=${position_value:,.0f} "
                f"composite={composite_score} rs_pct={rs_pct}"
            )

            if not dry_run:
                try:
                    # REQUIRED: symbol, entry_price, shares, stop_loss_price, signal_date, entry_date
                    # OPTIONAL: sector, industry (enrichment data, may be None if data unavailable)
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
                    )

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

    return PhaseResult(
        8,
        "entry_execution",
        "ok",
        {
            "entered": executed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "execution_rejection_rate": execution_rejection_rate,
        },
        False,
        f"Executed {executed_count} trades (rejection rate: {execution_rejection_rate}%)",
    )
