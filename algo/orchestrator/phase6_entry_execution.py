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
from datetime import date as _date
from typing import Any, Callable, Dict, List, Optional

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from algo.trading import PositionSizer, PreTradeChecks, TradeExecutor
from utils.db.context import DatabaseContext


logger = logging.getLogger(__name__)


def _compute_true_atr(
    symbol: str, run_date: _date, period: int = 14
) -> Optional[float]:
    """True ATR: GREATEST(H-L, |H-prev_C|, |L-prev_C|) averaged over `period` days.

    Fetches period+1 rows so the oldest row has a valid LAG(close). Anchored
    to run_date to avoid look-ahead contamination in historical replays.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT AVG(tr) AS atr
                FROM (
                    SELECT
                        GREATEST(
                            high - low,
                            ABS(high - LAG(close) OVER (ORDER BY date)),
                            ABS(low  - LAG(close) OVER (ORDER BY date))
                        ) AS tr,
                        ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC
                    LIMIT %s
                ) tr_data
                WHERE tr IS NOT NULL AND rn <= %s
            """,
                (symbol, run_date, period + 1, period),
            )
            row = cur.fetchone()
            return float(row[0]) if row is not None and row[0] is not None else None
    except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


def _compute_sma_50(symbol: str, run_date: _date) -> Optional[float]:
    """50-day SMA anchored to run_date."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT AVG(close) FROM (
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT 50
                ) recent
            """,
                (symbol, run_date),
            )
            row = cur.fetchone()
            return float(row[0]) if row is not None and row[0] is not None else None
    except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


def _get_latest_close(symbol: str, run_date: _date) -> Optional[float]:
    """Latest close price at or before run_date."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
                (symbol, run_date),
            )
            row = cur.fetchone()
            return float(row[0]) if row is not None and row[0] is not None else None
    except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    qualified_trades: Optional[List[Dict[str, Any]]] = None,
    exposure_constraints: Optional[Dict] = None,
    check_halt_flag: Optional[Callable] = None,
) -> PhaseResult:
    phase_start = time.time()
    logger.info("[PHASE 6] Starting entry execution")

    if not qualified_trades:
        logger.info("[PHASE 6] No qualified trades from Phase 5")
        log_phase_result_fn(6, "entry_execution", "success", "No qualified signals")
        return PhaseResult(
            6, "entry_execution", "ok", {"entered": 0}, False, "No signals to execute"
        )

    # Halt flag check before any trades
    if check_halt_flag and check_halt_flag():
        logger.warning("[PHASE 6] Halt flag set — skipping all entries")
        log_phase_result_fn(6, "entry_execution", "halt", "Halt flag active")
        return PhaseResult(
            6, "entry_execution", "halted", {"entered": 0}, True, "Halt flag active"
        )

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
        reason = exposure_constraints.get(
            "halt_reason", "Exposure policy halted new entries"
        )
        logger.warning(f"[PHASE 6] {reason}")
        log_phase_result_fn(6, "entry_execution", "halt", reason)
        return PhaseResult(6, "entry_execution", "halted", {"entered": 0}, True, reason)

    max_entries = (
        exposure_constraints.get("max_new_positions_today")
        if exposure_constraints
        else None
    )
    logger.info(
        f"[PHASE 6] Processing {len(qualified_trades)} qualified signals"
        + (f" (cap: {max_entries}/day)" if max_entries else "")
    )

    trade_executor = TradeExecutor(config=config)

    # Wire tier's max_concentration_pct into sizer so correction/caution limits are respected.
    # Each ExposurePolicy tier defines its own concentration ceiling (20%/16%/12%/10%).
    tier_max_conc = (
        exposure_constraints.get("max_concentration_pct")
        if exposure_constraints
        else None
    )
    # Convert AlgoConfig to dict using to_dict() method, or use empty dict if config is None
    sizer_config = config.to_dict() if config and hasattr(config, "to_dict") else {}
    if tier_max_conc is not None:
        sizer_config["max_concentration_pct"] = tier_max_conc
        logger.info(
            f"[PHASE 6] Position sizer: max_concentration_pct={tier_max_conc:.0f}% (from tier)"
        )

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
        return PhaseResult(
            6, "entry_execution", "halted", {"entered": 0}, True, error_msg
        )

    try:
        from config.credential_manager import get_credential_manager

        creds = get_credential_manager().get_alpaca_credentials()
        alpaca_key = creds.get("key")
        alpaca_secret = creds.get("secret")
    except Exception:
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
                logger.warning(
                    f"[PHASE 6] Halt flag set mid-loop at {symbol}, stopping"
                )
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

            # Compute price inputs anchored to run_date
            atr = _compute_true_atr(str(symbol), run_date)
            sma_50 = _compute_sma_50(str(symbol), run_date)
            # CRITICAL: Always use latest market close, not signal's stale entry_price
            # Signal entry_price may be from old price_date if Phase 5 fell back to prior date
            close = _get_latest_close(str(symbol), run_date)

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
                logger.info(
                    f"[PHASE 6] {symbol}: stop too tight ({risk_pct:.1f}%), skipping"
                )
                skipped_count += 1
                continue
            if risk_pct > 12.0:
                logger.info(
                    f"[PHASE 6] {symbol}: stop too wide ({risk_pct:.1f}%), skipping"
                )
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
                logger.info(
                    f"[PHASE 6] {symbol}: sizer blocked — {sizing.get('reason', 'unknown')}"
                )
                skipped_count += 1
                continue

            shares = sizing["shares"]
            position_value = shares * entry_price

            # Final hard-stop validation (includes earnings blackout check)
            try:
                pt_ok, pt_reason = pretrade.run_all(
                    symbol, position_value, portfolio_value, eval_date=run_date
                )
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
                            logger.info(
                                f"[PHASE 6] Reached max_new_positions_today={max_entries}, stopping"
                            )
                            break
                    else:
                        logger.error(
                            f"[PHASE 6] {symbol}: FAILED to execute trade: {result.get('message')} (status={result.get('status')})"
                        )
                        failed_count += 1
                except Exception as exec_err:
                    logger.error(
                        f"[PHASE 6] {symbol}: execution error: {exec_err}",
                        exc_info=True,
                    )
                    failed_count += 1
            else:
                logger.info(
                    f"[PHASE 6] DRY-RUN: Would execute {symbol} ({shares} shares @ ${entry_price:.2f})"
                )
                executed_count += 1
                if max_entries and executed_count >= max_entries:
                    logger.info(
                        f"[PHASE 6] Reached max_new_positions_today={max_entries}, stopping"
                    )
                    break

        except Exception as e:
            logger.error(
                f"[PHASE 6] Error processing {signal.get('symbol', '?')}: {e}",
                exc_info=True,
            )
            failed_count += 1

    elapsed = time.time() - phase_start
    logger.info(
        f"[PHASE 6] Done in {elapsed:.1f}s: {executed_count} executed, "
        f"{skipped_count} skipped, {failed_count} failed"
    )
    log_phase_result_fn(
        6, "entry_execution", "success", f"{executed_count} trades executed"
    )

    return PhaseResult(
        6,
        "entry_execution",
        "ok",
        {"entered": executed_count, "skipped": skipped_count, "failed": failed_count},
        False,
        f"Executed {executed_count} trades",
    )
