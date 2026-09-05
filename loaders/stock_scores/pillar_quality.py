"""Quality pillar: `_get_quality_metrics`/`_score_quality`, extracted verbatim (no logic
change) from loaders/load_stock_scores.py. StockScoresLoader keeps same-name, same-signature
instance methods that delegate here.
"""

import logging
from typing import Any

from utils.loaders.unavailable_markers import marker_loader_failed, marker_not_applicable
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


def _get_quality_metrics(quality_cache: dict[str, tuple[Any, ...]], symbol: str) -> dict[str, Any]:
    """Fetch quality metrics for symbol including Phase 3 expansion metrics.

    Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
    Raises RuntimeError on database errors or data type mismatches.

    VALIDATION RULES:
    - Row length validation: Must have 24 columns (10 base + 14 Phase 3 expansion)
    - Schema mismatch (len(row) < 24) → raises ValueError immediately
    - All numeric fields converted via safe_float() (detects data corruption)
    - data_unavailable=True flag → returns marker dict even if row exists
    - No row at all → returns marker dict with reason="no_quality_metrics_found"

    Fetches Phase 3 expansion fields (gross_margin, ebitda_margin, roic_pct,
    fcf_to_net_income, ocf_to_net_income, payout_ratio, free_cash_flow, operating_cash_flow,
    total_debt, total_cash, cash_per_share, ebitda, earnings_growth_yoy, revenue_growth_yoy,
    interest_coverage) - of these, only payout_ratio and interest_coverage are actually
    weighted inputs in `_score_quality`'s composite; the rest are reference/display only or
    were tested and excluded for no independent signal.

    MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes immediate
    fail-fast ValueError to prevent silent data corruption.
    """
    row = quality_cache.get(symbol)
    if row:
        # CRITICAL: Validate row has expected 25 columns before accessing indices
        # (10 original + 14 Phase 3 expansion + 1 interest_coverage + 1 data_unavailable flag = 26 total, minus symbol = 25)
        if len(row) < 25:
            raise ValueError(
                f"[STOCK_SCORES] {symbol}: quality_metrics row has {len(row)} columns, expected 25. "
                f"Schema mismatch detected - Phase 3 or interest_coverage fields missing. Failing fast."
            )
        data_unavailable = row[9]
        quality_score = safe_float(row[8], f"{symbol}.quality_score")
        # If marked unavailable, return marker even if row exists
        if data_unavailable:
            logger.debug(
                f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in quality_metrics "
                f"(likely REIT or security with missing SEC filings)"
            )
            return marker_not_applicable(symbol, "quality_metrics")
        # Row exists and data is available - return all fields including Phase 3 expansion
        return {
            "roe": safe_float(row[0], f"{symbol}.roe"),
            "roa": safe_float(row[1], f"{symbol}.roa"),
            "operating_margin": safe_float(row[2], f"{symbol}.operating_margin"),
            "net_margin": safe_float(row[3], f"{symbol}.net_margin"),
            "debt_to_equity": safe_float(row[4], f"{symbol}.debt_to_equity"),
            "current_ratio": safe_float(row[5], f"{symbol}.current_ratio"),
            "quick_ratio": safe_float(row[6], f"{symbol}.quick_ratio"),
            "debt_to_assets": safe_float(row[7], f"{symbol}.debt_to_assets", allow_none=True),
            "quality_score": quality_score,  # Pre-computed by load_value_quality_growth_metrics.py
            # Phase 3 expansion metrics (Session 358+)
            "gross_margin": safe_float(row[10], f"{symbol}.gross_margin", allow_none=True),
            "ebitda_margin": safe_float(row[11], f"{symbol}.ebitda_margin", allow_none=True),
            "roic_pct": safe_float(row[12], f"{symbol}.roic_pct", allow_none=True),
            "fcf_to_net_income": safe_float(row[13], f"{symbol}.fcf_to_net_income", allow_none=True),
            "ocf_to_net_income": safe_float(row[14], f"{symbol}.ocf_to_net_income", allow_none=True),
            "payout_ratio": safe_float(row[15], f"{symbol}.payout_ratio", allow_none=True),
            "free_cash_flow": safe_float(row[16], f"{symbol}.free_cash_flow", allow_none=True),
            "operating_cash_flow": safe_float(row[17], f"{symbol}.operating_cash_flow", allow_none=True),
            "total_debt": safe_float(row[18], f"{symbol}.total_debt", allow_none=True),
            "total_cash": safe_float(row[19], f"{symbol}.total_cash", allow_none=True),
            "cash_per_share": safe_float(row[20], f"{symbol}.cash_per_share", allow_none=True),
            "ebitda": safe_float(row[21], f"{symbol}.ebitda", allow_none=True),
            "earnings_growth_yoy": safe_float(row[22], f"{symbol}.earnings_growth_yoy", allow_none=True),
            "revenue_growth_yoy": safe_float(row[23], f"{symbol}.revenue_growth_yoy", allow_none=True),
            "interest_coverage": safe_float(row[24], f"{symbol}.interest_coverage", allow_none=True),
        }
    # No row exists at all
    logger.warning(
        f"[LOAD_STOCK_SCORES] No quality metrics available for {symbol} - score completeness will be reduced"
    )
    return marker_loader_failed(symbol, "no_quality_metrics", "Quality metrics table missing data")


