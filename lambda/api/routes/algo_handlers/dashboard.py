"""Route: algo"""

from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from utils.data_queries import (
    get_trade_win_loss_stats,
)
from utils.validation import (
    APIResponseValidator,
    format_decimal_string,
)

# Response caches for expensive queries - to avoid API Gateway timeout (30s limit)
_positions_cache: dict[str, Any] = {"data": None, "timestamp": 0.0, "cache_ttl_seconds": 300}
_scores_cache: dict[str, Any] = {"data": None, "timestamp": 0.0, "cache_ttl_seconds": 300}
_signals_cache: dict[str, Any] = {"data": None, "timestamp": 0.0, "cache_ttl_seconds": 300}

logger = logging.getLogger(__name__)


@db_route_handler("fetch algo positions")
@validate_api_response("pos")
def _get_algo_positions(cur: cursor, user_id: str | None = None) -> Any:  # noqa: C901
    """Get current open positions with computed fields.

    Provides comprehensive position data with:
    - Current price, unrealized P&L, risk metrics
    - Stop/target levels and distance percentages
    - Technical scores (Weinstein stage, Minervini trend)
    - Sector allocation for pie chart
    - Ladder percentage points for visualization
    """
    # OPTIMIZATION: Cache positions response for 60 seconds (positions don't update that frequently)
    # This reduces database load during dashboard refreshes
    current_time = time.time()
    cache_is_valid = (
        _positions_cache["data"] is not None
        and _positions_cache["timestamp"] > 0  # Ensure timestamp was actually set
        and (current_time - _positions_cache["timestamp"]) < _positions_cache["cache_ttl_seconds"]
    )

    # FIX: Secondary validation - ensure timestamp is not in future (clock skew guard)
    if cache_is_valid and _positions_cache["timestamp"] > current_time:
        logger.warning("[POSITIONS] Cache timestamp in future, skipping cache (possible clock skew)")
        cache_is_valid = False

    if cache_is_valid:
        logger.info(
            f"[POSITIONS] Returning cached response (age: {int(current_time - _positions_cache['timestamp'])}s)"
        )
        return _positions_cache["data"]

    # Use 2-second timeout - fast direct query completes well under this
    cur.execute("SET LOCAL statement_timeout = '2000ms'")

    # Initialize alerts tracking early so it can be used throughout
    stale_alerts = []

    # Query algo_positions base table directly (NO get_open_positions function which is slow)
    # NOTE: query errors (including statement_timeout) are intentionally NOT caught here -
    # they must propagate to @db_route_handler so it can return a real 5xx instead of a
    # false "zero positions" 200 OK.
    cur.execute("""
        SELECT * FROM algo_positions
        WHERE status = 'open'
        ORDER BY position_value DESC NULLS LAST
        LIMIT 1000
    """)
    positions = cur.fetchall()
    logger.info(f"[POSITIONS] Direct algo_positions query returned {len(positions)} positions")

    if not positions:
        logger.error(
            "[POSITIONS CRITICAL] algo_positions_with_risk returned 0 rows. "
            "This indicates a data sync issue: either algo_positions table not synced with live Alpaca state, "
            "or algo_positions was cleared but reconciliation incomplete, or view/table corruption. "
            "Returning empty portfolio rather than silently switching to algo_trades (different schema). "
            "Check: (1) algo_positions table populated? (2) Alpaca sync reconciliation completed? "
            "(3) algo_positions_with_risk view valid?"
        )
        stale_alerts.append("Position data unavailable: algo_positions sync incomplete")

    # FIX: Load sector data from company_profile for positions missing sector
    # (algo_trades currently has NULL sectors, so view defaults to "Unknown")
    sector_map: dict[str, str] = {}
    try:
        # Get list of open position symbols from the positions we fetched
        if positions:
            # CRITICAL FIX: positions are tuples from fetchall(), must convert to dict first
            open_symbols = []
            for p in positions:
                p_dict = safe_dict_convert(p)
                symbol = p_dict.get("symbol")
                if symbol:
                    open_symbols.append(symbol)

            if open_symbols:
                # Build placeholders for SQL query
                placeholders = ",".join(["%s"] * len(open_symbols))
                cur.execute(
                    f"""
                    SELECT ticker, sector FROM company_profile
                    WHERE ticker IN ({placeholders})
                    """,
                    tuple(open_symbols),
                )
                for row in cur.fetchall():
                    row_dict = safe_dict_convert(row)
                    ticker = row_dict.get("ticker")
                    sector = row_dict.get("sector")
                    if ticker and sector:
                        sector_map[ticker] = sector
                logger.debug(f"[POSITIONS] Loaded sector data for {len(sector_map)} symbols from company_profile")
    except Exception as e:
        logger.warning(f"[POSITIONS] Could not load company_profile sectors: {type(e).__name__}: {e}")

    items = []
    sector_risk: dict[str, float] = {}
    total_positions_fetched = len(positions)
    filtered_positions_count = 0
    logger.info(f"[POSITIONS] Starting loop with {total_positions_fetched} positions")

    for p in positions:
        try:
            d = safe_json_serialize(safe_dict_convert(p))
        except Exception as e:
            logger.error(f"[POSITIONS] Failed to convert position data: {type(e).__name__}: {e}")
            filtered_positions_count += 1
            continue
        symbol = d.get("symbol")

        if not symbol:
            logger.error("[POSITIONS] Position missing symbol — skipping")
            filtered_positions_count += 1
            continue

        # Validate and convert all required numeric fields upfront
        # If ANY required field is missing, None, empty, or non-numeric → skip this position
        try:
            pos_val = float(d.get("position_value"))
            entry = float(d.get("avg_entry_price"))
            cur_price = float(d.get("current_price"))
        except (ValueError, TypeError, AttributeError):
            logger.warning(
                f"[POSITIONS] {symbol}: missing or invalid numeric field(s) "
                f"(position_value, avg_entry_price, or current_price) — skipping"
            )
            filtered_positions_count += 1
            continue

        # CRITICAL: Reject NaN and Infinity values - these indicate data corruption
        # All position metrics must be valid positive numbers
        if math.isnan(pos_val) or math.isinf(pos_val):
            logger.warning(
                f"[POSITIONS] {symbol}: position_value is {pos_val} (NaN or Infinity) — data corruption — skipping"
            )
            filtered_positions_count += 1
            continue

        if math.isnan(entry) or math.isinf(entry):
            logger.warning(
                f"[POSITIONS] {symbol}: avg_entry_price is {entry} (NaN or Infinity) — data corruption — skipping"
            )
            filtered_positions_count += 1
            continue

        if math.isnan(cur_price) or math.isinf(cur_price):
            logger.warning(
                f"[POSITIONS] {symbol}: current_price is {cur_price} (NaN or Infinity) — data corruption — skipping"
            )
            filtered_positions_count += 1
            continue

        # Compute ladder_pct_* fields for visualization (Issue #2)
        # These fields are OPTIONAL - positions without stop/target prices are still valid
        stop_raw = d.get("stop_loss_price")
        t1_raw = d.get("target_1_price")
        t2_raw = d.get("target_2_price")
        t3_raw = d.get("target_3_price")

        # Only compute ladder if we have all price fields
        try:
            if all(v is not None for v in [stop_raw, t1_raw, t2_raw, t3_raw]):
                stop = float(stop_raw)
                t1 = float(t1_raw)
                t2 = float(t2_raw)
                t3 = float(t3_raw)

                # FIX: Use explicit None checks instead of falsy checks (0.0 is a valid price)
                if entry is not None and cur_price is not None and stop is not None:
                    lo = min(stop, entry, cur_price)
                    hi = max(t3 or t2 or t1 or entry, cur_price)
                    span = max(0.0001, hi - lo)

                    def pos(price: float | None, _lo: float = lo, _span: float = span) -> float | None:
                        if price is None:
                            return None
                        # Clamp to 0-100 range in case prices are outside ladder bounds
                        pct = ((price - _lo) / _span) * 100
                        return max(0.0, min(100.0, pct))

                    d["ladder_pct_stop"] = pos(stop)
                    d["ladder_pct_entry"] = pos(entry)
                    d["ladder_pct_current"] = pos(cur_price)
                    d["ladder_pct_t1"] = pos(t1)
                    d["ladder_pct_t2"] = pos(t2)
                    d["ladder_pct_t3"] = pos(t3)
                else:
                    d["ladder_pct_stop"] = None
                    d["ladder_pct_entry"] = None
                    d["ladder_pct_current"] = None
                    d["ladder_pct_t1"] = None
                    d["ladder_pct_t2"] = None
                    d["ladder_pct_t3"] = None
            else:
                # Missing ladder price fields - set to None
                d["ladder_pct_stop"] = None
                d["ladder_pct_entry"] = None
                d["ladder_pct_current"] = None
                d["ladder_pct_t1"] = None
                d["ladder_pct_t2"] = None
                d["ladder_pct_t3"] = None
        except (ValueError, TypeError) as e:
            error_msg = f"Ladder calculation failed: {type(e).__name__}: {e}"
            logger.warning(f"[POSITION DATA QUALITY] {symbol}: {error_msg}")
            d["ladder_pct_stop"] = None
            d["ladder_pct_entry"] = None
            d["ladder_pct_current"] = None
            d["ladder_pct_t1"] = None
            d["ladder_pct_t2"] = None
            d["ladder_pct_t3"] = None
            d["ladder_unavailable"] = True
            d["ladder_unavailable_reason"] = error_msg

        # Compute stage_label for stage distribution (Issue #8)
        stage_raw = d.get("weinstein_stage")
        stage = None
        d["stage_label"] = None
        if stage_raw is None:
            logger.warning(f"Position {d.get('symbol')} missing weinstein_stage")
        else:
            try:
                stage = int(stage_raw)
            except (ValueError, TypeError):
                logger.warning(f"Position {d.get('symbol')} has invalid weinstein_stage: {stage_raw}")

        if stage is not None:
            trend_score_raw = d.get("minervini_trend_score")
            trend_score = float(trend_score_raw) if trend_score_raw is not None else None
            if stage == 2:
                if trend_score is not None and trend_score < 4:
                    d["stage_label"] = "Early Stage-2"
                elif trend_score is not None and trend_score >= 6:
                    d["stage_label"] = "Late Stage-2"
                else:
                    d["stage_label"] = "Mid Stage-2"
            elif stage == 1:
                d["stage_label"] = "Stage 1 (base)"
            elif stage == 3:
                d["stage_label"] = "Stage 3 (top)"
            elif stage == 4:
                d["stage_label"] = "Stage 4 (down)"

        # Normalize field names for frontend compatibility
        if "percent_from_52w_low" in d:
            d["pct_from_52w_low"] = d.pop("percent_from_52w_low")
        if "percent_from_52w_high" in d:
            d["pct_from_52w_high"] = d.pop("percent_from_52w_high")

        # FIX: Ensure ALL positions have sector data from company_profile
        # Enrich if: (1) sector is "Unknown", (2) sector is None, (3) sector is empty string
        current_sector = d.get("sector")
        if (current_sector == "Unknown" or current_sector is None or current_sector == "") and symbol in sector_map:
            d["sector"] = sector_map[symbol]
            logger.debug(f"[POSITIONS] {symbol}: enriched sector from company_profile: {sector_map[symbol]}")
        elif (
            current_sector == "Unknown" or current_sector is None or current_sector == ""
        ) and symbol not in sector_map:
            # Position has missing/invalid sector and not in company_profile — this is a data quality issue
            logger.warning(
                f"[POSITIONS DATA QUALITY] {symbol}: sector missing/invalid ({current_sector!r}) and not found in company_profile"
            )

        items.append(d)
        logger.debug(f"[POSITIONS] Added {symbol} to items list (total now: {len(items)})")

        # Accumulate sector allocation - all added items have valid position_value
        sector = d.get("sector")
        if sector is not None and sector not in sector_risk:
            sector_risk[sector] = 0
        if sector is not None:
            sector_risk[sector] += pos_val

    # Sort positions by position value descending (largest positions first) for better UX
    # This makes the dashboard display more organized and easier to scan
    items.sort(key=lambda x: float(x.get("position_value", 0)), reverse=True)

    # Compute sector_allocation array after processing all positions (E5 fix)
    # CRITICAL: Fail-fast if portfolio appears empty after position processing
    # Division-by-zero fallback (setting total=1) would create FAKE allocation percentages
    total_abs_value = sum(abs(v) for v in sector_risk.values())
    if total_abs_value == 0:
        logger.error(
            "[POSITIONS CRITICAL] Portfolio allocation cannot be computed: "
            "total_abs_value is 0 after processing %d items. "
            "This indicates either no positions with valid sectors, or all positions skipped due to missing data. "
            "Check: (1) Positions have sector data? (2) Position values are non-zero?",
            len(items),
        )
        stale_alerts.append("Portfolio data incomplete: unable to compute sector allocation")
        sector_allocation = []
    else:
        sector_allocation = [
            {
                "sector": sector,
                "allocation_pct": round((abs(value) / total_abs_value) * 100, 1),
                "is_overweight": (abs(value) / total_abs_value) * 100 > 30,
            }
            for sector, value in sorted(sector_risk.items(), key=lambda x: abs(x[1]), reverse=True)
        ]

    freshness = check_data_freshness(cur, "algo_positions", "updated_at", warning_days=1)
    if freshness.get("is_stale"):
        age_days = freshness.get("data_age_days")
        age_display = f"{age_days}d old" if age_days is not None else "age unknown"
        stale_alerts.append(f"Position data {age_display}")

    # Track coverage metrics for data quality visibility
    valid_count = len(items)
    coverage_pct = (valid_count / total_positions_fetched * 100) if total_positions_fetched > 0 else 100.0

    # Alert if significant positions were filtered
    if filtered_positions_count > 0:
        logger.warning(
            f"[POSITIONS DATA QUALITY] Filtered {filtered_positions_count}/{total_positions_fetched} positions "
            f"({100 - coverage_pct:.1f}% filtered). Valid: {valid_count}."
        )
        stale_alerts.append(
            f"Position data incomplete: {filtered_positions_count} positions filtered "
            f"(missing price/value data). Showing {valid_count}/{total_positions_fetched} valid positions."
        )

    response_data = {
        "items": items,
        "sector_allocation": sector_allocation,
        "pagination": {"total": len(items), "limit": 10000, "offset": 0},
        "coverage": {
            "valid_count": valid_count,
            "total_count": total_positions_fetched,
            "filtered_count": filtered_positions_count,
            "coverage_pct": round(coverage_pct, 1),
        },
        "stale_alerts": stale_alerts,
        "data_freshness": freshness,
    }
    logger.debug(f"[POSITIONS] Before sanitization: {len(response_data.get('items', []))} items")
    sanitized = APIResponseValidator.sanitize_response(response_data)
    logger.debug(f"[POSITIONS] After sanitization: {len(sanitized.get('items', []))} items")

    # Cache the response for 60 seconds to reduce database load
    cached_response = json_response(200, sanitized)
    _positions_cache["data"] = cached_response
    _positions_cache["timestamp"] = time.time()
    logger.info("[POSITIONS] Response cached for 60 seconds")

    return cached_response


