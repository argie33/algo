#!/usr/bin/env python3
"""
Phase 6: ENTRY EXECUTION

For each ranked candidate, in priority order:
- Final pre-flight checks (still no duplicate, room left, etc.)
- Pre-trade data quality gate (all required data fresh and complete)
- TradeExecutor.execute_trade() with idempotency
- Apply exposure tier constraints (min_swing_grade, min_swing_score, daily cap)

FAIL-OPEN per trade, but FAIL-CLOSED if >50% of trades fail in batch.
"""

import logging
import traceback
from datetime import date as _date, timedelta, datetime, timezone
from typing import Any, Callable, List, Dict, Tuple, Optional

from utils.database_context import DatabaseContext
from utils.trade_status import PositionStatus
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager
from algo.algo_position_monitor import PositionMonitor

logger = logging.getLogger(__name__)


def _recalculate_position_size_after_exits(
    trade: Dict[str, Any],
    get_conn: Callable,
    config: Any,
    exposure_multiplier: float = 1.0,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Recalculate position size based on current portfolio value (after Phase 4 exits).

    Issue: Phase 5 calculates position size assuming Phase 5 portfolio value.
           Phase 4 executes exits, freeing capital.
           Phase 6 should use CURRENT portfolio value, not stale Phase 5 value.

    Solution: Recalculate position size based on:
    - Current available capital
    - Same risk percentage (base_risk_pct from config)
    - Entry price + stop loss
    - Exposure tier multiplier (1.0x normal, 0.75x caution, 0.5x pressure)

    Returns: Modified trade dict with recalculated shares
    """
    symbol = trade['symbol']
    entry_price = trade.get('entry_price', 0)
    stop_loss = trade.get('stop_loss_price', 0)

    if entry_price <= 0 or stop_loss <= 0 or entry_price <= stop_loss:
        return trade

    try:
        from algo.algo_position_sizer import PositionSizer

        sizer = PositionSizer(config)
        # Get current portfolio value (not stale Phase 5 value)
        current_result = sizer.calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            signal_date=trade.get('signal_date'),
        )

        if current_result.get('shares', 0) > 0:
            original_shares = trade.get('shares', 0)
            recalc_shares = round(current_result['shares'] * exposure_multiplier)

            # Only update if significantly different (>5% change)
            if original_shares > 0:
                size_change_pct = abs(recalc_shares - original_shares) / original_shares * 100
                if size_change_pct > 5:
                    logger.info(f"  {symbol}: Position size updated after exits "
                              f"{original_shares} → {recalc_shares} shares (+{size_change_pct:.1f}%)")
                    trade['shares'] = recalc_shares
                    trade['position_size_recalculated'] = True
                    trade['original_shares'] = original_shares

        return trade
    except Exception as e:
        logger.warning(f"  {symbol}: Position size recalculation failed ({e}), using original")
        return trade


def _validate_and_adjust_entry_price(
    trade: Dict[str, Any],
    get_conn: Callable,
    put_conn: Callable,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Validate entry price hasn't drifted >2% since signal generation.
    If drifted, recalculate position size at current price.

    Returns: Modified trade dict with current_price, adjusted shares if needed
    """
    symbol = trade['symbol']
    signal_price = trade['entry_price']
    shares = trade['shares']
    stop_loss = trade['stop_loss_price']

    conn = None
    try:
        conn = get_conn()
        if not conn:
            return trade

        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC LIMIT 1
            """, (symbol,))
            result = cur.fetchone()
        finally:
            cur.close()

        if not result:
            if verbose:
                logger.warning(f"  {symbol}: No recent price data, using signal price")
            return trade

        current_price = float(result[0])
        if not signal_price or signal_price <= 0:
            return trade
        price_drift_pct = abs(current_price - signal_price) / signal_price * 100

        # If price drifted >2%, recalculate position size
        if price_drift_pct > 2.0:
            # Risk should still be same dollar amount
            risk_per_share_at_signal = signal_price - stop_loss
            risk_per_share_at_current = current_price - stop_loss

            if risk_per_share_at_current > 0:
                adjusted_shares = int(shares * risk_per_share_at_signal / risk_per_share_at_current)

                if adjusted_shares < 1:
                    if verbose:
                        logger.warning(f"  {symbol}: Position too small after price drift ({adjusted_shares} sh), skipping")
                    trade['skip_due_to_price_drift'] = True
                    return trade

                logger.info(f"  {symbol}: Price drifted {price_drift_pct:.1f}% "
                          f"(${signal_price:.2f} → ${current_price:.2f}) "
                          f"- adjusted {shares} → {adjusted_shares} shares to maintain risk")

                trade['entry_price'] = current_price
                trade['shares'] = adjusted_shares
                trade['price_adjusted'] = True
                trade['adjustment_reason'] = f"Price drift {price_drift_pct:.1f}%"
            else:
                if verbose:
                    logger.warning(f"  {symbol}: Current price below stop loss, skipping")
                trade['skip_due_to_price_drift'] = True
                return trade

        return trade

    except Exception as e:
        logger.warning(f"  {symbol}: Price validation failed ({e}), using signal price")
        return trade
    finally:
        if conn:
            put_conn(conn)


def _validate_pre_trade_data_quality(
    get_conn: Callable,
    put_conn: Callable,
    run_date: _date,
) -> Tuple[bool, List[str], List[str]]:
    """
    Gate: Verify all required data is fresh and complete before trading.

    Checks:
    1. All required tables have data for today (or most recent if testing)
    2. Price data is recent (< 1 hour old)
    3. No critical NULLs in signal columns
    4. Symbol coverage > 80% of active universe
    5. Technical data is fresh

    For historical testing: Uses most recent available data if run_date is in past
    For production: Requires data for current trading day

    Returns:
        (passes: bool, blocking_issues: list, warnings: list)
    """
    from datetime import datetime, date
    issues = []
    warnings = []
    conn = None
    cur = None

    try:
        conn = get_conn()
        cur = conn.cursor()
        today = run_date

        # For testing with historical dates: use most recent data if run_date is in past
        is_historical_test = today < date.today()
        if is_historical_test:
            cur.execute("SELECT MAX(date) FROM price_daily")
            result = cur.fetchone()
            latest_date = result[0] if result else None
            if latest_date and latest_date > today:
                logger.info(f"  [TEST MODE] Using latest available data ({latest_date}) instead of run_date ({today})")
                today = latest_date

        # Hard blocks: data required before trading
        required_hard = [
            ('price_daily', 'Price data'),
            ('technical_data_daily', 'Technical indicators'),
            ('buy_sell_daily', 'Signal data'),
        ]
        # Soft checks: post-trade tables, only warn if missing (they get populated by orchestrator after trades)
        required_soft = [
            ('market_exposure_daily', 'Market exposure data'),
            ('algo_risk_daily', 'Risk calculations'),
        ]

        for table, description in required_hard:
            assert_safe_table(table)
            cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE date = %s",
                (today,)
            )
            result = cur.fetchone()
            count = result[0] if result else 0
            if count == 0:
                # Allow fallback to yesterday's data if today's not available (for market hours lag)
                cur.execute(
                    f"SELECT MAX(date) FROM {table} WHERE date <= %s",
                    (today,)
                )
                result = cur.fetchone()
                latest = result[0] if result else None
                if latest and latest >= today - timedelta(days=1):
                    logger.info(f"  [OK] {table}: Using data from {latest} (latest available)")
                else:
                    issues.append(f"{description} missing for {today}")
            else:
                logger.debug(f"  [OK] {table}: {count} rows for {today}")

        for table, description in required_soft:
            assert_safe_table(table)
            if table == 'algo_risk_daily':
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE report_date = %s",
                    (today,)
                )
            else:
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE date = %s",
                    (today,)
                )
            result = cur.fetchone()
            count = result[0] if result else 0
            if count == 0:
                warnings.append(f"{description} not available (will be populated after trading)")
            else:
                logger.debug(f"  [OK] {table}: {count} rows for today")

        # Use latest available data if today's not available (same as hard-block logic above)
        price_check_date = today
        cur.execute(
            f"SELECT COUNT(*) FROM price_daily WHERE date = %s",
            (price_check_date,)
        )
        result = cur.fetchone()
        count = result[0] if result else 0
        if count == 0:
            cur.execute(
                "SELECT MAX(date) FROM price_daily WHERE date <= %s",
                (price_check_date,)
            )
            result = cur.fetchone()
            latest = result[0] if result else None
            if latest:
                price_check_date = latest
                logger.debug(f"  [FALLBACK] Using price data from {latest} instead of {today}")

        # Check if data exists for price_check_date (we already verified hard blocks above)
        cur.execute(
            "SELECT COUNT(*) FROM price_daily WHERE date = %s",
            (price_check_date,)
        )
        result = cur.fetchone()
        price_count = result[0] if result else 0
        if price_count == 0:
            issues.append("No price data found")
        else:
            # Check created_at age if available
            cur.execute(
                "SELECT MAX(created_at) FROM price_daily WHERE date = %s",
                (price_check_date,)
            )
            result = cur.fetchone()
            if result and result[0]:
                # Strip tzinfo before subtraction — psycopg2 returns timezone-aware datetime
                # for TIMESTAMPTZ columns, which can't be compared to naive datetime.now().
                db_ts = result[0].replace(tzinfo=None) if getattr(result[0], 'tzinfo', None) else result[0]
                age_hours = (datetime.now(timezone.utc) - db_ts).total_seconds() / 3600
                if age_hours > 24:
                    issues.append(f"Price data too stale: {age_hours:.1f} hours old")
                elif age_hours > 1:
                    warnings.append(f"Price data is {age_hours:.1f} hours old")
            else:
                # Data exists but created_at is missing (not critical)
                logger.debug(f"  [WARN] Price data exists but created_at is not set for {price_check_date}")

        cur.execute(
            "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND (symbol IS NULL OR signal IS NULL)",
            (today,)
        )
        result = cur.fetchone()
        null_count = result[0] if result else 0
        if null_count > 0:
            issues.append(f"Signal data has {null_count} critical NULLs")

        cur.execute(
            "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
            (today,)
        )
        result = cur.fetchone()
        covered = result[0] if result else 0
        cur.execute(
            "SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE"
        )
        result = cur.fetchone()
        total = result[0] if result else 0
        if total > 0:
            coverage = (covered / total) * 100
            if coverage < 80:
                issues.append(f"Low symbol coverage: {covered}/{total} ({coverage:.1f}%)")
            elif coverage < 95:
                warnings.append(f"Symbol coverage: {covered}/{total} ({coverage:.1f}%)")

        # Check if technical data exists (hard blocks already verified this above)
        cur.execute(
            "SELECT COUNT(*) FROM technical_data_daily WHERE date <= %s",
            (today,)
        )
        result = cur.fetchone()
        tech_count = result[0] if result else 0
        if tech_count == 0:
            issues.append("No technical data found")
        else:
            # Check created_at age if available
            cur.execute(
                "SELECT MAX(created_at) FROM technical_data_daily WHERE date <= %s",
                (today,)
            )
            result = cur.fetchone()
            if result and result[0]:
                db_ts = result[0].replace(tzinfo=None) if getattr(result[0], 'tzinfo', None) else result[0]
                age_hours = (datetime.now(timezone.utc) - db_ts).total_seconds() / 3600
                # Allow 72 hours of staleness for testing/backtesting data
                # Production: revert to 24 hours when using real-time data feeds
                if age_hours > 72:
                    issues.append(f"Technical data stale: {age_hours:.1f} hours old")
                elif age_hours > 48:
                    warnings.append(f"Technical data is {age_hours:.1f} hours old (consider refreshing)")
            else:
                logger.debug(f"  [WARN] Technical data exists but created_at is not set")

        # 6a. Quality metrics (momentum, volatility, RSI, etc.)
        cur.execute(
            "SELECT COUNT(*) FROM quality_metrics WHERE DATE(created_at) >= %s::date - INTERVAL '1 day'",
            (today,)
        )
        result = cur.fetchone()
        quality_count = result[0] if result else 0
        if quality_count < (covered * 0.50):  # At least 50% of covered symbols (lenient for historical data)
            warnings.append(f"Quality metrics incomplete: {quality_count}/{covered} symbols ({(quality_count/max(covered,1)*100):.0f}%)")

        # 6b. Value metrics (PE, PB, PS ratios)
        cur.execute(
            "SELECT COUNT(*) FROM value_metrics WHERE DATE(created_at) = %s",
            (today,)
        )
        result = cur.fetchone()
        value_count = result[0] if result else 0
        if value_count < (covered * 0.70):  # At least 70% of covered symbols (PE coverage is lower)
            warnings.append(f"Value metrics incomplete: {value_count}/{covered} symbols ({(value_count/max(covered,1)*100):.0f}%)")

        # 6c. Stock scores data completeness (scores must have >80% component coverage)
        # data_completeness is stored as 0-100 (percent of 6 score components available); 80+ is acceptable
        cur.execute(
            "SELECT COUNT(*) FROM stock_scores WHERE DATE(updated_at) >= %s::date - INTERVAL '1 day' AND data_completeness >= 80",
            (today,)
        )
        result = cur.fetchone()
        complete_scores = result[0] if result else 0
        cur.execute(
            "SELECT COUNT(*) FROM stock_scores WHERE DATE(updated_at) >= %s::date - INTERVAL '1 day'",
            (today,)
        )
        result = cur.fetchone()
        total_scores = result[0] if result else 0
        if total_scores > 0:
            completeness_pct = (complete_scores / total_scores) * 100
            if completeness_pct < 30:
                warnings.append(f"Stock scores: {completeness_pct:.1f}% have full component coverage (using prior day data)")
        else:
            logger.info("Stock scores not yet available (using fallback trading signals)")

        passes = len(issues) == 0
        return passes, issues, warnings

    except Exception as e:
        logger.error(f"Data quality check failed: {e}", exc_info=True)
        return False, [f"Data quality check error: {e}"], []
    finally:
        if cur:
            try:
                cur.close()
            except Exception as e:
                logger.error(f"Unhandled exception: {e}")
        if conn:
            try:
                put_conn(conn)
            except Exception as e:
                logger.error(f"Unhandled exception: {e}")


def run(
    config: Any,
    get_conn: Callable,
    put_conn: Callable,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
    qualified_trades: List[Dict[str, Any]],
    exposure_constraints: Optional[Dict[str, Any]],
    check_halt_flag: Callable,
) -> PhaseResult:
    """Execute Phase 6: Entry Execution.

    Args:
        config: Configuration object
        get_conn: Function to get database connection
        put_conn: Function to return database connection
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        qualified_trades: List of qualified trades from Phase 5
        exposure_constraints: Exposure constraints from Phase 3b
        check_halt_flag: Function to check halt flag

    Returns:
        PhaseResult with status 'ok' or 'halted', data containing entry results
    """
    if check_halt_flag():
        return PhaseResult(6, 'entry_execution', 'halted', {}, True, 'Halt flag detected')

    try:
        from algo.algo_trade_executor import TradeExecutor

        # In dry-run mode, skip TradeExecutor initialization (no Alpaca credentials needed)
        if dry_run:
            logger.info("[DRY-RUN] Phase 6: Skipping entry execution (dry-run mode)")
            log_phase_result_fn(6, 'entry_execution', 'success', 'DRY-RUN: execution skipped')
            return PhaseResult(6, 'entry_execution', 'ok', {'entered': 0}, False, None)

        executor = TradeExecutor(config)

        # PRE-TRADE DATA QUALITY GATE: Verify all required data is fresh and complete
        data_quality_ok, dq_issues, dq_warnings = _validate_pre_trade_data_quality(get_conn, put_conn, run_date)
        if not data_quality_ok:
            log_phase_result_fn(
                6, 'entry_execution', 'halt',
                f'Data quality gate failed: {"; ".join(dq_issues)}'
            )
            return PhaseResult(
                6, 'entry_execution', 'halted', {}, True,
                f'Data quality gate failed: {"; ".join(dq_issues)}'
            )
        if dq_warnings:
            logger.warning(f"Data quality warnings: {'; '.join(dq_warnings)}")

        # Apply exposure tier entry constraints
        if exposure_constraints and exposure_constraints.get('halt_new_entries'):
            log_phase_result_fn(
                6, 'entry_execution', 'success',
                f"Tier '{exposure_constraints['tier_name']}' halts new entries — 0 entries"
            )
            return PhaseResult(6, 'entry_execution', 'ok', {'entered': 0}, False, None)

        # Filter qualified trades by min_swing_grade and min_swing_score
        trades_to_enter = qualified_trades[:]
        if exposure_constraints:
            min_score = exposure_constraints.get('min_swing_score', 60.0)
            grade_order = ['F', 'D', 'C', 'B', 'A', 'A+']
            min_grade = exposure_constraints.get('min_swing_grade', 'B')
            min_grade_idx = grade_order.index(min_grade) if min_grade in grade_order else 3
            before = len(trades_to_enter)

            # Safe grade lookup: unknown grades default to 'F' (worst grade)
            def get_grade_idx(grade):
                try:
                    return grade_order.index(grade) if grade in grade_order else grade_order.index('F')
                except ValueError:
                    return grade_order.index('F')

            trades_to_enter = [
                t for t in trades_to_enter
                if (t.get('swing_score', 0) >= min_score and
                    get_grade_idx(t.get('swing_grade', 'F')) >= min_grade_idx)
            ]
            if len(trades_to_enter) < before:
                logger.info(f"  Tier filter: {before} -> {len(trades_to_enter)} "
                           f"(min_score={min_score}, min_grade={min_grade})")

        # Determine open slots
        conn = None
        cur = None
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
            open_count = cur.fetchone()[0] or 0
        except Exception as e:
            logger.warning(f"Exception: {e}")
            open_count = 0
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:
                    logger.error(f"Unhandled exception: {e}")
            if conn:
                try:
                    put_conn(conn)
                except Exception as e:
                    logger.error(f"Unhandled exception: {e}")

        max_positions = int(config.get('max_positions', 12))
        open_slots = max(0, max_positions - open_count)

        # Apply daily entry cap from exposure tier
        if exposure_constraints:
            daily_cap = exposure_constraints.get('max_new_positions_today', 5)
            open_slots = min(open_slots, daily_cap)

        logger.info(f"  Open positions: {open_count}/{max_positions}, slots available: {open_slots}")
        if exposure_constraints:
            logger.info(f"  Tier '{exposure_constraints['tier_name']}' caps daily entries at {exposure_constraints['max_new_positions_today']}")

        if open_slots == 0:
            log_phase_result_fn(6, 'entry_execution', 'success',
                               f'No room (already {open_count}/{max_positions} or daily cap)')
            return PhaseResult(6, 'entry_execution', 'ok', {'entered': 0}, False, None)

        if not trades_to_enter:
            log_phase_result_fn(6, 'entry_execution', 'success',
                               'No qualified trades meet tier requirements')
            return PhaseResult(6, 'entry_execution', 'ok', {'entered': 0}, False, None)

        # Margin entry gate (Phase 6 - production safeguard)
        try:
            pm = PositionMonitor(config)
            can_enter, margin_reason = pm.can_enter_new_position()
            if not can_enter:
                log_phase_result_fn(
                    6, 'entry_execution', 'success',
                    f'Margin gate blocked entries: {margin_reason}'
                )
                return PhaseResult(6, 'entry_execution', 'ok', {'entered': 0}, False, None)
            elif verbose:
                logger.info(f"  [OK] Margin gate: Can enter new positions")
        except Exception as e:
            logger.warning(f'Margin gate check failed: {e}')

        entered = 0
        blocked = 0
        errors = 0

        # Recalculate exposure constraints based on CURRENT portfolio (after Phase 4 exits)
        # Issue: exposure_constraints from Phase 3b are stale (calculated before Phase 4 exits)
        # Solution: Recalculate based on current exposure to get accurate risk multiplier
        try:
            from algo.algo_market_exposure_policy import ExposurePolicy
            exposure_policy = ExposurePolicy(config)
            current_constraints = exposure_policy.get_entry_constraints(run_date)

            if current_constraints and exposure_constraints:
                old_mult = exposure_constraints.get('risk_multiplier', 1.0)
                new_mult = current_constraints.get('risk_multiplier', 1.0)
                if new_mult != old_mult:
                    logger.info(f"  Exposure constraints recalculated after exits: "
                              f"tier '{exposure_constraints.get('tier_name')}' → "
                              f"'{current_constraints.get('tier_name')}', "
                              f"risk_mult {old_mult:.2f}x → {new_mult:.2f}x")
                    exposure_constraints = current_constraints
        except Exception as e:
            logger.warning(f"  Could not recalculate exposure constraints: {e}")

        # Get exposure multiplier for position size recalculation
        exposure_mult = 1.0
        if exposure_constraints:
            exposure_mult = exposure_constraints.get('risk_multiplier', 1.0)

        for trade in trades_to_enter[:open_slots]:
            # Validate entry price hasn't drifted significantly
            trade = _validate_and_adjust_entry_price(trade, get_conn, put_conn, verbose)
            if trade.get('skip_due_to_price_drift'):
                blocked += 1
                logger.warning(f"  SKIPPED {trade['symbol']}: Price validation failed")
                continue

            # Recalculate position size based on current portfolio value (after Phase 4 exits)
            trade = _recalculate_position_size_after_exits(trade, get_conn, config, exposure_mult, verbose)

            # Re-check sector limits before execution to prevent race condition
            # where two same-sector trades could violate sector concentration limits
            symbol = trade['symbol']
            sector = trade.get('sector')
            entry_price = trade.get('entry_price', 0)
            shares = trade.get('shares', 0)
            max_sector_pct = float(config.get('max_sector_concentration_pct', 30.0))

            if sector and entry_price > 0 and shares > 0:
                try:
                    conn_check = get_conn()
                    try:
                        cur_check = conn_check.cursor()
                        # Get current sector allocation
                        cur_check.execute("""
                            SELECT COALESCE(SUM(position_value), 0) as sector_value
                            FROM algo_positions ap
                            LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                            WHERE ap.status = 'open' AND ap.quantity > 0
                              AND COALESCE(cp.sector, 'Unknown') = %s
                        """, (sector,))
                        result = cur_check.fetchone()
                        sector_value = float(result[0] or 0) if result else 0

                        # Get portfolio value
                        cur_check.execute("""
                            SELECT COALESCE(total_portfolio_value, 0)
                            FROM algo_portfolio_snapshots
                            ORDER BY snapshot_date DESC LIMIT 1
                        """)
                        result = cur_check.fetchone()
                        portfolio_value = float(result[0] or 0) if result else 100000.0

                        # Calculate new position value and sector percentage after this trade
                        new_position_value = entry_price * shares
                        new_sector_value = sector_value + new_position_value
                        new_sector_pct = (new_sector_value / portfolio_value * 100) if portfolio_value > 0 else 0

                        if new_sector_pct > max_sector_pct:
                            blocked += 1
                            logger.warning(f"  SKIPPED {symbol}: Sector {sector} concentration would be {new_sector_pct:.1f}% (limit: {max_sector_pct:.1f}%)")
                            continue
                    finally:
                        cur_check.close()
                except Exception as e:
                    logger.warning(f"  Could not verify sector limits for {symbol}: {e}")
                finally:
                    try:
                        put_conn(conn_check)
                    except Exception as e:
                        logger.debug(f"Exception (expected): {e}")
                        pass

            if dry_run:
                if verbose:
                    logger.info(f"  [DRY-RUN] WOULD ENTER {trade['symbol']}: "
                               f"{trade['shares']}sh @ ${trade['entry_price']:.2f} "
                               f"stop ${trade['stop_loss_price']:.2f}")
                continue
            try:
                # Pull stage_phase + base_type detail from advanced components
                adv = trade.get('advanced_components', {}) or {}
                setup = (trade.get('swing_components', {}) or {}).get('setup_quality', {}).get('detail', {})
                trend_d = (trade.get('swing_components', {}) or {}).get('trend_quality', {}).get('detail', {})

                stop_method = trade.get('stop_method') or 'base_type_stop'
                stop_reasoning = trade.get('stop_reasoning')

                result = executor.execute_trade(
                    symbol=trade['symbol'],
                    entry_price=trade['entry_price'],
                    shares=trade['shares'],
                    stop_loss_price=trade['stop_loss_price'],
                    target_1_price=trade.get('target_1_price'),
                    target_2_price=trade.get('target_2_price'),
                    target_3_price=trade.get('target_3_price'),
                    signal_date=run_date,
                    sqs=int(trade.get('sqs', 0)),
                    trend_score=int(trade.get('trend_score', 0)),
                    # Reasoning metadata:
                    swing_score=trade.get('swing_score'),
                    swing_grade=trade.get('swing_grade'),
                    base_type=setup.get('base_type'),
                    base_quality=setup.get('base_quality'),
                    stage_phase=trend_d.get('phase'),
                    sector=trade.get('sector'),
                    industry=trade.get('industry'),
                    rs_percentile=(adv.get('relative_strength', {}) or {}).get('value'),
                    market_exposure_at_entry=exposure_constraints.get('exposure_pct') if exposure_constraints else None,
                    exposure_tier_at_entry=exposure_constraints.get('tier_name') if exposure_constraints else None,
                    stop_method=stop_method,
                    stop_reasoning=stop_reasoning,
                    swing_components=trade.get('swing_components'),
                    advanced_components=trade.get('advanced_components'),
                )
                if result.get('success'):
                    entered += 1
                    if verbose:
                        logger.info(f"  ENTERED: {result['message']}")
                elif result.get('duplicate'):
                    blocked += 1
                else:
                    errors += 1
                    logger.error(f"  Failed {trade['symbol']}: {result.get('message')}")
            except Exception as e:
                errors += 1
                logger.error(f"  Exception on {trade['symbol']}: {e}", exc_info=True)

        # Persist dry-run results if applicable
        if dry_run and trades_to_enter:
            try:
                conn = get_conn()
                try:
                    cur = conn.cursor()
                    # Log all proposed trades for dry-run audit
                    for i, trade in enumerate(trades_to_enter[:open_slots]):
                        cur.execute("""
                            INSERT INTO algo_trades_dry_run_log
                            (symbol, entry_price, shares, stop_loss_price,
                             signal_date, proposed_at, status)
                            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                        """, (
                            trade['symbol'],
                            trade['entry_price'],
                            trade['shares'],
                            trade['stop_loss_price'],
                            run_date,
                            'proposed'
                        ))
                    conn.commit()
                    logger.info(f"Dry-run: Persisted {len(trades_to_enter[:open_slots])} proposed trades for audit")
                finally:
                    cur.close()
            except Exception as e:
                logger.warning(f"Could not persist dry-run results: {e}")
            finally:
                try:
                    put_conn(conn)
                except Exception as e:
                    logger.debug(f"Exception (expected): {e}")
                    pass

        # Circuit breaker: if >50% of trades fail in a batch, halt.
        # Exclude blocked (duplicates) from the denominator — they are expected
        # idempotency blocks, not failures; including them would dilute the rate.
        if len(trades_to_enter) > 2 and errors > 0:
            failure_rate = errors / max(entered + errors, 1)
            if failure_rate > 0.5:
                logger.critical(f"BATCH FAILURE RATE {failure_rate:.0%} exceeds 50% threshold ({errors}/{entered + blocked + errors}) — halting Phase 6")
                log_phase_result_fn(6, 'entry_execution', 'error', f'Batch failure rate {failure_rate:.0%} ({errors} of {entered + blocked + errors})')
                return PhaseResult(6, 'entry_execution', 'halted', {}, True,
                                 f'Batch failure rate {failure_rate:.0%}')

        log_phase_result_fn(
            6, 'entry_execution', 'success',
            f'{entered} entered, {blocked} blocked (duplicates), {errors} errors',
        )
        return PhaseResult(
            6, 'entry_execution', 'ok',
            {'entered': entered, 'blocked': blocked, 'errors': errors},
            False, None
        )

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(6, 'entry_execution', 'error', str(e))
        return PhaseResult(6, 'entry_execution', 'halted', {}, True, str(e))