def _score_quality(metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
    """Score quality metrics on 0-100 scale.

    CRITICAL: Uses only pre-computed quality_score (official model consensus). No fallback
    computation - if pre-computed score missing, returns explicit data_unavailable marker.
    For financial accuracy, missing scores are better than fabricated heuristics.

    The upstream quality_score (load_value_quality_growth_metrics.py) is an 8-weighted-
    component blend, no clusters: ROA 18%, ROCE 18% (not ROIC - avoids ROIC's cash-netting
    coverage gap), Debt-to-Equity 18% (not Debt-to-Assets - tests stronger), FCF Margin 15%
    (not Accruals Ratio - independent signal), ROE 11%, Margin Volatility (3Y)/Asset
    Turnover/Gross Profitability ~7% each - renormalized over whichever are available for a
    given symbol, with a 40-point minimum-available-weight floor out of a 101-point nominal
    total (below that, quality_score is None rather than a thin-sample extrapolation - see
    load_value_quality_growth_metrics.py's quality_components comment).

    Interest Coverage, Payout Ratio, Current Ratio, and Operating/Net Margin Trend & ROE
    Trend were tested and excluded - no significant cross-sectional signal. Altman
    Z''-Score was tried and dropped: the literature frames it as a discrete distress-triage
    classifier, not a continuously-scaled input for a magnitude-weighted composite.
    Margin/ROE trend fields are still computed/persisted (quality_metrics table) for
    reference, just not scored.

    This replaced the old "_enhance_quality_score" ±10-point bump layer entirely - one
    formula in one place instead of splitting the signal across two files/functions.
    _score_financial_stability/_score_dte removed as dead code (no other callers).
    """
    if not metrics or metrics.get("data_unavailable"):
        logger.warning(f"[STOCK_SCORES] Quality metrics unavailable for {symbol}")
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_metrics_data"}

    # CRITICAL: Require pre-computed quality_score. Do NOT fall back to dynamic computation -
    # that creates fabricated scores from heuristics. Missing quality_score indicates an
    # upstream issue (Phase 3 didn't run or metrics incomplete).
    if metrics.get("quality_score") is not None:
        quality_score_value = safe_float(metrics["quality_score"], f"{symbol}.quality_score")
        if quality_score_value is not None:
            logger.debug(f"[STOCK_SCORES] Using pre-computed quality_score for {symbol}: {quality_score_value}")
            return quality_score_value

    # FAIL-FAST: No pre-computed score and no fallback. This is explicit data unavailability.
    logger.warning(
        f"[STOCK_SCORES] Quality score unavailable for {symbol}. "
        f"Pre-computed quality_score missing - Phase 3 may not have completed or metrics incomplete. "
        f"Returning data_unavailable marker instead of fabricated heuristic score."
    )
    return {"symbol": symbol, "data_unavailable": True, "reason": "quality_score_unavailable"}
