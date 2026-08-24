#!/usr/bin/env python3

"""
Quantitative Market Exposure Engine - Trend & Momentum composite + hard vetoes

Composite 0-100 portfolio risk allocation score, built on THREE layers:
  1. A conviction composite: ONE scored pillar (Trend & Momentum) - the single signal
     with real, uncontested, decades-of-out-of-sample-replication evidence behind it
     (Faber/TSMOM). Two other pillars (Independent Risk Layers, Breadth & Sentiment)
     are still computed every run but carry ZERO composite weight - see "PASS
     2026-08-24" below for why, and "PILLAR 2/3" for what they're used for instead.
  2. A volatility-managed scaling multiplier on top of the composite - present in the
     architecture but pinned to 1.0 (inert) until backtested against this system's own
     history (see _vol_managed_multiplier's docstring).
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

PILLAR 1 - TREND & MOMENTUM (45pt, the anchor - largest single share of the composite):
    trend_30wk (55% of pillar):     SPY price vs rising/flat/falling 30-week MA
    spy_momentum (35% of pillar):   trailing 12-month return (TSMOM)
    market_technicals (10%,
      optional, degrades gracefully): SPY RSI(14) + MACD(12,26,9), blended 50/50 -
      deliberately does NOT re-derive SPY-vs-MA (already trend_30wk); RSI/MACD are
      distinct constructs not represented elsewhere in this pillar.
    If market_technicals is unavailable, the pillar renormalizes over trend_30wk/
    spy_momentum alone (55/35 -> ~61/39) rather than leaving weight unspent.

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
against this system's own history (once one exists - see _vol_managed_multiplier's
docstring for why that harness doesn't exist yet) demonstrates otherwise.

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
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.config.main import AlgoConfig
from algo.infrastructure.config.sql_intervals import get_interval_sql
from algo.risk.market_factor_calculator import MarketFactorCalculator
from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MarketExposure:
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

    # --- Internal sub-weights within Pillar 1 (Trend & Momentum). Renormalized over
    # whatever's available if market_technicals is unavailable (see _blend_scores).
    SUBW_TREND_30WK = 0.55
    SUBW_SPY_MOMENTUM = 0.35
    SUBW_MARKET_TECHNICALS = 0.10

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

    def _vol_managed_multiplier(self) -> float:
        """Layer 2: volatility-managed scaling multiplier (Moreira & Muir, 2017, JoF -
        scale exposure inversely to realized volatility).

        PINNED TO 1.0 (INERT) - Phase A of the 2026-08-23 redesign ships this layer's
        seam in the architecture without live logic. The underlying research is real
        but genuinely contested: Cederburg et al. found volatility-managed portfolios
        fail out-of-sample, and Barroso & Detzel found they don't survive transaction
        costs. This system has no out-of-sample validation harness for the exposure
        model yet (market_exposure_daily's own history is both too shallow, ~3.5
        months, and internally inconsistent across formula changes to serve as ground
        truth), so this multiplier must be proven against this system's own data
        (Phase B, a scoped Trend+Momentum+VIX+Credit backtest computable directly from
        price_daily/economic_data) before it's allowed to actually move exposure. Do
        not compute a real vol_mult here until that validation exists - an untested
        multiplier moving live position sizing is exactly the kind of unproven addition
        this redesign is trying to avoid.

        DATA AUDIT (2026-08-24, checked live against this system's own DB rather than
        assumed): VIXCLS in economic_data has real, ample history for a backtest signal
        (26 years, 2000-01-03 to present, 6692 rows) - VIX is NOT the blocker. Credit
        spread (BAMLH0A0HYM2) is permanently capped at a rolling ~3-year window - not a
        backfill gap but an external FRED distribution-policy change (April 2026, see
        _credit_spread's own docstring), unfixable without sourcing raw ICE data
        directly. The real binding constraint is price_daily itself: SPY (and the rest
        of the live trading universe - AAPL/MSFT/QQQ checked, same start) only goes
        back to 2021-05-19 locally (~5.25 years, 1321 rows) - a handful of unrelated
        legacy tickers (ERIC/DEO/ELLO/EDN/EC/CVE) have older history but aren't SPY or a
        usable market-wide proxy. 5.25 years is one bear-market sample (2022) - nowhere
        near the decades of data the Moreira-Muir/Cederburg/Barroso-Detzel literature
        itself used to reach even their CONTESTED conclusions, so a backtest run today
        would produce a result indistinguishable from noise on a single historical path,
        not real statistical proof - exactly what this docstring already said not to
        ship. Concrete unblock (not attempted this session - a historical price backfill
        is a real infrastructure action with API rate-limit/cost implications, must go
        through the pipeline scheduler per [[feedback_always_use_pipeline_scheduler_for_backfills]],
        not be run ad hoc): extend SPY's (and ideally the broader universe's) price
        history further back before attempting Phase B again.
        """
        return 1.0

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

            # ============= LAYER 2: VOLATILITY-MANAGED SCALING (inert, see docstring) =============
            vol_mult = self._vol_managed_multiplier()
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
                    "note": "inert (pinned to 1.0) pending Phase B backtest",
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

    # ====== Factor implementations ======
    # NOTE: Most factor calculations are delegated to MarketFactorCalculator (self.calculator.*).
    # The methods below (_has_market_confirmation, _ad_line, _credit_spread, the z-scored
    # macro factors, market technicals, slow macro veto) are the canonical implementations
    # for factors not yet migrated to MarketFactorCalculator, and are called directly from
    # compute().

    def _single_series_zscore_factor(
        self,
        eval_date: _date,
        cur: PsycopgCursor[Any],
        series_id: str,
        higher_is_worse: bool,
        lookback: int = 10000,
    ) -> dict[str, Any]:
        """Shared helper: z-score a single economic_data series against its own real
        history (standard Barra/Axioma-style normalization - see MarketFactorCalculator
        ._sample_zscore). Degrades to data_unavailable rather than raising - these are
        macro-watch-only inputs now (see module docstring), not scored composite factors.
        """
        cur.execute(
            "SELECT value::float FROM economic_data WHERE series_id = %s AND date <= %s "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT %s",
            (series_id, eval_date, lookback),
        )
        rows = [r[0] for r in cur.fetchall()]
        if not rows:
            return {"data_unavailable": True, "reason": f"No {series_id} data on or before {eval_date}"}
        current = rows[0]
        if math.isnan(current) or math.isinf(current):
            return {"data_unavailable": True, "reason": f"Non-finite {series_id} reading"}
        z = self.calculator._sample_zscore(current, rows)
        if z is None:
            return {
                "data_unavailable": True,
                "reason": (
                    f"Cannot z-score {series_id}: insufficient history (have {len(rows)}, need 15+) "
                    f"or zero variance in that history"
                ),
                "value": round(current, 3),
            }
        stress_z = z if higher_is_worse else -z
        return {
            "score": self.calculator._zscore_to_score(stress_z),
            "value": round(current, 3),
            "z": round(stress_z, 2),
        }

    def _yield_curve_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Yield curve reading: T10Y2Y + T10Y3M, each z-scored against own history,
        averaged - MACRO WATCH ONLY (see module docstring): not scored in the composite,
        feeds only the slow macro veto's persistence check (_yield_curve_inverted_persistent)
        and this dict's own z-scored snapshot for dashboard/audit display.

        T10Y2Y and T10Y3M are 0.941 correlated over their real 26-year FRED history (both
        backfilled to 1990 - see scripts/backfill_economic_data_history.py), i.e.
        substantially the same underlying curve-slope information. Both are still read
        (averaged into one z-score here) rather than picking just one, preserving the small,
        real divergence between the short and long end at regime turns (2001, 2019) - they
        already share one combined read, not two separately-weighted votes, so this isn't
        the double-counting pattern the pre-redesign file used to find and fix elsewhere. A
        more negative (more inverted) spread is the bearish direction for both, so z is
        flipped before scoring.
        """
        pieces = []
        detail: dict[str, Any] = {}
        for series_id, key in (("T10Y2Y", "t10y2y"), ("T10Y3M", "t10y3m")):
            r = self._single_series_zscore_factor(eval_date, cur, series_id, higher_is_worse=False)
            detail[key] = r
            if not r.get("data_unavailable"):
                pieces.append(r["score"])
        if not pieces:
            return {"data_unavailable": True, "reason": "Neither T10Y2Y nor T10Y3M could be z-scored", **detail}
        return {"score": round(sum(pieces) / len(pieces), 1), **detail}

    def _yield_curve_inverted_persistent(self, eval_date: _date, cur: PsycopgCursor[Any]) -> bool:
        """True if the averaged T10Y2Y/T10Y3M spread has been negative (inverted) on
        EVERY available trading day for the trailing YIELD_CURVE_INVERSION_WINDOW_DAYS
        sessions (~3 months) - a persistence check for the slow macro veto, distinct
        from _yield_curve_factor's single-day z-score read. Requires a full window of
        real data (returns False, not data_unavailable, if there isn't one - this is a
        veto input, and an unproven/incomplete signal must not trip a cap).
        """
        cur.execute(
            """
            SELECT a.date, (a.value + b.value) / 2.0
            FROM economic_data a
            JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10Y3M'
            WHERE a.series_id = 'T10Y2Y' AND a.date <= %s
              AND a.value IS NOT NULL AND b.value IS NOT NULL
            ORDER BY a.date DESC LIMIT %s
            """,
            (eval_date, self.YIELD_CURVE_INVERSION_WINDOW_DAYS),
        )
        rows = cur.fetchall()
        if len(rows) < self.YIELD_CURVE_INVERSION_WINDOW_DAYS:
            return False
        return all(float(r[1]) < 0 for r in rows)

    def _inflation_expectations_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Inflation Expectations reading: T5YIE + T10YIE breakeven average, z-scored -
        MACRO WATCH ONLY (see module docstring): not scored in the composite, feeds only
        the slow macro veto's tail-extreme check and this dict's own snapshot for
        dashboard/audit display.

        Averaging the 5Y and 10Y tenors of the same market-implied measurement (TIPS vs.
        nominal Treasury spread) is a standard fixed-income simplification - confirmed
        0.84 correlation between the two tenors, i.e. genuinely the same underlying
        signal read at two maturities. Elevated breakeven inflation implies the Fed is
        more likely to stay restrictive - the bearish direction for risk assets, so
        higher_is_worse.
        """
        cur.execute(
            """
            SELECT a.date, (a.value + b.value) / 2.0
            FROM economic_data a
            JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10YIE'
            WHERE a.series_id = 'T5YIE' AND a.date <= %s
              AND a.value IS NOT NULL AND b.value IS NOT NULL
            ORDER BY a.date DESC LIMIT 10000
            """,
            (eval_date,),
        )
        rows = [float(r[1]) for r in cur.fetchall()]
        if not rows:
            return {"data_unavailable": True, "reason": f"No overlapping T5YIE/T10YIE data on or before {eval_date}"}
        current = rows[0]
        if math.isnan(current) or math.isinf(current):
            return {"data_unavailable": True, "reason": "Non-finite breakeven average"}
        z = self.calculator._sample_zscore(current, rows)
        if z is None:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient breakeven history to z-score (have {len(rows)}, need 15+)",
                "value": round(current, 3),
            }
        return {"score": self.calculator._zscore_to_score(z), "value": round(current, 3), "z": round(z, 2)}

    def _market_technicals_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Market Technicals: SPY RSI(14) + MACD(12,26,9) histogram, blended - a minor
        (10% weight) sub-signal inside Pillar 1 (Trend & Momentum), not a standalone
        pillar - it's price-derived, same information family as trend_30wk/spy_momentum.

        Deliberately does NOT re-derive SPY price vs its 30-week MA (already trend_30wk)
        or vs the 50/200-DMA breadth reads (already Pillar 3's participation sub-score) -
        those are this file's existing long-term-trend/participation reads and adding
        another SPY-vs-MA sub-metric here would be exactly the double-counting bug class
        real multi-factor models are built to avoid. RSI and MACD are genuinely distinct
        constructs - not represented anywhere else in this model:

          - RSI(14): a bounded (0-100), universally-thresholded oscillator (70/30
            overbought/oversold is the standard convention). Scored contrarian-at-
            extremes with a neutral dead-zone (same convention as AAII/Put-Call): 40-60
            is neutral (50pts), ramping to 100 by RSI<=20 (oversold -> bullish
            contrarian) and down to 0 by RSI>=80 (overbought -> bearish contrarian).
          - MACD histogram, normalized by price (histogram/close, not raw points) and
            z-scored against its own trailing history (same Barra/Axioma-style
            normalization used elsewhere) - scored DIRECTLY (higher_is_worse=False):
            strengthening positive histogram is real trend-confirming bullish momentum,
            not an investor-psychology extreme to fade.

        Blended 50/50 - a short-term mean-reversion oscillator and a medium-term trend-
        confirmation signal, neither dominates the other's information content.
        """
        cur.execute(
            "SELECT close, date FROM price_daily WHERE symbol = 'SPY' AND date <= %s "
            "AND close IS NOT NULL ORDER BY date DESC LIMIT 400",
            (eval_date,),
        )
        rows = cur.fetchall()
        if len(rows) < 220:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient SPY price history for technicals (have {len(rows)}, need 220+)",
            }

        from algo.infrastructure import MarketCalendar

        most_recent_date = rows[0][1]
        expected_date = eval_date - timedelta(days=1)
        for _ in range(10):
            if MarketCalendar.is_trading_day(expected_date):
                break
            expected_date -= timedelta(days=1)
        if most_recent_date < expected_date:
            return {
                "data_unavailable": True,
                "reason": (
                    f"SPY price data is stale: most recent close from {most_recent_date}, "
                    f"but eval_date is {eval_date} (expected data from {expected_date})."
                ),
            }

        closes = [float(r[0]) for r in reversed(rows)]
        if any(math.isnan(c) or math.isinf(c) or c <= 0 for c in closes):
            return {"data_unavailable": True, "reason": "Non-finite or non-positive SPY close in technicals window"}

        rsi = self.calculator._compute_rsi(closes, period=14)
        if rsi is None:
            return {"data_unavailable": True, "reason": "RSI computation failed (insufficient data)"}

        hist_pct_series = self.calculator._macd_histogram_pct_series(closes)
        warm_up = 200
        zscore_window = hist_pct_series[warm_up:]
        if len(zscore_window) < 15:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient MACD history after warm-up to z-score (have {len(zscore_window)}, need 15+)",
            }
        current_hist_pct = zscore_window[-1]
        macd_z = self.calculator._sample_zscore(current_hist_pct, zscore_window)
        if macd_z is None:
            return {"data_unavailable": True, "reason": "Cannot z-score MACD histogram (zero variance in history)"}

        if rsi >= 80:
            rsi_score = 0.0
        elif rsi <= 20:
            rsi_score = 100.0
        elif rsi >= 60:
            rsi_score = 50.0 - (rsi - 60) / 20.0 * 50.0
        elif rsi <= 40:
            rsi_score = 50.0 + (40 - rsi) / 20.0 * 50.0
        else:
            rsi_score = 50.0

        macd_score = self.calculator._zscore_to_score(-macd_z)
        composite = round(0.5 * rsi_score + 0.5 * macd_score, 1)
        return {
            "score": composite,
            "rsi_14": round(rsi, 1),
            "rsi_score": round(rsi_score, 1),
            "macd_histogram_pct": round(current_hist_pct, 4),
            "macd_z": round(macd_z, 2),
            "macd_score": round(macd_score, 1),
        }

    def _has_market_confirmation(self, eval_date: _date, cur: PsycopgCursor[Any]) -> bool:
        """Detect a volume-backed rally day in last 30 days.

        A qualifying day: index closes ≥1.7% on volume above prior day.
        Used only as a hard veto condition (not a scoring factor): when SPY
        is below its 30-week MA and no such day has occurred, the market has
        not confirmed an attempted recovery, so exposure is capped at 40%.
        """
        interval_30d = get_interval_sql("30d")
        cur.execute(
            f"""
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       LAG(volume) OVER (ORDER BY date) AS prev_vol
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                  AND date >= %s::date - {interval_30d}
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

    def _ad_line(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """A/D line: cumulative advancers - decliners vs SPY direction.

        Uses pre-computed advance_decline_ratio from market_health_daily and
        SPY close from price_daily (fast, <1s indexed lookups) instead of
        computing LAG() window functions across 5000 stocks x 35 days (~175,000 rows).
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
            msg = (
                f"[MARKET_EXPOSURE CRITICAL] Insufficient A/D line data for {eval_date}: "
                f"{len(rows)} rows, need 5+. "
                f"A/D line is required for accurate market breadth assessment. "
                f"Cannot compute exposure score with missing historical data. "
                f"Check market_health_daily table for advance_decline_ratio data gaps."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        nets = []
        ad_dates = []
        for r in rows:
            if len(r) < 3:
                msg = (
                    f"[MARKET_EXPOSURE CRITICAL] A/D line query returned corrupted row with {len(r)} fields. "
                    f"Expected (date, ratio, spy_close). "
                    f"Cannot compute A/D line with malformed data. "
                    f"Check market_health_daily and price_daily tables."
                )
                logger.error(msg)
                raise RuntimeError(msg)
            row_date, ratio = r[0], r[1]
            if ratio is None:
                msg = (
                    f"[MARKET_EXPOSURE CRITICAL] A/D ratio corrupted/missing for {row_date}. "
                    f"Cannot compute A/D line with data gaps - requires complete daily sequence. "
                    f"Check market_health_daily table for data quality."
                )
                logger.error(msg)
                raise RuntimeError(msg)
            nets.append((float(ratio) - 1) / (float(ratio) + 1))
            ad_dates.append(row_date)

        if len(nets) < 2:
            msg = (
                f"[MARKET_EXPOSURE CRITICAL] Insufficient valid A/D ratios for {eval_date}. "
                f"A/D line calculation requires minimum 2 valid data points. "
                f"Check market_health_daily table for data completeness."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        first_net = nets[0]
        last_net = nets[-1]
        ad_change = last_net - first_net

        # Extract first and last SPY closes from the rows tuple data
        if len(rows[0]) < 3 or rows[0][2] is None:
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] First SPY close missing for A/D line on {eval_date}. "
                f"Cannot compute trend direction without benchmark data. "
                f"Check price_daily table for SPY data."
            )
        if len(rows[-1]) < 3 or rows[-1][2] is None:
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] Last SPY close missing for A/D line on {eval_date}. "
                f"Cannot compute trend direction without benchmark data. "
                f"Check price_daily table for SPY data."
            )

        first_spy = float(rows[0][2])
        last_spy = float(rows[-1][2])

        if math.isnan(first_spy) or math.isinf(first_spy) or math.isnan(last_spy) or math.isinf(last_spy):
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] Non-finite SPY price (first={first_spy}, last={last_spy}) on {eval_date}. "
                f"Cannot compute A/D line direction without valid benchmark price. "
                f"Check price_daily table for SPY data integrity."
            )

        if first_spy <= 0:
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] Invalid first SPY price {first_spy} on {eval_date}. "
                f"Cannot compute A/D line direction without valid benchmark price. "
                f"Check price_daily table for SPY data integrity."
            )

        spy_change_pct = (last_spy - first_spy) / first_spy * 100.0
        # Ordered worst to best: bearish_confirming (0, real broad decline) <
        # bearish_divergence (30, rally not broadly supported) < bullish_divergence (60,
        # breadth improving despite price dip - "hidden bullish") < bullish_confirming (100).
        if ad_change > 0 and spy_change_pct > 0:
            score = 100.0
            relation = "bullish_confirming"
        elif ad_change > 0 and spy_change_pct < 0:
            score = 60.0  # hidden bullish
            relation = "bullish_divergence"
        elif ad_change < 0 and spy_change_pct < 0:
            score = 0.0  # confirmed broad-based decline - worse than a mere divergence
            relation = "bearish_confirming"
        else:
            score = 30.0  # bearish divergence
            relation = "bearish_divergence"
        return {
            "score": score,
            "ad_change_20d": round(ad_change, 4),
            "spy_change_pct_20d": round(spy_change_pct, 2),
            "relation": relation,
            "direction": "up" if ad_change > 0 else "down",
        }

    def _credit_spread(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """HY OAS credit spread (BAMLH0A0HYM2) - credit leads equity.

        Based on Apollo/Torsten Slok research: HY spreads widen 4-6 weeks
        before equity markets price in credit risk. Rapidly widening spreads
        (>+1pp in 20 trading days) get an additional 20% score haircut.

        CRITICAL: Credit spread mean-reversion signal requires 20+ days of history.
        Without trend, we cannot reliably assess credit cycle direction.
        No fallback to partial history - require minimum 20 days or raise error.

        Scale: <3.5% = tight/healthy, 4-5% = mild stress, >7% = severe stress.

        FRED changed its distribution policy for ICE BofA index series (including this
        factor's own BAMLH0A0HYM2) in April 2026 - only a rolling ~3-year window is
        served via the API now regardless of request range. This is a permanent
        external ceiling on how much HY OAS history this factor can ever pull from FRED
        directly - not fixable without sourcing raw ICE data directly.
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
        if not rows or len(rows) < 1:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] No HY OAS data (BAMLH0A0HYM2) for {eval_date}. "
                f"Credit spreads are a required factor for exposure calculation. "
                f"Cannot assess credit market stress without HY spread data. "
                f"Check economic_data table for BAMLH0A0HYM2 series."
            )

        # Validate current HY value
        if len(rows[0]) < 1 or rows[0][0] is None:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Current HY OAS value is NULL for {eval_date}. "
                f"Cannot calculate credit spread score without current reading. "
                f"Check economic_data table - latest BAMLH0A0HYM2 entry may be corrupted."
            )

        hy = float(rows[0][0])

        if math.isnan(hy) or math.isinf(hy):
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Non-finite HY OAS value ({hy}) for {eval_date}. "
                f"Cannot calculate credit spread score without a valid current reading. "
                f"Check economic_data table for BAMLH0A0HYM2 data integrity."
            )

        # CRITICAL: 20-day trend is required for credit spread signal (mean-reversion indicator)
        if len(rows) < 20:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Insufficient HY OAS history for {eval_date}: "
                f"have {len(rows)} days, but require 20+ days for mean-reversion trend analysis. "
                f"Credit spread signals (leading economic indicator) require full 20-day window. "
                f"Cannot assess credit cycle direction with incomplete history - risk assessment incomplete. "
                f"Check: (1) economic_data table completeness, (2) BAMLH0A0HYM2 loader freshness"
            )

        # Validate 20d-ago value (last row in reverse-chronological order)
        if len(rows[-1]) < 1 or rows[-1][0] is None:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] 20-day historical HY OAS value is NULL for {eval_date}. "
                f"Cannot calculate credit spread trend without historical anchor. "
                f"Check economic_data table - older BAMLH0A0HYM2 entries may have gaps."
            )

        hy_20d_ago = float(rows[-1][0])
        if math.isnan(hy_20d_ago) or math.isinf(hy_20d_ago):
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Non-finite 20-day-ago HY OAS value ({hy_20d_ago}) for {eval_date}. "
                f"Cannot calculate credit spread trend without a valid historical anchor. "
                f"Check economic_data table for BAMLH0A0HYM2 data integrity."
            )
        widening_1pp = (hy - hy_20d_ago) > 1.0

        if hy < 3.5:
            score = 100.0
        elif hy < 4.5:
            score = 85.0
        elif hy < 5.5:
            score = 65.0
        elif hy < 7.0:
            score = 35.0
        else:
            score = 10.0

        # Rapid widening haircut: stress is accelerating
        if widening_1pp and hy > 4.0:
            score *= 0.80

        result = {
            "score": round(score, 1),
            "value": round(hy, 3),
            "widening_rapidly": widening_1pp,
            "hy_20d_ago": round(hy_20d_ago, 3),
        }
        return result

    @staticmethod
    def _sahm_ramp_score(sahm_value: float) -> float:
        """Map a Sahm value to a 0-100 factor score via a ramp anchored on Sahm's own real,
        published 0.50pp trigger - not a generic z-score.

        The raw historical Sahm-value series is heavily right-skewed (mean 0.497, stdev
        1.265, driven almost entirely by a handful of extreme 2008-09/2020 crisis
        readings) even though 80% of months never came remotely close to triggering. A
        generic sample z-score against that distribution would call a reading of 0.0
        "roughly average" purely because a few historic crisis spikes drag the mean up
        near the trigger threshold - the wrong tool for a fundamentally regime-switching
        statistic. This ramp instead respects the threshold's real, research-backed
        meaning directly: 100 at or below 0 (no recessionary signal at all), linearly
        down to 40 exactly AT the literal 0.50pp trigger, continuing down to 0 by +1.5pp.
        """
        if sahm_value <= 0.0:
            return 100.0
        if sahm_value < 0.50:
            return 100.0 - (sahm_value / 0.50) * 60.0
        if sahm_value >= 1.50:
            return 0.0
        return 40.0 - ((sahm_value - 0.50) / 1.0) * 40.0

    def _sahm_rule_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sahm Rule recession indicator, computed from UNRATE (FRED, monthly) -
        MACRO WATCH ONLY (see module docstring): not scored in the composite, feeds only
        the slow macro veto's "triggered" check and this dict's own snapshot for
        dashboard/audit display.

        Real-time Sahm Rule = (3-month average unemployment rate) minus (the minimum
        3-month average unemployment rate over the trailing 12 months). "triggered"
        (>= 0.50pp) is reported for transparency/logging/dashboard display and directly
        drives the slow macro veto. Requires 15 months of history (3 for the current
        average, 12 more for the trailing-minimum window); degrades to data_unavailable
        rather than raising.
        """
        cur.execute(
            "SELECT value::float, date FROM economic_data "
            "WHERE series_id = 'UNRATE' AND date <= %s AND value IS NOT NULL "
            "ORDER BY date DESC LIMIT 20",
            (eval_date,),
        )
        rows = cur.fetchall()
        if len(rows) < 15:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient UNRATE history for Sahm Rule (have {len(rows)} months, need 15+)",
            }
        values = [float(r[0]) for r in rows]
        if any(math.isnan(v) or math.isinf(v) for v in values):
            return {"data_unavailable": True, "reason": "Non-finite UNRATE reading in trailing window"}

        # rows[0] is the most recent month; 3-month trailing averages ending at each month
        # index i (i=0 is "ending this month") for i in 0..12, matching the official
        # methodology's 12-month lookback window of 3-month averages.
        trailing_3mo_avgs = [sum(values[i : i + 3]) / 3.0 for i in range(13)]
        current_avg = trailing_3mo_avgs[0]
        trailing_12mo_min = min(trailing_3mo_avgs[1:13])
        sahm_value = current_avg - trailing_12mo_min
        return {
            "score": self._sahm_ramp_score(sahm_value),
            "value": round(sahm_value, 2),
            "triggered": sahm_value >= 0.50,
        }

    def _slow_macro_veto(
        self, eval_date: _date, cur: PsycopgCursor[Any], sahm: dict[str, Any], infl: dict[str, Any]
    ) -> dict[str, Any]:
        """Layer 3, new: a deliberately slow, wide, rare tail-risk veto fed by Sahm Rule,
        yield-curve inversion persistence, and inflation-expectations tail extremes.

        Estrella & Mishkin (1998): yield-curve inversion leads recessions by 6-24
        months. Real recession/stress signals, but the wrong horizon for this system's
        days-to-weeks swing-trading exposure dial - so they no longer earn composite
        weight (see module docstring). Demoted here instead of dropped, because the
        underlying signals ARE real; a single trip caps exposure to SLOW_MACRO_VETO_CAP
        (45%) - a background elevated-risk flag, less severe than the daily-signal
        vetoes above, reflecting the genuinely longer horizon these operate on. Multiple
        simultaneous triggers still cap to the same 45% (not stacked lower) since all
        three are correlated reads of the same underlying macro-stress regime, not
        independent risks that compound.
        """
        reasons: list[str] = []

        if not sahm.get("data_unavailable") and sahm.get("triggered"):
            reasons.append(f"Sahm Rule triggered ({sahm.get('value')}pp >= 0.50pp recession signal)")

        if self._yield_curve_inverted_persistent(eval_date, cur):
            reasons.append(
                f"Yield curve (T10Y2Y/T10Y3M avg) inverted continuously for "
                f"{self.YIELD_CURVE_INVERSION_WINDOW_DAYS}+ trading days"
            )

        if not infl.get("data_unavailable"):
            infl_z = infl.get("z")
            if infl_z is not None and infl_z >= self.INFLATION_EXPECTATIONS_TAIL_Z:
                reasons.append(f"Inflation expectations at tail extreme (z={infl_z})")

        if reasons:
            return {"triggered": True, "reasons": reasons, "cap": self.SLOW_MACRO_VETO_CAP}
        return {"triggered": False, "reasons": [], "cap": 100.0}

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
            with DatabaseContext("write") as cur:
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
