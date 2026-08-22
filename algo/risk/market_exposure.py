#!/usr/bin/env python3

"""
Quantitative Market Exposure Engine - Research-backed 18-factor composite + hard vetoes

Composite 0-100 portfolio risk allocation score, built on exactly TWO mechanisms:
a single weighted-sum composite (every input that carries directional information
about market risk, on equal footing, summed to 100pt) and an independent hard-veto
layer (binary, rare, extreme conditions that override the composite regardless of
score - standard separation of alpha/context from risk management, matching how a
multi-strat shop keeps risk limits independent of and overriding to any signal).

REDESIGNED 2026-08-22 (goal: exposure-model integrity review) in two passes the same
day. Pass 1 removed a third, in-between "modifier" mechanism that had accumulated
since the 2026-08-20 redesign: 4 signals (economic overlay, sector rotation,
cross-asset confirmation, fundamental quality) were bolted on as post-score
point-deltas instead of properly weighted factors, each with its own arbitrary point
range and, in one case (VIX), a stray multiplicative combination nothing else in the
file used. Pass 1 also correlation-checked the newly-split-out macro signals against
EACH OTHER (ANFCI vs STLFSI4, T10Y2Y vs T10Y3M, T5YIE vs T10YIE) and dropped IG OAS
(0.952 corr with ANFCI) and CFNAI (only 37 rows, too sparse to verify) on that basis.

Pass 2 (same day, user-prompted second look) found that pass 1's redundancy audit
stopped one level too shallow: it checked the new macro signals against each other,
but never against the pre-existing, longer-history factors (Credit Spread, Yield
Curve) already in the model. Re-checked directly against real data in this DB:
  - STLFSI4 ("Financial Stress") correlates 0.748 with HY OAS (BAMLH0A0HYM2) - already
    a direct 7.5pt factor AND its own hard veto. That is MORE redundant than the
    0.057 STLFSI4-vs-ANFCI check pass 1 used to justify keeping it.
  - ANFCI ("Financial Conditions") correlates -0.762 with T10Y3M (already half of the
    Yield Curve factor) and 0.528 with HY OAS.
  - Both series also only have 2023-06+ history in this DB (~167 points, no recession
    in-sample) - too thin a sample to trust a 2.5-sigma tail read on their own, on top
    of being substantially explained by factors that DO have long, cycle-spanning
    history (T10Y3M back to 2015, UNRATE back to 2000).
Conclusion: Financial Conditions and Financial Stress were dropped entirely as
separately-scored factors (and ANFCI's extreme-tail veto with it) - not because the
pairwise checks in pass 1 were wrong (re-verified, they were correct), but because
checking only sibling-vs-sibling correlation among the newly-added signals missed
that the real overlap was with the model's own pre-existing pillars. Their combined
6pt budget was returned to Credit Spread (+3) and Yield Curve (+1) - the two
transparent, long-history pillars this info was actually chasing - with the
remaining 2pt going to Sahm Rule (see below).

Pass 2 also demoted Sahm Rule from a hard veto to a graded factor - not a redundancy
finding, a soundness one. A single monthly, revision-prone UNRATE print
unilaterally capping the whole portfolio at 25% is a real operational tail risk in
its own right, and the "near-100% historical hit rate" framing predates a concrete
counterexample: the real-time Sahm Rule triggered in mid-2024 with no NBER recession
following (Sahm herself attributed it to post-pandemic labor-supply/immigration
effects on the unemployment denominator, not a genuine downturn). A real multi-strat
risk desk would not hard-cap equity exposure off one lagging labor-market print with
no confirming signal from credit, vol, or breadth. UNRATE/Sahm's OWN history (24+
years, spans 2001/2008-09/2020) is long enough to trust statistically, unlike
ANFCI/STLFSI4 above - but naively z-scoring the raw Sahm-value series against that
history turned out to be its own mistake: live-checked, the series is heavily
right-skewed (mean 0.497, stdev 1.265, driven almost entirely by a handful of extreme
2008-09/2020 crisis readings, max 9.43) so its raw mean sits almost exactly ON the
0.50 trigger threshold purely from those rare spikes, even though 80% of all months
(243/304) never came close to triggering. A generic z-score would call today's
reading of 0.0 "roughly average" (z=-0.39) when it is actually deep in the calm
majority regime - the wrong read, and the wrong tool for a fundamentally
regime-switching statistic. Scored instead via a ramp anchored on Sahm's own
published, real methodology (100 at <=0, ramping to 40 exactly at the literal 0.50pp
trigger, continuing to 0 by +1.5pp) rather than force-fitting the same z-score
treatment used for continuous macro series onto a binary-regime indicator just for
superficial consistency.

Pass 3 (2026-08-22, user-flagged inconsistency during a post-merge review) caught pass
1/2 applying their own stated redundancy principle inconsistently: Yield Curve's two
rate-spread inputs (T10Y2Y/T10Y3M, only -0.28 correlated - genuinely close to
independent) were merged into ONE blended factor, but Breadth's two participation
inputs (% > 50-DMA / % > 200-DMA, 0.77 correlated in this DB - real, substantial
overlap, already noted in the "Breadth signal consolidation" paragraph below) were left
as two SEPARATELY weighted factors, each casting its own vote for the same underlying
"is the market broadly participating" read - exactly the double-counting pattern this
file otherwise treats as a bug (see Financial Conditions/Stress above). The original
"they're built to diverge at regime turns" rationale for keeping them separate is real,
but doesn't require separate weight budgets to preserve - a single blended factor still
carries both raw values in its detail dict (so the divergence is still visible on the
dashboard/frontend), it just casts one combined vote sized to the two inputs' original
relative importance (200-DMA weighted 62.5%, 50-DMA 37.5%, exactly preserving the prior
7.5:4.5 split) instead of two correlated votes. Merged into one BREADTH factor (12.0pt
total, unchanged from the prior 7.5+4.5 combined weight).

Every macro signal below that IS z-scored is checked against its own real historical
distribution (standard Barra/Axioma-style factor normalization) rather than scored
off fixed thresholds eyeballed from one day's snapshot - see each factor's own
docstring for its specific correlation/history-depth check.

    11.25pt  TREND 30-WK MA        SPY price vs rising/flat/falling 30-week MA
     7.50pt  SPY 12-MONTH MOMENTUM trailing 12-month return (TSMOM - most replicated quant signal)
    12.00pt  BREADTH               % > 200-DMA (long-term regime, linear 30-80%) + % > 50-DMA
                                    (short-term participation, linear 20-80%), blended 62.5%/37.5%
                                    - merged 2026-08-22 pass 3 from two separately-weighted
                                    factors (0.77 corr, real overlap; see "Breadth signal
                                    consolidation" below)
     7.50pt  SELLING PRESSURE      heavy-volume down days in last 25 sessions: 0-2=1.0, 3-4=0.6, 5+=0.2
     7.50pt  VIX REGIME            level (<15/15-25/25-35/35+) + genuine day-over-day trend
    10.50pt  CREDIT SPREADS        HY OAS (BAMLH0A0HYM2): credit leads equity (Apollo/Slok research);
                                    +3pt 2026-08-22 from the dropped Financial Conditions/Stress budget
                                    - this is the pillar that data was substantially re-deriving
     6.00pt  PUT/CALL RATIO        options market sentiment - contrarian at extremes (daily signal)
     5.25pt  NEW HIGHS - LOWS      market leadership quality (52-week NH vs NL)
     4.50pt  ADVANCE-DECLINE LINE  direction vs SPY over 20 days (confirmation/divergence)
     3.75pt  POSITIONING & FLOWS   insider buying breadth + short interest trend (replaces NAAIM,
                                    2026-08-20 - NAAIM's source went subscription-only 2026-08-01)
     2.25pt  AAII SENTIMENT        contrarian at extremes only (+/-15 spread; neutral in middle range)
     5.00pt  YIELD CURVE           T10Y2Y + T10Y3M avg, z-scored (confirmed non-redundant vs each
                                    other in this DB, -0.28 corr - the short end genuinely un-inverts
                                    before the long end normalizes, tracked as one factor not two);
                                    +1pt 2026-08-22 from the dropped Financial Conditions/Stress budget
     1.00pt  INFLATION EXPECTATIONS T5YIE + T10YIE avg (same measurement, two tenors - confirmed
                                    0.84 corr, a legitimate simple average not a bespoke blend)
     5.00pt  SECTOR ROTATION        defensive vs cyclical sector leadership (Mansfield RS / IBD
                                    leadership-rotation research); was a post-score point-penalty,
                                    now a normal weighted factor
     5.00pt  CROSS-ASSET CONFIRMATION gold/bonds/USD/oil vs equities, z-scored composite (was a
                                    binary "count >=2 of 4 flags" rule; asymmetric response curve
                                    kept - divergence still weighted more than agreement, a real
                                    documented asymmetry in risk-appetite research - but expressed
                                    as one factor's scoring curve, not a separate mechanism)
     2.50pt  EARNINGS REVISION BREADTH  % of universe with analyst target prices revised up over
                                    30d - a real, named practitioner indicator (Refinitiv/IBES
                                    revision ratios, Yardeni's Net Earnings Revisions Index),
                                    standing alone rather than blended (see below); scores
                                    unconditionally now (previously only applied when technical
                                    was already bullish, making a technically-weak-and-
                                    fundamentals-cracking market invisible to this signal)
     1.50pt  VALUATION EXTENSION BREADTH  % of universe at an extended P/E (>40) or P/S (>10) -
                                    an honestly-labeled first-pass heuristic, kept separate from
                                    revision breadth rather than blended into one "quality" score
                                    (2026-08-22: split from a single "Fundamental Quality" factor
                                    that mixed this, revision breadth, AND a duplicate of insider
                                    data already homed in Positioning into one number that implied
                                    more rigor than any single ingredient actually had)
     2.00pt  SAHM RULE              recession-onset ramp (see above) - demoted 2026-08-22 from a
                                    hard veto to a small graded factor; still checked directly
                                    against UNRATE, still the same 0.50pp trigger methodology,
                                    just no longer able to unilaterally cap the whole portfolio
                                    off one monthly print

Removed factors vs prior versions:
  - FOLLOW-THROUGH DAY (was 10pt): ~50% reliability per independent backtests
    (Quantifiable Edges, 37yr study); retained only as hard veto
  - MCCLELLAN OSCILLATOR (was 9pt): redundant with A/D line - both derive from
    advance/decline data; A/D line direction vs SPY is the less correlated signal
  - IG OAS / BAMLC0A0CM (2026-08-22): 0.952 correlation with ANFCI in this DB - scoring
    both would double-count the same underlying credit-conditions information
  - CFNAI (2026-08-22): only 37 rows of history in this DB, not enough to verify its
    relationship to the other macro signals either way
  - FINANCIAL CONDITIONS / ANFCI and FINANCIAL STRESS / STLFSI4 (2026-08-22, pass 2):
    substantially redundant with the pre-existing Credit Spread and Yield Curve
    factors (0.75/0.53/-0.76 corr) and built on only ~3 years of local history with
    no recession in-sample - see the pass-2 writeup above

Breadth signal consolidation: prior version had 5 breadth signals at 45pt total,
all highly correlated. Reduced to 3 signals covering genuinely distinct information:
BREADTH (participation - see below), NH/NL (leadership), A/D line (direction).
Live-checked 2026-08-22: % > 50-DMA and % > 200-DMA are themselves 0.77 correlated in
this DB - real overlap. Through pass 2 this was used to justify keeping them as two
separately-weighted factors deliberately (standard technical-analysis convention, e.g.
StockCharts/IBD breadth panels track both, and the two series are BUILT to diverge
exactly at regime turns, which is precisely when the extra information matters most).
Pass 3 kept the rationale but fixed the mechanism: separate weight budgets meant the
same participation read got two votes in the composite, the exact double-counting this
file treats as a bug everywhere else (Financial Conditions/Stress above; IG OAS/ANFCI
before that). Now ONE blended BREADTH factor (62.5% weight on 200-DMA, 37.5% on 50-DMA,
preserving the original 7.5:4.5 relative importance) - both raw values still live in
the factor's detail dict, so the regime-turn divergence this was protecting is still
fully visible on the dashboard/frontend, it just isn't double-weighted in the score.

HARD VETOES (cap exposure at <=25-40%; independent of the composite score - a risk
override, not an alpha input, same separation-of-concerns a real risk desk keeps):
  - SPY < rising 30-wk MA AND breadth_50 < 30%
  - VIX > 40 with a genuine rising trend (see VIX fix above - this veto previously fired
    on VIX>40 alone, since the old "rising" check was mathematically implied by VIX>40)
  - N+ selling-pressure days in last 25 sessions (N configurable via market_exposure_veto3_distribution_days_threshold)
  - No market confirmation signal (volume-backed rally) while SPY below 30-week MA
  - HY credit spread > 8.5% (systemic stress)

(Sahm Rule and Financial Conditions extreme-tail were both hard vetoes here through
2026-08-22 pass 1; both are gone from this list now - see the pass-2 writeup above
for why. Credit Spread remains the one signal that is deliberately both a graded
factor AND its own systemic-stress veto: unlike Sahm, HY OAS is a fast, daily,
market-based read, not a monthly government print, so a genuine >8.5% reading is a
real-time signal rather than a stale one.)
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

    # Factor weights (sum = 100). The original 12 are compressed by a uniform 0.75x
    # factor from their pre-2026-08-22 values (15/10/10/10/10/10/8/7/6/6/5/3) to free a
    # 25pt budget for the factors added 2026-08-22 pass 1 (see module docstring) - this
    # preserves each original factor's relative weight to the others exactly as
    # previously tuned, rather than introducing a second, unrelated set of freehand
    # numbers on top of an already-imperfect calibration. Pass 2 (same day) then dropped
    # Financial Conditions/Financial Stress entirely and redistributed their 6pt budget
    # into Credit Spread (+3), Yield Curve (+1), and the newly-graded Sahm Rule (+2) -
    # see module docstring for the evidence behind that reallocation.
    W_TREND_30WK = 11.25
    W_SPY_MOMENTUM = 7.5  # 12-month TSMOM (replaces follow-through day)
    # Merged 2026-08-22 pass 3 from W_BREADTH_200=7.5 + W_BREADTH_50=4.5 (two separately-
    # weighted, 0.77-correlated factors double-counting the same participation read) into
    # one blended factor - see module docstring "Breadth signal consolidation". Weight
    # unchanged in total; _breadth_factor() blends the two inputs 62.5%/37.5% internally
    # to preserve their original relative importance.
    W_BREADTH = 12.0
    W_SELLING_PRESSURE = 7.5  # heavy-volume down days
    W_VIX = 7.5  # level + genuine day-over-day trend
    W_CREDIT_SPREAD = 10.5  # HY OAS; +3pt 2026-08-22 pass 2 from dropped Financial Conditions/Stress
    W_PUT_CALL = 6.0  # options put/call ratio (replaces McClellan oscillator)
    W_NEW_HIGHS_LOWS = 5.25
    W_AD_LINE = 4.5  # A/D direction vs SPY
    W_POSITIONING = 3.75  # insider buying breadth + short interest trend (replaces NAAIM)
    W_AAII = 2.25  # extremes-only scoring
    W_YIELD_CURVE = 5.0  # T10Y2Y + T10Y3M avg, z-scored; +1pt 2026-08-22 pass 2 (see above)
    W_INFLATION_EXPECTATIONS = 1.0  # T5YIE + T10YIE avg, z-scored
    W_SECTOR_ROTATION = 5.0  # defensive vs cyclical leadership - was a post-score penalty
    W_CROSS_ASSET = 5.0  # gold/bonds/USD/oil vs equities - was a post-score penalty
    # Split 2026-08-22 from a single W_FUNDAMENTAL_QUALITY=4.0 (same total budget) into two
    # honestly-separate factors instead of one blend of a real measure, a first-pass
    # heuristic, and a duplicate of data already homed in Positioning - see
    # _earnings_revision_breadth_factor's docstring. Revision breadth keeps the larger share
    # since it's the more established of the two; valuation-extension breadth is explicitly
    # first-pass/uncalibrated.
    W_EARNINGS_REVISION = 2.5  # analyst target-price revision breadth, a real named indicator
    W_VALUATION_EXTENSION = 1.5  # % of universe at an extended P/E or P/S, first-pass heuristic
    # Demoted 2026-08-22 pass 2 from a hard veto to a small graded factor - see module
    # docstring for why (single lagging monthly print, real 2024 false-trigger precedent).
    W_SAHM_RULE = 2.0  # recession-onset ramp, anchored on Sahm's real 0.50pp trigger

    def __init__(self) -> None:
        self._validate_weights()
        self.calculator = MarketFactorCalculator()

    @classmethod
    def _validate_weights(cls) -> None:
        """Fail-fast if the 18 factor weights above don't sum to exactly 100.

        No test or runtime check previously protected this invariant (unlike
        algo/signals/filter_registry.py's FilterRegistry.validate(), which runs the
        equivalent check at module import time for its own weight table) - a future edit to
        one W_* constant without updating the others would silently produce a composite
        score that no longer means "0-100", with no error anywhere in the pipeline.
        """
        weights = [
            cls.W_TREND_30WK,
            cls.W_SPY_MOMENTUM,
            cls.W_BREADTH,
            cls.W_SELLING_PRESSURE,
            cls.W_VIX,
            cls.W_CREDIT_SPREAD,
            cls.W_PUT_CALL,
            cls.W_NEW_HIGHS_LOWS,
            cls.W_AD_LINE,
            cls.W_POSITIONING,
            cls.W_AAII,
            cls.W_YIELD_CURVE,
            cls.W_INFLATION_EXPECTATIONS,
            cls.W_SECTOR_ROTATION,
            cls.W_CROSS_ASSET,
            cls.W_EARNINGS_REVISION,
            cls.W_VALUATION_EXTENSION,
            cls.W_SAHM_RULE,
        ]
        total = sum(weights)
        if abs(total - 100.0) > 1e-6:
            raise ValueError(
                f"MarketExposure factor weights must sum to exactly 100, got {total}. "
                f"Weights: {weights}. Fix the W_* class constants before computing exposure."
            )

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

            # CRITICAL: Validate that all required factors are present with real scores.
            # This prevents using stale cached data with default/missing factor values.
            # Everything NOT in this set degrades gracefully in compute() (data_unavailable
            # marker, weight redistributed - see the renormalization fix in compute()) rather
            # than failing the whole computation, so its absence from a cached row is expected,
            # not corruption. FIXED 2026-08-22: "positioning" used to be listed here as
            # required even though compute() has always treated it as optional (graceful
            # data_unavailable skip, same as put_call_ratio) - this check would have rejected
            # a perfectly valid cached row on a day positioning genuinely had no data.
            required_factors = {
                "trend_30wk",
                "spy_momentum",
                "breadth",  # merged 2026-08-22 pass 3 (was breadth_200dma + breadth_50dma)
                "distribution_days",
                "vix_regime",
                # "put_call_ratio",  # OPTIONAL - no official source, skipped if unavailable
                "new_highs_lows",
                "ad_line",
                "credit_spread",
                "aaii_sentiment",
                # "positioning",  # OPTIONAL - insider/short-interest data may be thin some days
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
            f"[MARKET_EXPOSURE] Computing market exposure for {eval_date} (18 factors + 5 vetoes, using calculator methods)"
        )
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

            # --- 2. SPY 12-month momentum (TSMOM - most replicated quant signal) ---
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

            # --- 3. Breadth: % stocks above 50-DMA and 200-DMA, blended into one factor ---
            # MERGED 2026-08-22 pass 3 (user-flagged inconsistency vs. how Yield Curve
            # treats its own two inputs) - see module docstring "Breadth signal
            # consolidation". Both raw values are still kept in the factor detail (still
            # visible on dashboard/frontend); only the SCORING treats them as one 0.77-
            # correlated vote, weighted 62.5%/37.5% to preserve 200-DMA/50-DMA's original
            # 7.5:4.5 relative importance, rather than two separately-weighted votes for
            # the same participation read. _pct_above_ma() raises RuntimeError internally
            # (not data_unavailable) if either window's data is missing - breadth is
            # required, not optional, matching its pre-merge behavior.
            b50 = self.calculator._pct_above_ma(eval_date, ma_days=50, cur=cur)
            b200 = self.calculator._pct_above_ma(eval_date, ma_days=200, cur=cur)
            breadth = {
                "score": round(0.625 * b200["score"] + 0.375 * b50["score"], 1),
                "pct_above_50": b50["value"],
                "pct_above_200": b200["value"],
            }
            breadth_pts, breadth_avail = self.calculator._wt_pts(breadth, self.W_BREADTH)
            avail_max += breadth_avail
            factors["breadth"] = {**breadth, "pts": round(breadth_pts, 1), "max": self.W_BREADTH}
            score += breadth_pts
            logger.debug(f"  Breadth: 50DMA {b50['value']:.1f}% / 200DMA {b200['value']:.1f}%, {breadth_pts:.1f} pts")

            # --- 4. Selling pressure (heavy-volume down days) ---
            # CRITICAL: Selling pressure is required for hard veto checks (Veto 3: 6+ days)
            # Never silently exclude or default to None - must fail-fast on calculation error
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

            # --- 5. VIX regime (level + VIX3M term structure) ---
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
            vix_value_display = vix.get("value") if vix.get("value") is not None else "N/A"
            logger.debug(f"  VIX regime: {vix_value_display} (score {vix_pts:.1f} pts)")

            # --- 6. Put/call ratio (options sentiment - contrarian, 8pt optional) ---
            # OPTIONAL enrichment (Session 291+): No official source for put/call data.
            # Yfinance removed. Factor gracefully skipped if unavailable (don't fail, just skip).
            pc = self.calculator.put_call_ratio(eval_date, cur)
            if pc.get("data_unavailable"):
                logger.info(f"[PUT_CALL_RATIO] Unavailable (optional factor skipped): {pc.get('reason')}")
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["put_call_ratio"] = {
                    "data_unavailable": True,
                    "reason": pc.get("reason", "unknown"),
                    "pts": 0.0,
                    "max": self.W_PUT_CALL,
                }
            else:
                pc_pts, pc_avail = self.calculator._wt_pts(pc, self.W_PUT_CALL)
                avail_max += pc_avail
                factors["put_call_ratio"] = {
                    **pc,
                    "pts": round(pc_pts, 1),
                    "max": self.W_PUT_CALL,
                }
                score += pc_pts
                logger.info(
                    f"[PUT_CALL_RATIO] Value: {pc.get('value')}, Score: {pc.get('score'):.1f}, Points: {pc_pts:.1f}/{self.W_PUT_CALL}"
                )
                logger.debug(f"  Put/call ratio: {pc_pts:.1f} pts")

            # --- 7. New highs vs new lows ---
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

            # --- 8. A/D line confirmation ---
            ad = self._ad_line(eval_date, cur)
            ad_pts, ad_avail = self.calculator._wt_pts(ad, self.W_AD_LINE)
            avail_max += ad_avail
            factors["ad_line"] = {**ad, "pts": round(ad_pts, 1), "max": self.W_AD_LINE}
            score += ad_pts
            logger.info(
                f"[AD_LINE] Direction: {ad.get('direction')}, Score: {ad.get('score'):.1f}, Points: {ad_pts:.1f}/{self.W_AD_LINE}"
            )
            logger.debug(f"  A/D line: {ad_pts:.1f} pts")

            # --- 9. Credit spreads (HY OAS - credit leads equity) ---
            cs = self._credit_spread(eval_date, cur)
            cs_pts, cs_avail = self.calculator._wt_pts(cs, self.W_CREDIT_SPREAD)
            avail_max += cs_avail
            factors["credit_spread"] = {
                **cs,
                "pts": round(cs_pts, 1),
                "max": self.W_CREDIT_SPREAD,
            }
            score += cs_pts
            logger.info(
                f"[CREDIT_SPREAD] Value: {cs.get('value')} bps, Score: {cs.get('score'):.1f}, Points: {cs_pts:.1f}/{self.W_CREDIT_SPREAD}"
            )
            logger.debug(f"  Credit spreads: {cs_pts:.1f} pts")

            # --- 10. AAII sentiment (contrarian at extremes only) ---
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

            # --- 11. Positioning & flows: insider buying breadth + short interest trend ---
            # (5pt optional; replaces NAAIM 2026-08-20, see MarketFactorCalculator.positioning())
            positioning = self.calculator.positioning(eval_date, cur)
            if positioning.get("data_unavailable"):
                logger.info(f"[POSITIONING] Unavailable (optional factor skipped): {positioning.get('reason')}")
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["positioning"] = {
                    "data_unavailable": True,
                    "reason": positioning.get("reason", "unknown"),
                    "pts": 0.0,
                    "max": self.W_POSITIONING,
                }
            else:
                pos_pts, pos_avail = self.calculator._wt_pts(positioning, self.W_POSITIONING)
                avail_max += pos_avail
                factors["positioning"] = {
                    **positioning,
                    "pts": round(pos_pts, 1),
                    "max": self.W_POSITIONING,
                }
                score += pos_pts
                logger.debug(f"  Positioning: {pos_pts:.1f} pts")

            # --- 12. Yield Curve (T10Y2Y + T10Y3M avg, z-scored) ---
            yc = self._yield_curve_factor(eval_date, cur)
            if yc.get("data_unavailable"):
                logger.info(f"[YIELD_CURVE] Unavailable (optional factor skipped): {yc.get('reason')}")
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["yield_curve"] = {**yc, "pts": 0.0, "max": self.W_YIELD_CURVE}
            else:
                yc_pts, yc_avail = self.calculator._wt_pts(yc, self.W_YIELD_CURVE)
                avail_max += yc_avail
                factors["yield_curve"] = {**yc, "pts": round(yc_pts, 1), "max": self.W_YIELD_CURVE}
                score += yc_pts

            # --- 13. Inflation Expectations (T5YIE + T10YIE avg, z-scored) ---
            infl = self._inflation_expectations_factor(eval_date, cur)
            if infl.get("data_unavailable"):
                logger.info(f"[INFLATION_EXPECTATIONS] Unavailable (optional factor skipped): {infl.get('reason')}")
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["inflation_expectations"] = {**infl, "pts": 0.0, "max": self.W_INFLATION_EXPECTATIONS}
            else:
                infl_pts, infl_avail = self.calculator._wt_pts(infl, self.W_INFLATION_EXPECTATIONS)
                avail_max += infl_avail
                factors["inflation_expectations"] = {
                    **infl,
                    "pts": round(infl_pts, 1),
                    "max": self.W_INFLATION_EXPECTATIONS,
                }
                score += infl_pts

            # --- 14. Sector Rotation (defensive vs cyclical leadership) ---
            # FIXED 2026-08-22: was a post-score point-penalty applied outside the normal
            # weighted-factor pathway; now a normal factor (see _sector_rotation_factor).
            try:
                rotation = self._sector_rotation_factor(eval_date, cur)
            except Exception as e:
                logger.error(f"[SECTOR ROTATION] Detector failed: {type(e).__name__}: {e}.")
                raise RuntimeError(
                    f"[SECTOR_ROTATION] Computation failed: {type(e).__name__}: {e}. "
                    "Sector rotation detector must run successfully to assess market regime. "
                    "Check sector ranking loader and price data availability."
                ) from e
            if rotation.get("data_unavailable"):
                logger.info(f"[SECTOR_ROTATION] Unavailable (optional factor skipped): {rotation.get('reason')}")
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["sector_rotation"] = {**rotation, "pts": 0.0, "max": self.W_SECTOR_ROTATION}
            else:
                sr_pts, sr_avail = self.calculator._wt_pts(rotation, self.W_SECTOR_ROTATION)
                avail_max += sr_avail
                factors["sector_rotation"] = {**rotation, "pts": round(sr_pts, 1), "max": self.W_SECTOR_ROTATION}
                score += sr_pts

            # --- 15. Cross-Asset Confirmation (gold/bonds/USD/oil vs equities, z-scored) ---
            # FIXED 2026-08-22: was a post-score point-penalty gated on a binary "count of
            # trip-wires" rule; now a normal factor with a real z-scored composite and an
            # asymmetric scoring curve (see _cross_asset_factor).
            try:
                xasset = self._cross_asset_factor(eval_date, cur)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[CROSS_ASSET] Query failed, treating as unavailable: {e}")
                xasset = None
            if xasset is None:
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["cross_asset_confirmation"] = {
                    "data_unavailable": True,
                    "reason": "Insufficient price/economic history to compute cross-asset factor",
                    "pts": 0.0,
                    "max": self.W_CROSS_ASSET,
                }
            else:
                xa_pts, xa_avail = self.calculator._wt_pts(xasset, self.W_CROSS_ASSET)
                avail_max += xa_avail
                factors["cross_asset_confirmation"] = {**xasset, "pts": round(xa_pts, 1), "max": self.W_CROSS_ASSET}
                score += xa_pts

            # --- 16. Earnings Revision Breadth (analyst target-price revisions) ---
            # FIXED 2026-08-22: was one of three inputs blended into a single "Fundamental
            # Quality" score; now stands alone as its own real, named factor (see
            # _earnings_revision_breadth_factor's docstring for why the blend was dropped).
            try:
                revision = self._earnings_revision_breadth_factor(eval_date, cur)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[EARNINGS_REVISION] Query failed, treating as unavailable: {e}")
                revision = {"data_unavailable": True, "reason": f"Query failed: {type(e).__name__}"}
            if revision.get("data_unavailable"):
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["earnings_revision_breadth"] = {**revision, "pts": 0.0, "max": self.W_EARNINGS_REVISION}
            else:
                rev_pts, rev_avail = self.calculator._wt_pts(revision, self.W_EARNINGS_REVISION)
                avail_max += rev_avail
                factors["earnings_revision_breadth"] = {
                    **revision,
                    "pts": round(rev_pts, 1),
                    "max": self.W_EARNINGS_REVISION,
                }
                score += rev_pts

            # --- 17. Valuation Extension Breadth (% of universe at an extended P/E or P/S) ---
            # FIXED 2026-08-22: was the third input in the same blend, dropped for the same
            # reason - it's a legitimate, honestly-labeled first-pass heuristic on its own,
            # not equal-footing evidence with a real named indicator like revision breadth.
            try:
                valuation = self._valuation_extension_breadth(eval_date, cur)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[VALUATION_EXTENSION] Query failed, treating as unavailable: {e}")
                valuation = None
            if valuation is None:
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["valuation_extension_breadth"] = {
                    "data_unavailable": True,
                    "reason": "Insufficient sec_valuations sample",
                    "pts": 0.0,
                    "max": self.W_VALUATION_EXTENSION,
                }
            else:
                val_pts, val_avail = self.calculator._wt_pts(valuation, self.W_VALUATION_EXTENSION)
                avail_max += val_avail
                factors["valuation_extension_breadth"] = {
                    **valuation,
                    "pts": round(val_pts, 1),
                    "max": self.W_VALUATION_EXTENSION,
                }
                score += val_pts

            # --- 18. Sahm Rule (recession-onset ramp, demoted 2026-08-22 pass 2 from a hard
            # veto - see module docstring for the full reasoning: single lagging monthly
            # print, real 2024 false-trigger precedent, and a raw z-score against Sahm's own
            # history is the wrong tool for this specific right-skewed, regime-switching
            # series, so it's scored via a ramp anchored on the real published 0.50pp
            # trigger instead) ---
            try:
                sahm = self._sahm_rule_factor(eval_date, cur)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[SAHM_RULE] Query failed, treating as unavailable: {e}")
                sahm = {"data_unavailable": True, "reason": f"Query failed: {type(e).__name__}"}
            if sahm.get("data_unavailable"):
                logger.info(f"[SAHM_RULE] Unavailable (optional factor skipped): {sahm.get('reason')}")
                # Weight NOT added to avail_max here - see the renormalization
                # comment below compute()'s factor loop for why this matters.
                factors["sahm_rule"] = {**sahm, "pts": 0.0, "max": self.W_SAHM_RULE}
            else:
                sahm_pts, sahm_avail = self.calculator._wt_pts(sahm, self.W_SAHM_RULE)
                avail_max += sahm_avail
                factors["sahm_rule"] = {**sahm, "pts": round(sahm_pts, 1), "max": self.W_SAHM_RULE}
                score += sahm_pts

            # CRITICAL: the 12 original factors are still required; the factors added
            # 2026-08-22 (yield curve, inflation expectations, sector rotation, cross-asset,
            # earnings revision breadth, valuation extension breadth, sahm rule) are all
            # optional/graceful like put_call_ratio and positioning already were.
            #
            # FIXED 2026-08-22: previously, when an optional factor went unavailable, its
            # full weight was still added to avail_max (purely to dodge this exact check)
            # while never actually contributing to `score` - so the composite's real ceiling
            # silently dropped (e.g. to 92/100 with put_call_ratio out) and stayed there for
            # as long as the outage lasted, undetected beyond an info-level log line, despite
            # a comment directly above this claiming missing factors get renormalized. They
            # didn't. Each optional-factor block above now omits its weight from avail_max
            # entirely when unavailable (rather than adding it and relying on this check to
            # rescale something that was never actually short), so avail_max genuinely
            # reflects contributed weight - live-verified 2026-08-22: forcing 2 factors
            # unavailable dropped avail_max to 96/100 and correctly rescaled raw_score from
            # 64.5 to 67.1 (100/96x), not the earlier no-op where avail_max stayed pinned at
            # 100 and the "rescale" below silently did nothing. If avail_max comes in under
            # 100, the raw score is rescaled up proportionally so exposure_pct still resolves
            # on a real 0-100 scale, and the fact that it happened is logged at WARNING (an
            # extended outage on an unofficial data source should be visible).
            missing_factors = []
            unavailable_factors = []
            for factor_key, factor_data in factors.items():
                if factor_data.get("data_unavailable"):
                    unavailable_factors.append(factor_key)
                    continue
                if factor_data.get("pts") == 0.0 and factor_data.get("score") is None:
                    missing_factors.append(factor_key)

            if missing_factors:
                msg = (
                    f"[MARKET EXPOSURE CRITICAL] Incomplete factor data - cannot calculate exposure. "
                    f"Available: {avail_max:.1f}/100 points of factor weights. "
                    f"Missing REQUIRED factors ({len(missing_factors)}): {missing_factors}. "
                    f"Position sizing requires complete market assessment (all required factors). "
                    f"Cannot proceed with degraded market exposure calculation. "
                    f"Check data loaders: (1) verify calculator methods return data for {missing_factors}, "
                    f"(2) check market_health_daily table freshness, (3) verify technical_data_daily completeness"
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            if unavailable_factors:
                logger.warning(
                    f"[MARKET EXPOSURE] {len(unavailable_factors)} optional factor(s) unavailable, "
                    f"renormalizing: {unavailable_factors}. Available weight: {avail_max:.1f}/100."
                )

            if avail_max <= 0:
                raise RuntimeError(
                    "[MARKET EXPOSURE CRITICAL] No factor weight available at all (avail_max<=0). "
                    "Cannot compute a meaningful exposure score."
                )
            if avail_max < 100.0:
                score = score * (100.0 / avail_max)

            score = max(0.0, min(100.0, score))

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
                # "Scale: <3.5% = tight/healthy... >7% = severe stress"). This veto used to
                # compare against 850 as if the value were in basis points - since real-world
                # HY OAS has never exceeded ~20% even in 2008/March-2020, cs_value > 850 could
                # never be true, permanently disabling this hard veto. Compare in percent.
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

            # Vetoes 6 (Sahm Rule) and 7 (Financial Conditions extreme tail) were both
            # removed 2026-08-22 pass 2 - Sahm is now factor #19 above (a graded ramp, not a
            # binary trip-wire) and Financial Conditions/ANFCI was dropped entirely as
            # redundant with Credit Spread/Yield Curve (see module docstring). Both used to
            # live here as hard caps to 25%/40%.

            if halt_reasons:
                logger.warning(f"  Hard vetoes active: {'; '.join(halt_reasons)}, cap={cap}%")
            if cap < 100.0:
                logger.info(f"  Score capped from {score:.1f}% to {cap}%")

            final = min(score, cap)

            # Determine recommended state based on final exposure score. Sourced from
            # EXPOSURE_TIERS (algo/risk/exposure_policy.py) - the actual policy tier
            # tier_for_exposure() will select for this same score - rather than a second,
            # independently-hardcoded copy of the same 70/45/25 boundaries, which could
            # silently drift out of sync with the real policy tiers if either one is ever
            # tuned without remembering to update the other.
            from algo.risk.exposure_policy import tier_for_exposure

            regime = tier_for_exposure(final)["name"]

            logger.info(
                f"[MARKET_EXPOSURE_FINAL] exposure_pct={final}%, regime={regime}, raw_score={score:.1f}, factors_computed=18"
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
    # NOTE: Most factor calculations are delegated to MarketFactorCalculator (self.calculator.*).
    # The methods below (_has_market_confirmation, _ad_line, _credit_spread, the z-scored
    # macro factors, sector rotation, cross-asset, fundamental quality) are the canonical
    # implementations for factors not yet migrated to MarketFactorCalculator, and are
    # called directly from compute().

    def _single_series_zscore_factor(
        self,
        eval_date: _date,
        cur: PsycopgCursor[Any],
        series_id: str,
        higher_is_worse: bool,
        lookback: int = 800,
    ) -> dict[str, Any]:
        """Shared helper: z-score a single economic_data series against its own real
        history (standard Barra/Axioma-style normalization - see MarketFactorCalculator
        ._sample_zscore). Used standalone for series that are already professionally-built
        composites (ANFCI, STLFSI4) rather than remixed with unrelated series into a new
        bespoke blend. Degrades to data_unavailable rather than raising - these are all
        optional, newer factors (see module docstring on why Sahm Rule is the exception).
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
        """Yield curve factor: T10Y2Y + T10Y3M, each z-scored against own history, averaged.

        Correlation-checked 2026-08-22 against real data in this DB: T10Y2Y vs T10Y3M is
        only -0.28 correlated - genuinely distinct information (the short end can un-invert
        well before the long end normalizes), so both are used rather than one being
        dropped as redundant with the other. A more negative (more inverted) spread is the
        bearish direction for both, so z is flipped before scoring (positive z = stress,
        matching the convention every other z-scored factor in this file uses).
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

    # REMOVED 2026-08-22 pass 2 (_financial_conditions_factor / _financial_stress_factor,
    # ANFCI/STLFSI4 via _single_series_zscore_factor): both correlated substantially with
    # factors already in the model (STLFSI4 vs HY OAS 0.748, ANFCI vs T10Y3M -0.762, ANFCI
    # vs HY OAS 0.528) and both are built on only ~3 years of local history with no
    # recession in-sample - see module docstring for the full evidence. _single_series_
    # zscore_factor itself stays (still used by _yield_curve_factor's two components).

    def _inflation_expectations_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Inflation Expectations factor: T5YIE + T10YIE breakeven average, z-scored.

        Averaging the 5Y and 10Y tenors of the same market-implied measurement (TIPS vs.
        nominal Treasury spread) is a standard fixed-income simplification, not a bespoke
        blend - confirmed 0.84 correlation between the two tenors in this DB, i.e.
        genuinely the same underlying signal read at two maturities. Elevated breakeven
        inflation implies the Fed is more likely to stay restrictive - the bearish direction
        for risk assets, so higher_is_worse.
        """
        cur.execute(
            """
            SELECT a.date, (a.value + b.value) / 2.0
            FROM economic_data a
            JOIN economic_data b ON a.date = b.date AND b.series_id = 'T10YIE'
            WHERE a.series_id = 'T5YIE' AND a.date <= %s
              AND a.value IS NOT NULL AND b.value IS NOT NULL
            ORDER BY a.date DESC LIMIT 800
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

    def _sector_rotation_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sector Rotation factor: defensive vs. cyclical sector leadership.

        Mansfield RS rotation research and IBD leadership-rotation studies (see
        algo/signals/sector_rotation.py's own docstring) - defensive sectors typically lead
        1-3 months before major tops. FIXED 2026-08-22: was a post-score point-penalty
        (0/2/5/10 step function subtracted after the composite), now a normal weighted
        factor - defensive_lead_score (0-100, higher = more defensive leadership = more
        bearish) is inverted directly into a factor score instead of going through the
        detector's own coarser 4-tier penalty function.
        """
        from algo.signals.sector_rotation import SectorRotationDetector

        detector = SectorRotationDetector()
        rotation = detector.compute(eval_date)
        if not rotation:
            raise ValueError("Sector rotation detector returned no data")
        # Check data_unavailable FIRST (covers both an explicit data_unavailable=True and a
        # missing/None defensive_lead_score in one branch): the detector's own graceful-
        # degrade response (dataset too young for the 12w lookback) has no
        # "defensive_lead_score" key at all - checking for that key before this would
        # misclassify a legitimate, expected degrade as a malformed response and raise
        # instead of returning data_unavailable.
        if rotation.get("data_unavailable") or rotation.get("defensive_lead_score") is None:
            return {
                "data_unavailable": True,
                "reason": rotation.get("reason", "insufficient_sector_history"),
            }
        lead_score = float(rotation["defensive_lead_score"])
        return {
            "score": round(max(0.0, min(100.0, 100.0 - lead_score)), 1),
            "defensive_lead_score": lead_score,
            "signal": rotation.get("signal"),
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
                f"A/D line (6pt factor) is required for accurate market breadth assessment. "
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

        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `first_spy <= 0` never catches
        # NaN/Inf (always False in Python), and last_spy had no finiteness check at all - a
        # NaN would produce a NaN spy_change_pct, whose `> 0`/`< 0` comparisons below all
        # silently evaluate False, falling through to a default relation/score instead of
        # this function's own fail-closed RuntimeError contract for invalid benchmark data.
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
        # Confirmation: both same direction. Divergence: opposite.
        if (ad_change > 0 and spy_change_pct > 0) or (ad_change < 0 and spy_change_pct < 0):
            score = 100.0
            relation = "confirming"
        elif ad_change > 0 and spy_change_pct < 0:
            score = 60.0  # hidden bullish
            relation = "bullish_divergence"
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
        if not rows or len(rows) < 1:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] No HY OAS data (BAMLH0A0HYM2) for {eval_date}. "
                f"Credit spreads are a required 10pt factor for exposure calculation. "
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

        # FIXED 2026-08-20 (goal: finance-accuracy audit): same NaN-comparison-guard class
        # already fixed for _ad_line()'s SPY prices on 2026-08-10 (see that fix's comment
        # just below in this file) but never applied here - a NaN `hy` makes every tiered
        # `hy < X` comparison below evaluate False, falling through to the WORST-case branch
        # (score = 10.0, "severe stress") instead of this function's own fail-closed
        # RuntimeError contract. Worse than a merely-skipped signal: a corrupted HY OAS
        # reading would confidently score as the market's most stressed credit state
        # (a real 10pt factor feeding position sizing) rather than raising a diagnostic error.
        if math.isnan(hy) or math.isinf(hy):
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Non-finite HY OAS value ({hy}) for {eval_date}. "
                f"Cannot calculate credit spread score without a valid current reading. "
                f"Check economic_data table for BAMLH0A0HYM2 data integrity."
            )

        # CRITICAL: 20-day trend is required for credit spread signal (mean-reversion indicator)
        # Credit cycles need historical context - no fallback to 5d or current-only
        # Fail-fast: insufficient history is a data quality issue, not something to work around
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
        # Same NaN-guard class as `hy` above - a NaN here would silently make widening_1pp
        # False (NaN comparisons always evaluate False) instead of raising, masking a real
        # data-integrity gap in the 20-day trend anchor.
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

        Live-checked 2026-08-22 (pass 2): the raw historical Sahm-value series in this DB
        (304 monthly readings, 2001-2026) is heavily right-skewed - mean 0.497, stdev 1.265,
        driven almost entirely by a handful of extreme 2008-09/2020 crisis readings (max
        9.43) - even though 80% of months (243/304) never came remotely close to
        triggering. A generic sample z-score against that distribution would call a
        reading of 0.0 "roughly average" (z=-0.39, score ~58) purely because a few historic
        crisis spikes drag the mean up near the trigger threshold - the wrong read, and the
        wrong tool for a fundamentally regime-switching statistic (calm 80% of the time,
        rare violent spikes the rest). This ramp instead respects the threshold's real,
        research-backed meaning directly: 100 at or below 0 (no recessionary signal at
        all), linearly down to 40 exactly AT the literal 0.50pp trigger (already solidly
        bearish, not a cliff-edge discontinuity), continuing down to 0 by +1.5pp (a level
        only ever seen in genuine recessions in this DB's history).
        """
        if sahm_value <= 0.0:
            return 100.0
        if sahm_value < 0.50:
            return 100.0 - (sahm_value / 0.50) * 60.0
        if sahm_value >= 1.50:
            return 0.0
        return 40.0 - ((sahm_value - 0.50) / 1.0) * 40.0

    def _sahm_rule_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sahm Rule recession indicator, computed from UNRATE (FRED, monthly).

        DEMOTED 2026-08-22 pass 2 from a hard veto to a small graded factor - see module
        docstring for the full reasoning (single lagging monthly print, real 2024
        false-trigger precedent). The underlying Sahm math is unchanged from the original
        2026-08-20 veto: real-time Sahm Rule = (3-month average unemployment rate) minus
        (the minimum 3-month average unemployment rate over the trailing 12 months).
        "triggered" (>= 0.50pp) is still reported for transparency/logging/dashboard
        display, it just no longer caps exposure directly - _sahm_ramp_score does that
        continuously instead. Requires 15 months of history (3 for the current average, 12
        more for the trailing-minimum window); degrades to data_unavailable rather than
        raising, matching every other optional factor in this file.
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

    @staticmethod
    def _trailing_pct_change(
        symbol: str, eval_date: _date, cur: PsycopgCursor[Any], lookback_days: int = 20
    ) -> float | None:
        """% price change over the last `lookback_days` trading sessions from price_daily."""
        cur.execute(
            "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT %s",
            (symbol, eval_date, lookback_days + 1),
        )
        rows = cur.fetchall()
        if len(rows) < lookback_days + 1:
            return None
        current, baseline = rows[0][0], rows[-1][0]
        if current is None or baseline is None:
            return None
        current, baseline = float(current), float(baseline)
        if math.isnan(current) or math.isinf(current) or math.isnan(baseline) or math.isinf(baseline) or baseline <= 0:
            return None
        return (current - baseline) / baseline * 100.0

    @staticmethod
    def _rolling_20d_pct_change_price(
        symbol: str, eval_date: _date, cur: PsycopgCursor[Any], n_points: int = 260
    ) -> dict[_date, float]:
        """Trailing 20-session % change of `symbol`'s close, as a real time series (date ->
        pct change) covering the last `n_points` sessions - used to z-score a cross-asset
        reading against its own history instead of a fixed, eyeballed threshold.
        """
        cur.execute(
            """
            WITH p AS (
                SELECT date, close, LAG(close, 20) OVER (ORDER BY date) AS close_20d_ago
                FROM price_daily WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT %s
            )
            SELECT date, (close - close_20d_ago) / NULLIF(close_20d_ago, 0) * 100.0 AS chg_20d
            FROM p WHERE close_20d_ago IS NOT NULL AND close_20d_ago > 0
            """,
            (symbol, eval_date, n_points + 20),
        )
        return {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

    @staticmethod
    def _rolling_20d_pct_change_econ(
        series_id: str, eval_date: _date, cur: PsycopgCursor[Any], n_points: int = 260
    ) -> dict[_date, float]:
        """Same as _rolling_20d_pct_change_price but for an economic_data series. Row-based
        20-period lag (not calendar days) matches the convention every single-point
        cross-asset calc in this file already used for DTWEXBGS/DCOILWTICO.
        """
        cur.execute(
            """
            WITH p AS (
                SELECT date, value::float AS v,
                       LAG(value::float, 20) OVER (ORDER BY date) AS v_20d_ago
                FROM economic_data WHERE series_id = %s AND date <= %s AND value IS NOT NULL
                ORDER BY date DESC LIMIT %s
            )
            SELECT date, (v - v_20d_ago) / NULLIF(v_20d_ago, 0) * 100.0 AS chg_20d
            FROM p WHERE v_20d_ago IS NOT NULL AND v_20d_ago > 0
            """,
            (series_id, eval_date, n_points + 20),
        )
        return {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

    def _cross_asset_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any] | None:
        """Cross-Asset Confirmation factor: gold/bonds/USD/oil vs. equities.

        FIXED 2026-08-22: was a modifier that counted how many of 4 binary flags fired
        ("2-or-more of gold/bonds/USD/oil diverging") and applied a flat -8pt penalty
        regardless of whether it was 2 signals or 4. That "count of trip-wires" mechanic
        isn't how real cross-asset risk-appetite composites are built (e.g. Citi's Macro
        Risk Index, Credit Suisse's Risk Appetite Index) - they z-score each input against
        its own history and blend continuously. Now does the same: gold-vs-SPY and
        bonds-vs-SPY (relative performance) plus USD and oil (absolute moves - a genuine
        supply/inflation shock shows up as an outright price move, not underperformance vs.
        equities) each get a real ~260-session 20d-%-change history to z-score against,
        direction-normalized so positive z = risk-off, averaged into one composite z.

        The response curve stays deliberately asymmetric (divergence weighted more than
        agreement) - not because "modifiers are asymmetric as a category" but because this
        specific asymmetry is real, documented risk-appetite research (bad news moves
        markets more than equivalent good news; VIX itself only spikes on the downside).
        That's now expressed as this one factor's own scoring curve, not a separate
        combination mechanism sitting outside the normal weighted-factor pathway.
        """
        spy_series = self._rolling_20d_pct_change_price("SPY", eval_date, cur)
        if not spy_series:
            return None

        zs: list[float] = []
        detail: dict[str, Any] = {}

        for symbol, key in (("GLD", "gld"), ("TLT", "tlt")):
            asset_series = self._rolling_20d_pct_change_price(symbol, eval_date, cur)
            common_dates = sorted(set(asset_series) & set(spy_series))
            if len(common_dates) < 15:
                detail[f"{key}_vs_spy_chg_20d"] = None
                continue
            spread_series = [asset_series[d] - spy_series[d] for d in common_dates]
            current = spread_series[-1]  # common_dates sorted ascending -> most recent last
            detail[f"{key}_vs_spy_chg_20d"] = round(current, 1)
            z = self.calculator._sample_zscore(current, spread_series)
            if z is not None:
                zs.append(z)  # already positive = asset outperforming SPY = risk-off

        for series_id, key in (("DTWEXBGS", "usd"), ("DCOILWTICO", "oil")):
            econ_series = self._rolling_20d_pct_change_econ(series_id, eval_date, cur)
            if len(econ_series) < 15:
                detail[f"{key}_chg_20d"] = None
                continue
            latest_date = max(econ_series)
            current = econ_series[latest_date]
            detail[f"{key}_chg_20d"] = round(current, 1)
            z = self.calculator._sample_zscore(current, list(econ_series.values()))
            if z is not None:
                zs.append(z)  # positive = USD/oil spiking = risk-off

        if not zs:
            return None

        composite_z = sum(zs) / len(zs)
        if composite_z <= 0:
            score = min(100.0, 50.0 + (-composite_z) * 10.0)
        else:
            score = max(0.0, 50.0 - composite_z * 20.0)

        return {"score": round(score, 1), "composite_z": round(composite_z, 2), "n_signals": len(zs), **detail}

    def _valuation_extension_breadth(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any] | None:
        """% of the universe trading at an extended valuation TODAY (P/E > 40 or P/S > 10),
        a cross-sectional "froth breadth" gauge, its own standalone factor (see module
        docstring - split 2026-08-22 from what used to be a blended "Fundamental Quality"
        modifier).

        DEVIATION FROM DESIGN: the design memo specified this as "% of universe at an extreme
        percentile P/E/P/S/FCF-yield relative to its OWN trailing history" - live-verified
        2026-08-20 that `sec_valuations` is a single-row-per-symbol snapshot table (5,557 rows
        for 5,557 symbols, upserted not appended), with no per-symbol time series to compute a
        vs-own-history percentile against. A cross-sectional percentile-of-today's-universe
        (e.g. "top 20% of the universe by P/E") was considered and rejected - it's tautological
        by construction (always ~20% of the universe, by definition, regardless of whether the
        market as a whole is cheap or expensive that day), not a real time-varying signal.
        Using fixed absolute thresholds instead is both buildable today and more informative -
        it moves as the market's aggregate multiple genuinely expands/contracts. Thresholds are
        live-calibrated against this session's actual data (median P/E 21.8, 80th pct ~49;
        median P/S 2.8, 80th pct ~10) rather than picked blind, but are still a first pass, not
        backtested - same caveat as every other new threshold in this file.

        FCF-yield was in the design's list of 3 valuation dimensions but is deliberately
        excluded here: live-checked its distribution and median FCF yield across the universe
        is only 0.26%, meaning a "yield < 2%" cutoff (the equivalent-spirit threshold to P/E>40)
        would flag the *majority* of the universe as "extended" - this universe evidently
        includes enough unprofitable/low-FCF growth names that FCF yield isn't a clean froth
        signal here the way it might be for a mega-cap-only universe. Worth revisiting with a
        better-calibrated threshold later; not fabricating one now.
        """
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE (pe_ratio IS NOT NULL AND pe_ratio > 0 AND pe_ratio < 500)
                       OR (ps_ratio IS NOT NULL AND ps_ratio > 0 AND ps_ratio < 200)
                ) AS total,
                COUNT(*) FILTER (
                    WHERE (pe_ratio IS NOT NULL AND pe_ratio > 40 AND pe_ratio < 500)
                       OR (ps_ratio IS NOT NULL AND ps_ratio > 10 AND ps_ratio < 200)
                ) AS extended
            FROM sec_valuations
            WHERE data_unavailable IS NOT TRUE AND computed_at <= %s
            """,
            (eval_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None or int(row[0]) < 200:
            return None
        total, extended = int(row[0]), int(row[1] or 0)
        breadth_pct = extended * 100.0 / total
        # Linear: 15% breadth -> 100 (healthy, low froth), 35% -> 50, 55%+ -> 0 (high froth).
        # Inverted relative to the other two inputs: HIGH breadth here means MORE of the
        # universe is stretched, which should LOWER fundamental confirmation, not raise it.
        score = min(100.0, max(0.0, 100.0 - (breadth_pct - 15.0) / 0.4))
        return {"score": score, "breadth_pct": round(breadth_pct, 1), "active_count": total}

    def _earnings_revision_breadth_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Earnings Revision Breadth factor: % of the universe with analyst price targets
        revised UP over the trailing 30 days.

        FIXED 2026-08-22 (goal: exposure-model integrity review): this used to be one of
        three inputs blended into a single "Fundamental Quality" score alongside insider
        buying breadth and valuation-extension breadth - mixing one well-established
        measure with a first-pass heuristic and a duplicate (insider breadth is already the
        primary, unconditional home of that data in Positioning - see
        MarketFactorCalculator.positioning()) and presenting the result as if it were one
        coherent "quality" concept. It wasn't. Earnings revision breadth is its own real,
        named, practitioner-standard indicator - Refinitiv/IBES publish earnings revision
        ratios, Yardeni Research publishes a "Net Earnings Revisions Index" on exactly this
        concept - so it stands alone now instead of being diluted into a blend, and insider
        data was dropped from this area entirely (it wasn't adding new information, just a
        second, smaller-weighted echo of what Positioning already does with it).

        Also FIXED: previously only scored when the technical picture was already bullish
        (a conditional haircut) - meant a technically-weak-and-fundamentally-cracking
        market was invisible to this signal, exactly the combination it exists to catch.
        Scores unconditionally now, like every other factor - the weighted sum already
        handles how much a bearish technical picture should matter on top of a bearish
        fundamental one.

        No persisted daily history exists yet for this specific breadth percentage (it's
        computed fresh from current DB state each run - market_exposure_daily itself is
        only ~1 month deep), so this stays on its original linear threshold scoring rather
        than z-scoring against a history that doesn't exist - a first-pass calibration,
        flagged like every other not-yet-backtested threshold in this file, not a claim of
        precision it doesn't have.
        """
        cur.execute(
            """
            WITH current_asof AS (
                SELECT DISTINCT ON (symbol) symbol, target_price, date
                FROM analyst_sentiment_analysis
                WHERE date <= %s AND target_price IS NOT NULL AND data_unavailable IS NOT TRUE
                ORDER BY symbol, date DESC
            ),
            baseline_asof AS (
                SELECT DISTINCT ON (symbol) symbol, target_price
                FROM analyst_sentiment_analysis
                WHERE date <= %s::date - INTERVAL '30 days' AND target_price IS NOT NULL
                    AND data_unavailable IS NOT TRUE
                ORDER BY symbol, date DESC
            )
            SELECT
                COUNT(*) FILTER (WHERE c.target_price > b.target_price) AS rising,
                COUNT(*) AS total
            FROM current_asof c
            JOIN baseline_asof b ON c.symbol = b.symbol
            WHERE c.date >= %s::date - INTERVAL '10 days'
            """,
            (eval_date, eval_date, eval_date),
        )
        row = cur.fetchone()
        if not row or not row[1] or int(row[1]) < 200:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient analyst-coverage sample on or before {eval_date} (need 200+ symbols)",
            }
        revision_breadth_pct = int(row[0]) * 100.0 / int(row[1])
        # Linear: 35% -> 0, 50% -> 50, 65% -> 100 (illustrative, uncalibrated - see docstring).
        score = min(100.0, max(0.0, (revision_breadth_pct - 35) / 0.3))
        return {"score": round(score, 1), "revision_breadth_pct": round(revision_breadth_pct, 1)}

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

            # BUG FOUND 2026-08-17: result["factors"] is built up via `**`-spreading
            # sub-detector output dicts (e.g. the z-scored macro factors) whose fields
            # aren't guaranteed to already be JSON-safe (raw DB dates, Decimals). Same bug
            # class already found and fixed in phase9_reconciliation.py's audit log insert -
            # default=str is the same standard, safe fallback for an archival JSON column.
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
    logger.info("Factor breakdown:")
    for name, info in result["factors"].items():
        if "pts" not in info:
            raise KeyError(f"Factor '{name}' missing required 'pts' key: {info}")
        pts = info["pts"]
        if "max" not in info:
            raise KeyError(f"Factor '{name}' missing required 'max' key: {info}")
        max_pts = info["max"]
        logger.info(f"  {name:22s}: {pts:5.1f} / {max_pts:>3} pts  ({info})")
