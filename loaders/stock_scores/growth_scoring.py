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

from loaders.helpers.factor_normalization import sector_neutral_zscore, zscore_to_percentile_scale
from loaders.helpers.vqg_shared import apply_mortgage_reit_sector_override
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
# be certain on the right methodology", "we don't want to veer far from what they do"). That
# version's own comment claimed "all 12 fields are independently verified canonical to a named
# MSCI/Russell/S&P/IBD Growth-factor component" - re-checked against MSCI's and Barra's actual
# published methodology documents this session (fetched and read directly, not recalled from
# memory) and this does not hold up:
#
#   - MSCI's real Growth style (MSCI Global Investable Market Value and Growth Index Methodology,
#     Feb 2021, msci.com/eqb/methodology/meth_docs/MSCI_GIMIVGMethod_Feb2021.pdf) uses exactly 5
#     descriptors: long-term forward EPS growth rate, short-term forward EPS growth rate, current
#     internal growth rate (g = ROE x retention rate), long-term historical EPS growth TREND,
#     long-term historical sales-per-share growth TREND. The historical TREND descriptors are an
#     OLS regression of the last 5 years' (DILUTED) EPS/SPS against time, annualized, divided by
#     the mean absolute level over that window - NOT a two-point CAGR. See
#     loaders/helpers/growth_trend.py for the full formula and its worked-example verification.
#   - INDEPENDENTLY CORROBORATED (different document, different company lineage - Barra was
#     acquired by MSCI in 2004, predates common authorship): the classic Barra US-E3 Risk Model
#     Handbook, Appendix A "Descriptor Definitions", Growth section, EGRO ("Earnings growth rate
#     over last five years") - "First, the following regression is run: EPS_t = a + b*t, ...
#     This regression is run for the period t=1,...,5. EGRO is computed as: EGRO = b /
#     average(EPS_t)" - the SAME OLS-regression-over-5-years-divided-by-average-level
#     construction, independently arrived at.
#   - NEITHER MSCI's nor Barra's Growth descriptors include a forecast REVENUE growth rate, a
#     quarterly/trailing-4Q earnings "momentum" metric, or three separate overlapping
#     point-in-time growth rates (1y/3y/5y) for the same underlying quantity.
#     forward_revenue_growth_next_fy, quarterly_growth_momentum, and earnings_growth_4q_avg are
#     not named components of either published methodology.
#   - Live-verified (this session, 5,164-row growth_metrics query, Spearman correlation) that the
#     1y/3y/5y windows this repo scored as 6 independent votes are real duplicates of each other,
#     not diversifying signal: revenue_growth_3y vs 5y r=0.66, revenue_growth_1y vs 3y r=0.54,
#     eps_growth_3y vs 5y r=0.54, eps_growth_1y vs 3y r=0.46.
#   - EPS COLUMN FIX (found mid-session, user: "we are using the wrong eps stuff though arent
#     we"): annual_income_statement.earnings_per_share (what the pre-existing eps_growth_1y/3y/5y
#     use) is BASIC EPS - loaders/helpers/financial_statements_income_config.py maps
#     "earnings_per_share_basic" -> earnings_per_share and "earnings_per_share_diluted" ->
#     diluted_eps, two genuinely separate, both-maintained columns. MSCI's/Barra's real formula
#     specifies DILUTED EPS (institutional-standard - accounts for options/RSU/convertible
#     dilution). eps_growth_trend_5y is built from diluted_eps, not the pre-existing basic-EPS
#     series - a real fix, not a stylistic choice (see test_growth_trend_uses_diluted_eps_not_
#     basic_20260916.py). The pre-existing eps_growth_1y/3y/5y fields keep using basic EPS
#     unchanged - fixing those is separate, higher-blast-radius work, out of scope here.
#
# NO SUBSTITUTE SHIPPED FOR DATA WE DON'T HAVE (user: "I don't like the guesses ... we need to
# only use what the industry does"): forward_eps_growth_next_fy (this DB's next-FY analyst
# consensus) was tried as a stand-in for MSCI's "long-term forward EPS growth rate" (a real 3-5yr
# consensus LTG estimate) and DROPPED rather than shipped as a wrong-horizon guess. Live-checked
# this session: yfinance's own `growth_estimates` property has a real "LTG" row, but it returned
# NaN for every symbol tried (MSFT/NVDA/KO/T/JPM) - Yahoo's free tier doesn't populate real
# per-stock long-term consensus growth. A PEG-ratio-derived implied growth rate was also
# investigated and REJECTED - multiple sources confirm PEG's growth-rate horizon is vendor-
# dependent and undocumented by Yahoo (could be next-year, 1-3yr, or 5yr), so it can't be
# verified as the real LTG descriptor either. No other analyst-estimate data source is
# integrated into this system - real LTG data would need a new paid vendor (Zacks/FactSet/IBES/
# Finnhub), a separate cost/access decision, not a gap closeable here.
#
# YOUNG-COMPANY COVERAGE (explicitly checked, not assumed - "I don't want anything where we're
# losing out on the good younger growth companies"): MSCI's own text is explicit that a security
# without >=4 years of EPS/SPS history simply has the historical-TREND descriptor marked missing,
# NOT the whole Growth score - "Growth trends for securities without sufficient EPS or SPS values
# are considered to be missing." A young high-growth company still scores on
# forward_eps_growth_current_fy (needs only current analyst coverage) and sustainable_growth_rate
# (needs only 1 year of ROE/payout data) - the same "score what's available, renormalize"
# treatment GROWTH_MIN_FIELDS_AVAILABLE already implements below. Live-checked coverage: ~88% of
# this universe has >=4 years of revenue history, so the historical-trend legs are genuinely
# missing (not fabricated from insufficient data) for roughly 12% of symbols - the same tradeoff
# a real institutional provider makes, not a gap unique to this implementation.
#
# RESULT: 12 fields -> 4, real methodology matches ONLY - no substitute for a descriptor this
# system can't actually compute:
#   - eps_growth_trend_5y -> "long-term historical EPS growth trend" (verified formula match,
#     diluted EPS)
#   - sps_growth_trend_5y -> "long-term historical sales-per-share growth trend" (verified
#     formula match; MSCI's descriptor is per-SHARE sales, not raw revenue - sps_growth_trend_5y
#     divides revenue by diluted shares outstanding per year, same per-share normalization
#     reasoning as EPS vs raw net income)
#   - forward_eps_growth_current_fy -> "short-term forward EPS growth rate" (real ~12-month-ahead
#     analyst consensus - a genuine horizon match, not a proxy across a different time horizon)
#   - sustainable_growth_rate -> "current internal growth rate" (ROE x retention rate is
#     literally that descriptor's textbook definition, not just a loose analogy - EXACT match,
#     verified against this repo's own sustainable_growth_rate computation in vqg_quality.py)
# revenue_growth_1y/3y/5y, eps_growth_1y/3y/5y, forward_eps_growth_next_fy,
# forward_revenue_growth_next_fy, quarterly_growth_momentum, earnings_growth_4q_avg are DEMOTED
# to informational-only: still computed/persisted in growth_metrics and still API-served, but
# REMOVED from GROWTH_SCHEMA entirely (StockScoreAccordion.jsx) rather than kept as used:false
# rows - this repo's own established "if we're not scoring it we don't want to display it"
# convention (already applied to every other pillar's *_SCHEMA, see
# TestUnscoredValueFieldsNotDisplayed/test_growth_schema_has_no_unscored_rows).
#
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
# Net result at the time (2026-08-31 through 2026-09-16): 12 fields, claimed canonical to a named
# MSCI/Russell/S&P/IBD Growth-factor component. SUPERSEDED 2026-09-16 - see
# GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE above: only 4 of these 12 survive verification against
# MSCI's and Barra's real published methodology, with no guessed substitute for the one
# descriptor this system can't actually compute. Equal-weighted (1/4 = 25% each now, not 1/12).
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

        # Equal-weighted blend, NOT sign-flipped (see docstring - explicit user override of
        # this file's own growth-reversal research). Cap of 30% reused across every signed-rate
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
        every symbol in this run has a growth_score, winsorizes+z-scores each of the 12
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
                           {growth_field_columns},
                           cp.sector, COALESCE(cis.is_foreign_private_issuer, false), vm.market_cap
                    FROM stock_scores ss
                    JOIN growth_metrics gm ON gm.symbol = ss.symbol
                    LEFT JOIN company_profile cp ON cp.symbol = ss.symbol
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
            field_col_offset = {field: 10 + i for i, field in enumerate(GROWTH_SCORE_FIELDS)}
            # sector/is_fpi immediately follow the GROWTH_SCORE_FIELDS columns - their index must
            # move with that constant's length, not a hardcoded 12-field assumption. market_cap
            # (the column after is_fpi) is still selected below for the liquidity-floor join but
            # no longer read into a Python dict here - size-neutralization was removed 2026-09-16
            # (see the pct_by_field comment below).
            _sector_idx = 10 + len(GROWTH_SCORE_FIELDS)
            _fpi_idx = _sector_idx + 1

            sector_map: dict[str, str] = {}
            for row in rows:
                sector = apply_mortgage_reit_sector_override(row[0], row[_sector_idx])
                if sector is not None:
                    sector_map[row[0]] = sector

            # FPI peer-group split (2026-09-14, goal-session "fix z-scoring issues" directive -
            # see sector_neutral_zscore's own docstring in factor_normalization.py).
            # COALESCE(cis.is_foreign_private_issuer, false) per this query's own SELECT above.
            is_fpi: dict[str, bool] = {row[0]: bool(row[_fpi_idx]) for row in rows if len(row) > _fpi_idx}

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
                    raw_by_field[field][symbol] = val_f

            # SIZE NEUTRALIZATION REMOVED 2026-09-16 (factor-purity sweep - this leftover was
            # justified purely by pointing at "same as Value's div/cash-yield legs, 2026-09-15",
            # but Value's own MSCI-formula rebuild the SAME SESSION already dropped that exact
            # step (see value_metrics.py's "DROPPED from the prior construction to match MSCI
            # exactly: ... Barra-style size-neutralization ... not part of MSCI's literal
            # published formula") and Quality's rebuild dropped it too - Growth was the last
            # pillar still citing a precedent that no longer exists. Plain sector-relative
            # z-scoring (sector_neutral_zscore) matches MSCI's real Growth-trend methodology
            # (this file's own top-of-file citation), which has no size-residualization step.
            pct_by_field: dict[str, dict[str, float]] = {
                field: zscore_to_percentile_scale(
                    sector_neutral_zscore(values, sector_map, is_foreign_private_issuer=is_fpi)
                )
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

                weights = BASE_PILLAR_WEIGHTS
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
