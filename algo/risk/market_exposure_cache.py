#!/usr/bin/env python3

"""Cache-read and persistence mixin for MarketExposure (algo/risk/market_exposure.py).

Split out of market_exposure.py's monolithic MarketExposure class as part of the
2026-09-05 bloater-decomposition pass (same mixin pattern established by
algo/monitoring/position_monitor.py's split, commit 1d8a64f73: cohesive method groups
pulled into sibling mixin files, MarketExposure inherits from all of them via multiple
inheritance). Mechanical split only - no behavior change; every method body here is
byte-identical (aside from the qualified DatabaseContext access explained below) to
what was previously directly on MarketExposure.

Holds the cache-read (`try_load_cached`) and cache-write (`_persist`) sides of
market_exposure_daily, plus the small `_with_cursor` DB-cursor helper that only
`try_load_cached` uses.

Qualified module-attribute access (`import algo.risk.market_exposure as _me`, then
`_me.DatabaseContext(...)`) is used instead of a plain `from utils.db import
DatabaseContext` import, because tests (tests/unit/test_market_exposure_weights.py,
tests/unit/test_market_exposure_compute_end_to_end_20260824.py) patch
`algo.risk.market_exposure.DatabaseContext` directly - a function's globals are bound to
whatever module it is physically defined in, so a name patched on the base module would
be invisible to a plain import in this file. Same technique, same reasoning, as
algo/monitoring/position_order_management.py's `import algo.monitoring.position_monitor
as _pm` / `_pm.time`/`_pm.requests`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.risk.market_exposure as _me
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MarketExposureCacheMixin:
    """Cache read/write for MarketExposure: try_load_cached, _persist, _with_cursor."""

    def _with_cursor(self, operation: Callable[[PsycopgCursor[Any]], T]) -> T:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with _me.DatabaseContext("read") as cur:  # type: ignore[attr-defined]
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def try_load_cached(self, eval_date: _date | None = None) -> dict[str, Any] | None:  # noqa: C901
        """Load cached market exposure for today. Returns dict or None if not cached/stale.

        CRITICAL: Validates cache freshness both by date AND by TTL. Never silently uses stale cache.
        - If cached_date != eval_date, reject (different day entirely)
        - If cached_date == eval_date but > 10 hours old, reject (computed too early, using stale market data)
        Stale cache causes incorrect risk allocation and must be detected + logged, not silently accepted.
        """
        if eval_date is None:
            # Eastern Time, not system-local date.today() - eval_date drives an exact
            # WHERE date = %s cache lookup below. Fixed defensively (2026-07-21 audit) to
            # match every other eval_date default in this codebase, whether or not this
            # specific default is reachable from the current call graph.
            eval_date = datetime.now(EASTERN_TZ).date()

        def fetch_cached(cur: PsycopgCursor[Any]) -> dict[str, Any] | None:  # noqa: C901
            cur.execute(
                """
                SELECT raw_score, exposure_pct, regime, halt_reasons, distribution_days, factors, date, updated_at
                FROM market_exposure_daily
                WHERE date = %s
                LIMIT 1
            """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row is None:
                logger.debug(f"No cached market exposure for {eval_date}")
                return {
                    "data_unavailable": True,
                    "reason": "no_cache_entry",
                    "eval_date": str(eval_date),
                }

            (
                raw_score,
                exposure_pct,
                regime,
                halt_reasons_str,
                dist_days,
                factors_obj,
                cached_date,
                updated_at,
            ) = row

            # Validate cache freshness: must be today's data (cached_date == eval_date)
            # If cached value is from a different date, it's stale and should not be used
            if cached_date != eval_date:
                msg = (
                    f"CRITICAL: Cached market exposure is stale - cached from {cached_date}, "
                    f"but requested for {eval_date}. Not using stale cache to prevent incorrect risk allocation. "
                    f"This requires recomputation (check Phase 4 data loader)."
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            # Stale cache (same day, but computed too long ago): treat as a cache MISS so
            # compute() falls through and recomputes fresh data below - this must NOT raise.
            # Raising here made compute() fail outright with no path to fresh computation:
            # once the morning run's cache aged past max_age, every later same-day call
            # (force_recompute=False, the real production default) would hit this branch
            # and abort before ever reaching the actual computation code, permanently
            # marking market data_unavailable for the rest of the day instead of refreshing
            # it - confirmed live 2026-07-20 (computed 7-8h ago, every call raised instead
            # of recomputing).
            if updated_at:
                # updated_at is written via SQL `NOW()` into a `timestamp without time zone`
                # column, so a naive value here is in the DB session's local wall-clock time
                # (utils/bulk_insert_manager.py's documented convention), not necessarily
                # Eastern - confirmed live this session's actual `SHOW timezone` is
                # America/Chicago, a full hour off Eastern during DST. Mislabeling it as
                # Eastern via .replace(tzinfo=EASTERN_TZ) silently inflated every cache-age
                # computed here by that offset. Same fix as lambda/api/routes/utils.py's
                # normalize_to_utc_datetime - resolve the real session timezone dynamically.
                if not updated_at.tzinfo:
                    from utils.db.timezone_utils import get_db_timezone

                    naive_tz = get_db_timezone()
                    updated_at = updated_at.replace(tzinfo=naive_tz)
                now = datetime.now(timezone.utc)
                age = now - updated_at
                max_age = timedelta(hours=2)
                if age > max_age:
                    logger.info(
                        f"[MARKET_EXPOSURE] Cached market exposure is stale (computed "
                        f"{age.total_seconds() / 3600:.1f}h ago, max {max_age.total_seconds() / 3600:.0f}h) - "
                        f"treating as cache miss, recomputing fresh."
                    )
                    return {
                        "data_unavailable": True,
                        "reason": "cache_stale",
                        "eval_date": str(eval_date),
                    }

            if halt_reasons_str:
                try:
                    halt_reasons = json.loads(halt_reasons_str)
                    if not isinstance(halt_reasons, list):
                        raise RuntimeError(
                            f"halt_reasons is not a list: {type(halt_reasons)}. "
                            f"Corrupted market exposure data cannot be trusted for trading."
                        )
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"Malformed halt_reasons JSON: {e}. "
                        f"Corrupted market exposure data cannot be trusted for trading."
                    ) from e
            else:
                halt_reasons = []

            if isinstance(factors_obj, dict):
                factors = factors_obj
            elif factors_obj:
                try:
                    factors = json.loads(factors_obj)
                    if not isinstance(factors, dict):
                        raise RuntimeError(
                            f"factors is not a dict: {type(factors)}. "
                            f"Corrupted market exposure data cannot be trusted for trading."
                        )
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"Malformed factors JSON: {e}. Corrupted market exposure data cannot be trusted for trading."
                    ) from e
            else:
                factors = {}

            # CRITICAL: Validate that all 3 pillars are present with real scores. Each
            # pillar is itself a blend of required sub-factors (see compute()), so
            # unlike the prior 19-factor design, a pillar being present at all already
            # implies its required inputs were available - there is no longer a
            # separate "optional top-level factor" list to enumerate here.
            required_pillars = {"pillar_trend", "pillar_risk", "pillar_confirm"}
            missing_factors = []
            invalid_factors = []

            for factor_name in required_pillars:
                if factor_name not in factors:
                    missing_factors.append(factor_name)
                    continue

                factor_data = factors[factor_name]
                if not isinstance(factor_data, dict):
                    invalid_factors.append(f"{factor_name} is not a dict")
                    continue

                # Check that factor has a points value (cached factors should have "pts")
                if "pts" not in factor_data:
                    invalid_factors.append(f"{factor_name} missing 'pts' field")
                    continue

                pts = factor_data.get("pts")
                if pts is None:
                    invalid_factors.append(f"{factor_name} has NULL 'pts' value")
                    continue

            if missing_factors or invalid_factors:
                msg = (
                    f"[CACHE VALIDATION] Cached exposure for {eval_date} is incomplete or corrupted. "
                    f"Cannot use stale/partial factor data for risk allocation."
                )
                if missing_factors:
                    msg += f" Missing factors: {', '.join(missing_factors)}."
                if invalid_factors:
                    msg += f" Invalid factors: {'; '.join(invalid_factors)}."
                msg += " Will recompute exposure with fresh data."
                logger.warning(msg)
                return {
                    "data_unavailable": True,
                    "reason": "corrupted_factors",
                    "eval_date": str(eval_date),
                    "missing": missing_factors,
                    "invalid": invalid_factors,
                }

            if dist_days is None:
                raise ValueError("Distribution days data missing; cannot assess institutional distribution risk")
            result = {
                "eval_date": str(eval_date),
                "raw_score": raw_score,
                "capped_score": exposure_pct,
                "exposure_pct": exposure_pct,
                "regime": regime,
                "halt_reasons": halt_reasons,
                "distribution_days": dist_days,
                "factors": factors,
                "_cached": True,
            }
            logger.info(f"[OK] Loaded cached market exposure for {eval_date}: {exposure_pct}% ({regime})")
            return result

        try:
            return self._with_cursor(fetch_cached)
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _persist(self, eval_date: _date, result: dict[str, Any]) -> None:
        try:
            # Validate required fields FIRST (fail-fast, before using them)
            if "distribution_days" not in result:
                raise ValueError("Market exposure result missing required 'distribution_days' field")
            if "factors" not in result or not isinstance(result["factors"], dict):
                raise ValueError("Market exposure result missing or invalid 'factors' field")
            if "halt_reasons" not in result or not isinstance(result["halt_reasons"], list):
                raise ValueError("Market exposure result missing or invalid 'halt_reasons' field")

            # Determine tier from regime
            regime = result.get("regime")
            if not regime:
                logger.critical(
                    "CRITICAL: Market regime calculation returned None. "
                    "Cannot determine market exposure tier without knowing regime. "
                    "Risk tier sizing will be wrong."
                )
                raise ValueError(
                    "Market exposure: regime result missing. Cannot calculate position size tier. "
                    "Market regime evaluation incomplete."
                )
            if regime == "confirmed_uptrend":
                tier = "tier_1_strong_uptrend"
            elif regime == "uptrend_under_pressure":
                tier = "tier_2_pressure"
            elif regime == "caution":
                tier = "tier_3_caution"
            else:
                tier = "tier_4_correction"

            # Can enter if no halt reasons (now safe because validated above)
            is_entry_allowed = len(result["halt_reasons"]) == 0

            # CRITICAL: Validate exposure_pct range before persisting
            # Position sizing tier assignments depend on values in 0-100 range
            exposure_pct = result["exposure_pct"]
            if exposure_pct < 0 or exposure_pct > 100:
                msg = (
                    f"[EXPOSURE VALIDATION CRITICAL] exposure_pct={exposure_pct} outside valid range [0,100]. "
                    f"Calculation error - cannot persist invalid value. "
                    f"Check: (1) factor scoring logic (should be 0-100), (2) cap calculations, "
                    f"(3) hard veto logic applying excessive caps"
                )
                logger.critical(msg)
                raise ValueError(msg)

            # Map exposure score to long/short allocations
            if exposure_pct >= 0:
                long_exp = exposure_pct
                short_exp = 0
            else:
                long_exp = 0
                short_exp = abs(exposure_pct)

            # result["factors"] is built up from sub-detector output dicts whose fields
            # aren't guaranteed to already be JSON-safe (raw DB dates, Decimals) -
            # default=str is the same standard, safe fallback used for archival JSON
            # columns elsewhere in this codebase (e.g. phase9_reconciliation.py's audit
            # log insert).
            factors_json = json.dumps(result["factors"], default=str)
            halt_reasons_json = json.dumps(result["halt_reasons"], default=str)
            regime = result.get("regime")
            if not regime:
                raise ValueError("Market regime calculation missing. Cannot build exposure summary.")
            if "raw_score" not in result:
                raise ValueError(
                    "Market exposure raw_score missing from calculation result. "
                    "Cannot persist exposure data without risk score."
                )
            with _me.DatabaseContext("write") as cur:  # type: ignore[attr-defined]
                cur.execute(
                    """
                    INSERT INTO market_exposure_daily
                        (date, exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons,
                         long_exposure_pct, short_exposure_pct, is_entry_allowed, exposure_tier,
                         data_unavailable, reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date) DO UPDATE SET
                        exposure_pct = EXCLUDED.exposure_pct,
                        raw_score = EXCLUDED.raw_score,
                        regime = EXCLUDED.regime,
                        distribution_days = EXCLUDED.distribution_days,
                        factors = EXCLUDED.factors,
                        halt_reasons = EXCLUDED.halt_reasons,
                        long_exposure_pct = EXCLUDED.long_exposure_pct,
                        short_exposure_pct = EXCLUDED.short_exposure_pct,
                        is_entry_allowed = EXCLUDED.is_entry_allowed,
                        exposure_tier = EXCLUDED.exposure_tier,
                        data_unavailable = EXCLUDED.data_unavailable,
                        reason = EXCLUDED.reason,
                        updated_at = NOW()
                    """,
                    (
                        eval_date,
                        exposure_pct,
                        result.get("raw_score"),
                        regime,
                        result["distribution_days"],
                        factors_json,
                        halt_reasons_json,
                        long_exp,
                        short_exp,
                        is_entry_allowed,
                        tier,
                        False,  # data_unavailable - explicitly FALSE on successful computation
                        None,  # reason - NULL on successful computation
                    ),
                )
            logger.info(
                f"persist market_exposure OK for {eval_date}: "
                f"{exposure_pct}% exposure ({tier}), "
                f"entry_allowed={is_entry_allowed}"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"persist market_exposure failed for {eval_date}: {e}", exc_info=True)
