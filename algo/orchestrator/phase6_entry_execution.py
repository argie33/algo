#!/usr/bin/env python3

"""

PHASE 6: ENTRY EXECUTION



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

"""

import logging
import os
import time
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from algo.trading import PositionSizer, PreTradeChecks, TradeExecutor
from utils.db.context import DatabaseContext


logger = logging.getLogger(__name__)


def _batch_fetch_technical_data(
    symbols_with_precomputed: dict[str, dict], run_date: _date, period: int = 14
) -> dict[str, dict]:
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

        return precomputed_by_symbol

    # Fetch missing data only for symbols that lack precomputed values

    placeholders = ",".join(["%s"] * len(symbols_needing_fetch))

    result = precomputed_by_symbol.copy()

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                f"""

                WITH latest_prices AS (

                    SELECT DISTINCT ON (symbol) symbol, close

                    FROM price_daily

                    WHERE symbol IN ({placeholders}) AND date <= %s

                    ORDER BY symbol, date DESC

                ),

                sma_50_data AS (

                    SELECT symbol, AVG(close) AS sma_50

                    FROM (

                        SELECT symbol, close,

                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn

                        FROM price_daily

                        WHERE symbol IN ({placeholders}) AND date <= %s

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

                        WHERE symbol IN ({placeholders}) AND date <= %s

                    ) t

                    WHERE tr IS NOT NULL AND rn <= %s

                    GROUP BY symbol

                )

                SELECT

                    lp.symbol,

                    COALESCE(atr.atr, 0.0) AS atr,

                    COALESCE(sma.sma_50, 0.0) AS sma_50,

                    lp.close

                FROM latest_prices lp

                LEFT JOIN sma_50_data sma ON sma.symbol = lp.symbol

                LEFT JOIN atr_data atr ON atr.symbol = lp.symbol

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

                result[symbol] = {
                    "atr": float(atr) if atr else None,
                    "sma_50": float(sma_50) if sma_50 else None,
                    "close": float(close) if close else None,
                }

            return result

    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(f"Batch fetch technical data failed: {e}") from e


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    qualified_trades: list[dict[str, Any]] | None = None,
    exposure_constraints: dict | None = None,
    check_halt_flag: Callable | None = None,
) -> PhaseResult:

    phase_start = time.time()

    logger.info("[PHASE 6] Starting entry execution")

    if not qualified_trades:
        logger.info("[PHASE 6] No qualified trades from Phase 5")

        log_phase_result_fn(6, "entry_execution", "success", "No qualified signals")

        return PhaseResult(6, "entry_execution", "ok", {"entered": 0}, False, "No signals to execute")

    # Halt flag check before any trades

    if check_halt_flag and check_halt_flag():
        logger.warning("[PHASE 6] Halt flag set — skipping all entries")

        log_phase_result_fn(6, "entry_execution", "halt", "Halt flag active")

        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, "Halt flag active")

    # CRITICAL: Verify data freshness before executing trades

    # Trades should only execute on current market data (same day or previous trading day)

    try:
        with DatabaseContext("read") as cur:
            cur.execute("""SELECT MAX(date) as latest_price_date FROM price_daily""")

            result = cur.fetchone()

            latest_price_date = result[0] if result else None

            if latest_price_date is None or latest_price_date != run_date:
                msg = (
                    f"[PHASE 6 CRITICAL] Price data is stale (latest: {latest_price_date}, run_date: {run_date}). "
                    f"Cannot execute trades without current price data. "
                    f"Phase 1 (Data Freshness) should have caught this. Verify loader pipeline."
                )

                logger.critical(msg)

                log_phase_result_fn(6, "entry_execution", "halt", msg)

                return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, msg)

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[PHASE 6 CRITICAL] Data freshness check failed: {e}"

        logger.critical(msg)

        log_phase_result_fn(6, "entry_execution", "halt", msg)

        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, msg)

    # Exposure policy validation (fail-closed if constraints invalid)

    # CRITICAL: exposure_constraints MUST be provided by Phase 3b and have valid fields

    if exposure_constraints is None:
        msg = (
            "[PHASE 6 CRITICAL] exposure_constraints not provided by Phase 3b. "
            "Cannot execute entries without market exposure limits. "
            "Verify Phase 3b (Exposure Policy) completed successfully."
        )

        logger.critical(msg)

        log_phase_result_fn(6, "entry_execution", "halt", msg)

        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, msg)

    # Validate that exposure_constraints has required fields

    required_fields = ["tier_name", "risk_multiplier", "max_new_positions_today"]

    missing_fields = [f for f in required_fields if f not in exposure_constraints]

    if missing_fields:
        msg = (
            f"[PHASE 6 CRITICAL] exposure_constraints missing required fields: {missing_fields}. "
            "Cannot size positions without complete constraints."
        )

        logger.critical(msg)

        log_phase_result_fn(6, "entry_execution", "halt", msg)

        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, msg)

    # Check for halt flag set by exposure policy

    if exposure_constraints.get("halt_new_entries"):
        reason = exposure_constraints.get("halt_reason", "Exposure policy halted new entries")

        logger.warning(f"[PHASE 6] {reason}")

        log_phase_result_fn(6, "entry_execution", "halt", reason)

        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, reason)

    max_entries = exposure_constraints.get("max_new_positions_today") if exposure_constraints else None

    logger.info(
        f"[PHASE 6] Processing {len(qualified_trades)} qualified signals"
        + (f" (cap: {max_entries}/day)" if max_entries else "")
    )

    trade_executor = TradeExecutor(config=config)

    # Wire tier's max_concentration_pct into sizer so correction/caution limits are respected.

    # Each ExposurePolicy tier defines its own concentration ceiling (20%/16%/12%/10%).

    tier_max_conc = exposure_constraints.get("max_concentration_pct") if exposure_constraints else None

    # Convert AlgoConfig to dict using to_dict() method, or use empty dict if config is None

    sizer_config = config.to_dict() if config and hasattr(config, "to_dict") else {}

    if tier_max_conc is not None:
        sizer_config["max_concentration_pct"] = tier_max_conc

        logger.info(f"[PHASE 6] Position sizer: max_concentration_pct={tier_max_conc:.0f}% (from tier)")

    sizer = PositionSizer(config=sizer_config)

    liquidity = LiquidityChecks(config=config)

    # Fetch portfolio value once — avoids one Alpaca API call per symbol

    # CRITICAL: Must succeed. No fallback to default values.

    try:
        portfolio_value = sizer.get_portfolio_value()

        logger.info(f"[PHASE 6] Portfolio value: ${portfolio_value:,.0f}")

    except RuntimeError as e:
        # Portfolio value unavailable — fail-closed, halt all entries

        error_msg = f"[PHASE 6 HALT] Cannot determine portfolio value: {e}"

        logger.critical(error_msg)

        log_phase_result_fn(6, "entry_execution", "halt", error_msg)

        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, error_msg)

    try:
        from config.credential_manager import get_credential_manager

        creds = get_credential_manager().get_alpaca_credentials()

        alpaca_key = creds.get("key")

        alpaca_secret = creds.get("secret")

    except (RuntimeError, ValueError, KeyError) as e:
        logger.warning(f"Could not fetch Alpaca credentials: {e}")

        alpaca_key = None

        alpaca_secret = None

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

    symbols_with_precomputed = {}

    for sig in qualified_trades:
        symbol = sig.get("symbol")

        if symbol:
            symbols_with_precomputed[symbol] = {
                "sma_50": sig.get("sma_50"),
                "atr_14": sig.get("atr_14"),
                "close": sig.get("close"),
            }

    technical_data = _batch_fetch_technical_data(symbols_with_precomputed, run_date)

    precomputed_count = sum(
        1
        for sym, data in symbols_with_precomputed.items()
        if data.get("sma_50") is not None and data.get("atr_14") is not None and data.get("close") is not None
    )

    logger.info(
        f"[PHASE 6] Technical data: {precomputed_count}/{len(symbols_with_precomputed)} symbols reused from Phase 5. "
        f"ISSUE #8 FIX: Eliminated {precomputed_count} redundant SMA_50/ATR calculations."
    )

    for signal in qualified_trades:
        try:
            symbol = signal.get("symbol")

            if not symbol:
                raise RuntimeError(
                    "[PHASE 6] Signal missing symbol. "
                    "Cannot execute trade without stock symbol. "
                    "Verify signal_generation phase produced valid signals."
                )

            # Re-check halt flag each iteration — this loop can run for minutes

            if check_halt_flag and check_halt_flag():
                logger.warning(f"[PHASE 6] Halt flag set mid-loop at {symbol}, stopping")

                break

            # Liquidity: ADV, dollar volume, price history age

            entry_price_hint = signal.get("entry_price")

            liq_ok, liq_reason = liquidity.run_all(
                str(symbol),
                float(entry_price_hint) if entry_price_hint else 0.0,
                run_date,
            )

            if not liq_ok:
                logger.debug(f"[PHASE 6] {symbol}: liquidity — {liq_reason}")

                skipped_count += 1

                continue

            # Fetch pre-computed price inputs from batch cache

            tech_data = technical_data.get(str(symbol), {})

            atr = tech_data.get("atr")

            sma_50 = tech_data.get("sma_50")

            close = tech_data.get("close")

            if not all([atr, sma_50, close]):
                raise RuntimeError(
                    f"[PHASE 6] {symbol}: missing technical data. "
                    f"ATR={atr}, SMA_50={sma_50}, close={close}. "
                    f"Cannot compute stop loss or position size without complete technical indicators. "
                    f"Verify technical_data_daily loader completed successfully."
                )

            entry_price = float(close)  # type: ignore[arg-type]

            atr = float(atr)  # type: ignore[arg-type]

            sma_50 = float(sma_50)  # type: ignore[arg-type]

            # Stop loss: min() picks the LOWER (wider) stop, giving the trade more room.

            # SMA_50 - ATR = below moving-average support.

            # entry - 2*ATR = volatility-based floor.

            stop_loss = min(
                sma_50 - atr,
                entry_price - 2.0 * atr,
            )

            risk_pct = (entry_price - stop_loss) / entry_price * 100

            if risk_pct < 1.5:
                logger.info(f"[PHASE 6] {symbol}: stop too tight ({risk_pct:.1f}%), skipping")

                skipped_count += 1

                continue

            if risk_pct > 12.0:
                logger.info(f"[PHASE 6] {symbol}: stop too wide ({risk_pct:.1f}%), skipping")

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

            if sizing.get("status") != "ok" or sizing.get("shares", 0) < 1:
                logger.info(f"[PHASE 6] {symbol}: sizer blocked — {sizing.get('reason', 'unknown')}")

                skipped_count += 1

                continue

            shares = sizing["shares"]

            position_value = shares * entry_price

            # Final hard-stop validation (includes earnings blackout check)

            try:
                pt_ok, pt_reason = pretrade.run_all(symbol, position_value, float(portfolio_value), eval_date=run_date)

            except ValueError as e:
                raise RuntimeError(
                    f"[PHASE 6] {symbol}: pre-trade validation critical failure: {e}. "
                    f"System cannot proceed with entry execution if pre-trade checks fail."
                ) from e

            if not pt_ok:
                logger.info(f"[PHASE 6] {symbol}: pre-trade check — {pt_reason}")

                skipped_count += 1

                continue

            logger.info(
                f"[PHASE 6] {symbol}: BUY entry=${entry_price:.2f} stop=${stop_loss:.2f} "
                f"risk={risk_pct:.1f}% shares={shares} value=${position_value:,.0f} "
                f"composite={signal.get('composite_score', '?')} "
                f"rs_pct={signal.get('rs_percentile', '?')}"
            )

            if not dry_run:
                try:
                    result = trade_executor.execute_trade(
                        symbol=symbol,
                        entry_price=entry_price,
                        shares=float(shares),
                        stop_loss_price=stop_loss,
                        signal_date=run_date,
                        entry_date=run_date,
                        sector=signal.get("sector"),
                        industry=signal.get("industry"),
                        rs_percentile=signal.get("rs_percentile"),
                    )

                    if result.get("success"):
                        executed_count += 1

                        logger.info(
                            f"[PHASE 6] {symbol}: ENTERED trade_id={result.get('trade_id')} alpaca_order_id={result.get('alpaca_order_id')} status={result.get('status')}"
                        )

                        if max_entries and executed_count >= max_entries:
                            logger.info(f"[PHASE 6] Reached max_new_positions_today={max_entries}, stopping")

                            break

                    else:
                        logger.error(
                            f"[PHASE 6] {symbol}: FAILED to execute trade: {result.get('message')} (status={result.get('status')})"
                        )

                        failed_count += 1

                except (ValueError, ZeroDivisionError, TypeError) as exec_err:
                    logger.error(
                        f"[PHASE 6] {symbol}: execution error: {exec_err}",
                        exc_info=True,
                    )

                    failed_count += 1

            else:
                logger.info(f"[PHASE 6] DRY-RUN: Would execute {symbol} ({shares} shares @ ${entry_price:.2f})")

                executed_count += 1

                if max_entries and executed_count >= max_entries:
                    logger.info(f"[PHASE 6] Reached max_new_positions_today={max_entries}, stopping")

                    break

        except (RuntimeError, ValueError, TypeError, AttributeError) as e:
            logger.error(
                f"[PHASE 6] Error processing {signal.get('symbol', '?')}: {e}",
                exc_info=True,
            )

            failed_count += 1

    elapsed = time.time() - phase_start

    logger.info(
        f"[PHASE 6] Done in {elapsed:.1f}s: {executed_count} executed, {skipped_count} skipped, {failed_count} failed"
    )

    log_phase_result_fn(6, "entry_execution", "success", f"{executed_count} trades executed")

    return PhaseResult(
        6,
        "entry_execution",
        "ok",
        {"entered": executed_count, "skipped": skipped_count, "failed": failed_count},
        False,
        f"Executed {executed_count} trades",
    )
