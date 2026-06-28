#!/usr/bin/env python3

"""
Quantitative Market Exposure Engine - Research-backed 12-factor composite

Composite 0-100 portfolio risk allocation score. Factor selection and weights
derived from synthesis of academic momentum research (AQR/Moskowitz-Ooi-Pedersen),
Zweig breadth research, Weinstein stage analysis, AAII/NAAIM contrarian studies,
Apollo/Goldman credit cycle research, and Pan-Poteshman options flow research.

    15pt  TREND 30-WK MA        SPY price vs rising/flat/falling 30-week MA
    10pt  SPY 12-MONTH MOMENTUM trailing 12-month return (TSMOM — most replicated quant signal)
    10pt  BREADTH % > 200-DMA   long-term market participation (linear 30-80%)
    10pt  SELLING PRESSURE      heavy-volume down days in last 25 sessions: 0-2=1.0, 3-4=0.6, 5+=0.2
    10pt  VIX REGIME            level (<15/15-25/25-35/35+) + term structure (VIX3M/VIX ratio)
    10pt  CREDIT SPREADS        HY OAS (BAMLH0A0HYM2): credit leads equity (Apollo/Slok research)
     8pt  PUT/CALL RATIO        options market sentiment — contrarian at extremes (daily signal)
     7pt  NEW HIGHS - LOWS      market leadership quality (52-week NH vs NL)
     6pt  ADVANCE-DECLINE LINE  direction vs SPY over 20 days (confirmation/divergence)
     6pt  BREADTH % > 50-DMA   short-term market participation (linear 20-80%)
     5pt  NAAIM EXPOSURE        professional manager positioning (contrarian at extremes)
     3pt  AAII SENTIMENT        contrarian at extremes only (±15+ spread; neutral in middle range)

Removed factors vs prior version:
  - FOLLOW-THROUGH DAY (was 10pt): ~50% reliability per independent backtests
    (Quantifiable Edges, 37yr study); retained only as hard veto
  - MCCLELLAN OSCILLATOR (was 9pt): redundant with A/D line — both derive from
    advance/decline data; A/D line direction vs SPY is the less correlated signal

Breadth signal consolidation: prior version had 5 breadth signals at 45pt total,
all highly correlated. Now 4 signals at 26pt covering distinct information:
  % > 200-DMA (long-term regime), NH/NL (leadership), A/D line (direction),
  % > 50-DMA (short-term participation).

HARD VETOES (cap exposure at ≤25-40%):
  - SPY < rising 30-wk MA AND breadth_50 < 30%
  - VIX > 40 with rising trend
  - 6+ selling-pressure days in last 25 sessions
  - No market confirmation signal (volume-backed rally) while SPY below 30-week MA
  - HY credit spread > 8.5% (systemic stress)

ECONOMIC REGIME OVERLAY (penalty, not a factor; applied post-scoring):
  - Yield curve (T10Y2Y): inversion duration matters
  - Jobless claims trend (ICSA): rising claims precede recessions
  - St. Louis Financial Stress Index (STLFSI4): 18-variable composite
  - Chicago Fed National Activity Index (CFNAI): 85-indicator composite
  HY credit spread excluded from overlay (it is a direct 10pt factor above;
  including it in both places would double-count the same data series).

Output:
    market_exposure_pct (0-100): drives dynamic risk allocation
    state: 'confirmed_uptrend' | 'uptrend_under_pressure' | 'caution' | 'correction'
    factors: dict of each input + sub-score
    halt_reasons: list of any active hard vetoes

Persists daily to market_exposure_daily table for dashboard / audit.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime, time, timedelta
from typing import Any, TypeVar

import psycopg2
from psycopg2 import sql as pgsql
from psycopg2.extensions import cursor as PsycopgCursor  # noqa: N812

from algo.infrastructure import MarketCalendar
from algo.risk.market_factor_calculator import MarketFactorCalculator
from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MarketExposure:
    """Quantitative market regime + exposure % computation."""

    # Factor weights (sum = 100)
    W_TREND_30WK = 15
    W_SPY_MOMENTUM = 10  # 12-month TSMOM (replaces follow-through day)
    W_BREADTH_200 = 10
    W_SELLING_PRESSURE = 10  # heavy-volume down days (was distribution_days, was 8pt)
    W_VIX = 10  # level + VIX3M term structure (was 8pt)
    W_CREDIT_SPREAD = 10  # HY OAS (was 7pt)
    W_PUT_CALL = 8  # options put/call ratio (replaces McClellan oscillator)
    W_NEW_HIGHS_LOWS = 7
    W_AD_LINE = 6  # A/D direction vs SPY (was 5pt)
    W_BREADTH_50 = 6  # reduced from 14pt (was overweighted relative to 200-DMA)
    W_NAAIM = 5  # (was 3pt)
    W_AAII = 3  # extremes-only scoring (was 4pt)

    def __init__(self) -> None:
        self.calculator = MarketFactorCalculator()

    def _with_cursor(self, operation: Callable[[PsycopgCursor[Any]], T]) -> T:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
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
        if not eval_date:
            eval_date = _date.today()

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
                return None

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
                    f"CRITICAL: Cached market exposure is stale — cached from {cached_date}, "
                    f"but requested for {eval_date}. Not using stale cache to prevent incorrect risk allocation. "
                    f"This requires recomputation (check Phase 4 data loader)."
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            # CRITICAL: Also validate TTL — data computed > 10 hours ago uses stale market close prices
            # Position sizing must use fresh-enough data (ideally computed within 1 hour of market close)
            if updated_at:
                from utils.infrastructure.timezone import EASTERN_TZ

                now = datetime.now(EASTERN_TZ)
                age = now - updated_at.replace(tzinfo=EASTERN_TZ) if not updated_at.tzinfo else now - updated_at
                max_age = timedelta(hours=10)
                if age > max_age:
                    msg = (
                        f"CRITICAL: Cached market exposure is too old — computed {age.total_seconds()/3600:.1f}h ago, "
                        f"exceeds {max_age.total_seconds()/3600:.0f}h limit. "
                        f"Using such old data for position sizing violates risk management. "
                        f"Forcing recomputation with fresher market data."
                    )
                    logger.critical(msg)
                    return None

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

            # CRITICAL: Validate that all 12 required factors are present with real scores
            # This prevents using stale cached data with default/missing factor values
            required_factors = {
                "trend_30wk",
                "spy_momentum",
                "breadth_200dma",
                "breadth_50dma",
                "distribution_days",
                "vix_regime",
                "put_call_ratio",
                "new_highs_lows",
                "ad_line",
                "credit_spread",
                "aaii_sentiment",
                "naaim",
            }
            missing_factors = []
            invalid_factors = []

            for factor_name in required_factors:
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
                return None  # Force recomputation instead of using incomplete cache

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
            logger.info(f"✓ Loaded cached market exposure for {eval_date}: {exposure_pct}% ({regime})")
            return result

        try:
            return self._with_cursor(fetch_cached)
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def compute(self, eval_date: _date | None = None, force_recompute: bool = False) -> dict[str, Any]:  # noqa: C901
        """Compute full market exposure score. Returns dict.

        Args:
            eval_date: Date to compute for (default: today)
            force_recompute: If True, always recompute (don't use cache)
        """
        if not eval_date:
            eval_date = _date.today()

        # Check cache first (unless force_recompute=True)
        if not force_recompute:
            cached = self.try_load_cached(eval_date)
            if cached:
                return cached

        logger.info(f"Computing market exposure for {eval_date} (12 sequential queries)")
        with DatabaseContext("read") as cur:
            # Per-query timeout: 45s. Breadth queries use pre-computed sma_50/sma_200 from
            # technical_data_daily (fast indexed lookup). 45s x 12 = 540s max, fits in Lambda
            # 600s budget. Raised from 30s because some queries exceed 30s on t4g.micro even
            # without concurrent loaders (slow disk I/O on the small instance).
            cur.execute("SET statement_timeout = 45000")
            factors = {}
            score = 0.0
            avail_max = 0.0  # sum of weights for factors that have real data

            # --- 1. Trend 30-week MA (SPY vs SMA_150 + slope) ---
            t30 = self.calculator.trend_30wk(eval_date, cur)
            t30_pts, t30_avail = self.calculator._wt_pts(t30, self.W_TREND_30WK)
            avail_max += t30_avail
            factors["trend_30wk"] = {
                **t30,
                "pts": round(t30_pts, 1),
                "max": self.W_TREND_30WK,
            }
            score += t30_pts
            logger.debug(f"  Trend 30-week: {t30_pts:.1f} pts")

            # --- 2. SPY 12-month momentum (TSMOM — most replicated quant signal) ---
            mom = self.calculator.spy_momentum(eval_date, cur)
            mom_pts, mom_avail = self.calculator._wt_pts(mom, self.W_SPY_MOMENTUM)
            avail_max += mom_avail
            factors["spy_momentum"] = {
                **mom,
                "pts": round(mom_pts, 1),
                "max": self.W_SPY_MOMENTUM,
            }
            score += mom_pts
            logger.debug(f"  SPY 12-month momentum: {mom_pts:.1f} pts")

            # --- 3. Breadth: % stocks above 50-DMA ---
            b50 = self.calculator._pct_above_ma(eval_date, ma_days=50, cur=cur)
            b50_pts, b50_avail = self.calculator._wt_pts(b50, self.W_BREADTH_50)
            avail_max += b50_avail
            factors["breadth_50dma"] = {
                **b50,
                "pts": round(b50_pts, 1),
                "max": self.W_BREADTH_50,
            }
            score += b50_pts
            b50_val = b50.get("value")
            if b50_val is None:
                logger.warning(f"Breadth 50-DMA data unavailable for {eval_date}")
            else:
                logger.debug(f"  Breadth 50-DMA: {b50_val:.1f}%, {b50_pts:.1f} pts")

            # --- 4. Breadth: % stocks above 200-DMA ---
            b200 = self.calculator._pct_above_ma(eval_date, ma_days=200, cur=cur)
            b200_pts, b200_avail = self.calculator._wt_pts(b200, self.W_BREADTH_200)
            avail_max += b200_avail
            factors["breadth_200dma"] = {
                **b200,
                "pts": round(b200_pts, 1),
                "max": self.W_BREADTH_200,
            }
            score += b200_pts
            b200_val = b200.get("value")
            if b200_val is None:
                logger.warning(f"Breadth 200-DMA data unavailable for {eval_date}")
            else:
                logger.debug(f"  Breadth 200-DMA: {b200_val:.1f}%, {b200_pts:.1f} pts")

            # --- 5. Selling pressure (heavy-volume down days) ---
            # CRITICAL: Selling pressure is required for hard veto checks (Veto 3: 6+ days)
            # Never silently exclude or default to None — must fail-fast on calculation error
            try:
                sp = self.calculator.selling_pressure(eval_date, cur)
                if sp is None or not isinstance(sp, dict):
                    raise RuntimeError(
                        f"Selling pressure calculation failed: returned {type(sp).__name__} instead of dict"
                    )
                if "count" not in sp or sp["count"] is None:
                    raise RuntimeError(
                        "Selling pressure calculation incomplete: missing 'count' field. "
                        "Cannot determine distribution day veto without day count."
                    )
            except Exception as e:
                msg = (
                    f"[SELLING PRESSURE CRITICAL] Distribution days calculation failed: {type(e).__name__}: {e} "
                    f"Cannot compute exposure score without selling pressure data. "
                    f"Check: (1) price_daily table freshness, (2) volume data availability"
                )
                logger.critical(msg)
                raise RuntimeError(msg) from e

            sp_pts, sp_avail = self.calculator._wt_pts(sp, self.W_SELLING_PRESSURE)
            avail_max += sp_avail
            factors["distribution_days"] = {  # key preserved for frontend/API compatibility
                **sp,
                "pts": round(sp_pts, 1),
                "max": self.W_SELLING_PRESSURE,
            }
            score += sp_pts
            logger.debug(f"  Selling pressure: {sp['count']} days, {sp_pts:.1f} pts")

            # --- 6. VIX regime (level + VIX3M term structure) ---
            # _vix_regime() raises RuntimeError if VIX data is unavailable (critical dependency).
            # Term structure (VIX3M) is optional: if missing, calculation proceeds with level only.
            try:
                vix = self.calculator.vix_regime(eval_date, cur)
            except RuntimeError as e:
                logger.critical(f"[VIX CRITICAL] Exposure calculation halted: {e}")
                raise
            vix_pts, vix_avail = self.calculator._wt_pts(vix, self.W_VIX)
            avail_max += vix_avail
            factors["vix_regime"] = {**vix, "pts": round(vix_pts, 1), "max": self.W_VIX}
            score += vix_pts
            logger.debug(f"  VIX regime: {vix.get('value', 'N/A')} (score {vix_pts:.1f} pts)")

            # --- 7. Put/call ratio (options sentiment — contrarian, daily) ---
            pc = self.calculator.put_call_ratio(eval_date, cur)
            pc_pts, pc_avail = self.calculator._wt_pts(pc, self.W_PUT_CALL)
            avail_max += pc_avail
            factors["put_call_ratio"] = {
                **pc,
                "pts": round(pc_pts, 1),
                "max": self.W_PUT_CALL,
            }
            score += pc_pts
            logger.debug(f"  Put/call ratio: {pc_pts:.1f} pts")

            # --- 8. New highs vs new lows ---
            nhnl = self.calculator.new_highs_lows(eval_date, cur)
            nhnl_pts, nhnl_avail = self.calculator._wt_pts(nhnl, self.W_NEW_HIGHS_LOWS)
            avail_max += nhnl_avail
            factors["new_highs_lows"] = {
                **nhnl,
                "pts": round(nhnl_pts, 1),
                "max": self.W_NEW_HIGHS_LOWS,
            }
            score += nhnl_pts
            logger.debug(f"  New Highs/Lows: {nhnl_pts:.1f} pts")

            # --- 9. A/D line confirmation ---
            ad = self._ad_line(eval_date, cur)
            ad_pts, ad_avail = self.calculator._wt_pts(ad, self.W_AD_LINE)
            avail_max += ad_avail
            factors["ad_line"] = {**ad, "pts": round(ad_pts, 1), "max": self.W_AD_LINE}
            score += ad_pts
            logger.debug(f"  A/D line: {ad_pts:.1f} pts")

            # --- 10. Credit spreads (HY OAS — credit leads equity) ---
            cs = self._credit_spread(eval_date, cur)
            cs_pts, cs_avail = self.calculator._wt_pts(cs, self.W_CREDIT_SPREAD)
            avail_max += cs_avail
            factors["credit_spread"] = {
                **cs,
                "pts": round(cs_pts, 1),
                "max": self.W_CREDIT_SPREAD,
            }
            score += cs_pts
            logger.debug(f"  Credit spreads: {cs_pts:.1f} pts")

            # --- 11. AAII sentiment (contrarian at extremes only) ---
            aaii = self.calculator.aaii(eval_date, cur)
            aaii_pts, aaii_avail = self.calculator._wt_pts(aaii, self.W_AAII)
            avail_max += aaii_avail
            factors["aaii_sentiment"] = {
                **aaii,
                "pts": round(aaii_pts, 1),
                "max": self.W_AAII,
            }
            score += aaii_pts
            logger.debug(f"  AAII sentiment: {aaii_pts:.1f} pts")

            # --- 12. NAAIM professional manager exposure (contrarian at extremes) ---
            naaim = self.calculator.naaim(eval_date, cur)
            naaim_pts, naaim_avail = self.calculator._wt_pts(naaim, self.W_NAAIM)
            avail_max += naaim_avail
            factors["naaim"] = {
                **naaim,
                "pts": round(naaim_pts, 1),
                "max": self.W_NAAIM,
            }
            score += naaim_pts
            logger.debug(f"  NAAIM exposure: {naaim_pts:.1f} pts")

            # CRITICAL: Fail-fast if insufficient data available for meaningful score.
            # When avail_max < 60, we lack sufficient factors for reliable assessment.
            # Example: only VIX+Trend (25pts) scores 100% due to normalization,
            # misleading market exposure despite 75% of factors being N/A.
            min_avail_weight = 60.0
            if avail_max < min_avail_weight:
                msg = (
                    f"[MARKET EXPOSURE CRITICAL] Insufficient data for exposure calculation. "
                    f"Only {avail_max:.1f}/100 points of factor data available (threshold: {min_avail_weight}). "
                    f"Missing {100 - avail_max:.1f} points from market data pipeline. "
                    f"Cannot compute reliable market exposure score. "
                    f"Check: phase 4 loaders, technical_data_daily, price_daily freshness."
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            # Normalize to 100-point scale when some (but not too many) factors had no data,
            # so missing factors don't silently pull the score toward zero.
            if 0 < avail_max < 100:
                score = score / avail_max * 100
                logger.debug(f"  Score normalized: avail_max={avail_max:.1f}/100")
            score = max(0.0, min(100.0, score))

            try:
                from algo.signals.sector_rotation import SectorRotationDetector

                detector = SectorRotationDetector()
                # Use detector's own connection (don't share) to avoid transaction abort propagation
                rotation = detector.compute(eval_date)
                if rotation:
                    if "reduce_exposure_pts" not in rotation:
                        logger.error(f"Sector rotation missing 'reduce_exposure_pts' field: {rotation.keys()}")
                        raise ValueError(
                            "Sector rotation detector returned incomplete data: missing reduce_exposure_pts"
                        )
                    rot_penalty = rotation["reduce_exposure_pts"]
                    if rot_penalty > 0:
                        score = max(0.0, score - rot_penalty)
                        factors["sector_rotation"] = {
                            "signal": rotation["signal"],
                            "defensive_lead_score": rotation["defensive_lead_score"],
                            "penalty_applied": rot_penalty,
                            "pts": -rot_penalty,
                            "max": 0,
                        }
                    else:
                        factors["sector_rotation"] = {
                            "signal": rotation["signal"],
                            "defensive_lead_score": rotation["defensive_lead_score"],
                            "penalty_applied": 0,
                            "pts": 0,
                            "max": 0,
                        }
            except Exception as e:
                # Sector rotation detector failure is critical: cannot apply position-sizing penalty.
                msg = (
                    f"[SECTOR ROTATION CRITICAL] Detector failed, cannot assess defensive rotation: "
                    f"{type(e).__name__}: {e}"
                )
                logger.critical(msg)
                raise RuntimeError(msg) from e

            try:
                eco = self._economic_regime_overlay(eval_date, cur)
                if "penalty" not in eco or "cap" not in eco:
                    logger.error(f"Economic overlay missing required fields: {eco.keys()}")
                    raise ValueError("Economic regime overlay missing 'penalty' and/or 'cap' fields")
                eco_penalty = eco["penalty"]
                eco_cap = eco["cap"]
                if eco_penalty != 0 or eco_cap < 100.0:
                    score = max(0.0, min(100.0, score - eco_penalty))
                factors["economic_overlay"] = {**eco, "pts": -eco_penalty, "max": 0}
            except Exception as e:
                # CRITICAL: Economic regime overlay failed — RAISE ERROR, don't silently default to conservative cap
                # Using a default cap masks the underlying data quality issue and prevents alerts
                msg = (
                    f"[ECONOMIC OVERLAY CRITICAL] Macro economic assessment failed: {type(e).__name__}: {e} "
                    f"Cannot compute exposure score without valid economic regime analysis. "
                    f"Check: (1) economic_data table freshness, (2) FRED API connection, (3) series_id configuration"
                )
                logger.critical(msg)
                raise RuntimeError(msg) from e

            # --- HARD VETOES ---
            halt_reasons = []
            cap = eco_cap  # Start with eco-overlay cap (may already restrict)

            # Veto 1: SPY < rising 30wk MA AND breadth weak
            b50_value = b50.get("value")
            if t30.get("score") is not None and t30.get("above_30wma") is False:
                if b50_value is not None and b50_value < 30:
                    halt_reasons.append("SPY < 30wk MA AND <30% above 50-DMA")
                    cap = min(cap, 25.0)
                elif b50_value is None:
                    logger.warning("Veto 1 (SPY below 30wk MA): breadth data unavailable, skipping")
            # Veto 2: VIX > 40 rising (only if VIX data available)
            vix_value = vix.get("value")
            if vix_value is not None and vix_value > 40 and vix.get("rising"):
                halt_reasons.append(f"VIX {vix_value:.1f} rising > 40")
                cap = min(cap, 30.0)
            # Veto 3: 6+ selling-pressure days (severe institutional distribution)
            sp_count = sp.get("count")
            if sp_count is not None and sp_count >= 6:
                halt_reasons.append(f"{sp_count} selling-pressure days >= 6")
                cap = min(cap, 35.0)
            elif sp_count is None:
                logger.warning("Veto 3 (selling pressure): data unavailable, skipping")
            # Veto 4: No market confirmation signal while SPY below 30-week MA.
            # Only applies when SPY is actually below its 30-week MA — in smooth uptrends
            # SPY never drops enough to need confirmation, so this veto is dormant.
            try:
                has_confirmation = self._has_market_confirmation(eval_date, cur)
                if not has_confirmation and t30.get("score") is not None and t30.get("above_30wma") is False:
                    halt_reasons.append("No market confirmation signal while SPY below 30-week MA")
                    cap = min(cap, 40.0)
            except RuntimeError as e:
                logger.warning(f"Veto 4 (market confirmation): {e}, skipping")
                has_confirmation = True  # Conservative: assume confirmation if check fails
            # Veto 5: HY credit spread systemic stress (only if data available)
            cs_value = cs.get("value")
            if cs_value is not None:
                cs_value = float(cs_value)
                if cs_value > 850:  # OAS in basis points, 850 bps = 8.5%
                    halt_reasons.append(f"HY credit spread {cs_value:.0f} bps > 850 (systemic stress)")
                    cap = min(cap, 30.0)
            else:
                logger.warning("Veto 5 (credit spreads): data unavailable, skipping")

            if halt_reasons:
                logger.warning(f"  Hard vetoes active: {'; '.join(halt_reasons)}, cap={cap}%")
            if cap < 100.0:
                logger.info(f"  Score capped from {score:.1f}% to {cap}%")

            final = min(score, cap)

            # Determine recommended state based on final exposure score
            if final >= 70:
                regime = "confirmed_uptrend"
            elif final >= 45:
                regime = "uptrend_under_pressure"
            elif final >= 25:
                regime = "caution"
            else:
                regime = "correction"

            logger.info(f"  Final score: {final}% ({regime})")

            # CRITICAL: distribution_days is required for position sizing hard vetoes
            # Never default to 0 — missing data must be detected as error, not assumed "clean market"
            if sp_count is None:
                msg = (
                    "[EXPOSURE CRITICAL] Distribution days calculation failed (sp_count is None). "
                    "Cannot persist exposure score without distribution day count for veto checks. "
                    "Check: (1) selling_pressure() implementation, (2) distribution data freshness"
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            result = {
                "eval_date": str(eval_date),
                "raw_score": round(score, 1),
                "available_factors_max": round(avail_max, 1),
                "capped_score": round(final, 1),
                "exposure_pct": round(final, 1),
                "regime": regime,
                "halt_reasons": halt_reasons,
                "distribution_days": int(sp_count),
                "factors": factors,
            }
            self._persist(eval_date, result)
            return result

    # ====== Factor implementations ======

    @staticmethod
    def _wt_pts(factor: dict[str, Any], weight: int) -> tuple[float, float]:
        """Return (pts, avail_weight) for a scoring factor.

        When score_factor is None (data missing), returns (0.0, 0.0) so the
        factor is excluded from both the score and the available-max denominator.
        The caller normalizes the final score against avail_max so missing factors
        don't silently skew the result toward neutral.
        """
        sf = factor.get("score_factor")
        return (float(weight) * sf, float(weight)) if sf is not None else (0.0, 0.0)

    def _spy_momentum(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """SPY 12-month price momentum — trailing return over ~252 trading days.

        Time-series momentum (TSMOM) is the most replicated signal in quantitative
        finance. Source: Moskowitz, Ooi & Pedersen (JFE, 2012); AQR Century of
        Evidence on Trend-Following (2017). Positive 12-month return = uptrend;
        negative = bear market or correction.
        """
        cur.execute(
            """
            SELECT date, close FROM price_daily
            WHERE symbol = 'SPY' AND date <= %s
            ORDER BY date DESC LIMIT 255
            """,
            (eval_date,),
        )
        rows = cur.fetchall()
        if len(rows) < 250:
            return {
                "score_factor": None,
                "value": None,
                "reason": "Insufficient history",
            }

        current_close = float(rows[0][1])
        past_close = float(rows[251][1])  # ~252 trading days ago
        if past_close <= 0:
            raise ValueError(
                f"[MOMENTUM CALCULATION FAILED] Past close price invalid ({past_close}) for momentum calculation. "
                f"Cannot compute 12-month momentum without valid historical price. Check price_daily data."
            )
        momentum_pct = (current_close - past_close) / past_close * 100

        if momentum_pct > 20:
            sf = 1.0
        elif momentum_pct > 10:
            sf = 0.85
        elif momentum_pct > 5:
            sf = 0.70
        elif momentum_pct > 0:
            sf = 0.55
        elif momentum_pct > -5:
            sf = 0.35
        elif momentum_pct > -10:
            sf = 0.20
        else:
            sf = 0.05

        return {
            "score_factor": sf,
            "value": round(momentum_pct, 1),
            "current_close": round(current_close, 2),
            "past_close_252d": round(past_close, 2),
        }

    def _selling_pressure_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Institutional selling pressure: heavy-volume down days in last 25 sessions.

        Counts sessions where the market closes down ≥0.2% on above-average volume —
        a sign of institutional distribution rather than retail-driven selling.
        A cluster of these days signals professionals are reducing exposure.

        Scoring (gradient, not a cliff):
        - 0-2 days:  market absorbing selling, 1.0 factor
        - 3-4 days:  caution building, 0.6 factor
        - 5+ days:   pressure mounting, 0.2 factor
        - 6+ days:   severe pressure (also triggers hard veto cap)
        """
        dd_count = self._distribution_days(eval_date, cur)

        if dd_count <= 2:
            sf = 1.0
        elif dd_count <= 4:
            sf = 0.6
        else:  # 5+
            sf = 0.2

        return {
            "score_factor": sf,
            "count": dd_count,
            "regime": ("clean" if dd_count <= 2 else ("caution" if dd_count <= 4 else "pressure")),
        }

    def _distribution_days(self, eval_date: _date, cur: PsycopgCursor[Any]) -> int:
        """Count heavy-volume down days over last 25 trading sessions on SPY.

        A qualifying session: close declines ≥0.2% AND volume is heavier than
        the prior day. Rolling 25-session window. (LIMIT 26: first row lacks
        prev_close due to LAG, so only 25 valid comparisons are made.)
        """
        cur.execute(
            """
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       LAG(volume) OVER (ORDER BY date) AS prev_vol
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT 26
            )
            SELECT COUNT(*) FROM d
            WHERE prev_close IS NOT NULL
              AND close < prev_close * 0.998
              AND volume > prev_vol
            """,
            (eval_date,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"CRITICAL: Market confirmation query failed (returned None) for date {eval_date}")
        if row[0] is None:
            raise RuntimeError(f"CRITICAL: Market confirmation count is NULL for date {eval_date}")
        return int(row[0])

    def _has_market_confirmation(self, eval_date: _date, cur: PsycopgCursor[Any]) -> bool:
        """Detect a volume-backed rally day in last 30 days.

        A qualifying day: index closes ≥1.7% on volume above prior day.
        Used only as a hard veto condition (not a scoring factor): when SPY
        is below its 30-week MA and no such day has occurred, the market has
        not confirmed an attempted recovery, so exposure is capped at 40%.
        """
        cur.execute(
            """
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       LAG(volume) OVER (ORDER BY date) AS prev_vol
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                  AND date >= %s::date - INTERVAL '30 days'
            )
            SELECT 1 FROM d
            WHERE prev_close IS NOT NULL
              AND close >= prev_close * 1.017
              AND volume > prev_vol
            ORDER BY date DESC
            LIMIT 1
            """,
            (eval_date, eval_date),
        )
        return cur.fetchone() is not None

    def _trend_30wk(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """SPY vs 30-week (150d) MA + slope over 30 trading days.

        Reads pre-computed sma_150 from technical_data_daily (indexed lookup, <1s)
        instead of computing AVG() OVER a window across all SPY rows in price_daily
        (7000+ rows x window function = slow under load on t4g.micro).
        """
        cur.execute(
            """
            SELECT date, close, sma_150
            FROM technical_data_daily
            WHERE symbol = 'SPY' AND date <= %s
            ORDER BY date DESC
            LIMIT 35
            """,
            (eval_date,),
        )
        rows = cur.fetchall()
        if not rows or rows[0][2] is None:
            return {
                "score_factor": None,
                "value": None,
                "reason": "Insufficient history",
            }

        cur_close = float(rows[0][1])
        sma_now = float(rows[0][2])
        if sma_now <= 0:
            logger.warning(f"CRITICAL: SPY SMA is invalid ({sma_now}) on {eval_date}")
            return {"score_factor": None, "value": None, "reason": "Invalid SMA data"}

        sma_30d_ago = float(rows[30][2]) if len(rows) > 30 and rows[30][2] is not None else None
        if sma_30d_ago is None or sma_30d_ago <= 0:
            logger.warning(f"CRITICAL: SPY 30d-ago SMA is invalid ({sma_30d_ago}) on {eval_date}")
            return {"score_factor": None, "value": None, "reason": "Insufficient 30d history"}

        slope = (sma_now - sma_30d_ago) / sma_30d_ago * 100.0
        price_pct = (cur_close - sma_now) / sma_now * 100.0

        # Score: above and rising = 1.0, above and flat = 0.7, near = 0.5, below = 0.0
        if price_pct > 2 and slope > 1:
            sf = 1.0
        elif price_pct > 0 and slope > 0:
            sf = 0.75
        elif price_pct > -2 and abs(slope) < 1:
            sf = 0.5
        elif price_pct < 0:
            sf = 0.1
        else:
            sf = 0.3

        return {
            "score_factor": sf,
            "price": round(cur_close, 2),
            "sma_150": round(sma_now, 2),
            "slope_pct": round(slope, 2),
            "price_vs_ma_pct": round(price_pct, 2),
            "price_below_ma": cur_close < sma_now,
        }

    def _pct_above_ma(self, eval_date: _date, ma_days: int, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """% of all stocks above their N-day MA.

        Reads pre-computed price_above_sma50 / price_above_sma200 boolean flags
        from trend_template_data (single-table indexed scan, <1s) instead of
        joining technical_data_daily x price_daily (DISTINCT ON across 35k rows
        each, too slow on t4g.micro).
        """
        bool_col = "price_above_sma50" if ma_days == 50 else "price_above_sma200"
        col = pgsql.Identifier(bool_col)
        cur.execute(
            pgsql.SQL("""
            SELECT
                COUNT(*) FILTER (WHERE {} = TRUE)  AS above,
                COUNT(*) FILTER (WHERE {} IS NOT NULL) AS total
            FROM (
                SELECT DISTINCT ON (symbol) {}
                FROM trend_template_data
                WHERE date <= %s AND date >= %s::date - INTERVAL '7 days'
                ORDER BY symbol, date DESC
            ) latest
            """).format(col, col, col),
            (eval_date, eval_date),
        )
        row = cur.fetchone()
        if row is None or len(row) < 2 or row[0] is None or row[1] is None:
            raise RuntimeError(
                f"[MARKET EXPOSURE CRITICAL] No breadth data for {ma_days}-day MA on {eval_date} — "
                f"price_above_sma{ma_days} cannot be calculated. Check trend_template_data loader."
            )
        above, total = int(row[0]), int(row[1])
        if total <= 0:
            raise RuntimeError(f"[MARKET EXPOSURE CRITICAL] No stocks to calculate breadth for {ma_days}-day MA")
        pct = above / total * 100.0
        # Linear: 20% -> 0pts, 80% -> 1.0
        if ma_days == 50:
            sf = max(0.0, min(1.0, (pct - 20) / 60))
        else:  # 200
            sf = max(0.0, min(1.0, (pct - 30) / 50))
        return {
            "score_factor": sf,
            "value": round(pct, 1),
            "above": above,
            "total": total,
        }

    def _vix_regime(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """VIX level + VIX3M/VIX term structure.

        VIX level captures current implied volatility / fear.
        VIX term structure (VIX3M/VIX ratio) is more forward-looking:
        - Contango (VIX3M > VIX): market expects volatility to subside → positive signal
        - Backwardation (VIX3M < VIX): near-term stress worse than medium-term → negative
        VIX3M is pre-loaded to price_daily by load_market_health_daily.
        """
        cur.execute(
            """
            SELECT close, LAG(close, 5) OVER (ORDER BY date) AS prior
            FROM price_daily WHERE symbol = '^VIX' AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        vix_row = cur.fetchone()

        # Get VIX3M for term structure
        cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = '^VIX3M' AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        vix3m_row = cur.fetchone()

        if not vix_row or vix_row[0] is None:
            # Check if market is currently open (real-time VIX should be available during market hours)
            now = datetime.now(EASTERN_TZ)
            is_market_open = (
                MarketCalendar.is_trading_day(now.date()) and
                time(9, 30) <= now.time() <= time(16, 0)
            )

            if is_market_open:
                # During market hours, real-time VIX is critical for exposure calculation
                msg = (
                    f"[VIX CRITICAL] Real-time ^VIX missing during market hours ({eval_date} {now.time()}). "
                    f"Cannot assess market volatility for portfolio exposure during trading session. "
                    f"Exposure calculation halted — stale VIX data would incorrectly underestimate risk. "
                    f"Check: (1) Is yfinance API reachable? (2) Is ^VIX in price_daily? "
                    f"(3) Did load_prices run successfully today?"
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            # After market close, allow fallback to market_health_daily (same-day, acceptable age)
            cur.execute(
                """SELECT vix_level FROM market_health_daily
                   WHERE date <= %s AND vix_level IS NOT NULL
                   ORDER BY date DESC LIMIT 1""",
                (eval_date,),
            )
            r2 = cur.fetchone()
            if not r2 or r2[0] is None:
                msg = (
                    f"[VIX CRITICAL] No VIX data available for {eval_date} (post-market fallback): "
                    f"^VIX missing from price_daily AND vix_level missing/null in market_health_daily. "
                    f"Exposure calculation INCOMPLETE — risk assessment unavailable. "
                    f"Check that load_market_health_daily loader is running and fetching VIX from external sources."
                )
                logger.critical(msg)
                raise RuntimeError(msg)
            vix = float(r2[0])
            logger.info(
                f"[VIX] Post-market fallback: using vix_level={vix} from market_health_daily "
                f"(real-time ^VIX unavailable after close for {eval_date})"
            )
            return self._vix_score(vix, rising=False, term_structure=None)

        vix = float(vix_row[0])
        if vix_row[1] is None:
            raise RuntimeError(
                f"[VIX CRITICAL] Prior VIX value missing for {eval_date}. "
                f"Cannot assess VIX trend without historical comparison. "
                f"VIX direction signals are required for exposure risk adjustment."
            )
        prior = float(vix_row[1])
        rising = vix > prior * 1.05

        term_structure = None
        if vix3m_row and vix3m_row[0] is not None and vix > 0:
            vix3m = float(vix3m_row[0])
            term_structure = vix3m / vix  # >1.0 = contango, <1.0 = backwardation

        logger.debug(
            f"[VIX] Computed from ^VIX: value={vix:.2f}, rising={rising}, "
            f"term_structure={term_structure if term_structure else 'N/A'} for {eval_date}"
        )
        return self._vix_score(vix, rising=rising, term_structure=term_structure)

    def _vix_score(self, vix: float, rising: bool, term_structure: float | None = None) -> dict[str, Any]:
        # Base score from VIX level
        if vix < 15:
            sf = 1.0
        elif vix < 20:
            sf = 0.85
        elif vix < 25:
            sf = 0.65
        elif vix < 30:
            sf = 0.45
        elif vix < 35:
            sf = 0.30
        else:
            sf = 0.10

        # Rising VIX penalty: stress accelerating
        if rising and vix > 20:
            sf *= 0.75

        # Term structure adjustment
        ts_detail: dict[str, Any] = {}
        if term_structure is not None:
            if term_structure > 1.10:  # steep contango: market expects calm
                sf = min(1.0, sf * 1.10)
                ts_detail["term_structure_signal"] = "contango"
            elif term_structure > 1.0:  # mild contango
                sf = min(1.0, sf * 1.05)
                ts_detail["term_structure_signal"] = "mild_contango"
            elif term_structure < 0.90:  # backwardation: near-term stress
                sf *= 0.85
                ts_detail["term_structure_signal"] = "backwardation"
            else:
                ts_detail["term_structure_signal"] = "flat"
            ts_detail["vix3m_vix_ratio"] = round(term_structure, 3)

        return {
            "score_factor": round(sf, 3),
            "value": round(vix, 2),
            "rising": rising,
            **ts_detail,
        }

    def _put_call_ratio(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Put/call ratio — options market sentiment (contrarian, daily signal).

        High P/C ratio (>1.1): elevated put buying = fear/hedging = contrarian bullish.
        Low P/C ratio (<0.6): call-heavy = complacency/greed = contrarian bearish.
        Populated daily from SPY options chain via load_market_health_daily.
        Source: Pan & Poteshman (JoF, 2006) — statistically significant predictive
        power for subsequent returns from options flow data.
        """
        cur.execute(
            """
            SELECT put_call_ratio FROM market_health_daily
            WHERE date <= %s AND put_call_ratio IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            raise RuntimeError(
                f"[MARKET EXPOSURE CRITICAL] No put/call ratio data for {eval_date} — "
                f"required for options sentiment factor. Check market_health_daily loader."
            )

        pc = float(row[0])

        # Contrarian scoring: high P/C = fear = bullish for markets
        if pc > 1.2:
            sf = 1.0  # extreme fear → contrarian buy
        elif pc > 0.9:
            sf = 0.80  # elevated put buying
        elif pc > 0.7:
            sf = 0.65  # neutral
        elif pc > 0.5:
            sf = 0.40  # complacent
        else:
            sf = 0.20  # extreme greed → contrarian caution

        return {"score_factor": sf, "value": round(pc, 3)}

    def _new_highs_lows(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """52-week new highs vs new lows ratio.

        Reads pre-computed new_highs_count / new_lows_count from market_health_daily
        (fast, <1s indexed lookup) instead of computing 400-day window functions across
        price_daily (reads 2M+ rows with 3 window functions per symbol — too slow on t4g.micro).
        """
        cur.execute(
            """
            SELECT new_highs_count, new_lows_count
            FROM market_health_daily
            WHERE date <= %s AND new_highs_count IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"[MARKET EXPOSURE CRITICAL] No new highs/lows data for {eval_date} — "
                f"required for market leadership factor. Check market_health_daily loader."
            )
        if row["new_highs_count"] is None:
            raise ValueError(f"Breadth data missing: new_highs_count is None on {eval_date}")
        if row["new_lows_count"] is None:
            raise ValueError(f"Breadth data missing: new_lows_count is None on {eval_date}")
        new_hi = int(row["new_highs_count"])
        new_lo = int(row["new_lows_count"])
        net = new_hi - new_lo
        # Net +50 -> 1.0, 0 -> 0.5, -50 -> 0
        sf = max(0.0, min(1.0, 0.5 + net / 100.0))
        return {
            "score_factor": sf,
            "new_highs": new_hi,
            "new_lows": new_lo,
            "net": net,
        }

    def _ad_line(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """A/D line: cumulative advancers - decliners vs SPY direction.

        Uses pre-computed advance_decline_ratio from market_health_daily and
        SPY close from price_daily (fast, <1s indexed lookups) instead of
        computing LAG() window functions across 5000 stocks x 35 days (~175,000 rows).

        Returns {"score_factor": None} if data unavailable instead of raising.
        A/D line is a 6pt factor and missing breadth data is handled by returning None
        score — normalization will exclude this factor.
        """
        try:
            cur.execute(
                """
                WITH mh AS (
                    SELECT date, advance_decline_ratio
                    FROM market_health_daily
                    WHERE date <= %s AND advance_decline_ratio IS NOT NULL
                    ORDER BY date DESC LIMIT 22
                ),
                spy AS (
                    SELECT date, close FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 22
                )
                SELECT mh.date, mh.advance_decline_ratio AS ratio, spy.close AS spy_close
                FROM mh
                JOIN spy ON mh.date = spy.date
                ORDER BY mh.date ASC
                """,
                (eval_date, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < 5:
                logger.warning(f"Insufficient A/D line data for {eval_date}: {len(rows)} rows, need 5+")
                return {"score_factor": None, "reason": "Insufficient A/D line data"}

            nets = []
            for r in rows:
                ratio = r.get("ratio")
                if ratio is None:
                    logger.warning(f"A/D ratio missing for {r.get('date')}, skipping row")
                    continue
                nets.append((float(ratio) - 1) / (float(ratio) + 1))

            if len(nets) < 2:
                logger.warning(f"Insufficient valid A/D ratios for {eval_date}")
                return {"score_factor": None, "reason": "Insufficient valid A/D ratios"}

            first_net = nets[0]
            last_net = nets[-1]
            ad_change = last_net - first_net

            first_spy_val = rows[0].get("spy_close")
            last_spy_val = rows[-1].get("spy_close")

            if first_spy_val is None or last_spy_val is None:
                logger.warning(f"SPY close data missing for A/D calculation on {eval_date}")
                return {"score_factor": None, "reason": "SPY close data unavailable"}

            first_spy = float(first_spy_val)
            last_spy = float(last_spy_val)

            if first_spy <= 0:
                logger.warning(f"Invalid first SPY price {first_spy} on {eval_date}")
                return {"score_factor": None, "reason": "Invalid SPY price"}

            spy_change_pct = (last_spy - first_spy) / first_spy * 100.0
            # Confirmation: both same direction. Divergence: opposite.
            if (ad_change > 0 and spy_change_pct > 0) or (ad_change < 0 and spy_change_pct < 0):
                sf = 1.0
                relation = "confirming"
            elif ad_change > 0 and spy_change_pct < 0:
                sf = 0.6  # hidden bullish
                relation = "bullish_divergence"
            else:
                sf = 0.3  # bearish divergence
                relation = "bearish_divergence"
            return {
                "score_factor": sf,
                "ad_change_20d": round(ad_change, 4),
                "spy_change_pct_20d": round(spy_change_pct, 2),
                "relation": relation,
            }
        except Exception as e:
            logger.warning(f"A/D line calculation failed for {eval_date}: {e}")
            return {"score_factor": None, "reason": f"A/D calculation error: {e}"}

    def _aaii(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """AAII investor sentiment — contrarian at extremes only.

        Bull-bear spread (bullish% - bearish%) is the key metric.
        Signal is only meaningful at extreme readings (±15+ spread);
        in the normal middle range it is noise with low predictive value.
        """
        cur.execute(
            """
            SELECT bullish, bearish
            FROM aaii_sentiment
            WHERE date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            raise RuntimeError(
                f"[MARKET EXPOSURE CRITICAL] No AAII sentiment data for {eval_date} — "
                f"required for contrarian sentiment factor. Check aaii_sentiment loader."
            )

        bullish = float(row[0])
        if row[1] is None:
            raise RuntimeError(
                f"[MARKET EXPOSURE CRITICAL] AAII bearish sentiment missing for {eval_date} — "
                f"cannot calculate bull-bear spread without both sentiment indicators. "
                f"Check aaii_sentiment loader data completeness."
            )
        bearish = float(row[1])
        spread = bullish - bearish  # positive = more bulls than bears

        # Extremes-only scoring: neutral in the normal range (-15 to +15)
        if spread < -25:
            sf = 1.0  # extreme fear → strong contrarian buy
        elif spread < -15:
            sf = 0.75  # elevated bearishness
        elif spread < 15:
            sf = 0.50  # normal range — not predictive, neutral score
        elif spread < 25:
            sf = 0.30  # elevated bullishness
        else:
            sf = 0.15  # extreme greed → contrarian caution

        return {
            "score_factor": sf,
            "value": round(spread, 1),
            "bull_bear_spread": round(spread, 1),
            "bullish_pct": round(bullish, 1),
            "bearish_pct": round(bearish, 1),
        }

    def _naaim(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """NAAIM manager equity exposure — contrarian at extremes.

        Active manager exposure scale (0-100%):
        < 20: heavily underweight → contrarian bullish (managers will be forced to buy)
        > 80: heavily overweight → contrarian cautious (limited buying power left)
        """
        cur.execute(
            """
            SELECT naaim_number_mean
            FROM naaim
            WHERE date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            raise RuntimeError(
                f"[MARKET EXPOSURE CRITICAL] No NAAIM manager exposure data for {eval_date} — "
                f"required for professional positioning factor. Check naaim loader."
            )

        exposure = float(row[0])
        clamped = max(0.0, min(100.0, exposure))

        if clamped < 20:
            sf = 0.90
        elif clamped < 35:
            sf = 0.75
        elif clamped < 55:
            sf = 0.55
        elif clamped < 70:
            sf = 0.40
        elif clamped < 85:
            sf = 0.25
        else:
            sf = 0.15

        return {
            "score_factor": sf,
            "value": round(exposure, 1),
        }

    def _credit_spread(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """HY OAS credit spread (BAMLH0A0HYM2) — credit leads equity.

        Based on Apollo/Torsten Slok research: HY spreads widen 4-6 weeks
        before equity markets price in credit risk. Rapidly widening spreads
        (>+1pp in 20 trading days) get an additional 20% score haircut.

        Scale: <3.5% = tight/healthy, 4-5% = mild stress, >7% = severe stress.
        Note: HY OAS is intentionally excluded from the economic regime overlay
        to avoid double-counting this data series.

        Returns {"score_factor": None} if data unavailable instead of raising.
        Credit spread is a 10pt factor and missing economic data is handled by
        returning None score — normalization will exclude this factor.
        """
        try:
            cur.execute(
                """
                SELECT value::float, date
                FROM economic_data
                WHERE series_id = 'BAMLH0A0HYM2' AND date <= %s
                ORDER BY date DESC LIMIT 25
                """,
                (eval_date,),
            )
            rows = cur.fetchall()
            if not rows:
                logger.warning(f"No HY credit spread (BAMLH0A0HYM2) data for {eval_date}")
                return {"score_factor": None, "reason": "No credit spread data available"}

            hy = float(rows[0][0])

            # If we have trend data, use it; otherwise just use current level
            widening_1pp = False
            hy_20d_ago = None
            if len(rows) >= 20:
                hy_20d_ago = float(rows[-1][0])
                widening_1pp = (hy - hy_20d_ago) > 1.0
            elif len(rows) > 5:
                # Partial history available, use what we have
                hy_20d_ago = float(rows[-1][0])
                widening_1pp = (hy - hy_20d_ago) > 1.0
            else:
                logger.debug(f"Limited credit spread history for {eval_date}: {len(rows)} rows")

            if hy < 3.5:
                sf = 1.0
            elif hy < 4.5:
                sf = 0.85
            elif hy < 5.5:
                sf = 0.65
            elif hy < 7.0:
                sf = 0.35
            else:
                sf = 0.10

            # Rapid widening haircut: stress is accelerating
            if widening_1pp and hy > 4.0:
                sf *= 0.80

            result = {
                "score_factor": round(sf, 3),
                "value": round(hy, 3),
                "widening_rapidly": widening_1pp,
            }
            if hy_20d_ago is not None:
                result["hy_20d_ago"] = round(hy_20d_ago, 3)
            return result
        except Exception as e:
            logger.warning(f"Credit spread calculation failed for {eval_date}: {e}")
            return {"score_factor": None, "reason": f"Credit spread calculation error: {e}"}

    def _economic_regime_overlay(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Post-score macro stress penalty from yield curve, credit trend, jobless claims.

        Inspired by Yardeni/Slok/Goldman FCI methodology: when macro cycle signals
        deteriorate, reduce max exposure regardless of short-term price action.
        This overlay is applied AFTER factor scoring, not as a factor weight.

        Note: HY credit spread is excluded here — it is a direct 10pt factor.
        Including it in both places would double-count the same data series.

        Returns: {macro_stress_score, penalty, cap, contributing_signals}
        """
        stress = 0.0
        signals = []

        # Signal 1: Yield curve (T10Y2Y) — inversion duration matters
        cur.execute(
            """
            SELECT value::float, date FROM economic_data
            WHERE series_id = 'T10Y2Y' AND date <= %s
            ORDER BY date DESC LIMIT 60
            """,
            (eval_date,),
        )
        curve_rows = cur.fetchall()
        if curve_rows:
            latest_spread = float(curve_rows[0][0])
            # How many consecutive weeks inverted?
            weeks_inverted = sum(1 for r in curve_rows[:12] if float(r[0]) < 0)
            if latest_spread < -0.5 and weeks_inverted >= 8:
                stress += 35.0
                signals.append(f"Curve inverted {latest_spread:.2f}% for {weeks_inverted}+ weeks")
            elif latest_spread < 0:
                stress += 20.0
                signals.append(f"Curve inverted {latest_spread:.2f}%")
            elif latest_spread < 0.2:
                stress += 8.0
                signals.append(f"Curve flat {latest_spread:.2f}%")

        # Signal 2: Jobless claims trend — rising claims precede recessions
        cur.execute(
            """
            SELECT value::float, date FROM economic_data
            WHERE series_id = 'ICSA' AND date <= %s
            ORDER BY date DESC LIMIT 27
            """,
            (eval_date,),
        )
        claims_rows = cur.fetchall()
        if len(claims_rows) >= 26:
            claims_now = float(claims_rows[0][0])
            claims_26w = float(claims_rows[-1][0])
            if claims_26w <= 0:
                logger.warning(
                    f"Invalid 26-week claims baseline ({claims_26w}) — skipping jobless claims signal"
                )
                chg_pct = 0.0
            else:
                chg_pct = (claims_now - claims_26w) / claims_26w * 100
            if chg_pct > 30:
                stress += 30.0
                signals.append(f"Jobless claims +{chg_pct:.1f}% in 26w (severe)")
            elif chg_pct > 20:
                stress += 15.0
                signals.append(f"Jobless claims +{chg_pct:.1f}% in 26w (elevated)")

        # Signal 3: St. Louis Financial Stress Index — 18-variable financial market composite
        cur.execute(
            """
            SELECT value::float FROM economic_data
            WHERE series_id = 'STLFSI4' AND date <= %s
            ORDER BY date DESC LIMIT 5
            """,
            (eval_date,),
        )
        stlfsi_rows = cur.fetchall()
        if stlfsi_rows:
            stlfsi = float(stlfsi_rows[0][0])
            if stlfsi > 1.5:
                stress += 25.0
                signals.append(f"Financial stress index {stlfsi:.2f}s (severe stress)")
            elif stlfsi > 0.8:
                stress += 12.0
                signals.append(f"Financial stress index {stlfsi:.2f}s (elevated)")

        # Signal 4: Chicago Fed National Activity Index — 85-indicator broad economic composite
        cur.execute(
            """
            SELECT value::float FROM economic_data
            WHERE series_id = 'CFNAI' AND date <= %s
            ORDER BY date DESC LIMIT 4
            """,
            (eval_date,),
        )
        cfnai_rows = cur.fetchall()
        if cfnai_rows:
            cfnai_avg = sum(float(r[0]) for r in cfnai_rows[:3]) / min(3, len(cfnai_rows))
            if cfnai_avg < -0.7:
                stress += 20.0
                signals.append(f"CFNAI 3-mo avg {cfnai_avg:.2f} (below recession threshold)")
            elif cfnai_avg < -0.35:
                stress += 10.0
                signals.append(f"CFNAI 3-mo avg {cfnai_avg:.2f} (below trend growth)")

        stress = min(100.0, stress)

        # Apply penalty and cap based on macro stress level
        if stress >= 60:
            penalty = 7.0
            cap = 40.0
        elif stress >= 40:
            penalty = 4.0
            cap = 100.0
        elif stress <= 15:
            # Favorable macro: small bonus (better breadth, not capped)
            penalty = -2.0  # negative penalty = bonus
            cap = 100.0
        else:
            penalty = 0.0
            cap = 100.0

        return {
            "macro_stress_score": round(stress, 1),
            "penalty": round(penalty, 1),
            "cap": cap,
            "signals": signals,
        }

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
                    f"Calculation error — cannot persist invalid value. "
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

            factors_json = json.dumps(result["factors"])
            halt_reasons_json = json.dumps(result["halt_reasons"])
            regime = result.get("regime")
            if not regime:
                raise ValueError("Market regime calculation missing. Cannot build exposure summary.")
            if "raw_score" not in result:
                raise ValueError(
                    "Market exposure raw_score missing from calculation result. "
                    "Cannot persist exposure data without risk score."
                )
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO market_exposure_daily
                        (date, exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons,
                         long_exposure_pct, short_exposure_pct, is_entry_allowed, exposure_tier)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        exposure_tier = EXCLUDED.exposure_tier
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
                    ),
                )
            logger.info(
                f"persist market_exposure OK for {eval_date}: "
                f"{exposure_pct}% exposure ({tier}), "
                f"entry_allowed={is_entry_allowed}"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"persist market_exposure failed for {eval_date}: {e}", exc_info=True)


class MarketDataUnavailableError(RuntimeError):
    """Raised when market regime data is unavailable (Phase 4 not run or data missing)."""


def read_market_regime(eval_date: _date) -> dict[str, Any]:
    """Read market regime from market_exposure_daily (latest snapshot on or before eval_date).

    This is the canonical way for orchestrator phases to read market regime data.
    Ensures Phase 3b and Phase 5 read from the same source and same snapshot with
    consistent JSON deserialization and error handling.

    CRITICAL: Reads the latest available market_exposure_daily snapshot (date <= eval_date).
    This ensures all orchestrator phases running on the same day read the same market regime,
    regardless of execution order. The 4:05 PM EOD pipeline populates the daily snapshot once;
    all subsequent orchestrator runs use that snapshot.

    Args:
        eval_date: Date to read regime for (reads latest snapshot on or before this date)

    Returns:
        dict with: is_entry_allowed, exposure_pct, regime, halt_reasons, raw_score, exposure_tier

    Raises:
        MarketDataUnavailableError: When Phase 4 (market exposure) has not been run or data is missing/corrupt
        psycopg2.DatabaseError/OperationalError: For transient database issues (fail-closed, returns default regime)
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    is_entry_allowed, exposure_pct, regime, halt_reasons,
                    raw_score, exposure_tier, date
                FROM market_exposure_daily
                WHERE date <= %s
                ORDER BY date DESC
                LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row is None:
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] No market_exposure_daily data on or before {eval_date}. "
                    f"Phase 4 must compute daily market exposure. Cannot proceed with regime-aware position sizing. "
                    f"Run algo_market_exposure.py before trading."
                )

            (
                is_entry_allowed,
                exposure_pct,
                regime,
                halt_reasons_str,
                raw_score,
                exposure_tier,
                _cached_date,
            ) = row

            if exposure_pct is None:
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] market_exposure_daily for {eval_date} has NULL exposure_pct. "
                    f"Critical data corruption — cannot determine position sizing constraints. "
                    f"Cannot proceed until database is repaired."
                )

            # CRITICAL: Regime and exposure_tier are REQUIRED fields
            # Never allow fallback to "unknown" — position sizing requires valid tier names
            if not regime or regime == "":
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] market_exposure_daily for {eval_date} has NULL/empty regime. "
                    f"Cannot apply position sizing policy without valid regime. "
                    f"Phase 4 (market exposure calculation) must run successfully to produce valid regime."
                )
            if not exposure_tier or exposure_tier == "":
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] market_exposure_daily for {eval_date} has NULL/empty exposure_tier. "
                    f"Cannot apply position sizing policy without valid tier. "
                    f"Phase 4 (market exposure calculation) must run successfully to produce valid tier."
                )

            # Deserialize halt_reasons JSON with consistent error handling
            halt_reasons = []
            if halt_reasons_str:
                try:
                    halt_reasons = json.loads(halt_reasons_str)
                    if not isinstance(halt_reasons, list):
                        logger.warning(
                            f"[MARKET REGIME] halt_reasons is not a list: {type(halt_reasons)} for {eval_date}"
                        )
                        halt_reasons = []
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(
                        f"[MARKET REGIME] Malformed halt_reasons JSON for {eval_date}: {e} — treating as empty list"
                    )
                    halt_reasons = []

            return {
                "is_entry_allowed": bool(is_entry_allowed),
                "exposure_pct": float(exposure_pct),
                "regime": regime,
                "halt_reasons": halt_reasons,
                "raw_score": float(raw_score) if raw_score is not None else None,
                "exposure_tier": exposure_tier,
            }

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # CRITICAL: Never return fake "unknown" regime — raise error instead
        # Position sizing code cannot handle "unknown" tier; must fail-fast
        msg = (
            f"[MARKET REGIME CRITICAL] Could not read market regime for {eval_date}: {type(e).__name__}: {e} "
            f"— Market exposure data unavailable. Position sizing cannot proceed without valid regime. "
            f"Check: (1) market_exposure_daily table exists, (2) Phase 4 loader has run, (3) database connection"
        )
        logger.critical(msg)
        raise MarketDataUnavailableError(msg) from e


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compute market exposure for a date")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Eval date YYYY-MM-DD. Default = latest trading date in price_daily.",
    )
    args = parser.parse_args()
    me = MarketExposure()
    if args.date:
        eval_d = _date.fromisoformat(args.date)
    else:
        # Use latest trading date in price_daily
        def get_latest_date(cur: PsycopgCursor[Any]) -> Any:
            cur.execute("SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
            return cur.fetchone()

        with DatabaseContext("read") as cur:
            result = get_latest_date(cur)
            if not result or result[0] is None:
                logger.error("No price data available for SPY")
                exit(1)
            eval_d = result[0]
    result = me.compute(eval_d)
    logger.info(f"MARKET EXPOSURE — {result['eval_date']}")
    logger.info(f"Regime: {result['regime']}")
    logger.info(f"Exposure %: {result['exposure_pct']}%")
    logger.info(f"Raw score: {result['raw_score']}")
    logger.info(f"Selling pressure days: {result['distribution_days']}")
    if result["halt_reasons"]:
        logger.warning("HALT REASONS:")
        for r in result["halt_reasons"]:
            logger.warning(f"  - {r}")
    logger.info("Factor breakdown:")
    for name, info in result["factors"].items():
        if "pts" not in info:
            raise KeyError(f"Factor '{name}' missing required 'pts' key: {info}")
        pts = info["pts"]
        if "max" not in info:
            raise KeyError(f"Factor '{name}' missing required 'max' key: {info}")
        max_pts = info["max"]
        logger.info(f"  {name:22s}: {pts:5.1f} / {max_pts:>3} pts  ({info})")
