"""GrowthScoringMixin and Growth pillar constants, extracted from load_stock_scores.py
(2026-09-05, file-size-ratchet bloaters-decomposition split). Moved verbatim - no behavior
change.

GROWTH_SCORE_FIELDS/GROWTH_INPUT_IMPLAUSIBLE_PCT/GROWTH_MIN_FIELDS_AVAILABLE are re-exported
from loaders.load_stock_scores for backward compatibility - existing consumers (tests,
dashboard, research scripts) import these names directly from loaders.load_stock_scores and
must keep working unchanged.

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.` reference here resolves normally through the instance regardless of which mixin file
defines it.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

import psycopg2

from loaders.helpers.factor_normalization import universe_wide_zscore, zscore_to_percentile_scale
from loaders.stock_scores.pillar_weights import (
    BASE_PILLAR_WEIGHTS,
    DEFAULT_MIN_ADV_DOLLARS,
    DEFAULT_MIN_STOCK_PRICE,
    LIQUIDITY_FLOOR_JOIN_SQL,
)
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
from utils.loaders.unavailable_markers import marker_loader_failed
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")


def _owner() -> Any:
    """Lazy reference to the owner module (loaders.load_stock_scores), resolved at call time -
    see loaders/stock_scores/value_metrics.py's identical `_owner()` for the full rationale
    (test monkeypatching of DatabaseContext/execute_values on the owner module, and avoiding a
    top-level import of a module that may still be mid-import when run as a script). Copied
    verbatim, not re-derived, per this file's own "reuse the established pattern" mandate.
    """
    from loaders import load_stock_scores as _owner_mod

    return _owner_mod


# GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE: the 12-field version of this constant (2026-08-31 through
# 2026-09-16) is SUPERSEDED below (2026-09-16, /goal session: "assume any previous decisions in
# memory are wrong ... do what is proven best and right in the industry", later "really dig and
# be certain on the right methodology"). That version's own comment claimed "all 12 fields are
# independently verified canonical to a named MSCI/Russell/S&P/IBD Growth-factor component" -
# re-checked against MSCI's and Barra's actual published methodology documents this session
# (fetched and read directly, not recalled from memory) and this does not hold up:
#
#   - MSCI's real Growth style (MSCI Global Investable Market Value and Growth Index Methodology,
#     Feb 2021, msci.com/eqb/methodology/meth_docs/MSCI_GIMIVGMethod_Feb2021.pdf) uses exactly 5
#     descriptors: long-term forward EPS growth rate, short-term forward EPS growth rate, current
#     internal growth rate (g = ROE x retention rate), long-term historical EPS growth TREND,
#     long-term historical sales-per-share growth TREND. The historical TREND descriptors are an
#     OLS regression of the last 5 years' EPS/SPS against time, annualized, divided by the mean
#     absolute level over that window - NOT a two-point CAGR. See loaders/helpers/growth_trend.py
#     for the full formula, its worked-example verification, and why a two-point CAGR (what this
#     file's revenue_growth_1y/3y/5y and eps_growth_1y/3y/5y all are) is not the same computation.
#   - INDEPENDENTLY CORROBORATED (different document, different company lineage - Barra was
#     acquired by MSCI in 2004, predates common authorship): the classic Barra US-E3 Risk Model
#     Handbook, Appendix A "Descriptor Definitions", Growth section, EGRO ("Earnings growth rate
#     over last five years") - "First, the following regression is run: EPS_t = a + b*t, ...
#     This regression is run for the period t=1,...,5. EGRO is computed as: EGRO = b /
#     average(EPS_t)" - the SAME OLS-regression-over-5-years-divided-by-average-level
#     construction, independently arrived at. Barra's AGRO (asset growth) descriptor uses the
#     identical shape applied to total assets.
#   - NEITHER MSCI's nor Barra's Growth descriptors include a forecast REVENUE growth rate, a
#     quarterly/trailing-4Q earnings "momentum" metric, or three separate overlapping
#     point-in-time growth rates (1y/3y/5y) for the same underlying quantity.
#     forward_revenue_growth_next_fy, quarterly_growth_momentum, and earnings_growth_4q_avg are
#     not named components of either published methodology.
#   - Live-verified (this session, 5,164-row growth_metrics query, Spearman correlation) that the
#     1y/3y/5y windows this repo scored as 6 independent votes are real duplicates of each other,
#     not diversifying signal: revenue_growth_3y vs 5y r=0.66, revenue_growth_1y vs 3y r=0.54,
#     eps_growth_3y vs 5y r=0.54, eps_growth_1y vs 3y r=0.46 - the same "genuinely redundant,
#     consolidate rather than vote separately" tier this file's own Risk/Momentum siblings already
#     acted on (Risk's 6 volatility windows at r=0.52-0.92, Momentum's mom_3m/mom_6m at r=0.69).
#
# YOUNG-COMPANY COVERAGE (explicitly checked, not assumed - "I don't want anything where we're
# losing out on the good younger growth companies"): MSCI's own text is explicit that a security
# without >=4 years of EPS/SPS history simply has the historical-TREND descriptor marked missing,
# NOT the whole Growth score - "Growth trends for securities without sufficient EPS or SPS values
# are considered to be missing." A young high-growth company still scores on the OTHER 3
# descriptors (both forward-looking analyst-estimate legs, which need only current analyst
# coverage, and the internal growth rate, which needs only 1 year of ROE/payout data) - exactly
# the same "score what's available, renormalize" treatment GROWTH_MIN_FIELDS_AVAILABLE already
# implements below, not a new mechanism invented for this. Live-checked coverage: ~88% of this
# universe has >=4 years of revenue history (5,164-row query), so the historical-trend legs are
# genuinely missing (not fabricated from insufficient data) for roughly 12% of symbols - the same
# tradeoff a real institutional provider makes, not a gap unique to this implementation.
#
# RESULT: 12 fields -> 4, real methodology matches ONLY - no substitute shipped for a descriptor
# this system can't actually compute (see forward_eps_growth_next_fy note below):
#   - eps_growth_trend_5y -> "long-term historical EPS growth trend" (verified formula match)
#   - sps_growth_trend_5y -> "long-term historical sales-per-share growth trend" (verified
#     formula match; MSCI's descriptor is per-SHARE sales, not raw revenue - sps_growth_trend_5y
#     divides revenue by diluted shares outstanding per year, same per-share normalization
#     reasoning as EPS vs raw net income)
#   - forward_eps_growth_current_fy -> "short-term forward EPS growth rate" (real ~12-month-ahead
#     analyst consensus - a genuine horizon match, not a proxy across a different time horizon)
#   - sustainable_growth_rate -> "current internal growth rate" (ROE x retention rate is
#     literally that descriptor's textbook definition, not just a loose analogy - EXACT match,
#     verified against this repo's own sustainable_growth_rate computation in vqg_quality.py)
# forward_eps_growth_next_fy (MSCI's "long-term forward EPS growth rate") is NOT included - this
# DB's next-FY consensus is not the same time horizon as MSCI's real 3-5yr LTG estimate, and
# no genuine long-term consensus growth data exists in this system to fill that descriptor (live-
# checked: yfinance's own `growth_estimates` has an "LTG" row, but it returned NaN for every
# symbol tried this session - MSFT/NVDA/KO/T/JPM - real per-stock long-term growth data isn't in
# Yahoo's free tier anymore; sourcing it would need a new paid vendor integration, a separate
# decision, not something to paper over with a wrong-horizon substitute).
GROWTH_SCORE_FIELDS: tuple[str, ...] = (
    "eps_growth_trend_5y",
    "sps_growth_trend_5y",
    "forward_eps_growth_current_fy",
    "sustainable_growth_rate",
)

# GROWTH_INPUT_IMPLAUSIBLE_PCT (added 2026-08-31, /goal session - "make sure the results make
# sense" investigation). _score_single_growth's cap=30 already bounds every signed-rate
# candidate's OUTPUT at 100, but does nothing to distinguish a genuinely excellent ~30-100%
# grower from a candidate whose raw rate is in the hundreds or thousands of percent - both map
# to an identical, fully-saturated 100.
#
# RE-VERIFIED 2026-09-17 (factor-purity follow-up, flagged by an automated slop audit as
# curve-fit to named tickers - it was: the original justification below cited eps_growth_1y/
# fcf_growth_yoy/quarterly_growth_momentum, none of which are in GROWTH_SCORE_FIELDS any more
# after the 2026-09-16 12-field->4-field real-methodology trim - see
# GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE above). Re-checked directly against live growth_metrics for
# the CURRENT 4 fields rather than trusting the stale example: eps_growth_trend_5y (max 119.9%),
# sps_growth_trend_5y (max 107.8%), and forward_eps_growth_current_fy (max 17.8%, an analyst
# consensus estimate - naturally bounded) never exceed 150% at all in this universe (5,164 rows) -
# for those 3 fields this threshold is currently a no-op, not a live exclusion. sustainable_growth_rate
# (ROE x retention rate) is the one field where it still does real work: 37/5,164 symbols exceed
# it, up to VSA at 1,674.89% (SBR 1,072.55%, WHLR 946.15%, CVLT 942.85%) - a near-zero or
# distressed book-equity denominator blowing up an otherwise-mechanical ROE x retention
# computation, not a genuine sustainable growth rate. Same reasoning as the original finding
# (internally consistent with the symbol's own financials, not corrupted data, but not
# comparable "growth quality" to a clean sustainable grower) - kept as a real, currently-load-
# bearing guard for sustainable_growth_rate specifically, not vestigial dead weight left over
# from the field trim.
#
# Standard factor-investing practice (MSCI Barra, AQR) winsorizes/excludes outlier raw inputs
# before scoring for exactly this reason - a single anomalous field shouldn't get to fully
# saturate a multi-input equal-weighted blend. Set well above any plausible genuine "excellent"
# grower (the cap=30 curve already reaches its 100 ceiling at 30%) so normal strong growers are
# unaffected - only truly extreme values are excluded from the blend entirely (same "drop what's
# missing, don't hand its weight to a different candidate" pattern _score_growth already uses for
# None values), rather than counted as a full-credit 100.
# Deliberately NOT applied to eps_growth_stability - its own inverted curve already penalizes
# large values toward 0, so no separate exclusion is needed there (also no longer scored at all,
# see GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE).
GROWTH_INPUT_IMPLAUSIBLE_PCT = 150.0

# GROWTH_MIN_FIELDS_AVAILABLE (added 2026-08-31, same /goal session, found while actually looking
# at post-reload live results rather than just trusting the code change). _score_growth's equal-
# weighted blend had NO minimum-coverage floor at all - `if component_scores:` accepted even a
# single available field and renormalized it up to a full 0-100 score. Live-verified this produces
# a real, visible problem: after the 12-field trim, symbols like ATTO/GFUZ/VRXA/KWM/BLSM (each with
# exactly 1 of 12 fields available, that one field happening to be >=30%) landed a saturated 100
# growth_score - indistinguishable in the DB from NVDA's real 100 (built from 11/12 fields, all
# genuinely strong). Live sweep of the full universe: 76/4882 non-null-growth_metrics symbols have
# <=2/12 fields available, 11 of those score >=90 - a small slice of the universe, but exactly the
# kind of thin-sample extrapolation that lands at the TOP of any growth-sorted view, disproportionately
# visible. This is the identical problem Quality already solved for itself - see _score_quality's
# docstring ("40-point minimum-available-weight floor out of a 101-point nominal total... below
# that, quality_score is None rather than a thin-sample extrapolation") - Growth just never got the
# same treatment when it moved from single-input to multi-input. 5/12 (~42%) mirrored Quality's
# ~40%-of-101 ratio at the time.
# RESCALED 2026-09-16 (see GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE - 12 fields -> 4, real-methodology-
# only, no guessed substitutes): 2/4 (50%) - can't hit ~40% exactly with only 4 slots, and 1/4
# (25%) would recreate the exact single-field-renormalization problem this constant exists to
# prevent, so this rounds UP to the stricter, safer side rather than down to match the old ratio
# more closely.
GROWTH_MIN_FIELDS_AVAILABLE = 2


class GrowthScoringMixin:
    """See module docstring.

    `_growth_cache` is set on the instance by `_prepare_batch_context` (defined on
    StockScoresLoader itself, not any mixin) - declared type-checking-only below so mypy can
    see it without a real circular import.
    """

    if TYPE_CHECKING:
        _growth_cache: dict[str, tuple[Any, ...]]

    def _get_growth_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch growth metrics for symbol.

        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 27 columns (revenue_growth_1y/3y/5y, eps_growth_1y/
          3y/5y, book_value_growth, net_income_growth_yoy, operating_income_growth_yoy,
          sustainable_growth_rate, fcf_growth_yoy, ocf_growth_yoy, gross/operating/net_margin_
          trend, roe_trend, asset_growth_yoy, eps_growth_stability, quarterly_growth_momentum,
          earnings_growth_4q_avg, forward_eps_growth_current_fy, forward_eps_growth_next_fy,
          forward_revenue_growth_next_fy, eps_estimate_revision_90d_pct, eps_growth_trend_5y,
          sps_growth_trend_5y, data_unavailable) - extended 2026-09-16 to add the two
          MSCI/Barra-formula OLS growth-trend fields (see loaders/helpers/growth_trend.py).
        - Schema mismatch (len(row) < 27) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - No row at all → returns marker dict with reason="no_growth_metrics_found"

        STALE CLAIM REMOVED 2026-09-16 (found while extending this docstring for the trend
        fields, not the focus of that change): this docstring used to claim "data_unavailable=True
        flag -> returns marker dict even if row exists" and cite a "CRITICAL FIX 2026-07-01" that
        added that check - the FIX 2026-09-04 note in the code below already explains that check
        was deliberately REMOVED (a data_unavailable=True row can still carry real per-field
        values worth scoring), but the docstring above it was never updated to stop claiming the
        opposite. The code has been correct since 2026-09-04; only this comment was lying about it.

        MINIMUM DATA REQUIREMENT: Row must have exactly 27 columns. Missing columns causes
        immediate fail-fast ValueError. Dependent on upstream annual_income_statement availability.
        """
        row = self._growth_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 27 columns before accessing indices
            if len(row) < 27:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 27. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            # FIX 2026-09-04 (goal: "Missing SEC/XBRL data" reduction, real-scoring-consumption
            # follow-up to load_value_quality_growth_metrics.py's row-level unavailable fix):
            # this used to wholesale-discard the ENTIRE row via marker_not_applicable whenever
            # data_unavailable=True, even when individual fields carried real, non-NULL values -
            # notably quarterly_growth_momentum/earnings_growth_4q_avg, which
            # _mirror_shared_trend_fields() deliberately writes into growth_metrics regardless
            # of the row's own data_unavailable flag (see that function's 2026-09-03 fix
            # docstring: "growth_dict's own data_unavailable still gates the write target" -
            # the individual columns ARE written, just previously never reached this far).
            # Live-confirmed 121 growth_metrics rows have data_unavailable=TRUE but a real
            # quarterly_growth_momentum/earnings_growth_4q_avg/sustainable_growth_rate value
            # sitting in the table - the Coverage dashboard already showed these correctly (it
            # reads raw columns), but real composite scoring discarded them entirely here.
            # _score_growth's own multi-field blend below is already designed for partial
            # availability (GROWTH_MIN_FIELDS_AVAILABLE floor, equal-weighted renormalization
            # over whichever GROWTH_SCORE_FIELDS candidates are non-NULL) - it just never got
            # the chance to see these rows' real fields. A genuinely fully-empty row (data_
            # unavailable=True, every field NULL) still safely falls through to _score_growth's
            # own "no_growth_inputs_available" marker below, just via that path instead of this
            # one - same outcome, no regression.

            def _scale_fraction_to_pct(val: float | None) -> float | None:
                """forward_eps_growth_current_fy/next_fy and forward_revenue_growth_next_fy are
                stored as raw fractions (0.18 = 18%), unlike every other GROWTH_SCORE_FIELDS
                candidate which is already percentage-point scaled - _score_single_growth's
                cap=30 curve is calibrated for percentage-point inputs. Live-verified against
                the DB directly (not assumed from the column name): AAPL's real
                forward_eps_growth_next_fy=0.0816, not 8.16.
                """
                return val * 100 if val is not None else None

            # Row exists and data is available
            return {
                "revenue_growth_1y": safe_float(row[0], f"{symbol}.revenue_growth_1y"),
                "revenue_growth_3y": safe_float(row[1], f"{symbol}.revenue_growth_3y"),
                "revenue_growth_5y": safe_float(row[2], f"{symbol}.revenue_growth_5y"),
                "eps_growth_1y": safe_float(row[3], f"{symbol}.eps_growth_1y"),
                "eps_growth_3y": safe_float(row[4], f"{symbol}.eps_growth_3y"),
                "eps_growth_5y": safe_float(row[5], f"{symbol}.eps_growth_5y"),
                "book_value_growth": safe_float(row[6], f"{symbol}.book_value_growth", allow_none=True),
                "net_income_growth_yoy": safe_float(row[7], f"{symbol}.net_income_growth_yoy", allow_none=True),
                "operating_income_growth_yoy": safe_float(
                    row[8], f"{symbol}.operating_income_growth_yoy", allow_none=True
                ),
                "sustainable_growth_rate": safe_float(row[9], f"{symbol}.sustainable_growth_rate", allow_none=True),
                "fcf_growth_yoy": safe_float(row[10], f"{symbol}.fcf_growth_yoy", allow_none=True),
                "ocf_growth_yoy": safe_float(row[11], f"{symbol}.ocf_growth_yoy", allow_none=True),
                "gross_margin_trend": safe_float(row[12], f"{symbol}.gross_margin_trend", allow_none=True),
                "operating_margin_trend": safe_float(row[13], f"{symbol}.operating_margin_trend", allow_none=True),
                "net_margin_trend": safe_float(row[14], f"{symbol}.net_margin_trend", allow_none=True),
                "roe_trend": safe_float(row[15], f"{symbol}.roe_trend", allow_none=True),
                "asset_growth_yoy": safe_float(row[16], f"{symbol}.asset_growth_yoy", allow_none=True),
                "eps_growth_stability": safe_float(row[17], f"{symbol}.eps_growth_stability", allow_none=True),
                "quarterly_growth_momentum": safe_float(
                    row[18], f"{symbol}.quarterly_growth_momentum", allow_none=True
                ),
                "earnings_growth_4q_avg": safe_float(row[19], f"{symbol}.earnings_growth_4q_avg", allow_none=True),
                "forward_eps_growth_current_fy": _scale_fraction_to_pct(
                    safe_float(row[20], f"{symbol}.forward_eps_growth_current_fy", allow_none=True)
                ),
                "forward_eps_growth_next_fy": _scale_fraction_to_pct(
                    safe_float(row[21], f"{symbol}.forward_eps_growth_next_fy", allow_none=True)
                ),
                "forward_revenue_growth_next_fy": _scale_fraction_to_pct(
                    safe_float(row[22], f"{symbol}.forward_revenue_growth_next_fy", allow_none=True)
                ),
                "eps_estimate_revision_90d_pct": safe_float(
                    row[23], f"{symbol}.eps_estimate_revision_90d_pct", allow_none=True
                ),
                "eps_growth_trend_5y": safe_float(row[24], f"{symbol}.eps_growth_trend_5y", allow_none=True),
                "sps_growth_trend_5y": safe_float(row[25], f"{symbol}.sps_growth_trend_5y", allow_none=True),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No growth metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_growth_metrics", "Growth metrics table missing data")

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale via a multi-input blend. Returns marker dict if
        no real data.

        STALE SUMMARY FIXED (this pass, /goal factor-purity audit) - this paragraph used to
        describe the 2026-08-28 "restored to multi-input, explicit user override of the
        evidence" state (11/12-field equal-weighted blend, kept as an explicit deliberate
        exception to this file's normal evidence bar). SUPERSEDED 2026-09-16 (factor-purity
        sweep, /goal session: "assume any previous decisions in memory are wrong... do what is
        proven best and right in the industry") - see GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE above
        for the full evidence trail (MSCI GIMIVG methodology + Barra US-E3 EGRO/AGRO, fetched
        and read directly). GROWTH_SCORE_FIELDS is now exactly MSCI's/Barra's real 4 verifiable
        descriptors - eps_growth_trend_5y, sps_growth_trend_5y, forward_eps_growth_current_fy,
        sustainable_growth_rate - not a homegrown 11/12-field blend. This is no longer an
        explicit-override exception to the evidence bar; it IS the evidence-driven, real-
        methodology construction this file's other pillars already use.

        Scores every growth field the frontend's Growth tab displays (GROWTH_SCHEMA in
        StockScoreAccordion.jsx / GROWTH_SCORE_FIELDS above) - the single-input design was
        starving large swings of the universe of any Growth score purely on whichever ONE field
        happened to be missing for a given symbol (e.g. book_value_growth's 72.9% coverage
        starving ~27% of the universe), and displaying a dozen "computed but unscored" fields
        next to a "sole input" weight badge made the tab actively misleading (looked
        multi-factor, wasn't). Equal-weighted average of whichever of the GROWTH_SCORE_FIELDS
        candidates are non-null for this symbol (partial-availability renormalization - the
        same "score what's available, drop what's missing, don't hand the drop-outs' weight to
        a different candidate" pattern _score_quality/_score_stability already use elsewhere in
        this file) - NOT sign-flipped, plain "higher growth = higher score" per the user's
        explicit direction, overriding this file's own prior growth-reversal research (Cooper/
        Gulen/Schill 2008) for every candidate below, not just revenue_growth_1y.

        quarterly_growth_momentum/earnings_growth_4q_avg are both computed by
        _compute_quarterly_metrics in load_value_quality_growth_metrics.py (the loader that
        runs in the local dev pipeline, not the AWS-only enhanced loader an earlier version of
        this docstring wrongly attributed them to) and mirrored onto BOTH growth_metrics and
        quality_metrics - _get_growth_metrics reads growth_metrics's own copy of each, so
        `metrics` already carries both by the time this method sees it, same as every other
        candidate.

        REVISED 2026-08-31 (industry-alignment review, see GROWTH_SCORE_FIELDS's own docstring
        for the full rationale/evidence): net_income_growth_yoy swapped out for
        forward_eps_growth_current_fy/forward_eps_growth_next_fy/forward_revenue_growth_next_fy.
        forward_eps_growth_current_fy/next_fy and
        forward_revenue_growth_next_fy arrive from _get_growth_metrics already converted from
        their raw-fraction DB storage to the same percentage-point scale every other candidate
        uses (see that method's _scale_fraction_to_pct helper) - _score_single_growth's cap=30
        curve would otherwise silently collapse them toward the 0%-growth midpoint.

        Margin/ROE trend fields (operating_margin_trend/net_margin_trend/roe_trend) remain in
        Quality (relocated there 2026-08-27, then removed from scoring entirely the same day
        on their own isolated re-test - see load_value_quality_growth_metrics.py's
        quality_components comment) - not a Growth input either way, and NOT in
        GROWTH_SCORE_FIELDS.

        eps_growth_stability ADDED 2026-08-31 (/goal session, explicit user directive), then
        REMOVED again later the same day (separate /goal session, "figure out what is right and
        best... based on finance best practices, not our previous conversations" - see
        GROWTH_SCORE_FIELDS's own docstring for the full rationale). It was a dispersion metric
        (population stddev of trailing-4Q YoY EPS growth rates, percentage points, always >=0,
        lower=more consistent) scored via a dedicated inverted piecewise curve
        (_score_eps_growth_stability, deleted 2026-09-15 as dead code - see git history) rather
        than _score_single_growth - real, non-redundant signal, but an MSCI Quality-index component
        (earnings variability), not a named Growth-factor descriptor anywhere, so it didn't clear
        the same canon bar the other 12 fields are held to. fcf_growth_yoy was removed the same
        pass for a different reason - not canonical either, AND its own era-split predictive sign
        flips (H1 t=-2.09, H2 t=+2.45, live-reproduced) rather than just being weak.

        RETURN TYPES (STRICT):
        - >=GROWTH_MIN_FIELDS_AVAILABLE of GROWTH_SCORE_FIELDS available → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - 1..GROWTH_MIN_FIELDS_AVAILABLE-1 candidates available → returns marker dict with
          reason="insufficient_growth_inputs_thin_sample" (see that constant's own docstring -
          added 2026-08-31, a 1-2 field renormalization is thin-sample extrapolation, not an
          honest partial score, same principle Quality already applies to quality_score)
        - every GROWTH_SCORE_FIELDS candidate is None → returns marker dict with
          reason="no_growth_inputs_available"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float, in _get_growth_metrics)
        - Negative growth rates → valid scores (negative growth maps to 0-40 scale, positive to
          40-100, both continuous through 0 - see _score_single_growth)

        Internal function: caller (_compute_stock_score) explicitly handles marker dicts
        and uses them for growth metric computation.

        MINIMUM DATA REQUIREMENT: at least GROWTH_MIN_FIELDS_AVAILABLE of GROWTH_SCORE_FIELDS
        must be non-NULL (see that constant's own docstring for why).
        """
        if not metrics or metrics.get("data_unavailable"):
            reason = metrics.get("reason") if metrics else "metrics_is_none"
            logger.warning(
                f"[STOCK_SCORES] Growth metrics unavailable for {symbol}: {reason}. "
                f"ROOT CAUSE: Check upstream growth_metrics loader (depends on annual_income_statement/"
                f"annual_balance_sheet from SEC filings). Some stocks may lack recent annual filings "
                f"(IPOs, private equity, international)."
            )
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_growth_metrics_data"}

        def _score_single_growth(val: float | None, cap: float) -> float | None:
            """Pass-1 PLACEHOLDER ONLY - flat NEUTRAL_PLACEHOLDER_SCORE (50.0), not a curve, as
            of 2026-09-17 (factor-purity follow-up, "get rid of it" not just verify it's inert -
            same treatment already applied to Value's PE/PB curves and Quality's ROE/D2E/
            earnings-variability curves, see value_metrics.py's NEUTRAL_PLACEHOLDER_SCORE for
            the shared rationale). The removed [-50%,0]->[0,40] / [0,cap%]->[40,100] piecewise
            mapping was hand-set with no citation - live-audited before removing, not assumed
            safe: reconstructed this exact Pass-1 formula for all 3,063 real symbols with a
            scored growth_score and diffed against the actual stored value (the real universe-
            wide MSCI/Barra z-score composite computed by update_growth_sector_neutral_scores()
            below) - 109/3,063 landed within 0.5 points, and `_withhold_growth_below_floor()`
            independently confirms 0 symbols are currently stuck on Pass-1's value at all, so
            those 109 are coincidental correlation (both formulas are monotonic in the same raw
            rate), not the curve surviving as a live score. `cap` is accepted (unused) only so
            the call site below doesn't need updating; this function's only real job is a
            non-NULL placeholder so a symbol never shows a blank growth_score mid-run and Pass
            2's own `WHERE growth_score IS NOT NULL` gate has a row to correct.
            """
            del cap
            return None if val is None else 50.0

        # Equal-weighted blend over GROWTH_SCORE_FIELDS' real MSCI/Barra 4 descriptors, NOT
        # sign-flipped (see GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE above). Cap of 30% reused across every signed-rate
        # candidate: all of them share the same _cagr()/YoY-%-derived percentage-point scale
        # this file has always used that cap for (domain judgment, not separately fit per
        # field - same caveat already applied elsewhere in this file, e.g. asset_turnover,
        # gross_profitability, fcf_margin). No dispersion-metric candidate is scored here since
        # eps_growth_stability's removal 2026-08-31 (see GROWTH_SCORE_FIELDS's own docstring).
        # The dedicated inverted piecewise "badness" curve that used to score it here
        # (_score_eps_growth_stability, dispersion metric, breakpoints p25~=18/median~=53/
        # p75~=156/p90~=404 stddev pct-points -> 80/59/23/0) was deleted 2026-09-15 as dead code
        # (it had no caller since the 2026-08-31 removal) - see git history if a future
        # Quality-pillar pass wants to resurrect this exact curve for an earnings-variability
        # input there.
        component_scores = []
        for field in GROWTH_SCORE_FIELDS:
            raw = metrics.get(field)
            if raw is not None and raw > GROWTH_INPUT_IMPLAUSIBLE_PCT:
                # See GROWTH_INPUT_IMPLAUSIBLE_PCT's docstring: exclude rather than score at a
                # saturated 100 - an implausibly extreme rate isn't comparable "growth quality"
                # to a genuine strong grower even though both would otherwise map identically.
                continue
            score = _score_single_growth(raw, 30)
            if score is not None:
                component_scores.append(score)

        if len(component_scores) >= GROWTH_MIN_FIELDS_AVAILABLE:
            growth_score = sum(component_scores) / len(component_scores)
            logger.debug(
                f"[STOCK_SCORES] {symbol} growth_score computed: {growth_score:.2f} "
                f"({len(component_scores)}/{len(GROWTH_SCORE_FIELDS)} inputs available)"
            )
            return growth_score

        if component_scores:
            logger.info(
                f"[STOCK_SCORES] {symbol} growth_score withheld: only {len(component_scores)}/"
                f"{len(GROWTH_SCORE_FIELDS)} inputs available, below GROWTH_MIN_FIELDS_AVAILABLE="
                f"{GROWTH_MIN_FIELDS_AVAILABLE}. See that constant's docstring - a 1-2 field "
                f"renormalization is thin-sample extrapolation, not an honest partial score."
            )
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "insufficient_growth_inputs_thin_sample",
            }

        logger.warning(
            f"[STOCK_SCORES] {symbol} growth_score computation FAILED: all {len(GROWTH_SCORE_FIELDS)} "
            f"growth candidates are None. ROOT CAUSE: growth_metrics row exists but no growth "
            f"field could be computed for this symbol."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_growth_inputs_available"}

    @staticmethod
    def _components_with_corrected_growth(components_old: Any, growth_score_new: float | None) -> str:
        """Return components (the Pass-1 JSON breakdown dict) re-serialized with its 'growth'
        key set to growth_score_new, every other pillar untouched. Mirrors
        ValueMetricsMixin._components_with_corrected_value exactly (loaders/stock_scores/
        value_metrics.py) - same bug class this repo already fixed there (components silently
        disagreeing with the real *_score column after a batch-pass correction), just for the
        'growth' key instead of 'value'.
        """
        if isinstance(components_old, dict):
            components_new = dict(components_old)
        elif components_old:
            components_new = json.loads(components_old)
        else:
            components_new = {}
        components_new["growth"] = growth_score_new
        return json.dumps(components_new)

    def update_growth_sector_neutral_scores(self) -> None:
        """Batch pass: replace Growth's Pass-1 PROVISIONAL absolute-curve scores
        (`_score_single_growth`'s fixed [-50%,cap%] -> [0,100] mapping, identical for every
        sector) with a true universe-wide z-score against the current run's universe, then
        FULLY RECOMPUTE growth_score and composite_score from scratch off the raw stored
        growth_metrics columns (not patched relative to whatever growth_score/composite_score
        currently hold) - mirrors `update_value_multiples_percentiles()`'s pure-overwrite
        pattern (loaders/stock_scores/value_metrics.py) exactly, which itself mirrors
        `update_rs_percentiles()`'s. Method name kept as `..._sector_neutral_scores` despite no
        longer being sector-relative - same "name is stale, code is correct, don't rename a
        public batch-pass entry point over it" precedent as
        `update_momentum_sector_relative_mom_12_1` (see that method's own history).

        WHY, ORIGINAL 2026-09-08 RATIONALE (SUPERSEDED - see REVERSED TO UNIVERSE-WIDE note
        below): follow-up to the Quality pillar's own 2026-09-07 sector-neutral-zscore rewrite -
        see loaders/helpers/vqg_quality_batch.py's `update_quality_sector_neutral_scores()`, the
        method this one was originally modeled on. After Quality's THEN-sector-relative rewrite
        landed, `composite_score`'s leaderboard was still dominated by Financial Services
        (~60-66% of the top 50), and `growth_score` itself led every sector average for the
        exact reason Quality used to: `_score_single_growth` is an ABSOLUTE curve, identical
        across every sector, with no peer-group context - the same architectural gap this
        rewrite closed for Growth using the SAME primitive Quality then used, not a bespoke
        re-derivation.

        REVERSED TO UNIVERSE-WIDE 2026-09-17 (factor-purity follow-up, user: "where we
        inaccurately mixing industry things to a point where it doesn't make sense"). Growth was
        the LAST pillar still doing per-field sector-relative z-scoring, and it was never
        actually justified on its own evidence - it inherited the sector-relative treatment from
        Quality's OLD 2026-09-07 implementation, which was itself REBUILT to a real, cited MSCI
        universe-wide z-score on 2026-09-16 (see vqg_quality_batch.py's own "STEP 1 (MSCI
        Appendix I/II): z-score EACH variable UNIVERSE-WIDE ... NOT per-sector"). Momentum and
        Risk went through the identical arc even more explicitly: adopted sector-relative on an
        unverified "the real fund does this" assumption, then REVERSED to universe-wide once a
        real crosscheck (MTUM/USMV N-PORT holdings, see factor_normalization.py's
        `universe_wide_zscore` docstring) proved the assumption wrong. Growth's own sector-
        relative choice was NEVER put through that same non-circular test - a prior pass's
        docstring here claimed it "matches MSCI's real Growth-trend methodology (this file's own
        top-of-file citation)", which was false on inspection: GROWTH_SCORE_FIELDS_SUPERSEDED_
        NOTE at the top of this file (the actual citation) is entirely about which 4 descriptors
        match MSCI GIMIVG/Barra EGRO - it says nothing whatsoever about sector-relative
        computation, and MSCI's real Growth style index (same family as its Quality/Momentum
        style indexes, not the "Enhanced" sector-relative-composite construction Value's own
        MSCI Enhanced Value index uses) is a plain universe-wide z-score exactly like Quality and
        Momentum. This was a real instance of the SECTOR-NEUTRALITY GOVERNANCE POLICY
        (pillar_weights.py) being violated, not just applied ad hoc: a sector-relative/
        universe-wide classification was set here on inherited precedent alone, without the
        non-circular panel test that policy requires, and the precedent it inherited from had
        itself since been reversed. Now uses `universe_wide_zscore` - the same primitive
        Momentum/Risk/Quality all converged on - instead of `sector_neutral_zscore`. GICS sector
        (`company_profile.sector`)/FPI-peer-group split are no longer fetched or used here at
        all: a single universe-wide group makes both moot (FPI pooling only matters when the
        alternative is comparison against a narrower sector peer group).

        LIQUIDITY-BASED INVESTABILITY FLOOR (see pillar_weights.py's DEFAULT_MIN_STOCK_PRICE/
        DEFAULT_MIN_ADV_DOLLARS docstring for the 2026-09-15 rationale superseding the market-cap-
        floor version this paragraph used to describe): the sector-neutral z-score's peer group is
        the current run's universe - illiquid names' more extreme growth ratios would otherwise
        distort the percentile boundaries real, investable companies get ranked against. Sub-floor
        symbols simply aren't included in this pass and keep whatever Pass-1 already gave them.

        MECHANISM: Pass 1 (`_score_growth`, per-symbol, no access to the universe distribution)
        still runs first via `_compute_stock_score` so growth_score/composite_score are never
        NULL mid-run - `_score_single_growth`'s absolute curve is now PROVISIONAL scaffolding
        this method always overwrites, the identical relationship Quality's Pass-1 curve
        (`_margin_curve` in vqg_quality.py) has to its own batch pass. This method runs after
        every symbol in this run has a growth_score, winsorizes+z-scores each of the 4
        GROWTH_SCORE_FIELDS candidates WITHIN each symbol's own GICS sector
        (`company_profile.sector`, via `sector_neutral_zscore`), maps each z-score onto [0,100]
        (`zscore_to_percentile_scale`), then re-applies the SAME equal-weighted blend / minimum-
        coverage floor / implausible-value exclusion `_score_growth` already used - only the
        per-field TRANSFORM changes (absolute curve -> sector-neutral z-score), not the field
        list, the weighting, or either guard. This is an explicit, non-negotiable user directive
        (see GROWTH_SCORE_FIELDS/_score_growth's own docstrings) - not re-litigated here.

        STALE CLAIM REMOVED 2026-09-16 (factor-purity sweep, found while re-auditing this exact
        docstring against the code below it, not the focus of that pass): this used to claim
        "GROWTH_INPUT_IMPLAUSIBLE_PCT is still applied BEFORE the z-score" - false since
        2026-09-15, when that hard exclusion was deliberately REMOVED from this pass (see the
        code's own "GROWTH_INPUT_IMPLAUSIBLE_PCT's hard exclusion REMOVED from this pass" comment
        a few lines below) as redundant with `sector_neutral_zscore`'s own [1st,99th] percentile
        winsorization - the real MSCI/Barra/AQR-standard outlier treatment. The constant is NOT
        applied in this batch pass at all; it is still applied in Pass 1 (`_score_growth` above),
        which necessarily differs (see that function's own docstring) - a per-symbol Pass-1 call
        never sees the population, so it cannot winsorize against sector peers the way this
        population-level pass can. This docstring simply never got updated after the 2026-09-15
        change - the code has been correct since then, only this paragraph was lying about it.

        GROWTH_MIN_FIELDS_AVAILABLE is preserved exactly: a symbol with fewer than 2/4 fields
        available (after implausible-value exclusion) gets growth_score=None here (withheld,
        same "thin-sample extrapolation, not an honest partial score" principle as Pass 1's
        marker-dict return, adapted to this pass's "None is a valid overwrite" convention -
        see `update_value_multiples_percentiles()`'s VALUE_MIN_WEIGHT gate for the precedent).

        Composite_score is recomputed exactly as `update_value_multiples_percentiles()` recomputes
        it - from quality_score/value_score/risk_score/momentum_score as they currently stand
        (untouched by this pass) plus the new growth_score, via fixed `BASE_PILLAR_WEIGHTS`.
        Runs AFTER `update_value_multiples_percentiles()` in `post_run()` specifically so this
        pass's own composite recompute sees Value's own already-finalized value_score, not its
        Pass-1 provisional one - see `post_run()`'s own "ORDER MATTERS" comment.

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        growth_score/composite_score is a live-trading-relevant correctness issue.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                # FIX 2026-09-09: no gm.data_unavailable gate (Pass 1 scores partial-field rows despite it, see _get_growth_metrics 2026-09-04 fix) - ss.growth_score IS NOT NULL is the real gate.
                # ACTIVE-UNIVERSE GUARD (added 2026-09-09, migration 1276's own code fix - see
                # NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's own module-level comment in
                # utils/loaders/helpers.py for the full evidence trail). Without this, a closed-
                # end fund/BDC/trust row that predates (or later drifted out of) the active-
                # universe exclusion get_active_symbols(exclude_etfs=True) enforces for the
                # per-symbol fetch path keeps getting growth_score/composite_score freshly
                # recomputed here forever.
                # Growth-field column list built from GROWTH_SCORE_FIELDS itself (4 fields as of
                # the 2026-09-16 MSCI/Barra-aligned cut - see that constant's own
                # GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE) rather than a separately hand-maintained
                # column literal - field_col_offset below assumes column order/count matches
                # GROWTH_SCORE_FIELDS exactly, so a hardcoded list here could silently drift out
                # of sync with that constant.
                growth_field_columns = ", ".join(f"gm.{field}" for field in GROWTH_SCORE_FIELDS)
                cur.execute(
                    f"""
                    SELECT ss.symbol, ss.growth_score, ss.composite_score, ss.quality_score,
                           ss.value_score, ss.risk_score, ss.momentum_score, ss.components,
                           ss.data_completeness, ss.data_unavailable,
                           {growth_field_columns}, vm.market_cap
                    FROM stock_scores ss
                    JOIN growth_metrics gm ON gm.symbol = ss.symbol
                    JOIN stock_symbols su ON su.symbol = ss.symbol
                    LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                    LEFT JOIN value_metrics vm ON vm.symbol = ss.symbol
                    """
                    + LIQUIDITY_FLOOR_JOIN_SQL
                    + """
                    WHERE ss.growth_score IS NOT NULL
                      AND liq_floor.latest_close >= %s
                      AND liq_floor.avg_dollar_volume_20d >= %s
                      AND ("""
                    + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                    + ")",
                    (
                        getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                        getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                    ),
                )
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_growth_sector_neutral_scores: no eligible rows found "
                    "(growth_score IS NOT NULL joined to growth_metrics) - skipping, nothing to correct."
                )
                return

            # forward_eps_growth_current_fy is stored as a raw fraction in growth_metrics
            # (0.18 = 18%), same as _get_growth_metrics's own _scale_fraction_to_pct helper
            # handles for Pass 1 - scale to percentage points here too so it's on the same scale
            # as every other GROWTH_SCORE_FIELDS candidate before winsorization/z-scoring.
            fraction_fields = {
                "forward_eps_growth_current_fy",
            }
            # Column index (within the GROWTH_SCORE_FIELDS-width slice starting at row[10]) for
            # each candidate, matching the SELECT's dynamically-built column order above exactly.
            #
            # DEAD-COLUMN FIXED 2026-09-17 (factor-purity follow-up, same class of gap already
            # fixed in risk_scoring.py's `_fetch_risk_absolute_zscore_rows`): this comment used
            # to claim a trailing `vm.market_cap` column (fetched via a `LEFT JOIN value_metrics
            # vm`) was "still selected below for the liquidity-floor join" - false.
            # LIQUIDITY_FLOOR_JOIN_SQL (pillar_weights.py) computes its own avg_dollar_volume_20d/
            # latest_close from price_daily directly and never references `vm`/`market_cap` at
            # all - confirmed via grep, that JOIN and column existed purely as leftover
            # size-neutralization scaffolding from before it was removed 2026-09-16 (see the
            # pct_by_field comment below) and were never actually cleaned up with it. Removed the
            # dead `vm.market_cap` SELECT and its now-unnecessary `value_metrics` JOIN.
            #
            # cp.sector/FPI-peer-group columns REMOVED 2026-09-17 (same pass that reversed this
            # method to universe_wide_zscore below - see this method's own "REVERSED TO
            # UNIVERSE-WIDE" docstring note): a single universe-wide group has no sector/FPI peer
            # groups to build, so `company_profile`'s JOIN and the is_foreign_private_issuer
            # column this pass used to fetch are both gone, not just unused.
            field_col_offset = {field: 10 + i for i, field in enumerate(GROWTH_SCORE_FIELDS)}
            # market_cap re-added 2026-09-17 (MSCI-fidelity audit) - NOT the same dead column
            # removed above: that one fed the now-gone Barra-style size-NEUTRALIZATION step
            # (regressing out a size effect); this one feeds the z-score's own mean/stdev
            # WEIGHTING (MSCI Enhanced Value Index Methodology Appendix II: "the mean and
            # standard deviation are calculated using the free-float market-cap-weighted values")
            # - a different, still-live part of the real MSCI formula. Trailing column, so it
            # doesn't disturb field_col_offset's GROWTH_SCORE_FIELDS-width assumption above.
            market_cap_col = 10 + len(GROWTH_SCORE_FIELDS)
            market_caps: dict[str, float] = {
                row[0]: float(row[market_cap_col])
                for row in rows
                if len(row) > market_cap_col and row[market_cap_col] is not None
            }

            raw_by_field: dict[str, dict[str, float]] = {field: {} for field in GROWTH_SCORE_FIELDS}
            for row in rows:
                symbol = row[0]
                for field in GROWTH_SCORE_FIELDS:
                    val = row[field_col_offset[field]]
                    if val is None:
                        continue
                    val_f = float(val) * 100 if field in fraction_fields else float(val)
                    # GROWTH_INPUT_IMPLAUSIBLE_PCT's hard exclusion REMOVED from this pass
                    # 2026-09-15 (user directive: "get rid of all the extra shit beyond the
                    # barra and the industry guys"). It duplicated what `sector_size_neutral_
                    # zscore`'s own `_winsorize_group` already does to this exact population -
                    # clip to [1st, 99th] percentile per peer group - which is the real
                    # MSCI Barra/AQR-standard outlier treatment (winsorize, never drop a raw
                    # observation outright). A hand-picked absolute cutoff (150%) on top of
                    # that standard winsorization was genuinely redundant machinery, not a
                    # second layer of protection.
                    #
                    # RE-APPLIED, SCOPED TO sustainable_growth_rate ONLY (2026-09-19, /goal
                    # leaderboard dig-in, same failure class as Value's fcf_yield-fallback fix
                    # this session): the 2026-09-15 removal's premise - that `_winsorize_group`'s
                    # own [5th,95th] percentile clip already handles this population - assumed
                    # the extreme tail stays a normal-sized minority. Live-verified it no longer
                    # is: 339/4,611 symbols (7.35%) now sit beyond +/-150% (up from the 37/5,164
                    # (0.7%) this constant's own docstring measured when the removal landed),
                    # with a fat, wildly asymmetric tail (p1=-560%, p99=+111%, extremes to
                    # SMX -1971%/VSA +1675%) - a near-zero-or-negative stockholders_equity
                    # denominator blowing up ROE x retention rate (see vqg_quality.py's own
                    # MAX_PLAUSIBLE_GROWTH_PCT=2000 upstream guard - loose enough to let exactly
                    # this shape of value through to this table). At 7.35% the extreme tail is
                    # now bigger than the 5% window `_winsorize_group` robustifies against, so
                    # the "duplicated machinery" premise is gone - this is no longer a second
                    # layer of protection over an already-small tail, it's the only thing that
                    # keeps a majority-larger-than-the-clip-window tail from pulling this field's
                    # reference mean/stdev around for every OTHER symbol scored on it. Scoped to
                    # sustainable_growth_rate specifically, not all 4 fields: eps_growth_trend_5y/
                    # sps_growth_trend_5y/forward_eps_growth_current_fy remain live-verified
                    # naturally bounded (max/min within +/-120%, well under this threshold) - see
                    # this file's own GROWTH_INPUT_IMPLAUSIBLE_PCT docstring - so reintroducing
                    # the exclusion for those would in fact be the redundant machinery the
                    # 2026-09-15 removal correctly objected to. A symbol excluded here drops this
                    # leg entirely (renormalizes onto its other available GROWTH_SCORE_FIELDS
                    # candidates, subject to GROWTH_MIN_FIELDS_AVAILABLE), same "no plausible
                    # measurement -> omit, don't fabricate" pattern as Value's analogous fix.
                    if field == "sustainable_growth_rate" and abs(val_f) > GROWTH_INPUT_IMPLAUSIBLE_PCT:
                        continue
                    raw_by_field[field][symbol] = val_f

            # SIZE NEUTRALIZATION REMOVED 2026-09-16 (factor-purity sweep - this leftover was
            # justified purely by pointing at "same as Value's div/cash-yield legs, 2026-09-15",
            # but Value's own MSCI-formula rebuild the SAME SESSION already dropped that exact
            # step (see value_metrics.py's "DROPPED from the prior construction to match MSCI
            # exactly: ... Barra-style size-neutralization ... not part of MSCI's literal
            # published formula") and Quality's rebuild dropped it too.
            #
            # UNIVERSE-WIDE, not sector-relative (fixed 2026-09-17 - see this method's own
            # "REVERSED TO UNIVERSE-WIDE" docstring note): matches the same primitive Quality/
            # Momentum/Risk all converged on for a plain (non-"Enhanced") MSCI-style factor.
            pct_by_field: dict[str, dict[str, float]] = {
                field: zscore_to_percentile_scale(universe_wide_zscore(values, market_caps))
                for field, values in raw_by_field.items()
            }
            logger.info(
                "[STOCK_SCORES] Growth universe-wide z-score pass: "
                + ", ".join(f"{field}={len(pct_by_field[field])}" for field in GROWTH_SCORE_FIELDS)
            )

            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            updates: list[tuple[str, float | None, float, str | None, float, bool]] = []
            for row in rows:
                symbol = row[0]
                growth_score_old = float(row[1])
                composite_score_old = float(row[2])
                quality_score, value_score, risk_score, momentum_score = row[3], row[4], row[5], row[6]
                components_old = row[7]
                data_completeness_old = float(row[8]) if row[8] is not None else None
                data_unavailable_old = bool(row[9]) if row[9] is not None else False

                component_scores = [
                    pct_by_field[field][symbol] for field in GROWTH_SCORE_FIELDS if symbol in pct_by_field[field]
                ]

                if len(component_scores) >= GROWTH_MIN_FIELDS_AVAILABLE:
                    growth_score_new: float | None = round(sum(component_scores) / len(component_scores), 2)
                else:
                    if component_scores:
                        logger.info(
                            f"[STOCK_SCORES] {symbol} growth_score withheld in sector-neutral pass: only "
                            f"{len(component_scores)}/{len(GROWTH_SCORE_FIELDS)} inputs available, below "
                            f"GROWTH_MIN_FIELDS_AVAILABLE={GROWTH_MIN_FIELDS_AVAILABLE}."
                        )
                    growth_score_new = None

                # GROWTH RESTORED TO COMPOSITE 2026-09-17 (same-day reversal of the earlier
                # "removed from composite" decision - see pillar_weights.py's BASE_PILLAR_WEIGHTS
                # "ABOVE DECISION SUPERSEDED" note). growth_score_new votes in composite_score
                # and data_completeness again, using THIS pass's own freshly-recomputed value
                # (not the stale growth_score_old fetched above) - same "use the just-computed
                # value, not the pre-pass DB value" pattern quality_scoring.py/momentum_scoring.py/
                # risk_scoring.py/value_metrics.py already use for their own just-recomputed pillar.
                weights = BASE_PILLAR_WEIGHTS
                composite_val = 0.0
                for pillar_name, pillar_score in (
                    ("quality", quality_score),
                    ("value", value_score),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
                    ("growth", growth_score_new),
                ):
                    if pillar_score is not None:
                        composite_val += float(pillar_score) * weights[pillar_name]
                composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

                all_scores_new: dict[str, float | None] = {
                    "quality": float(quality_score) if quality_score is not None else None,
                    "value": float(value_score) if value_score is not None else None,
                    "risk": float(risk_score) if risk_score is not None else None,
                    "momentum": float(momentum_score) if momentum_score is not None else None,
                    "growth": growth_score_new,
                }
                available_weight = sum(
                    BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores_new.items() if score is not None
                )
                data_completeness_new = min(99.99, round(available_weight * 100, 2))
                data_unavailable_new = data_completeness_new < min_completeness_threshold

                if (
                    growth_score_new != growth_score_old
                    or composite_score_new != composite_score_old
                    or data_completeness_new != data_completeness_old
                    or data_unavailable_new != data_unavailable_old
                ):
                    components_json = self._components_with_corrected_growth(components_old, growth_score_new)
                    updates.append(
                        (
                            symbol,
                            growth_score_new,
                            composite_score_new,
                            components_json,
                            data_completeness_new,
                            data_unavailable_new,
                        )
                    )

            updates.extend(self._withhold_growth_below_floor())

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Growth sector-neutral z-score pass: no symbol's growth_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is a pure function of the raw stored ratios, same idempotency "
                    "property as update_value_multiples_percentiles())."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                # ::numeric/::boolean casts (added 2026-09-17, factor-purity follow-up - see
                # risk_scoring.py's identical fix, applied here for the same reason and same
                # live-confirmed effect): this UPDATE mixes real floats (corrected symbols) with
                # None (withheld, via `_withhold_growth_below_floor()`) in the same growth_score
                # column position - the same mixed-None/float psycopg2 wrong-inferred-
                # column-type gotcha already fixed for quality_score/momentum_score when THEIR
                # OWN withhold passes were added, never ported here despite this method's own
                # `_withhold_growth_below_floor()` landing 2026-09-16. Uncast, this raised
                # psycopg2.errors.DatatypeMismatch on every real run, and because post_run()
                # calls this method unguarded, the exception aborted every pass after it too
                # (update_momentum_sector_relative_mom_12_1/update_market_cap_tilted_weights) -
                # not just leaving growth_score stale.
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET growth_score = v.growth_score::numeric,
                        composite_score = v.composite_score::numeric,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness::numeric,
                        data_unavailable = v.data_unavailable::boolean,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, growth_score, composite_score, components,
                                           data_completeness, data_unavailable)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Growth sector-neutral z-score pass corrected "
                f"{len(updates)}/{len(rows)} symbols' growth_score/composite_score (post_run completed)"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Growth sector-neutral z-score batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _withhold_growth_below_floor(
        self,
    ) -> list[tuple[str, float | None, float, str | None, float, bool]]:
        """Companion to update_growth_sector_neutral_scores(): finds the COMPLEMENT of that
        method's own correction population - symbols with a real growth_score but ineligible for
        correction (below the liquidity floor, or excluded by
        NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE) - and withholds growth_score (NULL) plus
        recomputes composite_score/data_completeness/data_unavailable to match, rather than
        leaving Pass 1's stale, potentially-saturated absolute-curve value (`_score_single_growth`,
        including a value GROWTH_INPUT_IMPLAUSIBLE_PCT would otherwise have excluded) in place
        indefinitely.

        PORTED 2026-09-16 (factor-purity sweep - this exact bug class was already found and fixed
        for Quality (vqg_quality_batch.py's `_withhold_quality_below_floor`) and Momentum
        (momentum_scoring.py's `_withhold_momentum_below_floor`, commit c1a3dd899) but never
        ported here or to Value/Risk - see those two methods' own docstrings for the shared
        rationale. Same gap, same fix, same shape.

        Returns tuples in the same (symbol, growth_score, composite_score, components,
        data_completeness, data_unavailable) shape update_growth_sector_neutral_scores()'s own
        `updates` list uses, so the caller can extend one batch UPDATE with both.
        """
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                SELECT ss.symbol, ss.composite_score, ss.quality_score, ss.value_score,
                       ss.risk_score, ss.momentum_score, ss.components,
                       ss.data_completeness, ss.data_unavailable
                FROM stock_scores ss
                JOIN growth_metrics gm ON gm.symbol = ss.symbol
                JOIN stock_symbols su ON su.symbol = ss.symbol
                LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                LEFT JOIN (
                    SELECT symbol,
                           AVG(volume * close) AS avg_dollar_volume_20d,
                           (ARRAY_AGG(close ORDER BY date DESC))[1] AS latest_close
                    FROM (
                        SELECT symbol, volume, close, date,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                          AND COALESCE(data_unavailable, false) = false
                          AND volume IS NOT NULL AND close IS NOT NULL
                    ) ranked
                    WHERE rn <= 20
                    GROUP BY symbol
                ) liq_floor ON liq_floor.symbol = ss.symbol
                WHERE ss.growth_score IS NOT NULL
                  AND (
                        liq_floor.latest_close IS NULL
                        OR liq_floor.latest_close < %s
                        OR liq_floor.avg_dollar_volume_20d IS NULL
                        OR liq_floor.avg_dollar_volume_20d < %s
                        OR NOT ("""
                + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                + """)
                  )
                """,
                (
                    getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                    getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                ),
            )
            rows = cur.fetchall()

        if not rows:
            # No work to do - every scored symbol already cleared the liquidity floor and the
            # non-operating exclusion, so there's nothing to withhold this run. Not an error.
            return []

        min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)
        withheld: list[tuple[str, float | None, float, str | None, float, bool]] = []
        for (
            symbol,
            _composite_score_old,
            quality_score,
            value_score,
            risk_score,
            momentum_score,
            components_old,
            _dc_old,
            _du_old,
        ) in rows:
            weights = BASE_PILLAR_WEIGHTS
            composite_val = 0.0
            for pillar_name, pillar_score in (
                ("quality", quality_score),
                ("value", value_score),
                ("risk", risk_score),
                ("momentum", momentum_score),
            ):
                if pillar_score is not None:
                    composite_val += float(pillar_score) * weights[pillar_name]
            composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)
            available_weight = sum(
                weights[p]
                for p, s in (
                    ("quality", quality_score),
                    ("value", value_score),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
                )
                if s is not None
            )
            data_completeness_new = min(99.99, round(available_weight * 100, 2))
            data_unavailable_new = data_completeness_new < min_completeness_threshold
            components_json = self._components_with_corrected_growth(components_old, None)
            withheld.append(
                (
                    symbol,
                    None,
                    composite_score_new,
                    components_json,
                    data_completeness_new,
                    data_unavailable_new,
                )
            )
        logger.info(
            f"[STOCK_SCORES] Growth: withheld growth_score for {len(withheld)} symbols below the "
            f"liquidity floor / excluded from the scoring population (never reached by the "
            f"correction pass above) - see _withhold_growth_below_floor's docstring."
        )
        return withheld
