#!/usr/bin/env python3

"""
Quantitative Market Exposure Engine - Trend & Momentum composite + hard vetoes

Composite 0-100 portfolio risk allocation score, built on THREE layers:
  1. A conviction composite: ONE scored pillar (Trend & Momentum) - the single signal
     with real, uncontested, decades-of-out-of-sample-replication evidence behind it
     (Faber/TSMOM). Two other pillars (Independent Risk Layers, Breadth & Sentiment)
     are still computed every run but carry ZERO composite weight - see "PASS
     2026-08-24" below for why, and "PILLAR 2/3" for what they're used for instead.
  2. A volatility-managed scaling multiplier on top of the composite (Moreira & Muir,
     2017) - activated 2026-08-24 after a pre-specified Phase B backtest on SPY/QQQ's
     own price history confirmed a positive Sharpe/CAGR effect on both (see
     _vol_managed_multiplier's docstring for the methodology and results).
  3. An independent hard-veto layer (binary, rare, extreme conditions that override the
     composite regardless of score) - unchanged in spirit from prior versions, extended
     with one new slow-moving macro veto.

PASS 2026-08-24 (user-directed: the scored composite should be "all about trend ...
not all this other shit" - a direct pushback on PILLAR 2's "Independent Risk Layers"
naming after this file's own pass-4 correlation numbers (VIX vs Credit Spread 0.757,
Credit Spread vs Selling Pressure 0.612, VIX vs Selling Pressure 0.571 - see PILLAR 2
below) came back higher than the 0.748 correlation that got STLFSI4 dropped entirely
one pass earlier, and close to the 0.77 that got Breadth merged into one factor the
pass after that. Keeping 3 separately-weighted, 60-75%-correlated inputs equal-weighted
overweights their shared variance relative to Pillar 1's genuinely distinct signal -
"independent" oversold what the pillar's own audit had already found, and Pillar 3's
own docstring already conceded a "more heuristic evidence base than Pillars 1-2." Real
trend-following systems size off trend and use hard risk limits as a circuit breaker,
not a second scored opinion layered on top diluting the first with weaker-evidenced
inputs - so W_PILLAR_RISK and W_PILLAR_CONFIRM dropped from 30/25 to 0, and
W_PILLAR_TREND rose from 45 to 100 (the full composite). Pillar 2/3 are NOT deleted:
vix_regime/credit_spread/selling_pressure/breadth still directly gate hard vetoes 1-3-5
below and must keep computing (unchanged, "required/critical" as before); new_highs_
lows/ad_line/aaii/put_call_ratio/market_technicals-adjacent sub-signals don't gate any
veto but stay computed and persisted because they feed standalone market-internals
dashboard displays independent of exposure scoring (e.g. lambda/api/routes/market.py's
A/D line chart). Nothing here is silently dropped the way Financial Conditions/Stress
were in pass 2 below - it's a scoring-weight change, not a signal removal; the
distinction is explicit in the "max": 0.0 that now shows up on pillar_risk/
pillar_confirm in the persisted factors dict.

REDESIGNED 2026-08-23 (goal: replace the prior flat 19-factor weighted-sum design with
one grounded in real, verified empirical-finance literature rather than accumulated
convention - see conversation record for the full literature review). The prior design
grew through 7 ad-hoc redesign passes in the days before this one, each catching
double-counting after the fact via manual pairwise correlation checks; this redesign
groups factors into pillars up front specifically so that kind of redundancy is
structural rather than something to keep re-discovering.

Evidence framework behind the pillar/weight choices (full citations in the conversation
record that produced this design):
  - Welch & Goyal (2008, RFS): individual predictors, especially valuation/dividend-
    yield-based ones, fail to beat a historical-average benchmark out-of-sample ->
    valuation/fundamentals-based timing factors do not belong in the responsive
    composite (see "Dropped entirely" below).
  - Rapach, Strauss & Zhou (2010, RFS): combining many individually-weak signals via
    SIMPLE combination beats both individual predictors and the historical mean
    out-of-sample -> many sub-signals is fine, the combination method must stay simple
    (equal/near-equal blends within each pillar, not precision-optimized weights).
  - DeMiguel, Garlappi & Uppal (2009, RFS): naive/coarse equal-weighting beats
    "optimized" weighting out-of-sample at realistic sample sizes -> pillar weights are
    round numbers (45/30/25), not hand-tuned decimals.
  - Faber (2007) / Moskowitz-Ooi-Pedersen (2012, TSMOM): price-trend/moving-average
    following is the most robustly out-of-sample-replicated timing signal across
    decades and markets -> Trend & Momentum is the largest, anchor pillar.
  - Moreira & Muir (2017, JoF), with real out-of-sample/cost-survival critiques
    (Cederburg et al.; Barroso & Detzel): volatility-managed scaling is real but
    contested -> implemented as a bounded overlay, shipped inert until validated on
    this system's own data (Phase B, a separate follow-up - no out-of-sample
    validation harness for this model exists in this repo yet).
  - Asness/Moskowitz/Pedersen (2013) + Antonacci's Dual Momentum: layering only helps
    when the added signal is genuinely independent information, not redundant -> VIX,
    Credit Spreads, and Selling Pressure (mechanically distinct markets/measurements
    that co-move in risk-off regimes without being the same recomputation) form the
    Independent Risk Layers pillar alongside Trend.
  - Estrella & Mishkin (1998): yield-curve inversion leads recessions by 6-24 months ->
    macro/rate signals (Sahm Rule, Yield Curve, Inflation Expectations) are the wrong
    tool for a days-to-weeks swing-trading dial; demoted out of the scored composite
    entirely into a slow, wide, rare tail-risk veto instead (see "Slow macro veto"
    below), rather than dropped, since the underlying signals are real.

PILLAR 1 - TREND & MOMENTUM (100pt, the anchor and now the entire composite):
    trend_30wk (100% of pillar, SUBW_TREND_30WK=1.0): SPY price vs rising/flat/falling
      30-week MA - pure Faber (2007) binary trend signal, the sole scored input.
    spy_momentum (0% of pillar, SUBW_SPY_MOMENTUM=0.0):   trailing 12-month return
      (TSMOM) - still COMPUTED and persisted (components.spy_momentum, shown on both
      dashboards) but no longer scored. See "PILLAR 1 SUB-WEIGHT EVIDENCE" below.
    market_technicals (0% of pillar, SUBW_MARKET_TECHNICALS=0.0): SPY RSI(14) +
      MACD(12,26,9) - still computed/persisted, no longer scored, same reason.

    PILLAR 1 SUB-WEIGHT EVIDENCE (PASS 2026-08-24b): the 55/35/10 blend above (trend_30wk/
    spy_momentum/market_technicals) was itself never backtested against this system's own
    data before this pass - it was assembled from literature review (Rapach/Strauss/Zhou's
    "combine weak signals simply" + DeMiguel/Garlappi/Uppal's "naive equal-weighting beats
    optimized weighting"), not validated on real returns. Backtested here for the first
    time: a pre-specified, non-fitted comparison of {trend_30wk alone, spy_momentum alone,
    the 55/35/10 blend} as an exposure-scaling signal on SPY's real price history (local
    DB backfilled 1993-2026, 32 years) AND independently on QQQ (1999-2026, 26 years, a
    genuinely different asset - covers the 83%-drawdown dot-com crash from the other side).
    Weekly rebalance, no lookahead (signal at close(t) applied to return t->t+1), no fitted
    parameters - a confirmatory test of pre-specified candidates, not a combinatorial
    search (searching many indicator combinations on this system's own thin local history
    would be exactly the overfitting trap DeMiguel/Garlappi/Uppal warns about; comparing 3
    named, literature-motivated variants is not).
    Result on both assets: trend_30wk ALONE has higher Sharpe and CAGR than the 55/35/10
    blend (SPY: Sharpe 1.10 vs 1.03, CAGR 12.3% vs 8.2%; QQQ: Sharpe 0.99 vs 0.81, CAGR
    15.2% vs 9.6%) - momentum's slower 12-month lookback net DRAGS on risk-adjusted return
    relative to the faster 30-week trend signal in this system's specific implementation,
    across every full-period aggregate tested. spy_momentum alone (100% weight) is clearly
    the weakest of any variant on both assets (SPY Sharpe 0.58, QQQ Sharpe 0.31) - this
    isn't "drop momentum entirely was untested," it's "momentum alone is worse, and the
    blend is worse than trend alone too."
    Important nuance, NOT swept under the rug: regime-by-regime on SPY, trend_30wk-alone
    beat the blend in all 8 tested regimes (dot-com/GFC/COVID/2022 bears and the 4
    intervening bulls) - a clean sweep. On QQQ it did NOT replicate as cleanly: the blend
    gave better (smaller) drawdowns in 3 of 4 crisis regimes (GFC -7.9% vs -10.4%, COVID
    -12.4% vs -14.2%, 2022 -6.1% vs -6.9%), losing only on bull-market upside capture - the
    aggregate Sharpe/CAGR edge for trend-alone holds because the bull-market gap dwarfs the
    crisis-regime gap, not because trend-alone dominates every regime on every asset. This
    is a real, asset-dependent tradeoff (somewhat worse crash protection for meaningfully
    better bull-market capture), decided here in favor of the metric the composite is
    actually built to optimize (aggregate risk-adjusted return), not a claim that momentum
    has zero defensive value anywhere.
    Caveats: single-signal-family two-asset test (SPY/QQQ, both US large-cap equity
    indices, not a cross-market sample the way TSMOM's original literature used); weekly
    (not daily) rebalancing; no transaction costs; cash modeled at 0% return (understates
    the blend's relative appeal slightly, doesn't reverse the direction). Revisit if a
    third, structurally different asset class or a real walk-forward/out-of-sample harness
    (see _vol_managed_multiplier's own docstring for a similarly-scoped SPY/QQQ backtest,
    now run) contradicts this.

PILLAR 2 - INDEPENDENT RISK LAYERS (30pt, equal-weighted simple average per Rapach et
al. - three mechanically distinct measurements that co-move in risk-off regimes without
being redundant recomputations of each other, same logic Yield Curve's two rate spreads
already used):
    vix_regime:        options-implied volatility level + genuine day-over-day trend
    credit_spread:      HY OAS (BAMLH0A0HYM2) - credit leads equity
    selling_pressure:   heavy-volume down days in the last 25 sessions (institutional
                         distribution - realized price/volume selling, not a
                         recomputation of VIX or Credit Spread despite co-moving with
                         both in real stress episodes)
    All three are required/critical - if any is unavailable, compute() raises rather
    than silently degrading this pillar (matches their pre-redesign criticality).

PILLAR 3 - BREADTH & SENTIMENT (25pt, confirmation role - real logic, more heuristic
evidence base than Pillars 1-2, so smallest of the three scored pillars):
    Participation sub-score (50% of pillar), equal blend of three "how many stocks are
    confirming" reads - breadth (% above 50/200-DMA, itself a 62.5/37.5 blend, unchanged
    from the prior design's own 2026-08-22 breadth-consolidation fix), new_highs_lows,
    and ad_line. All three required/critical, matching their pre-redesign criticality.
    Sentiment sub-score (50% of pillar), contrarian-at-extremes only: aaii (required)
    blended with put_call_ratio when available (optional, renormalizes to aaii alone
    if not).

PILLAR 3 VETO SCOPE (decided 2026-08-24, user-directed evidence review - "is there a
proven reason to keep these lingering, or use them only as confirmation/at extremes"):
breadth's 50-DMA reading (b50) already feeds Hard Veto 1 below (SPY < 30wk MA AND weak
breadth) - that stays, it's a real, decades-old technical-analysis convention (weak
breadth confirming a broken trend). new_highs_lows, ad_line, aaii, and put_call_ratio
do NOT feed any veto and are staying that way: unlike Pillar 2's veto inputs (VIX>40,
credit spread>8.5%, distribution-day counts - genuine institutional risk-desk
conventions with real multi-decade track records across 2008/2011/2020), there is no
comparably real, out-of-sample-proven extreme threshold for these four. AAII survey
sentiment specifically has been shown (DeVault, Sias & Starks, "Sentiment Metrics and
Investor Demand," Journal of Finance 2019) to mostly extrapolate recent price action
rather than carry independent predictive content; breadth-divergence "blowoff" signals
in the Hindenburg Omen family have a documented poor real-world out-of-sample record
despite popularity. Inventing a veto threshold for any of the four here would repeat
the exact unproven-addition mistake this file's own "Dropped entirely" list below
exists to avoid. They stay computed, persisted, and displayed (dashboard/market-
internals use, e.g. lambda/api/routes/market.py's A/D line chart) - informational only,
not because no one got around to wiring them in, but because the evidence doesn't
support a veto or composite-score role for them. Revisit only if a real backtest
against THIS SYSTEM'S OWN trade history (still doesn't exist - stock_scores_history only
started 2026-08-24, too shallow to validate anything yet; _vol_managed_multiplier's
2026-08-24 Phase B backtest is SPY/QQQ price-history-based, a narrower validation of a
different layer, not this) demonstrates otherwise.

SLOW MACRO VETO (Layer 3, new): Sahm Rule, Yield Curve inversion, and Inflation
Expectations are real recession/stress signals but lead by 6-24 months (Estrella-
Mishkin) - too slow for this system's responsive exposure dial, so they no longer earn
composite weight. Instead they feed one deliberately sluggish, wide veto: Sahm Rule
triggered (>=0.50pp, already a 3-month-smoothed statistic - see _sahm_ramp_score), OR
the T10Y2Y/T10Y3M average spread inverted on every session for 3+ continuous months
(persistence check, distinct from a single-day z-score read), OR inflation expectations
at a real tail extreme (z>=2.0 against 26 years of history) caps exposure to 45% - a
background elevated-risk flag, less severe than the daily-signal-driven vetoes below,
reflecting the genuinely longer horizon these signals actually operate on.

Dropped entirely (not scored, not veto-fed) - evidence-based, not "kept because
already there":
  - valuation_extension_breadth: the exact Welch-Goyal failure mode (valuation-based
    timing), and structurally unbacktestable (no persisted daily history - "first-pass/
    uncalibrated" per its own prior docstring).
  - earnings_revision_breadth: same "computes fresh from current DB state each run,
    no persisted history" structural gap; a real indicator in principle, revisit only
    once it has its own history table.
  - sector_rotation, cross_asset_confirmation, positioning: not covered by the
    evidence framework above at all - these were post-score bolt-ons as recently as
    2026-08-22, exactly the accumulated-convention pattern this redesign replaces.
    positioning's short-interest leg also has only 3 FINRA settlement cycles of local
    history - too thin to trust regardless of the literature question.

HARD VETOES (cap exposure independent of the composite score - a risk override, not an
alpha input, same separation-of-concerns a real risk desk keeps):
  - SPY < rising 30-wk MA AND breadth_50 < 30% -> cap 25%
  - VIX > 40 with a genuine rising trend -> cap 30%
  - N+ selling-pressure days in the last 25 sessions (configurable) -> cap 35%
  - No market confirmation signal (volume-backed rally) while SPY below 30-week MA -> cap 40%
  - HY credit spread > 8.5% (systemic stress) -> cap 30%
  - Slow macro veto (Sahm / persistent yield-curve inversion / inflation-expectations
    tail extreme) -> cap 45%

Output:
    market_exposure_pct (0-100): drives dynamic risk allocation
    state: 'confirmed_uptrend' | 'uptrend_under_pressure' | 'caution' | 'correction'
    factors: dict of {pillar_trend, pillar_risk, pillar_confirm, macro_watch}, each
             pillar carrying its own sub-factor detail under "components" for
             transparency/dashboard display
    halt_reasons: list of any active hard vetoes

Persists daily to market_exposure_daily table for dashboard / audit. Downstream
consumers (position_sizer.py's continuous exposure_pct/100 multiplier,
exposure_policy.py's tier_for_exposure() 70/45/25 bucketing, and the 4-value regime
taxonomy hardcoded across the orchestrator phases) are UNCHANGED by this redesign -
Layer 1's pillar weights still sum to 100 and Layers 2-3 stay within the existing 0-100
scale, so nothing downstream needed to change to consume this new internal structure.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any, TypeVar

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.config.main import AlgoConfig
from algo.risk.market_factor_calculator import MarketFactorCalculator
from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _annualized_std(returns: list[float]) -> float | None:
    """Annualized sample stdev of a list of daily returns. Same guard convention as
    algo/risk/capital_routing.py's _annualized_vol (NaN/Infinity-safe, needs >=2 obs).
    """
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    daily_vol = math.sqrt(variance)
    if math.isnan(daily_vol) or math.isinf(daily_vol):
        return None
    return daily_vol * math.sqrt(252)


# Imported here (not at module top) because market_exposure_cache.py and
# market_exposure_technicals.py (both below) import this module back (`import
# algo.risk.market_exposure as _me`) to reach names - DatabaseContext, _annualized_std -
# that are patched/defined on this module; placing these imports before those names
# exist would be a circular-import failure. Same convention as
# algo/monitoring/position_monitor.py's mixin imports.
from algo.risk.market_exposure_cache import MarketExposureCacheMixin  # noqa: E402
from algo.risk.market_exposure_macro import MarketExposureMacroMixin  # noqa: E402
from algo.risk.market_exposure_technicals import MarketExposureTechnicalsMixin  # noqa: E402


class MarketExposure(
    MarketExposureCacheMixin,
    MarketExposureMacroMixin,
    MarketExposureTechnicalsMixin,
):
    """Quantitative market regime + exposure % computation."""

    # --- Pillar weights (Layer 1). Coarse round numbers per DeMiguel/Garlappi/Uppal -
    # deliberately NOT decimal-precision-tuned. Must sum to exactly 100 (_validate_weights).
    #
    # REDESIGNED 2026-08-24 (user-directed: composite should be "all about trend ... not
    # all this other shit" - the score should be the one signal with real, uncontested
    # out-of-sample evidence, not diluted by weaker/contested ones). Independent Risk
    # Layers and Breadth & Sentiment are no longer scored - see module docstring's new
    # "PASS 2026-08-24" section for the full reasoning. Pillar 2/3 components are still
    # COMPUTED (they still feed hard vetoes 1-5 directly, and several sub-signals feed
    # standalone dashboard/market-internals displays unrelated to exposure scoring), just
    # at zero weight - a risk override and audit trail, not an alpha input, same
    # separation this file's hard-veto layer already keeps.
    W_PILLAR_TREND = 100.0  # Trend & Momentum - the ONLY scored pillar (Faber/TSMOM)
    W_PILLAR_RISK = 0.0  # Independent Risk Layers - veto/context only, not scored
    W_PILLAR_CONFIRM = 0.0  # Breadth & Sentiment - veto/context only, not scored

    # --- Internal sub-weights within Pillar 1 (Trend & Momentum).
    # PASS 2026-08-24b (backtest-driven): spy_momentum and market_technicals dropped to
    # 0 weight - see "PILLAR 1 SUB-WEIGHT EVIDENCE" in the module docstring for the full
    # backtest. Both sub-signals are still COMPUTED every run (persisted in
    # pillar_trend.components, still shown on both dashboards) - this is a scoring-weight
    # change, not a signal removal, the same distinction PASS 2026-08-24's Pillar 2/3
    # zero-weighting already established.
    SUBW_TREND_30WK = 1.0
    SUBW_SPY_MOMENTUM = 0.0
    SUBW_MARKET_TECHNICALS = 0.0

    # --- Pillar 3 internal split: Participation vs. Sentiment sub-scores, equal weight.
    SUBW_PARTICIPATION = 0.5
    SUBW_SENTIMENT = 0.5

    # --- Slow macro veto (Layer 3, new) ---
    SLOW_MACRO_VETO_CAP = 45.0
    YIELD_CURVE_INVERSION_WINDOW_DAYS = 63  # ~3 trading months
    INFLATION_EXPECTATIONS_TAIL_Z = 2.0

    def __init__(self) -> None:
        self._validate_weights()
        self.calculator = MarketFactorCalculator()

    @classmethod
    def _validate_weights(cls) -> None:
        """Fail-fast if the 3 pillar weights don't sum to exactly 100.

        Unlike the prior 19-factor design, individual sub-weights within a pillar do
        NOT need to sum to 100 or to anything in particular - _blend_scores()
        renormalizes over whatever sub-signals are actually available at compute time.
        Only the top-level pillar allocation (what fraction of the 0-100 composite each
        pillar controls) is a real invariant worth a hard fail-fast check.
        """
        weights = [cls.W_PILLAR_TREND, cls.W_PILLAR_RISK, cls.W_PILLAR_CONFIRM]
        total = sum(weights)
        if abs(total - 100.0) > 1e-6:
            raise ValueError(
                f"MarketExposure pillar weights must sum to exactly 100, got {total}. "
                f"Weights: {weights}. Fix the W_PILLAR_* class constants before computing exposure."
            )

    @staticmethod
    def _blend_scores(weighted_scores: list[tuple[float, float]]) -> float:
        """Weighted average of (score, weight) pairs, renormalized so the supplied
        weights sum to 1.0 regardless of how many are present - used to blend a
        pillar's (or sub-score's) inputs when one or more optional inputs may be
        unavailable, without leaving unspent weight the way the prior design's
        avail_max mechanism had to correct for after the fact.
        """
        total_weight = sum(w for _, w in weighted_scores)
        if total_weight <= 0:
            raise ValueError("No weight available to blend pillar sub-scores (all inputs unavailable)")
        return sum(s * w for s, w in weighted_scores) / total_weight

    def compute(self, eval_date: _date | None = None, force_recompute: bool = False) -> dict[str, Any]:  # noqa: C901
        """Compute full market exposure score. Returns dict.

        Args:
            eval_date: Date to compute for (default: today)
            force_recompute: If True, always recompute (don't use cache)
        """
        if eval_date is None:
            eval_date = datetime.now(EASTERN_TZ).date()

        from algo.infrastructure import MarketCalendar

        if not MarketCalendar.is_trading_day(eval_date):
            raise ValueError(
                f"[MARKET_EXPOSURE] Refusing to compute/persist exposure for {eval_date}: not a trading day "
                f"(weekend or holiday). market_exposure_daily rows must represent real trading days - "
                f"callers (loaders, scripts, manual testing) must pass an actual trading-day eval_date."
            )

        # Check cache first (unless force_recompute=True)
        if not force_recompute:
            cached = self.try_load_cached(eval_date)
            if cached and not cached.get("data_unavailable"):
                return cached

        logger.info(
            f"[MARKET_EXPOSURE] Computing market exposure for {eval_date} "
            f"(3-pillar architecture: Trend&Momentum/Independent Risk/Breadth&Sentiment + slow macro veto)"
        )
        with DatabaseContext("read") as cur:
            # Per-query timeout: 45s, same budget as the prior design.
            cur.execute("SET statement_timeout = 45000")

            # ============= PILLAR 1: TREND & MOMENTUM (45pt) =============
            t30 = self.calculator.trend_30wk(eval_date, cur)  # required, raises
            mom = self.calculator.spy_momentum(eval_date, cur)  # required, raises
            try:
                mtech = self._market_technicals_factor(eval_date, cur)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[MARKET_TECHNICALS] Query failed, treating as unavailable: {e}")
                mtech = {"data_unavailable": True, "reason": f"Query failed: {type(e).__name__}"}

            trend_parts = [(t30["score"], self.SUBW_TREND_30WK), (mom["score"], self.SUBW_SPY_MOMENTUM)]
            if not mtech.get("data_unavailable"):
                trend_parts.append((mtech["score"], self.SUBW_MARKET_TECHNICALS))
            else:
                logger.info(f"[MARKET_TECHNICALS] Unavailable, renormalizing Pillar 1: {mtech.get('reason')}")
            pillar_trend_score = self._blend_scores(trend_parts)
            trend_pts = pillar_trend_score * self.W_PILLAR_TREND / 100.0
            logger.debug(f"  Pillar 1 (Trend & Momentum): {pillar_trend_score:.1f}/100 -> {trend_pts:.1f} pts")

            # ============= PILLAR 2: INDEPENDENT RISK LAYERS (30pt) =============
            # CRITICAL: all three are required for hard veto checks (VIX veto 2, selling
            # pressure veto 3, credit spread veto 5) as well as the pillar score - never
            # silently exclude or default. Same fail-fast contract as the prior design.
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

            try:
                vix = self.calculator.vix_regime(eval_date, cur)
            except RuntimeError as e:
                logger.critical(f"[VIX CRITICAL] Exposure calculation halted: {e}")
                raise

            cs = self._credit_spread(eval_date, cur)  # required, raises internally

            pillar_risk_score = self._blend_scores([(sp["score"], 1.0), (vix["score"], 1.0), (cs["score"], 1.0)])
            risk_pts = pillar_risk_score * self.W_PILLAR_RISK / 100.0
            logger.debug(f"  Pillar 2 (Independent Risk Layers): {pillar_risk_score:.1f}/100 -> {risk_pts:.1f} pts")

            # ============= PILLAR 3: BREADTH & SENTIMENT (25pt) =============
            # Participation sub-score (50% of pillar): breadth + new_highs_lows + ad_line,
            # all required/critical, equal-weighted (matches Pillar 2's simple-combination
            # treatment - Rapach/Strauss/Zhou).
            b50 = self.calculator._pct_above_ma(eval_date, ma_days=50, cur=cur)
            b200 = self.calculator._pct_above_ma(eval_date, ma_days=200, cur=cur)
            breadth = {
                "score": round(0.625 * b200["score"] + 0.375 * b50["score"], 1),
                "pct_above_50": b50["value"],
                "pct_above_200": b200["value"],
            }
            nhnl = self.calculator.new_highs_lows(eval_date, cur)  # required, raises
            ad = self._ad_line(eval_date, cur)  # required, raises
            participation_score = self._blend_scores(
                [(breadth["score"], 1.0), (nhnl["score"], 1.0), (ad["score"], 1.0)]
            )

            # Sentiment sub-score (50% of pillar): aaii required, put_call_ratio optional.
            aaii = self.calculator.aaii(eval_date, cur)  # required, raises
            pc = self.calculator.put_call_ratio(eval_date, cur)  # optional
            sentiment_parts = [(aaii["score"], 1.0)]
            if not pc.get("data_unavailable"):
                sentiment_parts.append((pc["score"], 1.0))
            else:
                logger.info(
                    f"[PUT_CALL_RATIO] Unavailable, Sentiment sub-score falls back to AAII alone: {pc.get('reason')}"
                )
            sentiment_score = self._blend_scores(sentiment_parts)

            pillar_confirm_score = self._blend_scores(
                [(participation_score, self.SUBW_PARTICIPATION), (sentiment_score, self.SUBW_SENTIMENT)]
            )
            confirm_pts = pillar_confirm_score * self.W_PILLAR_CONFIRM / 100.0
            logger.debug(
                f"  Pillar 3 (Breadth & Sentiment): participation={participation_score:.1f} "
                f"sentiment={sentiment_score:.1f} -> {pillar_confirm_score:.1f}/100 -> {confirm_pts:.1f} pts"
            )

            score = trend_pts + risk_pts + confirm_pts
            score = max(0.0, min(100.0, score))

            # ============= LAYER 2: VOLATILITY-MANAGED SCALING (see docstring) =============
            vol_mult = self._vol_managed_multiplier(eval_date, cur)
            scaled_score = max(0.0, min(100.0, score * vol_mult))

            # ============= MACRO WATCH (slow-veto feed only, not scored) =============
            try:
                sahm = self._sahm_rule_factor(eval_date, cur)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[SAHM_RULE] Query failed, treating as unavailable: {e}")
                sahm = {"data_unavailable": True, "reason": f"Query failed: {type(e).__name__}"}
            yc = self._yield_curve_factor(eval_date, cur)
            infl = self._inflation_expectations_factor(eval_date, cur)
            slow_macro = self._slow_macro_veto(eval_date, cur, sahm, infl)

            # --- HARD VETOES ---
            halt_reasons = []
            cap = 100.0

            # Veto 1: SPY < rising 30wk MA AND breadth weak
            b50_value = b50.get("value")
            if t30.get("score") is not None and not t30.get("above_30wma"):
                if b50_value is not None and b50_value < 30:
                    halt_reasons.append("SPY < 30wk MA AND <30% above 50-DMA")
                    cap = min(cap, 25.0)
                elif b50_value is None:
                    msg = (
                        "[VETO 1 CRITICAL] Breadth data unavailable for veto check. "
                        "Cannot apply 25% cap without knowing market breadth. "
                        "Check: market_health_daily table freshness and breadth data"
                    )
                    logger.critical(msg)
                    raise RuntimeError(msg)
            # Veto 2: VIX > 40 rising (only if VIX data available)
            vix_value = vix.get("value")
            if vix_value is not None and vix_value > 40 and vix.get("rising"):
                halt_reasons.append(f"VIX {vix_value:.1f} rising > 40")
                cap = min(cap, 30.0)
            # Veto 3: selling-pressure days threshold (severe institutional distribution)
            sp_count = sp.get("count")
            sp_threshold_val = AlgoConfig().get("market_exposure_veto3_distribution_days_threshold")
            if sp_threshold_val is None:
                raise ValueError(
                    "[VETO 3 CONFIG] Missing config 'market_exposure_veto3_distribution_days_threshold'. "
                    "Cannot apply selling-pressure veto without threshold. "
                    "Check algo_config table has this key."
                )
            sp_threshold = int(sp_threshold_val)
            if sp_count is not None and sp_count >= sp_threshold:
                halt_reasons.append(f"{sp_count} selling-pressure days >= {sp_threshold}")
                cap = min(cap, 35.0)
            elif sp_count is None:
                msg = (
                    "[VETO 3 CRITICAL] Selling pressure data unavailable for distribution detection. "
                    "Cannot apply 35% cap without knowing institutional distribution. "
                    "Check: selling_pressure() implementation, price_daily table freshness"
                )
                logger.critical(msg)
                raise RuntimeError(msg)
            # Veto 4: No market confirmation signal while SPY below 30-week MA.
            # Only applies when SPY is actually below its 30-week MA - in smooth uptrends
            # SPY never drops enough to need confirmation, so this veto is dormant.
            try:
                has_confirmation = self._has_market_confirmation(eval_date, cur)
                if not has_confirmation and t30.get("score") is not None and not t30.get("above_30wma"):
                    halt_reasons.append("No market confirmation signal while SPY below 30-week MA")
                    cap = min(cap, 40.0)
            except RuntimeError as e:
                msg = (
                    f"[VETO 4 CRITICAL] Market confirmation check failed: {e}. "
                    f"Cannot proceed with position sizing without confirmation signal."
                )
                logger.critical(msg)
                raise RuntimeError(msg) from e
            # Veto 5: HY credit spread systemic stress (critical hard veto)
            cs_value = cs.get("value")
            if cs_value is not None:
                cs_value = float(cs_value)
                # _credit_spread() returns "value" as raw percent (e.g. 3.5 for 3.5%,
                # matching its own scoring bands hy < 3.5/4.5/5.5/7.0 and the docstring
                # "Scale: <3.5% = tight/healthy... >7% = severe stress").
                if cs_value > 8.5:  # 8.5% OAS = systemic stress threshold
                    halt_reasons.append(f"HY credit spread {cs_value:.2f}% > 8.5% (systemic stress)")
                    cap = min(cap, 30.0)
            else:
                msg = (
                    "[VETO 5 CRITICAL] Credit spread data unavailable for systemic stress check. "
                    "Cannot apply 30% cap without knowing credit market stress. "
                    "HY credit spread (OAS) is a leading indicator of systemic risk. "
                    "Check: credit_spreads table and ensure recent readings are loaded"
                )
                logger.critical(msg)
                raise RuntimeError(msg)
            # Veto 6: slow macro veto (Sahm Rule / persistent yield-curve inversion /
            # inflation-expectations tail extreme) - see module docstring and
            # _slow_macro_veto's own docstring for the 6-24 month lag reasoning.
            if slow_macro["triggered"]:
                halt_reasons.extend(slow_macro["reasons"])
                cap = min(cap, slow_macro["cap"])

            if halt_reasons:
                logger.warning(f"  Hard vetoes active: {'; '.join(halt_reasons)}, cap={cap}%")
            if cap < 100.0:
                logger.info(f"  Score capped from {scaled_score:.1f}% to {cap}%")

            final = min(scaled_score, cap)

            # Determine recommended state based on final exposure score. Sourced from
            # EXPOSURE_TIERS (algo/risk/exposure_policy.py) - the actual policy tier
            # tier_for_exposure() will select for this same score - rather than a second,
            # independently-hardcoded copy of the same 70/45/25 boundaries, which could
            # silently drift out of sync with the real policy tiers if either one is ever
            # tuned without remembering to update the other. UNCHANGED by this redesign -
            # see module docstring on why the downstream regime taxonomy stays as-is.
            from algo.risk.exposure_policy import tier_for_exposure

            regime = tier_for_exposure(final)["name"]

            logger.info(
                f"[MARKET_EXPOSURE_FINAL] exposure_pct={final}%, regime={regime}, raw_score={score:.1f}, "
                f"pillars=trend:{pillar_trend_score:.0f}/risk:{pillar_risk_score:.0f}/confirm:{pillar_confirm_score:.0f}"
            )

            # CRITICAL: distribution_days is required for position sizing hard vetoes
            # Never default to 0 - missing data must be detected as error, not assumed "clean market"
            if sp_count is None:
                msg = (
                    "[EXPOSURE CRITICAL] Distribution days calculation failed (sp_count is None). "
                    "Cannot persist exposure score without distribution day count for veto checks. "
                    "Check: (1) selling_pressure() implementation, (2) distribution data freshness"
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            factors = {
                "pillar_trend": {
                    "score": round(pillar_trend_score, 1),
                    "pts": round(trend_pts, 1),
                    "max": self.W_PILLAR_TREND,
                    "components": {"trend_30wk": t30, "spy_momentum": mom, "market_technicals": mtech},
                },
                "pillar_risk": {
                    "score": round(pillar_risk_score, 1),
                    "pts": round(risk_pts, 1),
                    "max": self.W_PILLAR_RISK,
                    "components": {"selling_pressure": sp, "vix_regime": vix, "credit_spread": cs},
                },
                "pillar_confirm": {
                    "score": round(pillar_confirm_score, 1),
                    "pts": round(confirm_pts, 1),
                    "max": self.W_PILLAR_CONFIRM,
                    "components": {
                        "participation": {
                            "score": round(participation_score, 1),
                            "breadth": breadth,
                            "new_highs_lows": nhnl,
                            "ad_line": ad,
                        },
                        "sentiment": {
                            "score": round(sentiment_score, 1),
                            "aaii_sentiment": aaii,
                            "put_call_ratio": pc,
                        },
                    },
                },
                "macro_watch": {
                    "sahm_rule": sahm,
                    "yield_curve": yc,
                    "inflation_expectations": infl,
                    "slow_macro_veto": slow_macro,
                },
                "vol_managed_scaling": {
                    "multiplier": vol_mult,
                    "note": (
                        "active since 2026-08-24 (Phase B backtest passed on SPY/QQQ)"
                        if eval_date >= self._VOL_MANAGED_ACTIVATION_DATE
                        else "inert (pinned 1.0): eval_date precedes 2026-08-24 activation"
                    ),
                },
            }

            result = {
                "eval_date": str(eval_date),
                "raw_score": round(score, 1),
                "available_factors_max": 100.0,  # always fully available - pillars renormalize internally
                "capped_score": round(final, 1),
                "exposure_pct": round(final, 1),
                "regime": regime,
                "halt_reasons": halt_reasons,
                "distribution_days": int(sp_count),
                "factors": factors,
            }
            self._persist(eval_date, result)
            return result


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
                    raw_score, exposure_tier, date, data_unavailable, reason
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
                data_unavailable,
                reason,
            ) = row

            # GOVERNANCE: Check data_unavailable flag FIRST before using any data
            # If upstream loader marked data as unavailable, fail-fast regardless of other fields
            if data_unavailable:
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] market_exposure_daily for {eval_date} marked data_unavailable=True. "
                    f"Reason: {reason}. "
                    f"Cannot apply position sizing policy with unavailable market regime data. "
                    f"Check upstream loader status and fix the data source."
                )

            # CRITICAL FIX: Use trading-day logic, not calendar days
            # market_exposure_daily is generated after market close (~4:05 PM ET) each trading day.
            # On Mondays, data from Friday is 3-5 calendar days old but is from the most recent trading day - that's NORMAL
            # Do NOT halt on Monday with "data 3 days old" when that data is from Friday's close
            from algo.infrastructure import MarketCalendar

            now_et = datetime.now(EASTERN_TZ)
            if MarketCalendar.is_trading_day(eval_date) and eval_date == now_et.date() and now_et.hour < 16:
                # PREVIOUS BUG: required _cached_date == eval_date whenever eval_date was a trading
                # day, with no exception for "today, but before the 4:05 PM EOD load has run yet".
                # That made every intraday/morning read of today's own regime raise unconditionally,
                # every single trading day - the EOD row for today cannot exist before EOD runs.
                # Same-day, pre-close: the previous trading day's snapshot is the most recent
                # COMPLETE one and is the expected/acceptable data.
                expected_trading_day = eval_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(expected_trading_day):
                        break
                    expected_trading_day -= timedelta(days=1)
            elif MarketCalendar.is_trading_day(eval_date):
                # eval_date is a trading day that has already closed (today after 4 PM ET, or a
                # historical/backfill date): require that day's own data.
                expected_trading_day = eval_date
            else:
                # eval_date is a weekend/holiday: data from the most recent trading day is expected.
                expected_trading_day = eval_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(expected_trading_day):
                        break
                    expected_trading_day -= timedelta(days=1)

            if _cached_date < expected_trading_day:
                calendar_age = (eval_date - _cached_date).days
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] market_exposure_daily data too stale: {_cached_date} vs expected {expected_trading_day} "
                    f"(calendar age: {calendar_age} days). Cannot apply position sizing policy with stale market regime."
                )

            if exposure_pct is None:
                raise MarketDataUnavailableError(
                    f"[MARKET REGIME] market_exposure_daily for {eval_date} has NULL exposure_pct. "
                    f"Critical data corruption - cannot determine position sizing constraints. "
                    f"Cannot proceed until database is repaired."
                )

            # CRITICAL: Regime and exposure_tier are REQUIRED fields
            # Never allow fallback to "unknown" - position sizing requires valid tier names
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
                        f"[MARKET REGIME] Malformed halt_reasons JSON for {eval_date}: {e} - treating as empty list"
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
        # CRITICAL: Never return fake "unknown" regime - raise error instead
        # Position sizing code cannot handle "unknown" tier; must fail-fast
        msg = (
            f"[MARKET REGIME CRITICAL] Could not read market regime for {eval_date}: {type(e).__name__}: {e} "
            f"- Market exposure data unavailable. Position sizing cannot proceed without valid regime. "
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
    logger.info(f"MARKET EXPOSURE - {result['eval_date']}")
    logger.info(f"Regime: {result['regime']}")
    logger.info(f"Exposure %: {result['exposure_pct']}%")
    logger.info(f"Raw score: {result['raw_score']}")
    logger.info(f"Selling pressure days: {result['distribution_days']}")
    if result["halt_reasons"]:
        logger.warning("HALT REASONS:")
        for r in result["halt_reasons"]:
            logger.warning(f"  - {r}")
    logger.info("Pillar breakdown:")
    for name, info in result["factors"].items():
        if "pts" not in info:
            continue  # macro_watch/vol_managed_scaling carry no pts/max - display only
        pts = info["pts"]
        max_pts = info["max"]
        logger.info(f"  {name:16s}: {pts:5.1f} / {max_pts:>4} pts  (score={info.get('score')})")
    macro_watch = result["factors"]["macro_watch"]
    if macro_watch["slow_macro_veto"].get("triggered"):
        logger.warning(f"  Slow macro veto active: {macro_watch['slow_macro_veto']['reasons']}")
