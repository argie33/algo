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

import itertools
import json
import logging
from typing import TYPE_CHECKING, Any

import psycopg2

from loaders.helpers.factor_normalization import sector_neutral_zscore, zscore_to_percentile_scale
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS, _value_risk_adjusted_weights
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


# GROWTH_SCORE_FIELDS: the multi-input equal-weighted blend _score_growth scores (RESTORED
# 2026-08-28, user directive - see _score_growth's docstring for the full history/evidence
# trail). Order matches GROWTH_SCHEMA in StockScoreAccordion.jsx - every field the frontend's
# Growth tab displays is scored here, not just whichever one field last "won" an isolated
# Fama-MacBeth test. Kept at module level (not a local inside _score_growth) so
# tests/unit/test_scores_frontend_weight_badges_match_backend.py can import it directly instead
# of re-deriving the field list via source-regex, same convention as BASE_PILLAR_WEIGHTS.
#
# ocf_growth_yoy/asset_growth_yoy REMOVED 2026-08-28 (user directive, /goal session: "remove
# these two from growth score and from react"). Raw values remain computed/persisted in
# growth_metrics (load_value_quality_growth_metrics.py) and available via the API for reference
# - only the scoring input and the frontend GROWTH_SCHEMA row were removed, same
# still-computed/no-longer-scored treatment this file already uses elsewhere (e.g. margin/ROE
# trend fields, altman_z_score).
#
# book_value_growth REMOVED 2026-08-28 (user directive, /goal session: live-observed
# persistent "No data" on StockDetail for the stock under review). Same still-computed/
# no-longer-scored treatment as above - raw value remains in growth_metrics (migration 1242)
# for reference, just no longer scored or shown in GROWTH_SCHEMA.
#
# operating_income_growth_yoy REMOVED 2026-08-28 (user directive, /goal session: "remove this
# Operating Income Growth (YoY) ... from growth from the score and the react"). Same still-
# computed/no-longer-scored treatment as above - raw value remains in growth_metrics
# (load_value_quality_growth_metrics.py) for reference, just no longer scored or shown in
# GROWTH_SCHEMA.
#
# 2026-08-31 INDUSTRY-ALIGNMENT REVIEW (goal session: "dig and be certain we come up with the
# right list... best regarded metrics for identifying the growth factor"). Compared the prior
# 11-field list against MSCI/Russell/S&P's own published Growth-factor methodologies and
# IBD CAN SLIM, then re-verified every quantitative claim directly against the live DB (not
# carried over from a prior memory - see feedback_verify_specific_quantitative_claims_before_trusting
# in memory for why that matters on this exact file). Two changes:
#
# 1. net_income_growth_yoy REMOVED. Every major growth-style methodology (MSCI, Russell, S&P,
#    Zacks, IBD) defines the "earnings growth" descriptor on a PER-SHARE (EPS) basis
#    specifically because it is buyback/dilution-adjusted - a company can grow raw net income
#    only by issuing shares (real dilution, no per-owner benefit) or shrink net income while
#    growing EPS via buybacks (common for mature compounders). Raw net-income growth is not a
#    named component of any of those methodologies. This is a methodological objection, NOT a
#    redundancy fix - live Spearman correlation vs eps_growth_1y is only 0.16 (re-verified
#    2026-08-31, matches the same-day correction in
#    growth_pillar_industry_alignment_reviewed_no_action_20260828 - net_income_growth_yoy is
#    NOT a near-duplicate of anything else in this blend), so it was carrying real independent
#    variance, just not the industry-standard variance for this factor.
# 2. forward_eps_growth_current_fy / forward_eps_growth_next_fy / forward_revenue_growth_next_fy
#    ADDED. Forward (analyst-consensus) EPS growth is the headline Growth descriptor in MSCI's
#    "Long Term Forward EPS Growth Rate", Russell's 2-year I/B/E/S forecast EPS growth, and
#    S&P's growth methodology - this pillar was previously 100% backward-looking with no
#    forward-estimate input at all (flagged as the clearest institutional-comparison gap in
#    growth_pillar_industry_alignment_reviewed_no_action_20260828, "not fixable now" at the
#    time). That's since changed: forward_eps_growth_current_fy/next_fy and
#    forward_revenue_growth_next_fy were added to growth_metrics 2026-08-29 (real yfinance
#    analyst-estimate data, not a placeholder) and now have live per-symbol coverage of
#    73.1%/75.8%/76.7% respectively - comparable to already-scored fields like fcf_growth_yoy
#    (72.1%) - even though analyst_earnings_estimates itself still only has ~24 distinct
#    snapshot dates (no backfill capability), too little historical depth to backtest
#    predictive power in this DB. Included on industry-standard-methodology grounds, consistent
#    with this pillar's standing user override to prioritize matching well-regarded growth
#    definitions over requiring a fresh era-robust regression result for every candidate (see
#    growth_pillar_restored_multi_input_not_inverted_user_override_20260828). Correlate weakly
#    with every backward-looking field already in this blend (|r|<=0.33, mostly <0.1) and with
#    each other (0.42 forward EPS vs forward revenue) - genuinely new information, not
#    redundant with anything already here. eps_estimate_revision_90d_pct (the 4th field on the
#    same table) deliberately NOT added - estimate-revision momentum is a distinct factor style
#    (Zacks Rank's basis) from a growth-RATE level, and mixing a revision-momentum metric into a
#    naive equal-weight average of growth levels would conflate two different things this file
#    is otherwise careful to keep separate (see Growth-vs-Momentum pillar separation elsewhere
#    in this file) - stays informational-only in GROWTH_SCHEMA, fetched but unscored, same
#    treatment as eps_growth_stability above.
#
# fcf_growth_yoy was also reviewed against this same "is it in MSCI/Russell/S&P's canon"
# standard and is the other non-canonical member (FCF growth isn't a named Growth-factor
# descriptor in any of the three) - kept anyway: it functions as a "quality of growth" check
# (cash-backed earnings growth vs an accounting-only number) rather than a duplicate growth-
# rate, is not correlated with anything else in the blend (|r|<=0.32), and this codebase
# already trusts cash-flow-based measures elsewhere (FCF Yield in Value). Secondary/
# supplementary rather than core-canon, but not "wrong" - left in.
#
# eps_growth_stability ADDED 2026-08-31 (/goal session, explicit user directive: "add earnings
# variability as additional input to growth score"). Previously fetched into `metrics` but
# deliberately excluded from GROWTH_SCORE_FIELDS/this blend (see the now-superseded note in
# _score_growth's docstring) because, unlike every other candidate here, it's a dispersion
# metric (population stddev, in percentage points, of the trailing-4-quarter YoY EPS growth
# rates - see _compute_quarterly_metrics in load_value_quality_growth_metrics.py), always >=0
# and "lower is better" rather than a signed growth rate on the same higher-is-better scale.
# "Earnings variability" is itself a named signal in institutional factor methodology (e.g. it's
# one of MSCI's own three Quality-index components, alongside ROE and leverage) - the user's
# framing of it as a Growth input rather than Quality is an explicit, direct product decision,
# not a methodology dispute to relitigate (same footing as this pillar's standing multi-input
# user override - see _score_growth's docstring). Real, live-computed data: 3,879/4,862 non-
# unavailable growth_metrics rows have a value (79.8% coverage, live-verified 2026-08-31 -
# comparable to already-scored fcf_growth_yoy's 72.1% and quarterly_growth_momentum's 79.5%),
# not a placeholder. Scored via a dedicated inverted piecewise curve
# (_score_growth's _score_eps_growth_stability), NOT _score_single_growth - see that helper's
# own docstring for why (this field's scale/shape has nothing in common with a signed growth
# rate, so it can't reuse the shared cap=30 linear transform every other candidate does).
# fcf_growth_yoy / eps_growth_stability REMOVED 2026-08-31 (goal session: "figure out what is
# right and best, best proven validated best practices" - user explicitly asked to judge every
# field on finance merit alone, not on what a prior session had already decided). Both were kept
# through 3 earlier reviews on "real, uncorrelated signal" grounds - true, but insufficient once
# actually held to the SAME two-part bar the other 12 fields already clear:
# 1. fcf_growth_yoy: not a named component of MSCI/Russell/S&P/IBD's Growth methodology (cash-
#    flow growth isn't a canonical Growth descriptor anywhere), AND its own era-split predictive
#    evidence - independently reproduced this session via
#    `python -m algo.research.fama_macbeth_growth_factors` (not reused from a prior claim) -
#    actively FLIPS SIGN with real significance both ways (H1 2014-2020-06 t=-2.09, H2
#    2020-06-2026 t=+2.45, full-sample t=0.43). This is the identical "era-inconsistent, reject"
#    pattern this file has used to reject every other flipping candidate (e.g.
#    net_income_growth_yoy/operating_income_growth_yoy, asset_growth_yoy under the no-flip
#    convention) - not weak evidence, actively unstable evidence.
# 2. eps_growth_stability: real, non-redundant signal (~0 correlation with every growth-rate
#    field, live-checked) and legitimate, well-established methodology - but it's MSCI's own
#    Quality-index earnings-variability component, not a Growth-factor descriptor in MSCI's,
#    Russell's, S&P's, or IBD's published methodology. Held to the same "must be a named
#    component of a real Growth methodology" standard as the other 12, it doesn't qualify for
#    THIS pillar - it may belong in Quality instead (which has no earnings-variability input of
#    its own, only the related-but-distinct Margin Volatility), but that's a separate Quality-
#    pillar decision, not made here. Still computed/persisted in growth_metrics and displayed as
#    a tracked-not-scored row in GROWTH_SCHEMA (frontend), per this repo's standing "convert
#    removed fields to informational rows, don't delete" practice - not scored here.
# Net result: 12 fields, all independently verified canonical to a named MSCI/Russell/S&P/IBD
# Growth-factor component, equal-weighted (1/12 ~= 8.3% each - see GROWTH_SCHEMA/weight badges).
GROWTH_SCORE_FIELDS: tuple[str, ...] = (
    "revenue_growth_1y",
    "eps_growth_1y",
    "revenue_growth_3y",
    "eps_growth_3y",
    "revenue_growth_5y",
    "eps_growth_5y",
    "forward_eps_growth_current_fy",
    "forward_eps_growth_next_fy",
    "forward_revenue_growth_next_fy",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
    "earnings_growth_4q_avg",
)