@db_route_handler("fetch algo status")
@validate_api_response("run")
def _get_algo_status(cur: cursor) -> Any:
    """Get latest algo execution status plus latest portfolio snapshot.

    Returns sensible defaults if data is missing, allowing dashboard to render
    instead of showing "Panel Unavailable" error.
    """
    cur.execute("""
            SELECT
                details->>'run_id' AS run_id,
                action_type,
                action_date,
                details->>'summary' AS message,
                status,
                created_at
            FROM algo_audit_log
            ORDER BY created_at DESC
            LIMIT 1
        """)
    row = cur.fetchone()

    # If no audit log, use sensible defaults
    if row is None:
        row = {
            "run_id": "not_started",
            "action_type": "INIT",
            "action_date": None,
            "message": "No trading activity yet",
            "status": "ready",
        }
    else:
        row = safe_dict_convert(row)

    # Fetch and validate portfolio snapshot: RESILIENT fallback to computed data
    # If orchestrator hasn't run (Phase 9 snapshot missing), compute from algo_positions + algo_trades
    portfolio = None
    try:
        cur.execute("""
                SELECT total_portfolio_value, total_cash, daily_return_pct,
                       unrealized_pnl_total, position_count
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
        snap = cur.fetchone()
        if snap is not None:
            snap = safe_dict_convert(snap)
            pv_raw = snap.get("total_portfolio_value")
            tc_raw = snap.get("total_cash")
            pc_raw = snap.get("position_count")
            unrealized_pnl_raw = snap.get("unrealized_pnl_total")
            daily_return_raw = snap.get("daily_return_pct")

            if pv_raw is None or tc_raw is None or pc_raw is None:
                logger.warning("[PORTFOLIO] Snapshot has NULL critical fields, falling back to computed portfolio")
            else:
                try:
                    pv = float(pv_raw)
                    tc_float = float(tc_raw)
                    pc = int(pc_raw)
                    unrealized_pnl = float(unrealized_pnl_raw) if unrealized_pnl_raw is not None else 0.0
                    unrealized_pnl_pct = None
                    if pv > 0 and unrealized_pnl is not None:
                        unrealized_pnl_pct = unrealized_pnl / pv * 100

                    portfolio = {
                        "total_portfolio_value": format_decimal_string(pv, precision=2, allow_none=True),
                        "total_cash": format_decimal_string(tc_float, precision=2),
                        "position_count": pc,
                        "daily_return_pct": format_decimal_string(
                            float(daily_return_raw) if daily_return_raw is not None else None,
                            precision=2,
                            allow_none=True,
                        ),
                        "unrealized_pnl_pct": format_decimal_string(
                            unrealized_pnl_pct,
                            precision=2,
                            allow_none=True,
                        ),
                        "unrealized_pnl_dollars": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                    }
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"[PORTFOLIO] Snapshot data type conversion failed, falling back to computed: {type(e).__name__}: {e}"
                    )

        if portfolio is None:
            # FALLBACK: Compute portfolio from algo_positions + algo_trades when snapshot unavailable
            # This allows dashboard to show data even if orchestrator hasn't run Phase 9
            logger.info(
                "[PORTFOLIO] algo_portfolio_snapshots empty or unavailable, computing from algo_positions + algo_trades"
            )
            cur.execute("""
                SELECT
                  COUNT(DISTINCT symbol) as pos_count,
                  COALESCE(SUM(position_value), 0) as total_positions_value,
                  COALESCE(SUM(CASE WHEN status='closed' THEN quantity * current_price ELSE 0 END), 0) as closed_value
                FROM algo_positions
                WHERE status IN ('open', 'closed')
            """)
            pos_result = cur.fetchone()
            if pos_result:
                pos_result = safe_dict_convert(pos_result)
            pos_count = pos_result.get("pos_count") if pos_result else 0
            pos_value = float(pos_result.get("total_positions_value", 0)) if pos_result else 0.0
            closed_value = float(pos_result.get("closed_value", 0)) if pos_result else 0.0

            # Get initial cash from portfolio snapshot if available, else use default
            # CRITICAL: algo_trades table does NOT have initial_cash column
            # Use default of $100,000 (standard Alpaca paper trading starting balance)
            # This is a reasonable assumption for paper trading accounts
            initial_cash = 100000.0

            # Try to get actual initial balance from first portfolio snapshot if available
            cur.execute("""
                SELECT total_portfolio_value
                FROM algo_portfolio_snapshots
                ORDER BY created_at ASC LIMIT 1
            """)
            first_snapshot = cur.fetchone()
            if first_snapshot:
                first_snapshot = safe_dict_convert(first_snapshot)
            if first_snapshot and first_snapshot.get("total_portfolio_value"):
                try:
                    # If we have a first snapshot, use its value as our baseline
                    # This represents the portfolio value at the very beginning
                    initial_cash = float(first_snapshot["total_portfolio_value"])
                except (ValueError, TypeError):
                    pass  # Fall back to default if conversion fails

            # Compute cash as: initial - (all positions value) + (closed positions)
            total_spent = pos_value
            tc_float = initial_cash - total_spent + closed_value
            pv = tc_float + pos_value

            portfolio = {
                "total_portfolio_value": format_decimal_string(pv, precision=2, allow_none=True),
                "total_cash": format_decimal_string(tc_float, precision=2),
                "position_count": int(pos_count),
                "daily_return_pct": None,  # Unavailable without snapshot
                "unrealized_pnl_pct": None,  # Unavailable without snapshot
                "unrealized_pnl_dollars": None,  # Unavailable without snapshot
            }
            logger.info(f"[PORTFOLIO] Computed: total_value={pv:.2f}, cash={tc_float:.2f}, positions={pos_count}")

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        import traceback

        logger.error(f"[_GET_ALGO_STATUS] Exception: {type(e).__name__}: {e}\nTraceback: {traceback.format_exc()}")
        code, error_type, message = handle_db_error(e, "fetch portfolio data")
        return error_response(code, error_type, message)

    # CRITICAL FIX: Check freshness for BOTH algo_audit_log AND algo_portfolio_snapshots
    # Root cause of "portfolio stale" errors: only audit_log was checked, allowing 24h-old portfolio data
    audit_freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
    portfolio_freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)

    # Use portfolio freshness as the primary freshness indicator (data_freshness returned to frontend)
    # Include both checks in response so frontend can detect stale portfolio data
    combined_freshness = portfolio_freshness.copy() if portfolio_freshness else {}
    combined_freshness["audit_log_freshness"] = audit_freshness

    # Map audit status to success boolean for API contract
    # Status can be: "success", "halted", "error", or other phase-specific statuses
    success = row["status"] == "success" if row["status"] else False

    return json_response(
        200,
        {
            "run_id": row["run_id"],
            "success": success,
            "last_run": row["action_date"].isoformat() if row["action_date"] else None,
            "current_phase": row["action_type"],
            "status": row["status"],
            "message": row["message"],
            "portfolio": portfolio,
            "data_freshness": combined_freshness,
        },
    )


@db_route_handler("fetch algo trades")
@validate_api_response("trades")
def _get_algo_trades(cur: cursor, limit: int = 200, user_id: str | None = None, status: str | None = None) -> Any:
    """Get recent trades with all fields for frontend.

    Scoped to user if user_id provided, filtered by status if provided.
    """
    where_parts: list[str] = []
    params: list[Any] = []

    if user_id:
        where_parts.append("cognito_sub = %s")
        params.append(user_id)

    if status:
        # Validate status parameter to prevent SQL injection
        valid_statuses = ["open", "closed", "halted", "cancelled"]
        if status not in valid_statuses:
            logger.warning(f"Invalid trade status requested: {status}, ignoring filter")
            status = None
        else:
            where_parts.append("status = %s")
            params.append(status)

    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    params.append(limit)

    cur.execute(
        f"""
            SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_time,
                   entry_quantity, entry_reason, exit_price, exit_date, exit_time,
                   exit_reason, exit_r_multiple, profit_loss_dollars, profit_loss_pct,
                   status, base_type, stage_phase,
                   trade_duration_days, mfe_pct, mae_pct, created_at
            FROM algo_trades
            {where_clause}
            ORDER BY trade_date DESC, trade_id DESC
            LIMIT %s
        """,
        params,
    )
    trades = cur.fetchall()
    items = [safe_json_serialize(safe_dict_convert(t)) for t in trades]
    freshness = check_data_freshness(cur, "algo_trades", "created_at", warning_days=1)
    response_data = {
        "items": items,
        "pagination": {"total": len(items), "limit": limit, "offset": 0},
    }
    sanitized = APIResponseValidator.sanitize_response(response_data)

    # FIX: Pass freshness separately to json_response so it's included in response
    return json_response(200, sanitized, data_freshness=freshness)


@db_route_handler("fetch circuit breakers")
@validate_api_response("cb")
def _get_circuit_breakers(cur: cursor) -> Any:  # noqa: C901
    """Get real-time circuit breaker state with current values vs thresholds."""
    try:
        today = date.today()
        breakers = []

        # CRITICAL: Validate required circuit breaker configuration tables exist
        required_tables = [
            "algo_portfolio_snapshots",
            "algo_trades",
            "market_health_daily",
            "algo_positions",
        ]
        missing_tables = []
        for table in required_tables:
            try:
                from utils.validation import assert_safe_table

                table_safe = assert_safe_table(table)
                cur.execute(psycopg2.sql.SQL("SELECT 1 FROM {} LIMIT 1").format(psycopg2.sql.Identifier(table_safe)))
            except psycopg2.errors.UndefinedTable:
                missing_tables.append(table)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Unexpected error checking table {table}: {type(e).__name__}: {e}")
                missing_tables.append(table)

        if missing_tables:
            logger.error(f"ALERT: Circuit breaker CRITICAL config tables missing: {missing_tables}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Data unavailable",
                    },
                    "errorType": "missing_critical_tables",
                    "message": (
                        f"Circuit breaker configuration incomplete: missing tables {missing_tables}. "
                        "Trading is disabled until data is available."
                    ),
                    "_error": (
                        f"Circuit breaker configuration incomplete: missing tables {missing_tables}. "
                        "Trading is disabled until data is available."
                    ),
                },
            )

        # Fetch pre-computed circuit breaker metrics from database
        # CRITICAL: Fail-fast if metrics are unavailable (don't default to 0 for trading safety)
        cbm_data = {}
        computed_at: datetime | None = None
        data_age_seconds: int | None = None
        data_stale: bool = False
        try:
            cur.execute(
                "SELECT portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct, open_risk_pct, "
                "consecutive_losses, vix_level, market_stage, check_date FROM circuit_breaker_status "
                "ORDER BY check_date DESC LIMIT 1"
            )
            cbm_row = cur.fetchone()
            if not cbm_row:
                logger.warning("Circuit breaker metrics unavailable (circuit_breaker_status table empty)")
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data unavailable",
                        },
                        "errorType": "missing_circuit_breaker_data",
                        "message": "Circuit breaker metrics unavailable. Trading disabled until data is available.",
                        "_error": "Circuit breaker metrics unavailable. Trading disabled until data is available.",
                    },
                )
            cbm_row = safe_dict_convert(cbm_row)

            # Extract check_date timestamp and calculate data age
            check_date = cbm_row["check_date"]
            if check_date is not None:
                # check_date is a trading date in ET timezone; convert to datetime at midnight ET
                from datetime import datetime as dt
                from zoneinfo import ZoneInfo

                et = ZoneInfo("America/New_York")
                computed_at = dt.combine(check_date, dt.min.time()).replace(tzinfo=et)
                now_et = datetime.now(et)
                data_age_seconds = int((now_et - computed_at).total_seconds())

                # On weekends/holidays, accept data from previous trading day
                from algo.infrastructure.market_calendar import MarketCalendar
                today_trading = MarketCalendar.is_trading_day(datetime.now().date())
                threshold_seconds = 86400 if today_trading else 259200  # 1 day if trading, 3 days if market closed
                data_stale = data_age_seconds > threshold_seconds

                if data_stale:
                    logger.critical(
                        f"[CIRCUIT_BREAKER_STALE] Data age {data_age_seconds}s (>{threshold_seconds}s). "
                        f"Trading halted. Computed at: {computed_at.isoformat()}"
                    )
                    return json_response(
                        503,
                        {
                            "breakers": [],
                            "any_triggered": True,  # Fail-closed: treat stale data as triggered
                            "triggered_count": 0,
                            "data_freshness": {
                                "data_age_seconds": data_age_seconds,
                                "is_stale": True,
                                "warning": (
                                    f"Circuit breaker data stale ({data_age_seconds}s old). "
                                    "Cannot proceed with risk assessment. Trading disabled."
                                ),
                            },
                            "errorType": "stale_circuit_breaker_data",
                            "message": (
                                f"Circuit breaker data is {data_age_seconds}s old (>{threshold_seconds}s threshold). "
                                "All trading halted until fresh metrics available."
                            ),
                            "_error": "Circuit breaker data stale. Trading disabled.",
                        },
                    )

            # Validate critical fields exist and are non-null (fail-closed)
            critical_fields = [
                "portfolio_drawdown_pct",
                "daily_loss_pct",
                "weekly_loss_pct",
                "open_risk_pct",
                "consecutive_losses",
                "market_stage",
                "vix_level",
            ]
            missing = [f for f in critical_fields if cbm_row[f] is None]
            if missing:
                logger.error(f"Circuit breaker critical fields missing: {missing}")
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "incomplete_circuit_breaker_data",
                        "message": f"Circuit breaker data incomplete (missing {', '.join(missing)}). Trading disabled.",
                        "_error": "Circuit breaker data incomplete. Trading disabled.",
                    },
                )

            cbm_data = {
                "drawdown": float(cbm_row["portfolio_drawdown_pct"]),
                "daily_loss": float(cbm_row["daily_loss_pct"]),
                "weekly_loss": float(cbm_row["weekly_loss_pct"]),
                "total_risk": float(cbm_row["open_risk_pct"]),
                "consecutive_losses": int(cbm_row["consecutive_losses"]),
                "vix_level": float(cbm_row["vix_level"]),  # VIX is optional
                "market_stage": int(cbm_row["market_stage"]),
            }
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
            Exception,
        ) as e:
            code, error_type, message = handle_db_error(e, "fetch circuit breaker metrics")
            return error_response(code, error_type, message)

        # CB1: Portfolio drawdown (from pre-computed metrics)
        try:
            dd = cbm_data["drawdown"]
            threshold_dd = 20.0
            breakers.append(
                {
                    "id": "drawdown",
                    "label": "Portfolio Drawdown",
                    "triggered": dd >= threshold_dd,
                    "current": dd,
                    "threshold": threshold_dd,
                    "unit": "%",
                    "description": f"Halt when drawdown from peak ≥ {threshold_dd:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB1 (drawdown) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (drawdown): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB2: Daily loss (from pre-computed metrics)
        try:
            daily_loss = cbm_data["daily_loss"]
            threshold_dl = 2.0
            breakers.append(
                {
                    "id": "daily_loss",
                    "label": "Daily Loss",
                    "triggered": daily_loss >= threshold_dl,
                    "current": daily_loss,
                    "threshold": threshold_dl,
                    "unit": "%",
                    "description": f"Halt when today's loss ≥ {threshold_dl:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB2 (daily_loss) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (daily_loss): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB3: Consecutive losses (from pre-computed metrics)
        try:
            streak = cbm_data["consecutive_losses"]
            threshold_cl = 3
            breakers.append(
                {
                    "id": "consecutive_losses",
                    "label": "Consecutive Losses",
                    "triggered": streak >= threshold_cl,
                    "current": streak,
                    "threshold": threshold_cl,
                    "unit": "",
                    "description": f"Halt after {threshold_cl} consecutive losing trades",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB3 (consecutive_losses) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (consecutive_losses): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB4: VIX spike (from pre-computed metrics)
        # CRITICAL: Fail-fast if VIX unavailable (market volatility essential for trading risk assessment)
        try:
            if not cbm_data:
                raise ValueError("Circuit breaker metrics data missing")
            vix = cbm_data["vix_level"]
            if vix is None:
                logger.error(
                    "[CB4 CRITICAL] VIX level is NULL. Cannot assess market volatility/fear. Trading disabled."
                )
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "missing_vix_data",
                        "message": "VIX data unavailable. Market volatility metrics required for risk assessment. "
                        "Trading disabled.",
                        "_error": "VIX data unavailable. Trading disabled.",
                    },
                )
            threshold_vix = 35.0
            breakers.append(
                {
                    "id": "vix_spike",
                    "label": "VIX Spike",
                    "triggered": vix >= threshold_vix,
                    "current": vix,
                    "threshold": threshold_vix,
                    "unit": "",
                    "description": f"Halt when VIX ≥ {threshold_vix:.0f} (extreme fear)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB4 (vix_spike) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "vix_computation_error",
                    "message": f"VIX computation error: {e!s}. Market volatility data unavailable.",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB5: Weekly portfolio loss (from pre-computed metrics)
        try:
            weekly_loss = cbm_data["weekly_loss"]
            threshold_wl = 5.0
            breakers.append(
                {
                    "id": "weekly_loss",
                    "label": "Weekly Loss",
                    "triggered": weekly_loss >= threshold_wl,
                    "current": weekly_loss,
                    "threshold": threshold_wl,
                    "unit": "%",
                    "description": f"Halt when 7-day loss ≥ {threshold_wl:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB5 (weekly_loss) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (weekly_loss): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB6: Market stage break (Stage 4 = downtrend) (from pre-computed metrics)
        try:
            stage = cbm_data["market_stage"]
            breakers.append(
                {
                    "id": "market_stage",
                    "label": "Market Stage",
                    "triggered": stage == 4,
                    "current": stage,
                    "threshold": 4,
                    "unit": "",
                    "description": "Halt when market enters Stage 4 (confirmed downtrend)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB6 (market_stage) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (market_stage): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB7: Total open risk (from pre-computed metrics)
        try:
            risk_pct = cbm_data["total_risk"]
            threshold_risk = 4.0
            breakers.append(
                {
                    "id": "total_risk",
                    "label": "Total Open Risk",
                    "triggered": risk_pct >= threshold_risk,
                    "current": risk_pct,
                    "threshold": threshold_risk,
                    "unit": "%",
                    "description": f"Halt when total open risk ≥ {threshold_risk:.0f}% of portfolio",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB7 (total_risk) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (total_risk): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB8: Intraday market health (SPY down >2% yesterday)
        # CRITICAL: Fail-fast if SPY price data missing (market health essential for trading)
        try:
            cur.execute(
                """
                    SELECT close FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 2
                """,
                (today,),
            )
            prices = cur.fetchall()
            if len(prices) < 2:
                logger.error(
                    "[CB8 CRITICAL] SPY price history insufficient (%d prices, need 2). "
                    "Cannot assess market health for trading decisions. Trading disabled.",
                    len(prices),
                )
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "missing_spy_price_data",
                        "message": "SPY price data insufficient. Market health assessment required for trading. "
                        "Trading disabled.",
                        "_error": "SPY price data unavailable. Trading disabled.",
                    },
                )
            latest = float(prices[0][0])
            prior = float(prices[1][0])
            if not (latest > 0 and prior > 0):
                raise ValueError(f"Invalid SPY prices: latest={latest}, prior={prior}")
            market_change = (latest - prior) / prior * 100
            threshold_mc = -2.0
            breakers.append(
                {
                    "id": "intraday_health",
                    "label": "Prior-Day Market Health",
                    "triggered": market_change <= threshold_mc,
                    "current": round(market_change, 2),
                    "threshold": threshold_mc,
                    "unit": "%",
                    "description": f"Halt if SPY dropped >{abs(threshold_mc):.0f}% yesterday (await stability)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB8 (intraday_health) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "market_health_computation_error",
                    "message": f"SPY price computation error: {e!s}. Market health unavailable.",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB9: Win rate floor
        try:
            # Get win/loss stats from centralized data query (single source of truth)
            wr_stats = get_trade_win_loss_stats(cur, limit=30)
            # Fail-fast: Check for missing data explicitly. None means no trades (insufficient data),
            # not "zero wins". Do not convert to 0 (silent fallback).
            wins = wr_stats["wins"]
            losses = wr_stats["losses"]
            total = wr_stats["total"]
            win_rate = None
            threshold_wr = 40.0

            # Only compute win_rate if we have actual data (all values non-None)
            decisive = None
            if total is not None and total > 0 and wins is not None and losses is not None:
                decisive = wins + losses
                if decisive > 0:
                    win_rate = wins / decisive * 100

            if win_rate is not None and total is not None and total > 0 and decisive is not None and decisive >= 10:
                breakers.append(
                    {
                        "id": "win_rate",
                        "label": "Win Rate Floor",
                        "triggered": win_rate < threshold_wr,
                        "current": round(win_rate, 1),
                        "threshold": threshold_wr,
                        "unit": "%",
                        "description": f"Halt if win rate drops below {threshold_wr:.0f}% (last 30 closed)",
                    }
                )
            else:
                breakers.append(
                    {
                        "id": "win_rate",
                        "label": "Win Rate Floor",
                        "triggered": False,
                        "current": None,
                        "threshold": threshold_wr,
                        "unit": "%",
                        "description": "Insufficient trades to calculate win rate",
                    }
                )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB9 (win_rate) computation failed: {type(e).__name__}: {e}")
            breakers.append(
                {
                    "id": "win_rate",
                    "label": "Win Rate Floor",
                    "triggered": False,
                    "current": None,
                    "threshold": 40,
                    "unit": "%",
                    "description": "Insufficient closed trades (need 10+)",
                }
            )

        any_halted = any(b["triggered"] for b in breakers)
        triggered_count = sum(1 for b in breakers if b["triggered"])
        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)

        # Enrich all breakers with data staleness information
        # CRITICAL: Include computed_at age and staleness flag for frontend to detect stale VIX/market_stage
        # FIX: Add data_unavailable flag when data_age_seconds is null (computation failed)
        for breaker in breakers:
            # Add staleness metadata to each breaker
            breaker["data_age_seconds"] = data_age_seconds
            breaker["data_stale"] = data_stale

            # Add explicit data_unavailable flag when age couldn't be computed
            if data_age_seconds is None:
                breaker["data_unavailable"] = True
                breaker["staleness_warning"] = "Circuit breaker computation date unavailable - cannot assess data age"
            elif data_stale:
                breaker["data_unavailable"] = False
                breaker["staleness_warning"] = (
                    f"Data is {data_age_seconds}s old (>{3600}s threshold). "
                    "Consider this breaker unreliable for trading decisions."
                )
            else:
                breaker["data_unavailable"] = False
                breaker["staleness_warning"] = None

            # Format decimal values for consistent API response
            if breaker["unit"] == "%":
                breaker["current"] = format_decimal_string(breaker["current"], precision=2, allow_none=True)
                breaker["threshold"] = format_decimal_string(breaker["threshold"], precision=2, allow_none=False)
            elif breaker["unit"] == "" and breaker["id"] == "vix_spike":
                breaker["current"] = format_decimal_string(breaker["current"], precision=2, allow_none=True)
                breaker["threshold"] = format_decimal_string(breaker["threshold"], precision=2, allow_none=False)

        # Enhance freshness metadata with circuit breaker-specific staleness data
        cb_freshness = freshness.copy() if freshness else {}
        cb_freshness["circuit_breaker_data_age_seconds"] = data_age_seconds
        cb_freshness["circuit_breaker_computed_at"] = computed_at.isoformat() if computed_at else None

        cb_response = {
            "breakers": breakers,
            "any_triggered": any_halted,
            "triggered_count": triggered_count,
            "data_freshness": cb_freshness,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return json_response(200, cb_response)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch circuit breakers")
        return error_response(code, error_type, message)


@db_route_handler("fetch dashboard signals")
@validate_api_response("sig")
def _get_dashboard_signals(cur: cursor) -> Any:
    """Get dashboard-specific signal data from algo_signals table.

    Queries algo_signals (populated by orchestrator Phase 8) instead of
    buy_sell_daily (legacy table that's no longer populated). Returns active signals
    ranked by signal_quality_score, grade distribution, near-miss signals, and 7-day trend.
    """
    try:
        cur.execute("SET LOCAL statement_timeout = '20000ms'")

        # Fetch active signals from algo_signals (source of truth from orchestrator Phase 8)
        cur.execute("""
            SELECT COUNT(*) AS n, MAX(signal_date) AS d
            FROM algo_signals
            WHERE signal_active = true AND signal_date >= CURRENT_DATE - 7
        """)
        sig = cur.fetchone()
        if sig is not None:
            sig = safe_dict_convert(sig)
        if sig is None or sig.get("n") is None or sig.get("n") == 0:
            # No signals available - return empty response instead of error
            logger.info("[DASHBOARD SIGNALS] No active signals found in last 7 days")
            sig_response = {
                "n": 0,
                "total": 0,
                "date": None,
                "buy_sigs": [],
                "near": [],
                "top_a": [],
                "grades": {"a": 0, "b": 0, "c": 0, "d": 0, "total": 0},
                "trend": [],
                "data_freshness": {"data_age_days": None, "is_stale": False, "max_date": None, "warning": None},
            }
            # Ensure empty response is also JSON-serializable
            sig_response = safe_json_serialize(sig_response)
        else:
            total_n = int(sig["n"])

            # Top active signals with quality scores - cast date to text at source
            cur.execute("""
                SELECT s.symbol, s.signal_quality_score,
                       cp.sector, s.entry_price,
                       s.signal_date::text as signal_date
                FROM algo_signals s
                LEFT JOIN company_profile cp ON cp.ticker = s.symbol
                WHERE s.signal_active = true AND s.signal_date >= CURRENT_DATE - 7
                ORDER BY COALESCE(s.signal_quality_score, 0) DESC NULLS LAST
                LIMIT 30
            """)
            buy_sigs = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Grade distribution (A/B/C/D by signal_quality_score from algo_signals)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE s.signal_quality_score >= 80) AS a,
                    COUNT(*) FILTER (WHERE s.signal_quality_score >= 60 AND s.signal_quality_score < 80) AS b,
                    COUNT(*) FILTER (WHERE s.signal_quality_score >= 40 AND s.signal_quality_score < 60) AS c,
                    COUNT(*) FILTER (WHERE s.signal_quality_score < 40 OR s.signal_quality_score IS NULL) AS d,
                    COUNT(*) AS total
                FROM algo_signals s
                WHERE s.signal_active = true AND s.signal_date >= CURRENT_DATE - 7
            """)
            grades_r = cur.fetchone()
            grades = (
                safe_json_serialize(safe_dict_convert(grades_r))
                if grades_r
                else {"a": 0, "b": 0, "c": 0, "d": 0, "total": 0}
            )

            # Near-misses: signals with decent scores (55-69 range)
            cur.execute("""
                SELECT s.symbol, s.signal_quality_score AS score, cp.sector
                FROM algo_signals s
                LEFT JOIN company_profile cp ON cp.ticker = s.symbol
                WHERE s.signal_active = true AND s.signal_date >= CURRENT_DATE - 7
                  AND s.signal_quality_score BETWEEN 55 AND 69
                ORDER BY s.signal_quality_score DESC NULLS LAST
                LIMIT 15
            """)
            near = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Top A-grade signals (score >= 80)
            cur.execute("""
                SELECT s.symbol, s.signal_quality_score AS score
                FROM algo_signals s
                WHERE s.signal_active = true AND s.signal_date >= CURRENT_DATE - 7
                  AND s.signal_quality_score >= 80
                ORDER BY s.signal_quality_score DESC NULLS LAST
                LIMIT 20
            """)
            top_a = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Signal count trend: last 7 days - cast date to text at source
            cur.execute("""
                SELECT s.signal_date::text as date,
                       COUNT(*) FILTER (WHERE s.signal_quality_score >= 60 OR s.signal_quality_score IS NULL) AS buy_n,
                       COUNT(*) AS total_n
                FROM algo_signals s
                WHERE s.signal_active = true AND s.signal_date >= CURRENT_DATE - 7
                GROUP BY s.signal_date
                ORDER BY s.signal_date DESC
                LIMIT 7
            """)
            trend = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Count qualifying high-quality signals (score >= 70)
            cur.execute("""
                SELECT COUNT(*) AS n
                FROM algo_signals s
                WHERE s.signal_active = true AND s.signal_date >= CURRENT_DATE - 7
                  AND s.signal_quality_score >= 70
            """)
            count_row = cur.fetchone()
            if count_row:
                count_row = safe_dict_convert(count_row)
            qualifying_buy_count = int(count_row["n"]) if count_row and count_row.get("n") else 0

            freshness = check_data_freshness(cur, "algo_signals", "signal_date", warning_days=1)
            # Ensure freshness dict has dates as strings (check_data_freshness converts them, but be explicit)
            if freshness and "max_date" in freshness and freshness["max_date"] is not None:
                freshness["max_date"] = str(freshness["max_date"])
            freshness = safe_json_serialize(freshness)

            # Cast date to string at source
            sig_date = None
            if sig and sig.get("d"):
                sig_date = str(sig["d"])

            sig_response = {
                "n": qualifying_buy_count,
                "total": total_n,
                "date": sig_date,
                "buy_sigs": buy_sigs[:15] if buy_sigs else [],
                "near": near[:8] if near else [],
                "top_a": top_a[:20] if top_a else [],
                "grades": grades,
                "trend": trend,
                "data_freshness": freshness,
            }

        return json_response(200, sig_response)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch dashboard signals")
        return error_response(code, error_type, message)


@db_route_handler("fetch dashboard scores")
@validate_api_response("scores")
def _get_dashboard_scores(cur: cursor, limit: int = 50) -> Any:
    """Get top stock scores with composite and component scores for dashboard."""
    try:
        # Allow 25 seconds for query to complete (safe before API Gateway limit)
        cur.execute("SET LOCAL statement_timeout = '25000ms'")
        cur.execute(
            """
            SELECT symbol, composite_score, growth_score, momentum_score,
                   quality_score, value_score, stability_score, positioning_score,
                   data_completeness, updated_at
            FROM stock_scores
            WHERE composite_score > 0
            AND data_completeness >= 70
            ORDER BY composite_score DESC
            LIMIT %s
        """,
            (limit,),
        )
        rows = cur.fetchall()
        logger.info(f"[SCORES] Direct query returned {len(rows)} rows")

        top_scores = []
        for row in rows:
            score_dict = safe_json_serialize(safe_dict_convert(row))
            top_scores.append(score_dict)

        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=1)

        response = {
            "top": top_scores,
            "total": len(top_scores),
        }

        return json_response(200, response, data_freshness=freshness, preserve_arrays=True)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch dashboard scores")
        return error_response(code, error_type, message)


@db_route_handler("fetch equity curve")
def _get_equity_curve(cur: cursor, days: int = 180) -> Any:
    """Get equity curve for last N days."""
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        cur.execute(
            """
                WITH snapshots AS (
                    SELECT snapshot_date, total_portfolio_value, total_cash,
                           unrealized_pnl_total, position_count, daily_return_pct,
                           MAX(total_portfolio_value) OVER (
                               ORDER BY snapshot_date ASC
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                           ) AS running_peak
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= %s AND total_portfolio_value > 0
                )
                SELECT snapshot_date, total_portfolio_value, total_cash,
                       unrealized_pnl_total, position_count, daily_return_pct,
                       ROUND(
                           (total_portfolio_value - running_peak) / NULLIF(running_peak, 0) * 100,
                           4
                       ) AS drawdown_pct
                FROM snapshots
                ORDER BY snapshot_date DESC
                LIMIT 1000
            """,
            (cutoff_date,),
        )
        curve = cur.fetchall()
        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
        return list_response(
            [safe_json_serialize(safe_dict_convert(c)) for c in reversed(curve) if c is not None],
            data_freshness=freshness,
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch equity curve")
        return error_response(code, error_type, message)
