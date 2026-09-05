"""Algo dashboard handler: /api/algo/positions.

Split 2026-09-05 (file-size-ratchet compliance split of the original 2160-line
algo_handlers/dashboard.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/scores_handlers/). This module
holds only `_get_algo_positions` and its private response cache; the other six handlers
(`_get_algo_status`, `_get_algo_trades`, `_get_circuit_breakers`, `_get_dashboard_signals`,
`_get_dashboard_scores`, `_get_equity_curve`) live in their own sibling modules. All names
are re-exported from `algo_handlers/dashboard/__init__.py` so existing callers (e.g.
routes/algo.py's `from .algo_handlers.dashboard import (...)`) require zero changes. Pure
move, no logic changed.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    json_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from utils.validation import APIResponseValidator

# Response cache for expensive positions query - to avoid API Gateway timeout (30s limit)
# CRITICAL FIX (BLOCKER #5): Position sizing depends on current prices, so cache must be short
# OPTIMIZATION: positions cache reduces DB load (60s TTL) but BLOCKER #5 fix: max 5min for price-sensitive calcs
# - Before cache: Risk calculations were using 30-min-old prices, causing drift from target risk
# - After fix: Cache queries ALWAYS use latest portfolio/price state, no stale risk exposure
_positions_cache: dict[str, Any] = {"data": None, "timestamp": 0.0, "cache_ttl_seconds": 60}
_positions_cache_lock = threading.Lock()

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

    with _positions_cache_lock:
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
            cache_age_seconds = int(current_time - _positions_cache["timestamp"])
            logger.info(f"[POSITIONS] Returning cached response (age: {cache_age_seconds}s)")

            # CRITICAL: Add cache freshness metadata to cached response
            # Frontend needs to know response was cached, not just when underlying data was fetched
            cached_response = (
                _positions_cache["data"].copy()
                if isinstance(_positions_cache["data"], dict)
                else _positions_cache["data"]
            )
            if isinstance(cached_response, dict) and "body" in cached_response:
                # json_response format: {"statusCode": 200, "body": {...}}
                body = cached_response.get("body")
                if isinstance(body, dict):
                    if "data_freshness" not in body:
                        body["data_freshness"] = {}
                    if isinstance(body["data_freshness"], dict):
                        body["data_freshness"]["cache_age_seconds"] = cache_age_seconds
                        body["data_freshness"]["cache_ttl_seconds"] = _positions_cache["cache_ttl_seconds"]
                        body["data_freshness"]["from_cache"] = True

            return cached_response

    # Use 5-second timeout for main query - enrichment queries are non-critical so they
    # can timeout without blocking the response. Main algo_positions query must complete.
    cur.execute("SET LOCAL statement_timeout = '5000ms'")

    # Initialize alerts tracking early so it can be used throughout
    stale_alerts = []

    # Query algo_positions base table directly (NO get_open_positions function which is slow)
    # NOTE: query errors (including statement_timeout) are intentionally NOT caught here -
    # they must propagate to @db_route_handler so it can return a real 5xx instead of a
    # false "zero positions" 200 OK.
    # CRITICAL: Filter by user_id (cognito_sub) to prevent user A from seeing user B's positions
    if not user_id:
        raise ValueError("[AUTH CRITICAL] user_id (cognito_sub) required for positions query - authentication missing")
    cur.execute(
        """
        SELECT * FROM algo_positions
        WHERE status = 'open' AND cognito_sub = %s
        ORDER BY position_value DESC NULLS LAST
        LIMIT 1000
    """,
        (user_id,),
    )
    positions = cur.fetchall()
    logger.info(f"[POSITIONS] Direct algo_positions query returned {len(positions)} positions")

    if not positions:
        # 0 rows in algo_positions is NOT necessarily a sync failure: broker-held positions
        # opened outside the algo's own entry execution (e.g. manually, or pre-dating algo
        # tracking) are intentionally never INSERTed by sync_alpaca_positions (see
        # algo/infrastructure/alpaca_sync_manager.py) -- inserting them with a synthetic
        # asset_id-as-position_id created duplicate NULL-stop records that tripped the
        # circuit breaker. Distinguish that expected case from a genuine sync problem by
        # checking if algo_untracked_positions has any rows (LIVE COUNT, not stale snapshot).
        # CRITICAL: Filter by user_id to count only this user's untracked positions
        cur.execute("SELECT COUNT(*) FROM algo_untracked_positions WHERE cognito_sub = %s", (user_id,))
        untracked_count_row = cur.fetchone()
        broker_position_count = untracked_count_row[0] if untracked_count_row and untracked_count_row[0] else None
        if broker_position_count:
            logger.info(
                f"[POSITIONS] algo_positions has 0 open rows, but broker holds "
                f"{broker_position_count} position(s) in algo_untracked_positions (manual/external). "
                "This is expected, not a sync failure -- see "
                "alpaca_sync_manager.sync_alpaca_positions."
            )
            stale_alerts.append(
                f"⚠️ {broker_position_count} broker position(s) held outside algo tracking (manual/external). "
                "Shown in untracked_items section with no stop/target management."
            )
        else:
            logger.info(
                "[POSITIONS] algo_positions has 0 open rows and algo_untracked_positions empty - no open positions."
            )

    # FIX: Load sector/company_name from company_profile and technical scores from
    # trend_template_data for positions. algo_positions (the base table) does not carry
    # these columns at all -- they must be joined in here explicitly rather than relying
    # on algo_positions_with_risk, whose schema has drifted across many competing migrations.
    # CRITICAL: Enrichment queries must complete - if unavailable, fail-fast (no degradation)
    sector_map: dict[str, str] = {}
    company_name_map: dict[str, str] = {}
    technical_map: dict[str, dict[str, Any]] = {}
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
                # Set a separate, more generous timeout for enrichment queries (non-critical)
                # These may take longer and we don't want them to block positions response
                try:
                    cur.execute("SET LOCAL statement_timeout = '10000ms'")
                    # Build placeholders for SQL query
                    placeholders = ",".join(["%s"] * len(open_symbols))
                    cur.execute(
                        f"""
                        SELECT ticker, sector, short_name FROM company_profile
                        WHERE ticker IN ({placeholders})
                        """,
                        tuple(open_symbols),
                    )
                    for row in cur.fetchall():
                        row_dict = safe_dict_convert(row)
                        ticker = row_dict.get("ticker")
                        sector = row_dict.get("sector")
                        short_name = row_dict.get("short_name")
                        if ticker and sector:
                            sector_map[ticker] = sector
                        if ticker and short_name:
                            company_name_map[ticker] = short_name
                    logger.debug(
                        f"[POSITIONS] Loaded sector/name data for {len(sector_map)} symbols from company_profile"
                    )

                    cur.execute(
                        f"""
                        SELECT DISTINCT ON (symbol) symbol, weinstein_stage, minervini_trend_score
                        FROM trend_template_data
                        WHERE symbol IN ({placeholders}) AND data_unavailable IS NOT TRUE
                        ORDER BY symbol, date DESC
                        """,
                        tuple(open_symbols),
                    )
                    for row in cur.fetchall():
                        row_dict = safe_dict_convert(row)
                        ticker = row_dict.get("symbol")
                        if ticker:
                            technical_map[ticker] = {
                                "weinstein_stage": row_dict.get("weinstein_stage"),
                                "minervini_trend_score": row_dict.get("minervini_trend_score"),
                            }
                    logger.debug(
                        f"[POSITIONS] Loaded technical scores for {len(technical_map)} symbols from trend_template_data"
                    )
                except (psycopg2.errors.QueryCanceled, psycopg2.errors.OperationalError) as enrichment_error:
                    # Enrichment queries timed out or failed - FAIL-FAST
                    # Cannot return positions dashboard with incomplete enrichment data
                    error_msg = (
                        f"[POSITIONS API CRITICAL] Enrichment queries failed: {type(enrichment_error).__name__}. "
                        f"Cannot load sector/company profile/technical data required for complete position display. "
                        f"Check: (1) company_profile table, (2) trend_template_data availability, (3) database load"
                    )
                    logger.critical(error_msg)
                    return error_response(503, "enrichment_data_unavailable", error_msg)
    except Exception as e:
        logger.warning(
            f"[POSITIONS] Could not load company_profile/trend_template_data enrichment: {type(e).__name__}: {e}"
        )

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
            logger.error("[POSITIONS] Position missing symbol - skipping")
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
                f"(position_value, avg_entry_price, or current_price) - skipping"
            )
            filtered_positions_count += 1
            continue

        # CRITICAL: Reject NaN and Infinity values - these indicate data corruption
        # All position metrics must be valid positive numbers
        if math.isnan(pos_val) or math.isinf(pos_val):
            logger.warning(
                f"[POSITIONS] {symbol}: position_value is {pos_val} (NaN or Infinity) - data corruption - skipping"
            )
            filtered_positions_count += 1
            continue

        if math.isnan(entry) or math.isinf(entry):
            logger.warning(
                f"[POSITIONS] {symbol}: avg_entry_price is {entry} (NaN or Infinity) - data corruption - skipping"
            )
            filtered_positions_count += 1
            continue

        if math.isnan(cur_price) or math.isinf(cur_price):
            logger.warning(
                f"[POSITIONS] {symbol}: current_price is {cur_price} (NaN or Infinity) - data corruption - skipping"
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

        # distance_to_stop_pct / distance_to_t1_pct: how far (in %) the current price is
        # from the stop / first profit target. Distinct from ladder_pct_* above (a 0-100
        # normalized position across the full stop-to-target range) - these are simple,
        # direct risk-distance metrics the CLI dashboard panel (dashboard/panels/positions.py)
        # has always expected under these exact field names, but nothing ever produced them
        # (no such DB column, no prior computation here) - the "Dist%"/"T1->" columns on the
        # live TUI dashboard have always rendered blank. entry/cur_price are already validated
        # non-None above; stop/t1 are optional per-position (not every position has both set).
        try:
            d["distance_to_stop_pct"] = (
                round((cur_price - float(stop_raw)) / cur_price * 100, 2) if stop_raw is not None else None
            )
            d["distance_to_t1_pct"] = (
                round((float(t1_raw) - cur_price) / cur_price * 100, 2) if t1_raw is not None else None
            )
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.warning(f"[POSITION DATA QUALITY] {symbol}: distance-to-stop/t1 calculation failed: {e}")
            d["distance_to_stop_pct"] = None
            d["distance_to_t1_pct"] = None

        # Enrich with technical scores (weinstein_stage/minervini_trend_score live only in
        # trend_template_data, never on algo_positions itself)
        if d.get("weinstein_stage") is None and symbol in technical_map:
            d["weinstein_stage"] = technical_map[symbol]["weinstein_stage"]
        if d.get("minervini_trend_score") is None and symbol in technical_map:
            d["minervini_trend_score"] = technical_map[symbol]["minervini_trend_score"]
        if d.get("company_name") is None and symbol in company_name_map:
            d["company_name"] = company_name_map[symbol]

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
            # CRITICAL: Position has missing/invalid sector and not in company_profile.
            # This is a data quality issue that should FAIL, not silently continue with Unknown.
            # Cannot compute sector exposure risk without complete enrichment.
            error_msg = (
                f"Position {symbol} has missing/invalid sector ({current_sector!r}) "
                f"and not found in company_profile. Cannot proceed without sector enrichment. "
                f"Fix company_profile loader or remove position from portfolio."
            )
            logger.error(error_msg)
            return error_response(503, "sector_enrichment_incomplete", error_msg)

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
    # FAIL-FAST: All items must have position_value (no fallback to 0)
    for item in items:
        if "position_value" not in item or item["position_value"] is None:
            raise ValueError(f"[POSITIONS SORT] Item missing position_value: {item.get('symbol', '?')}")
    items.sort(key=lambda x: float(x["position_value"]), reverse=True)

    # OPTIMIZATION: Remove unnecessary NULL fields to reduce payload
    # Fields that are never populated or only used for closed positions
    unnecessary_fields = {
        "closed_at",  # Only for closed positions
        "cognito_sub",  # Not needed in API response
        "distribution_day_count",  # Not populated
        "exit_reason",  # Only for closed positions
        "initial_risk_per_share",  # Not populated
        "is_open",  # Always true for returned positions
        "ladder_scale_max",  # Not used by frontend
        "ladder_scale_min",  # Not used by frontend
        "profit_loss_dollars",  # Not populated
        "risk_pct",  # Not populated
        "risk_rank",  # Not populated
        "stage_in_exit_plan",  # Not populated
        "target_1_hit_time",  # Not used
        "target_2_hit_time",  # Not used
        "target_3_hit_time",  # Not used
        "trade_duration_days",  # Not populated
        "entry_price",  # Duplicate of avg_entry_price
    }
    before_count = len(items[0]) if items else 0
    removed_count = 0
    for item in items:
        for field in unnecessary_fields:
            if field in item:
                item.pop(field)
                removed_count += 1
    after_count = len(items[0]) if items else 0
    logger.info(
        f"[POSITIONS] Field cleanup: {before_count} -> {after_count} fields/pos, {removed_count} total fields removed"
    )

    # Compute sector_allocation array after processing all positions (E5 fix)
    # CRITICAL: Fail-fast if portfolio appears empty after position processing
    # Division-by-zero fallback (setting total=1) would create FAKE allocation percentages
    total_abs_value = sum(abs(v) for v in sector_risk.values())
    if total_abs_value == 0 and not items:
        # No open positions is a normal, expected state (already logged as such above at
        # "no open positions" / "held outside algo tracking") - not a data-quality failure.
        # This branch used to log it as "[POSITIONS CRITICAL]" via logger.error() regardless
        # of whether items was empty (flat portfolio, benign) or non-empty with zero-value
        # positions (genuinely suspicious), contradicting this same function's own earlier
        # handling of the identical zero-positions case and generating a false CRITICAL
        # alert - and a misleading "data incomplete" dashboard banner - on every flat day.
        logger.debug("[POSITIONS] No open positions - sector allocation is empty (not an error)")
        sector_allocation: list[dict[str, Any]] = []
    elif total_abs_value == 0:
        logger.error(
            "[POSITIONS CRITICAL] Portfolio allocation cannot be computed: "
            "total_abs_value is 0 after processing %d items with open positions. "
            "This indicates all positions have zero value or invalid sector data despite passing enrichment. "
            "Check: (1) Position values are non-zero? (2) sector_risk accumulation logic.",
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

    # Fetch untracked positions (broker-held, not entered by algo)
    untracked_items: list[dict[str, Any]] = []
    try:
        # CRITICAL: Filter by user_id to prevent user A from seeing user B's untracked positions
        cur.execute(
            """
            SELECT id, symbol, quantity, current_price, position_value, detected_at, last_seen_at
            FROM algo_untracked_positions
            WHERE cognito_sub = %s
            ORDER BY position_value DESC NULLS LAST
            LIMIT 1000
        """,
            (user_id,),
        )
        untracked_positions = cur.fetchall()
        logger.info(f"[UNTRACKED POSITIONS] Found {len(untracked_positions)} untracked positions")

        for up in untracked_positions:
            up_dict = safe_dict_convert(up)
            symbol = up_dict.get("symbol")

            if not symbol:
                logger.warning("[UNTRACKED] Position missing symbol - skipping")
                continue

            # Validate numeric fields (fail-fast on missing data)
            qty = up_dict.get("quantity")
            current_price = up_dict.get("current_price")
            position_value = up_dict.get("position_value")
            if qty is None or current_price is None or position_value is None:
                logger.warning(
                    f"[UNTRACKED] {symbol}: missing position data (qty={qty}, price={current_price}, value={position_value}) - skipping. "
                    "This position requires manual enrichment."
                )
                continue
            try:
                qty = float(qty)
                current_price = float(current_price)
                position_value = float(position_value)
            except (ValueError, TypeError):
                logger.warning(f"[UNTRACKED] {symbol}: invalid numeric fields - skipping")
                continue

            # Look up enrichment data (sector, company name, technical scores)
            # FAIL-FAST: Don't silently default - check for missing data
            sector = sector_map.get(symbol)
            if sector is None:
                logger.warning(
                    f"[UNTRACKED] {symbol}: sector enrichment missing - skipping. Data quality issue detected."
                )
                continue
            company_name = company_name_map.get(symbol)
            if company_name is None:
                logger.warning(
                    f"[UNTRACKED] {symbol}: company_name enrichment missing - skipping. Data quality issue detected."
                )
                continue
            technical = technical_map.get(symbol)
            if technical is None:
                logger.warning(
                    f"[UNTRACKED] {symbol}: technical enrichment missing - skipping. Data quality issue detected."
                )
                continue

            untracked_item = {
                "symbol": symbol,
                "position_source": "MANUAL",  # Flag for UI to show visually distinct
                "quantity": qty,
                "current_price": current_price,
                "position_value": position_value,
                "sector": sector,
                "company_name": company_name,
                "weinstein_stage": technical.get("weinstein_stage"),
                "minervini_trend_score": technical.get("minervini_trend_score"),
                "detected_at": up_dict.get("detected_at"),
                "last_seen_at": up_dict.get("last_seen_at"),
                # Untracked positions have no stop/target (managed externally)
                "stop_loss_price": None,
                "target_1_price": None,
                "target_2_price": None,
                "target_3_price": None,
                "unrealized_pnl": None,
                "unrealized_pnl_pct": None,
            }
            untracked_items.append(untracked_item)

        if untracked_items:
            stale_alerts.append(
                f"⚠️ {len(untracked_items)} position(s) held at broker but NOT managed by algo (manual/external entries). "
                f"These have no stop/target management."
            )

    except Exception as e:
        logger.error(f"[UNTRACKED POSITIONS] Failed to fetch untracked positions: {e}")
        # FAIL-FAST: Mark data unavailable instead of silently returning empty array
        stale_alerts.append(
            f"⚠️ UNTRACKED POSITIONS DATA UNAVAILABLE: Query failed ({type(e).__name__}). "
            f"Manual/external positions cannot be retrieved. Check database connectivity."
        )
        untracked_items = []

    response_data = {
        "items": items,
        "untracked_items": untracked_items,
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
    with _positions_cache_lock:
        _positions_cache["data"] = cached_response
        _positions_cache["timestamp"] = time.time()
    logger.info("[POSITIONS] Response cached for 60 seconds")

    return cached_response
