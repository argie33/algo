"""Growth pillar: `_get_growth_metrics`/`_score_growth`, extracted verbatim (no logic change)
from loaders/load_stock_scores.py. StockScoresLoader keeps same-name, same-signature instance
methods that delegate here, passing GROWTH_SCORE_FIELDS/GROWTH_INPUT_IMPLAUSIBLE_PCT/
GROWTH_MIN_FIELDS_AVAILABLE through explicitly (those module constants stay defined in
load_stock_scores.py - several other modules/tests import them directly from there, e.g.
"from loaders.load_stock_scores import GROWTH_SCORE_FIELDS" - so they aren't moved here, to
avoid a circular import and to keep that external import path unchanged).
"""

import itertools
import logging
from typing import Any

from utils.loaders.unavailable_markers import marker_loader_failed
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


def _get_growth_metrics(growth_cache: dict[str, tuple[Any, ...]], symbol: str) -> dict[str, Any]:
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

    Checks the data_unavailable flag: some securities have rows marked data_unavailable=True
    with NULL values, which must return a marker rather than NULLs.

    MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes
    immediate fail-fast ValueError. Dependent on upstream annual_income_statement availability.
    """
    row = growth_cache.get(symbol)
    if row:
        # CRITICAL: Validate row has expected 25 columns before accessing indices
        # (21 + forward_eps_growth_current_fy/next_fy + forward_revenue_growth_next_fy +
        # eps_estimate_revision_90d_pct, added 2026-08-31)
        if len(row) < 25:
            raise ValueError(
                f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 25. "
                f"Schema mismatch detected - cannot safely access data. Failing fast."
            )
        # Deliberately does NOT discard the whole row via marker_not_applicable just because
        # data_unavailable=True - some rows have that flag set but still carry real,
        # non-NULL values in individual fields (e.g. quarterly_growth_momentum,
        # earnings_growth_4q_avg), and _score_growth's multi-field blend is already designed
        # to renormalize over whichever fields are actually present. A fully-empty row still
        # falls through safely to _score_growth's own "no_growth_inputs_available" marker.

        def _scale_fraction_to_pct(val: float | None) -> float | None:
            """forward_eps_growth_current_fy/next_fy and forward_revenue_growth_next_fy are
            stored as raw fractions (0.18 = 18%), unlike every other GROWTH_SCORE_FIELDS
            candidate which is already percentage-point scaled - _score_single_growth's
            cap=30 curve is calibrated for percentage-point inputs.
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
            "operating_income_growth_yoy": safe_float(row[8], f"{symbol}.operating_income_growth_yoy", allow_none=True),
            "sustainable_growth_rate": safe_float(row[9], f"{symbol}.sustainable_growth_rate", allow_none=True),
            "fcf_growth_yoy": safe_float(row[10], f"{symbol}.fcf_growth_yoy", allow_none=True),
            "ocf_growth_yoy": safe_float(row[11], f"{symbol}.ocf_growth_yoy", allow_none=True),
            "gross_margin_trend": safe_float(row[12], f"{symbol}.gross_margin_trend", allow_none=True),
            "operating_margin_trend": safe_float(row[13], f"{symbol}.operating_margin_trend", allow_none=True),
            "net_margin_trend": safe_float(row[14], f"{symbol}.net_margin_trend", allow_none=True),
            "roe_trend": safe_float(row[15], f"{symbol}.roe_trend", allow_none=True),
            "asset_growth_yoy": safe_float(row[16], f"{symbol}.asset_growth_yoy", allow_none=True),
            "eps_growth_stability": safe_float(row[17], f"{symbol}.eps_growth_stability", allow_none=True),
            "quarterly_growth_momentum": safe_float(row[18], f"{symbol}.quarterly_growth_momentum", allow_none=True),
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
    logger.warning(f"[LOAD_STOCK_SCORES] No growth metrics available for {symbol} - score completeness will be reduced")
    return marker_loader_failed(symbol, "no_growth_metrics", "Growth metrics table missing data")


