"""Market-breadth scan (_get_markets) route handler, extracted from
lambda/api/routes/algo_handlers/market.py (2026-09-05, file-size ratchet: that file is a
Tier-2 bloater flagged for decomposition). Body is verbatim, no logic changed - only moved
file. Imported back into market.py (re-exported) since lambda/api/routes/algo.py and several
tests reference it as market.py's own attribute.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, cast

import psycopg2
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

from .signals import _TIER_CONFIG

logger = logging.getLogger(__name__)


@db_route_handler("get markets")
@validate_api_response("mkt")
def _get_markets(cur: cursor) -> Any:  # noqa: C901
    try:
        # Latest exposure row (skip non-trading days to get last valid trading day)
        cur.execute("""
                SELECT date, exposure_pct, raw_score, regime, factors, halt_reasons, distribution_days
                FROM market_exposure_daily
                WHERE date <= CURRENT_DATE
                ORDER BY date DESC
                LIMIT 1
            """)
        row = cur.fetchone()

        if not row:
            return error_response(503, "data_unavailable", "Market exposure data not yet available")

        row = safe_json_serialize(safe_dict_convert(row))

        halt_reasons = []
        if row.get("halt_reasons"):
            try:
                halt_reasons = (
                    json.loads(row["halt_reasons"]) if isinstance(row["halt_reasons"], str) else row["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                halt_reasons = []

        factors = {}
        if row.get("factors"):
            try:
                factors_val = json.loads(row["factors"]) if isinstance(row["factors"], str) else row["factors"]
                factors = factors_val if isinstance(factors_val, dict) else {}
            except (json.JSONDecodeError, TypeError):
                factors = {}

        regime_val = row.get("regime")
        if regime_val is None or regime_val == "":
            logger.error(
                f"[MARKETS API] CRITICAL: market regime is missing or empty for {row.get('date')}. "
                f"Cannot determine risk tier for position sizing (affects exposure caps 25-100%). "
                f"Check: market_exposure_daily table, load_market_exposure_daily logs."
            )
            return error_response(
                503,
                "data_unavailable",
                "Market regime data unavailable - cannot determine risk tier for position sizing",
            )
        tier_key = str(regime_val).lower()
        tier_conf = _TIER_CONFIG.get(tier_key)
        if tier_conf is None:
            logger.error(
                f"[MARKETS API] CRITICAL: No tier configuration for regime '{tier_key}'. "
                f"Regime value from market_exposure_daily does not map to TIER_CONFIG. "
                f"Database or configuration mismatch."
            )
            return error_response(
                503,
                "data_unavailable",
                f"Unknown market regime '{tier_key}' - cannot apply risk tier constraints",
            )
        active_tier = {"name": tier_key, **tier_conf}
        if "halt" not in tier_conf:
            logger.error(
                f"[MARKETS API] Tier config for '{tier_key}' missing 'halt' field. "
                f"Configuration incomplete-cannot determine entry eligibility rules."
            )
            return error_response(
                500,
                "configuration_error",
                f"Tier configuration incomplete for '{tier_key}'",
            )
        active_tier["halt"] = bool(halt_reasons) or tier_conf["halt"]

        # History: last 90 sessions for ExposureHistory chart (skip non-trading days)
        history = []
        history_data_unavailable = False
        try:
            cur.execute("""
                    SELECT date, exposure_pct, regime, distribution_days
                    FROM market_exposure_daily
                    WHERE date <= CURRENT_DATE
                    ORDER BY date DESC
                    LIMIT 90
                """)
            for h in cur.fetchall():
                try:
                    h = safe_json_serialize(safe_dict_convert(h))
                    d = h.get("date")
                    history.append(
                        {
                            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                            "exposure_pct": (float(h["exposure_pct"]) if h.get("exposure_pct") is not None else None),
                            "regime": h.get("regime"),
                            "distribution_days": h.get("distribution_days"),
                        }
                    )
                except Exception as hist_err:
                    logger.error(
                        f"[MARKETS_API] Failed to parse history item: {hist_err}. Marking history unavailable."
                    )
                    history_data_unavailable = True
                    break
        except Exception as h_err:
            logger.error(f"[MARKETS_API] Failed to fetch market history: {h_err}. History data unavailable.")
            history_data_unavailable = True

        # Sector rankings for SectorRotationMap
        sectors = []
        sectors_data_unavailable = False
        try:
            cur.execute("""
                    SELECT sector_name AS name, current_rank AS rank, rank_4w_ago, momentum_score AS momentum
                    FROM sector_ranking
                    WHERE date = (SELECT MAX(date) FROM sector_ranking WHERE date <= CURRENT_DATE)
                    ORDER BY current_rank ASC NULLS LAST
                """)
            for sr in cur.fetchall():
                try:
                    sr = safe_json_serialize(safe_dict_convert(sr))
                    sectors.append(
                        {
                            "name": sr.get("name"),
                            "rank": sr.get("rank"),
                            "rank_4w_ago": sr.get("rank_4w_ago"),
                            "momentum": (float(sr["momentum"]) if sr.get("momentum") is not None else None),
                        }
                    )
                except Exception as item_err:
                    logger.error(f"[MARKETS_API] Failed to parse sector item: {item_err}. Marking sectors unavailable.")
                    sectors_data_unavailable = True
                    break
        except Exception as se:
            logger.error(f"[MARKETS_API] Failed to fetch sector rankings: {se}. Sectors data unavailable.")
            sectors_data_unavailable = True

        # Fetch market health from market_health_daily for dashboard KPIs
        # Skip today if it's not a trading day (Saturday/Sunday or holiday)
        # Markets only have valid data on trading days
        market_health = {}
        try:
            cur.execute("""
                    SELECT date, market_trend, market_stage, vix_level, spy_change_pct,
                           up_volume_percent, advance_decline_ratio, new_highs_count,
                           new_lows_count, breadth_momentum_10d, put_call_ratio,
                           put_call_ratio_data_unavailable, put_call_ratio_unavailable_reason,
                           yield_curve_slope, yield_curve_data_unavailable, yield_curve_unavailable_reason,
                           fed_rate_environment
                    FROM market_health_daily
                    WHERE date <= CURRENT_DATE AND vix_level IS NOT NULL
                    ORDER BY date DESC LIMIT 1
                """)
            mh_row = cur.fetchone()
            if not mh_row:
                return error_response(
                    503,
                    "data_unavailable",
                    "Market health data not available (market_health_daily has no rows with valid VIX)",
                )
            market_health = safe_json_serialize(safe_dict_convert(mh_row))

            # VIX is guaranteed non-NULL from query filter (WHERE vix_level IS NOT NULL)
            vix_val = market_health.get("vix_level")
            if vix_val is None:
                logger.error(
                    "[MARKETS API] CRITICAL BUG: Query filtered for vix_level IS NOT NULL but got NULL. "
                    "This should never happen - indicates database or query logic error."
                )
                raise ValueError(
                    "Market health VIX validation failed (query logic error). Check API query and database state."
                )

            # Validate VIX is numeric and > 0 (VIX is never zero or negative)
            try:
                vix_float = float(vix_val)
                # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `vix_float <= 0` never
                # caught NaN/Inf (always False in Python) - the raise below silently never
                # fired for a NaN VIX, so this try block "succeeded" and a NaN VIX (this
                # dashboard's own docstring: "critical for position sizing") reached the
                # caller unvalidated.
                if math.isnan(vix_float) or math.isinf(vix_float) or vix_float <= 0:
                    raise ValueError(
                        f"VIX {vix_float} is invalid (must be > 0 and finite). Data quality issue in market_health_daily."
                    )
            except (ValueError, TypeError) as e:
                logger.error(
                    f"[MARKETS API] CRITICAL: VIX validation failed: {e}. "
                    f"Cannot parse VIX value: {vix_val} ({type(vix_val).__name__}). "
                    f"Market health validation requires numeric VIX > 0."
                )
                raise ValueError(f"VIX data invalid: {e}") from e

            pcr_val = market_health.get("put_call_ratio")
            pcr_stale_val = None
            pcr_stale_date = None
            if pcr_val is None and market_health.get("put_call_ratio_data_unavailable"):
                cur.execute("""
                    SELECT date, put_call_ratio FROM market_health_daily
                    WHERE put_call_ratio IS NOT NULL AND put_call_ratio_data_unavailable IS NOT TRUE
                    ORDER BY date DESC LIMIT 1
                """)
                stale_row = cur.fetchone()
                if stale_row:
                    stale_row = safe_dict_convert(stale_row)
                    pcr_stale_val = stale_row.get("put_call_ratio")
                    pcr_stale_date = stale_row.get("date")
                    if pcr_stale_val is not None:
                        try:
                            pcr_stale_val = float(pcr_stale_val)
                        except (ValueError, TypeError):
                            pcr_stale_val = None
                            pcr_stale_date = None
            market_health["put_call_ratio_stale_value"] = pcr_stale_val
            market_health["put_call_ratio_stale_date"] = str(pcr_stale_date) if pcr_stale_date else None

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as mhe:
            logger.error(f"CRITICAL: Failed to fetch market_health_daily: {mhe}")
            return error_response(
                503,
                "data_unavailable",
                f"Market health unavailable: {type(mhe).__name__}",
            )
        except ValueError as ve:
            logger.error(f"[MARKETS API] Market health validation failed: {ve}")
            return error_response(
                503,
                "data_unavailable",
                str(ve),
            )

        # Fetch latest SPY close for dashboard header (critical for position sizing)
        spy_close = None
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 1
            """)
            spy_row = cur.fetchone()
            if not spy_row:
                return error_response(503, "data_unavailable", "SPY price data not available")
            spy_row = safe_dict_convert(spy_row)
            if spy_row.get("close") is None:
                return error_response(503, "data_unavailable", "SPY price data not available")
            spy_close = float(spy_row["close"])
            # CRITICAL: Validate SPY price is reasonable (> 0)
            # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `spy_close <= 0` never
            # caught NaN/Inf (always False in Python).
            if math.isnan(spy_close) or math.isinf(spy_close) or spy_close <= 0:
                logger.error(
                    f"[MARKETS API] Invalid SPY close: {spy_close} <= 0. Data quality issue in price_daily table."
                )
                return error_response(503, "data_unavailable", f"Invalid SPY price data: {spy_close}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as spy_e:
            logger.error(f"CRITICAL: Failed to fetch SPY price: {spy_e}")
            return error_response(
                503,
                "data_unavailable",
                f"SPY price unavailable: {type(spy_e).__name__}",
            )

        current_date = row.get("date")

        # Capital routing (2026-08-24, user-directed /goal) - see algo/risk/capital_routing.py's
        # module docstring. Non-critical/optional - degrades gracefully, must not 503 this endpoint.
        capital_routing: dict[str, Any] = {"data_unavailable": True, "reason": "no_data"}
        try:
            cur.execute("""
                    SELECT date, exposure_pct, uninvested_capital_pct, gld_trend_up, ief_trend_up,
                           dbc_trend_up, gld_vol_20d, ief_vol_20d, dbc_vol_20d, gld_weight, ief_weight,
                           dbc_weight, cash_weight, move_index, move_veto, factors, data_unavailable, reason
                    FROM capital_routing_daily
                    WHERE date <= CURRENT_DATE
                    ORDER BY date DESC
                    LIMIT 1
                """)
            cr_row = cur.fetchone()
            if cr_row:
                cr_row = safe_json_serialize(safe_dict_convert(cr_row))
                if cr_row.get("data_unavailable"):
                    capital_routing = {
                        "data_unavailable": True,
                        "reason": cr_row.get("reason") or "data_unavailable",
                        "date": cr_row.get("date"),
                    }
                else:
                    cr_factors = {}
                    if cr_row.get("factors"):
                        try:
                            cr_factors_val = (
                                json.loads(cr_row["factors"])
                                if isinstance(cr_row["factors"], str)
                                else cr_row["factors"]
                            )
                            cr_factors = cr_factors_val if isinstance(cr_factors_val, dict) else {}
                        except (json.JSONDecodeError, TypeError):
                            cr_factors = {}
                    capital_routing = {
                        "data_unavailable": False,
                        "date": cr_row.get("date"),
                        "exposure_pct": (
                            float(cr_row["exposure_pct"]) if cr_row.get("exposure_pct") is not None else None
                        ),
                        "uninvested_capital_pct": (
                            float(cr_row["uninvested_capital_pct"])
                            if cr_row.get("uninvested_capital_pct") is not None
                            else None
                        ),
                        "gld_trend_up": cr_row.get("gld_trend_up"),
                        "ief_trend_up": cr_row.get("ief_trend_up"),
                        "dbc_trend_up": cr_row.get("dbc_trend_up"),
                        "gld_vol_20d": (
                            float(cr_row["gld_vol_20d"]) if cr_row.get("gld_vol_20d") is not None else None
                        ),
                        "ief_vol_20d": (
                            float(cr_row["ief_vol_20d"]) if cr_row.get("ief_vol_20d") is not None else None
                        ),
                        "dbc_vol_20d": (
                            float(cr_row["dbc_vol_20d"]) if cr_row.get("dbc_vol_20d") is not None else None
                        ),
                        "gld_weight": (float(cr_row["gld_weight"]) if cr_row.get("gld_weight") is not None else 0.0),
                        "ief_weight": (float(cr_row["ief_weight"]) if cr_row.get("ief_weight") is not None else 0.0),
                        "dbc_weight": (float(cr_row["dbc_weight"]) if cr_row.get("dbc_weight") is not None else 0.0),
                        "cash_weight": (float(cr_row["cash_weight"]) if cr_row.get("cash_weight") is not None else 1.0),
                        "move_index": (float(cr_row["move_index"]) if cr_row.get("move_index") is not None else None),
                        "move_veto": bool(cr_row.get("move_veto")),
                        "factors": cr_factors,
                    }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as cr_e:
            logger.warning(f"[MARKETS API] Capital routing fetch failed (non-fatal, optional): {cr_e}")
            capital_routing = {"data_unavailable": True, "reason": f"query_failed: {type(cr_e).__name__}"}

        # Validate vix_regime is present in factors; fail-fast if missing (critical market signal)
        # 2026-08-23 pillar redesign moved vix_regime from a top-level factors key to
        # factors.pillar_risk.components.vix_regime (see algo/risk/market_exposure.py's module
        # docstring) - this check must follow it or the endpoint would 503 on every call.
        pillar_risk_vix = ((factors.get("pillar_risk") or {}).get("components") or {}).get("vix_regime")
        if pillar_risk_vix is None:
            error_msg = (
                f"vix_regime missing/null in factors.pillar_risk.components for {current_date}: "
                f"market exposure computation has not completed successfully. "
                f"Check market_exposure_daily table and load_market_exposure_daily logs."
            )
            logger.error(f"[MARKETS API] {error_msg}")
            return error_response(503, "data_unavailable", error_msg)

        # distribution_days is a key market factor; fail-fast if missing
        try:
            dist_days_raw = row.get("distribution_days")
            if dist_days_raw is None:
                raise ValueError(
                    f"distribution_days missing from market_exposure_daily for {current_date}. "
                    f"Market exposure computation has not completed successfully. "
                    f"Check market_exposure_daily table and load_market_exposure_daily logs."
                )
        except ValueError as e:
            logger.error(f"[MARKETS API] Market data validation failed: {e}")
            return error_response(503, "data_unavailable", str(e))

        response_data = {
            "exposure_pct": (float(row["exposure_pct"]) if row.get("exposure_pct") is not None else None),
            "raw_score": (float(row["raw_score"]) if row.get("raw_score") is not None else None),
            "regime": row.get("regime"),
            "halt_reasons": halt_reasons,
            "distribution_days": int(dist_days_raw) if isinstance(dist_days_raw, (int, float)) else dist_days_raw,
            "factors": factors,
            "spy_close": spy_close,
            "date": (current_date.isoformat() if hasattr(current_date, "isoformat") else str(current_date)),
        }

        # Include spy_close in market_health as well (required by dashboard fetcher)
        market_health["spy_close"] = spy_close

        # Set put_call_ratio/yield_curve availability flags for dashboard fetcher.
        # Trust the loader's own *_data_unavailable columns (now selected above) rather than
        # re-deriving from NULL-ness - the two can diverge, and the same re-derive-from-NULL
        # anti-pattern already caused a real stale-value bug elsewhere in this codebase (see
        # algo/risk/market_factor_calculator.py). Only fall back to NULL-inference if the column
        # itself is missing (nullable, defaults to false, but be defensive for older rows).
        if market_health.get("put_call_ratio_data_unavailable") is None:
            market_health["put_call_ratio_data_unavailable"] = market_health.get("put_call_ratio") is None
        if market_health.get("yield_curve_data_unavailable") is None:
            market_health["yield_curve_data_unavailable"] = market_health.get("yield_curve_slope") is None

        # Build response with market data (not a list response)
        # Contract requires: spy_close, vix_level (required), plus optional market data fields
        vix_level = market_health.get("vix_level")
        response: dict[str, object] = {
            "statusCode": 200,
            "data": {
                "spy_close": spy_close,
                "vix_level": float(vix_level) if vix_level is not None else None,
                "current": response_data,
                "active_tier": active_tier,
                "history": history,
                "history_data_unavailable": history_data_unavailable,
                "sectors": sectors,
                "sectors_data_unavailable": sectors_data_unavailable,
                "capital_routing": capital_routing,
                "market_health": market_health,
                # Add breadth indicators at top level
                "adr": (
                    float(market_health.get("advance_decline_ratio"))
                    if market_health.get("advance_decline_ratio") is not None
                    else None
                ),
                "nh": (
                    int(market_health.get("new_highs_count"))
                    if market_health.get("new_highs_count") is not None
                    else None
                ),
                "nl": (
                    int(market_health.get("new_lows_count"))
                    if market_health.get("new_lows_count") is not None
                    else None
                ),
                "pcr": (
                    float(market_health.get("put_call_ratio"))
                    if market_health.get("put_call_ratio") is not None
                    else None
                ),
            },
        }

        # Add additional market indicators at top level
        data = cast(dict[str, Any], response["data"])
        data["bmom"] = (
            float(market_health.get("breadth_momentum_10d"))
            if market_health.get("breadth_momentum_10d") is not None
            else None
        )
        data["ycs"] = (
            float(market_health.get("yield_curve_slope"))
            if market_health.get("yield_curve_slope") is not None
            else None
        )
        data["fed"] = market_health.get("fed_rate_environment")

        # BUG FOUND 2026-08-17: this endpoint (the one the dashboard's fetch_market() actually
        # calls, /api/algo/markets - NOT the separate /api/algo/market singular endpoint) never
        # returned a real freshness signal for market_health_daily/market_exposure_daily. The
        # dashboard's MARKET panel (dashboard/panels/market.py) instead self-computed "age" from
        # the fetch's own datetime.now(ET) timestamp, which is always ~0 seconds old regardless
        # of how stale the underlying VIX/exposure data actually is - VIX and market regime
        # directly feed position sizing, so stale data here with zero warning is a real risk.
        # Mirrors the same fix already applied to the algo_positions/algo_trades/algo_signals
        # endpoints. Uses market_health_daily specifically (not market_exposure_daily) since
        # VIX/breadth data is the more failure-prone side of this combined payload.
        freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)

        return json_response(200, data, data_freshness=freshness)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(
            f"[MARKETS_HANDLER_ERROR] Failed to fetch markets: {type(e).__name__}: {e}\n"
            f"  Operation: Query market_exposure_daily\n"
            f"  Endpoint: GET /api/algo/markets\n"
            f"  Full Traceback:\n{error_trace}"
        )
        return error_response(
            503, "service_unavailable", f"Failed to fetch markets data: {type(e).__name__}: {str(e)[:100]}"
        )
