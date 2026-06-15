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

import json
import logging
from psycopg2 import sql as pgsql
from utils.db import DatabaseContext
from datetime import date as _date

logger = logging.getLogger(__name__)


class MarketExposure:
    """Quantitative market regime + exposure % computation."""

    # Factor weights (sum = 100)
    W_TREND_30WK = 15
    W_SPY_MOMENTUM = 10       # 12-month TSMOM (replaces follow-through day)
    W_BREADTH_200 = 10
    W_SELLING_PRESSURE = 10   # heavy-volume down days (was distribution_days, was 8pt)
    W_VIX = 10                # level + VIX3M term structure (was 8pt)
    W_CREDIT_SPREAD = 10      # HY OAS (was 7pt)
    W_PUT_CALL = 8            # options put/call ratio (replaces McClellan oscillator)
    W_NEW_HIGHS_LOWS = 7
    W_AD_LINE = 6             # A/D direction vs SPY (was 5pt)
    W_BREADTH_50 = 6          # reduced from 14pt (was overweighted relative to 200-DMA)
    W_NAAIM = 5               # (was 3pt)
    W_AAII = 3                # extremes-only scoring (was 4pt)

    def __init__(self):
        pass

    def _with_cursor(self, operation):
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except Exception as e:
            logger.debug(f"Database operation failed: {e}")
            return None

    def try_load_cached(self, eval_date=None):
        """Load cached market exposure for today. Returns dict or None if not cached."""
        if not eval_date:
            eval_date = _date.today()

        def fetch_cached(cur):
            cur.execute(
                """
                SELECT raw_score, exposure_pct, regime, halt_reasons, distribution_days, factors
                FROM market_exposure_daily
                WHERE date = %s
                LIMIT 1
            """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            (
                raw_score,
                exposure_pct,
                regime,
                halt_reasons_str,
                dist_days,
                factors_obj,
            ) = row
            halt_reasons = json.loads(halt_reasons_str) if halt_reasons_str else []
            factors = (
                factors_obj
                if isinstance(factors_obj, dict)
                else (json.loads(factors_obj) if factors_obj else {})
            )

            result = {
                "eval_date": str(eval_date),
                "raw_score": raw_score,
                "capped_score": exposure_pct,
                "exposure_pct": exposure_pct,
                "regime": regime,
                "halt_reasons": halt_reasons,
                "distribution_days": dist_days or 0,
                "factors": factors,
                "_cached": True,
            }
            logger.info(
                f"✓ Loaded cached market exposure for {eval_date}: {exposure_pct}% ({regime})"
            )
            return result

        try:
            return self._with_cursor(fetch_cached)
        except Exception as e:
            logger.debug(f"Could not load cached exposure: {e}")
            return None

    def compute(self, eval_date=None, force_recompute=False):
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

        logger.info(
            f"Computing market exposure for {eval_date} (12 sequential queries)"
        )
        with DatabaseContext("read") as cur:
            # Per-query timeout: 45s. Breadth queries use pre-computed sma_50/sma_200 from
            # technical_data_daily (fast indexed lookup). 45s × 12 = 540s max, fits in Lambda
            # 600s budget. Raised from 30s because some queries exceed 30s on t4g.micro even
            # without concurrent loaders (slow disk I/O on the small instance).
            cur.execute("SET statement_timeout = 45000")
            factors = {}
            score = 0.0

            # --- 1. Trend 30-week MA (SPY vs SMA_150 + slope) ---
            t30 = self._trend_30wk(eval_date, cur)
            t30_pts = self.W_TREND_30WK * t30["score_factor"]
            factors["trend_30wk"] = {
                **t30,
                "pts": round(t30_pts, 1),
                "max": self.W_TREND_30WK,
            }
            score += t30_pts
            logger.debug(f"  Trend 30-week: {t30_pts:.1f} pts")

            # --- 2. SPY 12-month momentum (TSMOM — most replicated quant signal) ---
            mom = self._spy_momentum(eval_date, cur)
            mom_pts = self.W_SPY_MOMENTUM * mom["score_factor"]
            factors["spy_momentum"] = {
                **mom,
                "pts": round(mom_pts, 1),
                "max": self.W_SPY_MOMENTUM,
            }
            score += mom_pts
            logger.debug(f"  SPY 12-month momentum: {mom_pts:.1f} pts")

            # --- 3. Breadth: % stocks above 50-DMA ---
            b50 = self._pct_above_ma(eval_date, ma_days=50, cur=cur)
            b50_pts = self.W_BREADTH_50 * b50["score_factor"]
            factors["breadth_50dma"] = {
                **b50,
                "pts": round(b50_pts, 1),
                "max": self.W_BREADTH_50,
            }
            score += b50_pts
            logger.debug(
                f"  Breadth 50-DMA: {(b50.get('value') or 0):.1f}%, {b50_pts:.1f} pts"
            )

            # --- 4. Breadth: % stocks above 200-DMA ---
            b200 = self._pct_above_ma(eval_date, ma_days=200, cur=cur)
            b200_pts = self.W_BREADTH_200 * b200["score_factor"]
            factors["breadth_200dma"] = {
                **b200,
                "pts": round(b200_pts, 1),
                "max": self.W_BREADTH_200,
            }
            score += b200_pts
            logger.debug(
                f"  Breadth 200-DMA: {(b200.get('value') or 0):.1f}%, {b200_pts:.1f} pts"
            )

            # --- 5. Selling pressure (heavy-volume down days) ---
            sp = self._selling_pressure_factor(eval_date, cur)
            sp_pts = self.W_SELLING_PRESSURE * sp["score_factor"]
            factors["distribution_days"] = {  # key preserved for frontend/API compatibility
                **sp,
                "pts": round(sp_pts, 1),
                "max": self.W_SELLING_PRESSURE,
            }
            score += sp_pts
            logger.debug(
                f"  Selling pressure: {sp.get('count', 0)} days, {sp_pts:.1f} pts"
            )

            # --- 6. VIX regime (level + VIX3M term structure) ---
            vix = self._vix_regime(eval_date, cur)
            vix_pts = self.W_VIX * vix["score_factor"]
            factors["vix_regime"] = {**vix, "pts": round(vix_pts, 1), "max": self.W_VIX}
            score += vix_pts
            logger.debug(f"  VIX regime: {vix_pts:.1f} pts")

            # --- 7. Put/call ratio (options sentiment — contrarian, daily) ---
            pc = self._put_call_ratio(eval_date, cur)
            pc_pts = self.W_PUT_CALL * pc["score_factor"]
            factors["put_call_ratio"] = {
                **pc,
                "pts": round(pc_pts, 1),
                "max": self.W_PUT_CALL,
            }
            score += pc_pts
            logger.debug(f"  Put/call ratio: {pc_pts:.1f} pts")

            # --- 8. New highs vs new lows ---
            nhnl = self._new_highs_lows(eval_date, cur)
            nhnl_pts = self.W_NEW_HIGHS_LOWS * nhnl["score_factor"]
            factors["new_highs_lows"] = {
                **nhnl,
                "pts": round(nhnl_pts, 1),
                "max": self.W_NEW_HIGHS_LOWS,
            }
            score += nhnl_pts
            logger.debug(f"  New Highs/Lows: {nhnl_pts:.1f} pts")

            # --- 9. A/D line confirmation ---
            ad = self._ad_line(eval_date, cur)
            ad_pts = self.W_AD_LINE * ad["score_factor"]
            factors["ad_line"] = {**ad, "pts": round(ad_pts, 1), "max": self.W_AD_LINE}
            score += ad_pts
            logger.debug(f"  A/D line: {ad_pts:.1f} pts")

            # --- 10. Credit spreads (HY OAS — credit leads equity) ---
            cs = self._credit_spread(eval_date, cur)
            cs_pts = self.W_CREDIT_SPREAD * cs["score_factor"]
            factors["credit_spread"] = {
                **cs,
                "pts": round(cs_pts, 1),
                "max": self.W_CREDIT_SPREAD,
            }
            score += cs_pts
            logger.debug(f"  Credit spreads: {cs_pts:.1f} pts")

            # --- 11. AAII sentiment (contrarian at extremes only) ---
            aaii = self._aaii(eval_date, cur)
            aaii_pts = self.W_AAII * aaii["score_factor"]
            factors["aaii_sentiment"] = {
                **aaii,
                "pts": round(aaii_pts, 1),
                "max": self.W_AAII,
            }
            score += aaii_pts
            logger.debug(f"  AAII sentiment: {aaii_pts:.1f} pts")

            # --- 12. NAAIM professional manager exposure (contrarian at extremes) ---
            naaim = self._naaim(eval_date, cur)
            naaim_pts = self.W_NAAIM * naaim["score_factor"]
            factors["naaim"] = {
                **naaim,
                "pts": round(naaim_pts, 1),
                "max": self.W_NAAIM,
            }
            score += naaim_pts
            logger.debug(f"  NAAIM exposure: {naaim_pts:.1f} pts")

            score = max(0.0, min(100.0, score))

            try:
                from algo.signals.sector_rotation import SectorRotationDetector

                detector = SectorRotationDetector()
                # Use detector's own connection (don't share) to avoid transaction abort propagation
                rotation = detector.compute(eval_date)
                if rotation:
                    rot_penalty = rotation.get("reduce_exposure_pts", 0)
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
                factors["sector_rotation"] = {"error": str(e)[:60]}

            try:
                eco = self._economic_regime_overlay(eval_date, cur)
                eco_penalty = eco.get("penalty", 0)
                eco_cap = eco.get("cap", 100.0)
                if eco_penalty != 0 or eco_cap < 100.0:
                    score = max(0.0, min(100.0, score - eco_penalty))
                factors["economic_overlay"] = {**eco, "pts": -eco_penalty, "max": 0}
            except Exception as e:
                factors["economic_overlay"] = {"error": str(e)[:60], "pts": 0, "max": 0}
                eco_cap = 100.0

            # --- HARD VETOES ---
            halt_reasons = []
            cap = eco_cap  # Start with eco-overlay cap (may already restrict)

            # Veto 1: SPY < rising 30wk MA AND breadth weak
            if t30.get("price_below_ma") and b50.get("value", 100) < 30:
                halt_reasons.append("SPY < 30wk MA AND <30% above 50-DMA")
                cap = min(cap, 25.0)
            # Veto 2: VIX > 40 rising (only if VIX data available)
            vix_value = vix.get("value")
            if vix_value is not None and vix_value > 40 and vix.get("rising"):
                halt_reasons.append(f"VIX {vix_value:.1f} rising > 40")
                cap = min(cap, 30.0)
            # Veto 3: 6+ selling-pressure days (severe institutional distribution)
            sp_count = sp.get("count", 0)
            if sp_count >= 6:
                halt_reasons.append(f"{sp_count} selling-pressure days >= 6")
                cap = min(cap, 35.0)
            # Veto 4: No market confirmation signal while SPY below 30-week MA.
            # Only applies when SPY is actually below its 30-week MA — in smooth uptrends
            # SPY never drops enough to need confirmation, so this veto is dormant.
            has_confirmation = self._has_market_confirmation(eval_date, cur)
            if not has_confirmation and t30.get("price_below_ma"):
                halt_reasons.append("No market confirmation signal while SPY below 30-week MA")
                cap = min(cap, 40.0)
            # Veto 5: HY credit spread systemic stress
            if cs.get("value") and cs["value"] > 8.5:
                halt_reasons.append(
                    f'HY credit spread {cs["value"]:.2f}% > 8.5% (systemic stress)'
                )
                cap = min(cap, 30.0)

            if halt_reasons:
                logger.warning(
                    f"  Hard vetoes active: {'; '.join(halt_reasons)}, cap={cap}%"
                )
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

            result = {
                "eval_date": str(eval_date),
                "raw_score": round(score, 1),
                "capped_score": round(final, 1),
                "exposure_pct": round(final, 1),
                "regime": regime,
                "halt_reasons": halt_reasons,
                "distribution_days": sp_count,
                "factors": factors,
            }
            self._persist(eval_date, result)
            return result

    # ====== Factor implementations ======

    def _spy_momentum(self, eval_date, cur):
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
            return {"score_factor": 0.5, "value": None, "reason": "Insufficient history"}

        current_close = float(rows[0][1])
        past_close = float(rows[251][1])  # ~252 trading days ago
        momentum_pct = (
            (current_close - past_close) / past_close * 100 if past_close > 0 else 0
        )

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

    def _selling_pressure_factor(self, eval_date, cur):
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
            "regime": (
                "clean"
                if dd_count <= 2
                else ("caution" if dd_count <= 4 else "pressure")
            ),
        }

    def _distribution_days(self, eval_date, cur):
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
        return int(row[0]) if row is not None and row[0] is not None else 0

    def _has_market_confirmation(self, eval_date, cur):
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

    def _trend_30wk(self, eval_date, cur):
        """SPY vs 30-week (150d) MA + slope over 30 trading days.

        Reads pre-computed sma_150 from technical_data_daily (indexed lookup, <1s)
        instead of computing AVG() OVER a window across all SPY rows in price_daily
        (7000+ rows × window function = slow under load on t4g.micro).
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
                "score_factor": 0.1,
                "value": None,
                "reason": "Insufficient history",
            }

        cur_close = float(rows[0][1])
        sma_now = float(rows[0][2])
        sma_30d_ago = (
            float(rows[30][2])
            if len(rows) > 30 and rows[30][2] is not None
            else sma_now
        )

        slope = (sma_now - sma_30d_ago) / sma_30d_ago * 100.0 if sma_30d_ago > 0 else 0
        price_pct = (cur_close - sma_now) / sma_now * 100.0 if sma_now > 0 else 0

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

    def _pct_above_ma(self, eval_date, ma_days, cur):
        """% of all stocks above their N-day MA.

        Reads pre-computed price_above_sma50 / price_above_sma200 boolean flags
        from trend_template_data (single-table indexed scan, <1s) instead of
        joining technical_data_daily × price_daily (DISTINCT ON across 35k rows
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
        if not row or not row[1]:
            return {"score_factor": 0.5, "value": None}
        above, total = int(row[0]), int(row[1])
        pct = above / total * 100.0 if total > 0 else 0
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

    def _vix_regime(self, eval_date, cur):
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
            # Fallback to market_health_daily if ^VIX missing
            cur.execute(
                "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            r2 = cur.fetchone()
            if not r2 or r2[0] is None:
                return {"score_factor": 0.1, "value": None}
            vix = float(r2[0])
            return self._vix_score(vix, rising=False, term_structure=None)

        vix = float(vix_row[0])
        prior = float(vix_row[1]) if vix_row[1] is not None else vix
        rising = vix > prior * 1.05

        term_structure = None
        if vix3m_row and vix3m_row[0] is not None and vix > 0:
            vix3m = float(vix3m_row[0])
            term_structure = vix3m / vix  # >1.0 = contango, <1.0 = backwardation

        return self._vix_score(vix, rising=rising, term_structure=term_structure)

    def _vix_score(self, vix, rising, term_structure=None):
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
        ts_detail = {}
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

    def _put_call_ratio(self, eval_date, cur):
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
            return {"score_factor": 0.5, "value": None, "reason": "No put/call data"}

        pc = float(row[0])

        # Contrarian scoring: high P/C = fear = bullish for markets
        if pc > 1.2:
            sf = 1.0    # extreme fear → contrarian buy
        elif pc > 0.9:
            sf = 0.80   # elevated put buying
        elif pc > 0.7:
            sf = 0.65   # neutral
        elif pc > 0.5:
            sf = 0.40   # complacent
        else:
            sf = 0.20   # extreme greed → contrarian caution

        return {"score_factor": sf, "value": round(pc, 3)}

    def _new_highs_lows(self, eval_date, cur):
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
            return {"score_factor": 0.5, "value": None}
        new_hi = int(row["new_highs_count"] or 0)
        new_lo = int(row["new_lows_count"] or 0)
        net = new_hi - new_lo
        # Net +50 -> 1.0, 0 -> 0.5, -50 -> 0
        sf = max(0.0, min(1.0, 0.5 + net / 100.0))
        return {
            "score_factor": sf,
            "new_highs": new_hi,
            "new_lows": new_lo,
            "net": net,
        }

    def _ad_line(self, eval_date, cur):
        """A/D line: cumulative advancers - decliners vs SPY direction.

        Uses pre-computed advance_decline_ratio from market_health_daily and
        SPY close from price_daily (fast, <1s indexed lookups) instead of
        computing LAG() window functions across 5000 stocks × 35 days (~175,000 rows).
        """
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
            return {"score_factor": 0.5, "value": None}

        # Check if SPY data is fresh (no older than 1 trading day)
        if rows and rows[-1]:
            latest_date = rows[-1].get("date")
            if latest_date:
                from algo.infrastructure import MarketCalendar
                from datetime import timedelta

                expected_date = eval_date - timedelta(days=1)
                while expected_date > eval_date - timedelta(days=10):
                    if MarketCalendar.is_trading_day(expected_date):
                        break
                    expected_date -= timedelta(days=1)
                if latest_date < expected_date:
                    logger.warning(
                        f"SPY data stale: latest {latest_date} vs expected {expected_date}, returning neutral A/D score"
                    )
                    return {"score_factor": 0.5, "value": None, "stale": True}

        # Compute A/D cumulative change using ratio → net = (ratio-1)/(ratio+1)
        nets = [
            (float(r.get("ratio") or 1) - 1) / (float(r.get("ratio") or 1) + 1)
            for r in rows
        ]
        first_net = nets[0]
        last_net = nets[-1]
        ad_change = last_net - first_net
        first_spy_val = rows[0].get("spy_close")
        first_spy = float(first_spy_val) if first_spy_val is not None else 0.0
        last_spy_val = rows[-1].get("spy_close")
        last_spy = float(last_spy_val) if last_spy_val is not None else 0.0
        spy_change_pct = (
            (last_spy - first_spy) / first_spy * 100.0 if first_spy > 0 else 0
        )
        # Confirmation: both same direction. Divergence: opposite.
        if (ad_change > 0 and spy_change_pct > 0) or (
            ad_change < 0 and spy_change_pct < 0
        ):
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

    def _aaii(self, eval_date, cur):
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
            return {"score_factor": 0.5, "value": None, "reason": "No AAII data"}

        bullish = float(row[0])
        bearish = float(row[1]) if row[1] is not None else 0.0
        spread = bullish - bearish  # positive = more bulls than bears

        # Extremes-only scoring: neutral in the normal range (-15 to +15)
        if spread < -25:
            sf = 1.0    # extreme fear → strong contrarian buy
        elif spread < -15:
            sf = 0.75   # elevated bearishness
        elif spread < 15:
            sf = 0.50   # normal range — not predictive, neutral score
        elif spread < 25:
            sf = 0.30   # elevated bullishness
        else:
            sf = 0.15   # extreme greed → contrarian caution

        return {
            "score_factor": sf,
            "value": round(spread, 1),
            "bull_bear_spread": round(spread, 1),
            "bullish_pct": round(bullish, 1),
            "bearish_pct": round(bearish, 1),
        }

    def _naaim(self, eval_date, cur):
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
            return {"score_factor": 0.5, "value": None, "reason": "No NAAIM data"}

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

    def _credit_spread(self, eval_date, cur):
        """HY OAS credit spread (BAMLH0A0HYM2) — credit leads equity.

        Based on Apollo/Torsten Slok research: HY spreads widen 4-6 weeks
        before equity markets price in credit risk. Rapidly widening spreads
        (>+1pp in 20 trading days) get an additional 20% score haircut.

        Scale: <3.5% = tight/healthy, 4-5% = mild stress, >7% = severe stress.
        Note: HY OAS is intentionally excluded from the economic regime overlay
        to avoid double-counting this data series.
        """
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
            return {"score_factor": 0.7, "value": None, "reason": "No HY spread data"}

        hy = float(rows[0][0])
        # Trend: compare latest vs 20 days ago
        hy_20d_ago = float(rows[-1][0]) if len(rows) >= 20 else hy
        widening_1pp = (hy - hy_20d_ago) > 1.0  # widened > 1pp in ~20 trading days

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

        return {
            "score_factor": round(sf, 3),
            "value": round(hy, 3),
            "hy_20d_ago": round(hy_20d_ago, 3),
            "widening_rapidly": widening_1pp,
        }

    def _economic_regime_overlay(self, eval_date, cur):
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
                signals.append(
                    f"Curve inverted {latest_spread:.2f}% for {weeks_inverted}+ weeks"
                )
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
            chg_pct = (
                (claims_now - claims_26w) / claims_26w * 100 if claims_26w > 0 else 0
            )
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
                signals.append(f"Financial stress index {stlfsi:.2f}σ (severe stress)")
            elif stlfsi > 0.8:
                stress += 12.0
                signals.append(f"Financial stress index {stlfsi:.2f}σ (elevated)")

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
            cfnai_avg = sum(float(r[0]) for r in cfnai_rows[:3]) / min(
                3, len(cfnai_rows)
            )
            if cfnai_avg < -0.7:
                stress += 20.0
                signals.append(
                    f"CFNAI 3-mo avg {cfnai_avg:.2f} (below recession threshold)"
                )
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

    def _persist(self, eval_date, result):
        try:
            # Determine tier from regime
            regime = result.get("regime", "caution")
            if regime == "confirmed_uptrend":
                tier = "tier_1_strong_uptrend"
            elif regime == "uptrend_under_pressure":
                tier = "tier_2_pressure"
            elif regime == "caution":
                tier = "tier_3_caution"
            else:
                tier = "tier_4_correction"

            # Can enter if no halt reasons
            is_entry_allowed = len(result.get("halt_reasons", [])) == 0

            # Map exposure score to long/short allocations
            exposure_pct = result["exposure_pct"]
            if exposure_pct >= 0:
                long_exp = exposure_pct
                short_exp = 0
            else:
                long_exp = 0
                short_exp = abs(exposure_pct)

            factors_json = json.dumps(result.get("factors", {}))
            halt_reasons_json = json.dumps(result.get("halt_reasons", []))
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
                        result.get("raw_score", exposure_pct),
                        result.get("regime", "unknown"),
                        result.get("distribution_days", 0),
                        factors_json,
                        halt_reasons_json,
                        long_exp,
                        short_exp,
                        is_entry_allowed,
                        tier,
                    ),
                )
            logger.info(
                f"persist market_exposure OK for {eval_date}: {exposure_pct}% exposure ({tier}), entry_allowed={is_entry_allowed}"
            )
        except Exception as e:
            logger.error(
                f"persist market_exposure failed for {eval_date}: {e}", exc_info=True
            )


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
        def get_latest_date(cur):
            cur.execute(
                "SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1"
            )
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
        pts = info.get("pts", 0)
        max_pts = info.get("max", "?")
        logger.info(f"  {name:22s}: {pts:5.1f} / {max_pts:>3} pts  ({info})")