# GROWTH_INPUT_IMPLAUSIBLE_PCT (added 2026-08-31, /goal session - "make sure the results make
# sense" investigation). _score_single_growth's cap=30 already bounds every signed-rate
# candidate's OUTPUT at 100, but does nothing to distinguish a genuinely excellent ~30-100%
# grower from a candidate whose raw rate is in the hundreds or thousands of percent - both map
# to an identical, fully-saturated 100. Live-verified two such cases dominating the top of
# composite_score: KARO's eps_growth_1y=1889.36% traces to FY2026 net_income of $993.9M vs
# $50.8M the prior year on an almost-unchanged share count (30.89M -> 30.89M, no split) -
# implying a ~2x P/E on its $2.08B market cap, which is not a real recurring-earnings story,
# almost certainly a one-off item (asset sale/tax benefit/settlement) counted at face value.
# DX similarly has fcf_growth_yoy=739.5%, quarterly_growth_momentum=140.35% - both 5-25x this
# cap. Neither looks like corrupted data (both are internally consistent with their own
# financials, so the existing garbage-value bound elsewhere in this codebase - which catches
# actual data-corruption cases up to +/-2000% - correctly leaves them alone), but they are not
# comparable "growth quality" to a clean, sustainable 30-100% grower either. Standard factor-
# investing practice (MSCI Barra, AQR) winsorizes/excludes outlier raw inputs before scoring for
# exactly this reason - a single anomalous field shouldn't get to fully saturate a multi-input
# equal-weighted blend. Set well above any plausible genuine "excellent" grower (the cap=30
# curve already reaches its 100 ceiling at 30%) so normal strong growers (e.g. YB's real
# eps_growth_1y=123.18%) are unaffected - only truly extreme values are excluded from the blend
# entirely (same "drop what's missing, don't hand its weight to a different candidate" pattern
# _score_growth already uses for None values), rather than counted as a full-credit 100.
# Deliberately NOT applied to eps_growth_stability - its own inverted curve already penalizes
# large values toward 0, so no separate exclusion is needed there.
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
# same treatment when it moved from single-input to multi-input. 5/12 (~42%) mirrors Quality's
# ~40%-of-101 ratio; below this, _score_growth returns a data_unavailable marker instead of a
# score built from too little evidence, same "honest partial data, not thin-sample extrapolation"
# principle, not a new one invented here.
GROWTH_MIN_FIELDS_AVAILABLE = 5


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

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 25 columns (revenue_growth_1y/3y/5y, eps_growth_1y/
          3y/5y, book_value_growth, net_income_growth_yoy, operating_income_growth_yoy,
          sustainable_growth_rate, fcf_growth_yoy, ocf_growth_yoy, gross/operating/net_margin_
          trend, roe_trend, asset_growth_yoy, eps_growth_stability, quarterly_growth_momentum,
          earnings_growth_4q_avg, forward_eps_growth_current_fy, forward_eps_growth_next_fy,
          forward_revenue_growth_next_fy, eps_estimate_revision_90d_pct, data_unavailable) -
          extended 2026-08-31 to add the 4 forward/analyst-estimate fields (see
          GROWTH_SCORE_FIELDS/_score_growth for why 3 of the 4 now feed growth_score).
        - Schema mismatch (len(row) < 25) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_growth_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes
        immediate fail-fast ValueError. Dependent on upstream annual_income_statement availability.
        """
        row = self._growth_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 25 columns before accessing indices
            # (21 + forward_eps_growth_current_fy/next_fy + forward_revenue_growth_next_fy +
            # eps_estimate_revision_90d_pct, added 2026-08-31)
            if len(row) < 25:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 25. "
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
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No growth metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_growth_metrics", "Growth metrics table missing data")

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale via a multi-input blend. Returns marker dict if
        no real data.

        RESTORED TO MULTI-INPUT 2026-08-28 (user directive, /goal session: "get the rest of the
        growth inputs back in there the ones that are in the react" + explicit pushback that
        revenue_growth_1y's sign-flip "shouldn't be inverted"). This pillar had been rebuilt 3
        times in 48h into an increasingly narrow single-input, sign-flipped design (the original
        11-input blend -> book_value_growth alone -> revenue_growth_1y alone, each justified by
        isolated Fama-MacBeth "winner take all" testing - see git history for that evidence
        trail, not repeated here since it no longer describes the live formula). A same-day
        re-test of a genuine multi-input blend (algo/research/growth_multi_input_blend_test_20260828.py)
        found neither the single-input nor an equal-weighted 5-candidate blend era-robust once
        controlled for the other 5 pillars (see
        growth_multi_input_blend_tested_not_robust_reit_signal_backwards_20260828 in memory) -
        so this restore is NOT an evidence-driven reversal, it's an explicit user override of
        that evidence, the same footing as this file's Dividend-Yield-over-Net-Payout-Yield
        precedent (_score_value's docstring: "REVERTED back to Dividend Yield 2026-08-28 on
        explicit user directive").

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
        (_score_eps_growth_stability, kept below but unused by this method now) rather than
        _score_single_growth - real, non-redundant signal, but an MSCI Quality-index component
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
            """Score a single growth rate capped at `cap`%.

            Continuous through val=0: negative growth maps [-50, 0] -> [0, 40], positive
            growth maps [0, cap] -> [40, 100]. Both branches meet at 40 for 0% growth, so a
            modest positive grower always outscores any decliner.
            """
            if val is None:
                return None
            if val <= 0:
                # Negative growth: map [-50, 0] → [0, 40]
                # FIXED 2026-08-27 (goal-mode data-coverage audit): max(0, ...)/min(100, ...)
                # with int literals return the literal Python int when the float argument
                # saturates past the boundary (e.g. min(100, 105.3) -> int 100, not 100.0).
                # is_real_score() downstream does isinstance(result, float), so any saturated
                # score silently failed that check and got discarded as "unknown_reason" -
                # affected 761/5194 symbols (every one with book_value_growth <= -30% or
                # >= +50%, both common), NOT a data gap. Use float literals so the boundary
                # case still returns a real float.
                return max(0.0, 40 + (val / 50) * 40)
            # Positive growth: map [0, cap] → [40, 100]
            return min(100.0, 40 + (val / cap) * 60)

        def _score_eps_growth_stability(val: float | None) -> float | None:
            """Score eps_growth_stability (population stddev, percentage points, of the
            trailing-4-quarter YoY EPS growth rates) as an inverted "earnings variability"
            input: lower dispersion = more consistent execution = higher score. Always >=0, so
            it needs its own curve rather than _score_single_growth's signed [-50,cap] shape.

            Piecewise-linear "badness" curve (100 minus it), same convention this codebase
            already uses for other dispersion/volatility metrics (see _margin_curve in
            load_value_quality_growth_metrics.py's quality scoring), re-scaled for this field's
            live distribution (verified directly against growth_metrics, not assumed):
            p25~=18, median~=53, p75~=156, p90~=404 percentage points of stddev. Anchors: 0
            stddev -> 100 (perfectly consistent), ~p25 -> 80, ~median -> ~59, ~p75 -> ~23,
            >=p90 -> 0. Breakpoints are domain judgment calibrated to the real distribution,
            not separately fit/backtested - same caveat this file already applies to its other
            fixed-cap curves (e.g. the cap=30 above).
            """
            if val is None:
                return None
            if val <= 0:
                return 100.0
            breakpoints = [(20.0, 20.0), (75.0, 55.0), (200.0, 90.0), (400.0, 100.0)]
            if val < breakpoints[0][0]:
                badness = (val / breakpoints[0][0]) * breakpoints[0][1]
            else:
                badness = breakpoints[-1][1]
                for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
                    if val < x1:
                        badness = y0 + (val - x0) / (x1 - x0) * (y1 - y0)
                        break
            return max(0.0, 100.0 - badness)

        # Equal-weighted blend, NOT sign-flipped (see docstring - explicit user override of
        # this file's own growth-reversal research). Cap of 30% reused across every signed-rate
        # candidate: all of them share the same _cagr()/YoY-%-derived percentage-point scale
        # this file has always used that cap for (domain judgment, not separately fit per
        # field - same caveat already applied elsewhere in this file, e.g. asset_turnover,
        # gross_profitability, fcf_margin). No dispersion-metric candidate is scored here since
        # eps_growth_stability's removal 2026-08-31 (see GROWTH_SCORE_FIELDS's own docstring) -
        # _score_eps_growth_stability is kept, unused, in case a future Quality-pillar pass wants
        # this exact well-tested dispersion curve for an earnings-variability input there.
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
        sector) with a true sector-neutral z-score against the current run's universe, then
        FULLY RECOMPUTE growth_score and composite_score from scratch off the raw stored
        growth_metrics columns (not patched relative to whatever growth_score/composite_score
        currently hold) - mirrors `update_value_multiples_percentiles()`'s pure-overwrite
        pattern (loaders/stock_scores/value_metrics.py) exactly, which itself mirrors
        `update_rs_percentiles()`'s.

        WHY (2026-09-08, follow-up to the Quality pillar's own 2026-09-07 sector-neutral-zscore
        rewrite - see loaders/helpers/factor_normalization.py's module docstring and
        loaders/helpers/vqg_quality_batch.py's `update_quality_sector_neutral_scores()`, the
        method this one is modeled on). After Quality's rewrite landed, `composite_score`'s
        leaderboard was still dominated by Financial Services (~60-66% of the top 50), and
        `growth_score` itself led every sector average for the exact reason Quality used to:
        `_score_single_growth` is an ABSOLUTE curve, identical across every sector, with no
        peer-group context - the same architectural gap this rewrite closes for Growth using the
        SAME shared primitive Quality already validated (`sector_neutral_zscore()`/
        `zscore_to_percentile_scale()`), not a bespoke re-derivation.

        MECHANISM: Pass 1 (`_score_growth`, per-symbol, no access to the universe distribution)
        still runs first via `_compute_stock_score` so growth_score/composite_score are never
        NULL mid-run - `_score_single_growth`'s absolute curve is now PROVISIONAL scaffolding
        this method always overwrites, the identical relationship Quality's Pass-1 curve
        (`_margin_curve` in vqg_quality.py) has to its own batch pass. This method runs after
        every symbol in this run has a growth_score, winsorizes+z-scores each of the 12
        GROWTH_SCORE_FIELDS candidates WITHIN each symbol's own GICS sector
        (`company_profile.sector`, via `sector_neutral_zscore`), maps each z-score onto [0,100]
        (`zscore_to_percentile_scale`), then re-applies the SAME equal-weighted blend / minimum-
        coverage floor / implausible-value exclusion `_score_growth` already used - only the
        per-field TRANSFORM changes (absolute curve -> sector-neutral z-score), not the field
        list, the weighting, or either guard. This is an explicit, non-negotiable user directive
        (see GROWTH_SCORE_FIELDS/_score_growth's own docstrings) - not re-litigated here.

        GROWTH_INPUT_IMPLAUSIBLE_PCT is still applied BEFORE the z-score (a raw value more than
        150% away from 0% is excluded from a field's z-score population entirely, same as Pass
        1's exclusion from the curve-blend) - `sector_neutral_zscore`'s own [1st,99th] percentile
        winsorization is a separate, milder safeguard against ordinary sector-distribution tails
        and does not substitute for excluding a value this codebase has already identified as a
        likely one-off (KARO's eps_growth_1y=1889%, DX's fcf_growth_yoy=739.5% - see that
        constant's own docstring for the full evidence).

        GROWTH_MIN_FIELDS_AVAILABLE is preserved exactly: a symbol with fewer than 5/12 fields
        available (after implausible-value exclusion) gets growth_score=None here (withheld,
        same "thin-sample extrapolation, not an honest partial score" principle as Pass 1's
        marker-dict return, adapted to this pass's "None is a valid overwrite" convention -
        see `update_value_multiples_percentiles()`'s VALUE_MIN_WEIGHT gate for the precedent).

        Composite_score is recomputed exactly as `update_value_multiples_percentiles()` recomputes
        it - from quality_score/value_score/risk_score/momentum_score as they currently stand
        (untouched by this pass) plus the new growth_score, via `_value_risk_adjusted_weights`.
        Runs AFTER `update_value_multiples_percentiles()` in `post_run()` specifically so this
        pass's own composite recompute sees Value's own already-finalized value_score, not its
        Pass-1 provisional one - see `post_run()`'s own "ORDER MATTERS" comment.

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        growth_score/composite_score is a live-trading-relevant correctness issue.
        """
        try:
            with _owner().DatabaseContext("write") as cur:
                cur.execute("""
                    SELECT ss.symbol, ss.growth_score, ss.composite_score, ss.quality_score,
                           ss.value_score, ss.risk_score, ss.momentum_score, ss.components,
                           ss.data_completeness, ss.data_unavailable,
                           gm.revenue_growth_1y, gm.eps_growth_1y, gm.revenue_growth_3y, gm.eps_growth_3y,
                           gm.revenue_growth_5y, gm.eps_growth_5y, gm.forward_eps_growth_current_fy,
                           gm.forward_eps_growth_next_fy, gm.forward_revenue_growth_next_fy,
                           gm.sustainable_growth_rate, gm.quarterly_growth_momentum, gm.earnings_growth_4q_avg,
                           cp.sector
                    FROM stock_scores ss
                    JOIN growth_metrics gm ON gm.symbol = ss.symbol
                    LEFT JOIN company_profile cp ON cp.symbol = ss.symbol
                    WHERE ss.growth_score IS NOT NULL
                      AND COALESCE(gm.data_unavailable, false) = false
                """)
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_growth_sector_neutral_scores: no eligible rows found "
                    "(growth_score IS NOT NULL joined to growth_metrics) - skipping, nothing to correct."
                )
                return

            # forward_eps_growth_current_fy/next_fy and forward_revenue_growth_next_fy are stored
            # as raw fractions in growth_metrics (0.18 = 18%), same as _get_growth_metrics's own
            # _scale_fraction_to_pct helper handles for Pass 1 - scale to percentage points here
            # too so they're on the same scale as every other GROWTH_SCORE_FIELDS candidate before
            # winsorization/z-scoring.
            fraction_fields = {
                "forward_eps_growth_current_fy",
                "forward_eps_growth_next_fy",
                "forward_revenue_growth_next_fy",
            }
            # Column index (within the 12-field slice starting at row[10]) for each
            # GROWTH_SCORE_FIELDS candidate, matching the SELECT's column order above exactly.
            field_col_offset = {field: 10 + i for i, field in enumerate(GROWTH_SCORE_FIELDS)}

            sector_map: dict[str, str] = {}
            for row in rows:
                sector = row[22]
                if sector is not None:
                    sector_map[row[0]] = sector

            raw_by_field: dict[str, dict[str, float]] = {field: {} for field in GROWTH_SCORE_FIELDS}
            for row in rows:
                symbol = row[0]
                for field in GROWTH_SCORE_FIELDS:
                    val = row[field_col_offset[field]]
                    if val is None:
                        continue
                    val_f = float(val) * 100 if field in fraction_fields else float(val)
                    if val_f > GROWTH_INPUT_IMPLAUSIBLE_PCT:
                        # See GROWTH_INPUT_IMPLAUSIBLE_PCT's own docstring - excluded from the
                        # z-score population entirely, not merely winsorized down to the 99th
                        # percentile, same as Pass 1's exclusion from the curve-blend.
                        continue
                    raw_by_field[field][symbol] = val_f

            pct_by_field: dict[str, dict[str, float]] = {
                field: zscore_to_percentile_scale(sector_neutral_zscore(values, sector_map))
                for field, values in raw_by_field.items()
            }
            logger.info(
                "[STOCK_SCORES] Growth sector-neutral z-score universe ("
                f"{len(sector_map)}/{len(rows)} symbols mapped to a GICS sector): "
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

                risk_score_float = float(risk_score) if risk_score is not None else None
                weights = _value_risk_adjusted_weights(risk_score_float)
                composite_val = 0.0
                for pillar_name, pillar_score in (
                    ("quality", quality_score),
                    ("growth", growth_score_new),
                    ("value", value_score),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
                ):
                    if pillar_score is not None:
                        composite_val += float(pillar_score) * weights[pillar_name]
                composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

                all_scores_new: dict[str, float | None] = {
                    "quality": float(quality_score) if quality_score is not None else None,
                    "growth": growth_score_new,
                    "value": float(value_score) if value_score is not None else None,
                    "risk": float(risk_score) if risk_score is not None else None,
                    "momentum": float(momentum_score) if momentum_score is not None else None,
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

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Growth sector-neutral z-score pass: no symbol's growth_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is a pure function of the raw stored ratios, same idempotency "
                    "property as update_value_multiples_percentiles())."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET growth_score = v.growth_score,
                        composite_score = v.composite_score,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness,
                        data_unavailable = v.data_unavailable,
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