def _score_growth(
    metrics: dict[str, Any] | None,
    symbol: str,
    growth_score_fields: tuple[str, ...],
    growth_input_implausible_pct: float,
    growth_min_fields_available: int,
) -> float | dict[str, Any]:
    """Score growth metrics on 0-100 scale via a multi-input blend. Returns marker dict if
    no real data.

    Scores every growth field the frontend's Growth tab displays (GROWTH_SCHEMA in
    StockScoreAccordion.jsx / GROWTH_SCORE_FIELDS, passed in as `growth_score_fields`): equal-
    weighted average of whichever candidates are non-null for this symbol (partial-
    availability renormalization - the same "score what's available, drop what's missing"
    pattern _score_quality/_score_stability use elsewhere in this file). NOT sign-flipped -
    plain "higher growth = higher score" per explicit user direction, overriding this
    file's own prior growth-reversal research (Cooper/Gulen/Schill 2008) for every
    candidate.

    quarterly_growth_momentum/earnings_growth_4q_avg are computed by
    _compute_quarterly_metrics in load_value_quality_growth_metrics.py and mirrored onto
    BOTH growth_metrics and quality_metrics - _get_growth_metrics reads growth_metrics's
    own copy, so `metrics` already carries both by the time this method sees it.

    forward_eps_growth_current_fy/next_fy and forward_revenue_growth_next_fy arrive from
    _get_growth_metrics already converted from their raw-fraction DB storage to the same
    percentage-point scale every other candidate uses (_scale_fraction_to_pct) -
    _score_single_growth's cap=30 curve would otherwise silently collapse them toward the
    0%-growth midpoint.

    Margin/ROE trend fields (operating_margin_trend/net_margin_trend/roe_trend) are scored
    under Quality, not Growth, and are NOT in GROWTH_SCORE_FIELDS.

    eps_growth_stability and fcf_growth_yoy are deliberately excluded from
    GROWTH_SCORE_FIELDS (see that constant's own docstring for rationale);
    _score_eps_growth_stability below is kept but unused by this method.

    RETURN TYPES (STRICT):
    - >=growth_min_fields_available of growth_score_fields available → returns float (0-100)
    - metrics marked data_unavailable=True → returns marker dict (never None)
    - metrics is None or missing → returns marker dict (never None)
    - 1..growth_min_fields_available-1 candidates available → returns marker dict with
      reason="insufficient_growth_inputs_thin_sample" (a 1-2 field renormalization is
      thin-sample extrapolation, not an honest partial score - same principle Quality
      applies to quality_score)
    - every growth_score_fields candidate is None → returns marker dict with
      reason="no_growth_inputs_available"

    ERROR HANDLING:
    - Type conversion errors → RuntimeError (via _safe_float, in _get_growth_metrics)
    - Negative growth rates → valid scores (negative growth maps to 0-40 scale, positive to
      40-100, both continuous through 0 - see _score_single_growth)

    Internal function: caller (_compute_stock_score) explicitly handles marker dicts
    and uses them for growth metric computation.

    MINIMUM DATA REQUIREMENT: at least growth_min_fields_available of growth_score_fields
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
            # Negative growth: map [-50, 0] → [0, 40]. Use float literals (0.0/100.0), not
            # int - is_real_score() downstream does isinstance(result, float), and
            # max(0, ...)/min(100, ...) with int literals return a plain int once the value
            # saturates past the boundary, silently failing that check.
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

    # Equal-weighted blend, NOT sign-flipped (see docstring). Cap of 30% reused across every
    # signed-rate candidate - all share the same _cagr()/YoY-%-derived percentage-point
    # scale (domain judgment, not separately fit per field). No dispersion-metric candidate
    # is scored here; _score_eps_growth_stability is kept but unused (see docstring).
    component_scores = []
    for field in growth_score_fields:
        raw = metrics.get(field)
        if raw is not None and raw > growth_input_implausible_pct:
            # See GROWTH_INPUT_IMPLAUSIBLE_PCT's docstring: exclude rather than score at a
            # saturated 100 - an implausibly extreme rate isn't comparable "growth quality"
            # to a genuine strong grower even though both would otherwise map identically.
            continue
        score = _score_single_growth(raw, 30)
        if score is not None:
            component_scores.append(score)

    if len(component_scores) >= growth_min_fields_available:
        growth_score = sum(component_scores) / len(component_scores)
        logger.debug(
            f"[STOCK_SCORES] {symbol} growth_score computed: {growth_score:.2f} "
            f"({len(component_scores)}/{len(growth_score_fields)} inputs available)"
        )
        return growth_score

    if component_scores:
        logger.info(
            f"[STOCK_SCORES] {symbol} growth_score withheld: only {len(component_scores)}/"
            f"{len(growth_score_fields)} inputs available, below GROWTH_MIN_FIELDS_AVAILABLE="
            f"{growth_min_fields_available}. See that constant's docstring - a 1-2 field "
            f"renormalization is thin-sample extrapolation, not an honest partial score."
        )
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "insufficient_growth_inputs_thin_sample",
        }

    logger.warning(
        f"[STOCK_SCORES] {symbol} growth_score computation FAILED: all {len(growth_score_fields)} "
        f"growth candidates are None. ROOT CAUSE: growth_metrics row exists but no growth "
        f"field could be computed for this symbol."
    )
    return {"symbol": symbol, "data_unavailable": True, "reason": "no_growth_inputs_available"}
