"""Constants and small pure functions shared between load_value_quality_growth_metrics.py
and its extracted compute mixins (vqg_value.py/vqg_quality.py/vqg_growth.py).

Lives in its own module with NO import of load_value_quality_growth_metrics (or anything
that imports it) specifically so any vqg_*.py mixin can import these at module level
without risking a circular import with the owner loader - see
vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory for the exact
circular-import crash this separation avoids (a prior extraction imported shared names
from the owner module itself, which broke the moment the owner was run as a script rather
than imported as a package).

load_value_quality_growth_metrics.py re-imports every name here under the same name, so
`loaders.load_value_quality_growth_metrics.X` still resolves for existing callers/tests.
"""

from datetime import datetime, timezone
from typing import Any

# Full timestamp, not just date - a date-only value casts to midnight and makes the
# freshness monitor see stale data for hours after the actual load time.
_LOADER_RUN_TIMESTAMP: str | None = None


def get_loader_timestamp() -> str:
    """Get the current run timestamp (ISO format with time component).

    Initialized on first call to capture when the loader run() started.
    All rows written in this run will have the same timestamp for consistency.
    """
    global _LOADER_RUN_TIMESTAMP
    if _LOADER_RUN_TIMESTAMP is None:
        _LOADER_RUN_TIMESTAMP = datetime.now(timezone.utc).isoformat()
    return _LOADER_RUN_TIMESTAMP


def peg_ratio_reason_from_eps_history(eps_rows: list[tuple[Any, Any]]) -> str:
    """Given the two most recent (fiscal_year, earnings_per_share) rows (newest first, both
    non-NULL EPS), decide why peg_ratio is unavailable when pe_ratio IS present.

    load_sec_valuations.py only computes peg_ratio when YoY EPS growth is positive (declining
    or newly-profitable earnings make PEG not meaningful, same "not applicable" class as
    unprofitable_stock/non_dividend_paying_stock elsewhere in this file) - distinguish that
    from a genuine <2-fiscal-years-on-file gap ("insufficient_history"), since scores.py's
    `_categorize_reason()` buckets them into different UI categories.

    Args:
        eps_rows: 0-2 (fiscal_year, earnings_per_share) tuples, already filtered to non-NULL
            EPS and ordered fiscal_year DESC (i.e. exactly what the caller's DB query returns).
    """
    if len(eps_rows) < 2:
        return "insufficient_history"
    ttm_eps_for_growth, prior_eps_for_growth = eps_rows[0][1], eps_rows[1][1]
    if prior_eps_for_growth is None or prior_eps_for_growth <= 0:
        return "negative_earnings_growth"
    if ttm_eps_for_growth is not None and ttm_eps_for_growth <= prior_eps_for_growth:
        return "negative_earnings_growth"
    return "missing_sec_data"


def intrinsic_value_reason_from_fcf_yield(fcf_yield: float | None, fcf_yield_reason: str | None = None) -> str:
    """Decide why intrinsic_value_per_share (the DCF result) is unavailable when it's NULL.

    fcf_yield being present does NOT imply FCF was positive (it only requires being within
    +/-1000% of market cap) - _compute_dcf_intrinsic_value's first gate is `fcf <= 0` (the
    2-stage FCFE model can't discount a cash-burning company), so fcf_yield <= 0 must map to
    "negative_free_cash_flow", not a generic "implausible_dcf_result".

    Args:
        fcf_yield: sec_valuations.fcf_yield for this symbol (same sign as the FCF that fed
            the DCF, since both derive from the same ocf - capex over the same positive
            market_cap).
        fcf_yield_reason: the already-computed fcf_yield_unavailable_reason for this symbol
            (e.g. "capex_never_tagged_in_recent_filings", "no_recent_free_cash_flow_reported")
            when fcf_yield is None - propagate this specific reason instead of collapsing to
            the generic "missing_cash_flow_data" label; that label is only a fallback when no
            specific reason is available (e.g. direct callers/tests).
    """
    if fcf_yield is None:
        return fcf_yield_reason or "missing_cash_flow_data"
    if fcf_yield <= 0:
        return "negative_free_cash_flow"
    return "implausible_dcf_result"


# Sanity bound for the 4 percentage-point-delta trend fields (gross/operating/net margin
# trend, ROE trend), stored in NUMERIC(10,4) columns. A near-zero prior-year denominator
# (equity/revenue crossing from negative to barely-positive) makes the delta mathematically
# enormous despite being a real computation - treat as unavailable rather than let it
# overflow the column and roll back the entire 3-table write for that symbol.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# Plausibility bound for growth-RATE fields (distinct from the margin/ROE trend fields
# above, which are percentage-POINT deltas bounded by the 0-100% margin range and stay on
# MAX_TREND_PERCENTAGE_POINTS). A near-zero prior-period denominator can produce
# mathematically enormous but meaningless growth rates; genuine hypergrowth small-caps can
# hit a few hundred percent but essentially never four or five digits.
MAX_PLAUSIBLE_GROWTH_PCT = 2_000.0

# Sanity bound for absolute-dollar fields (free_cash_flow, operating_cash_flow, total_debt,
# total_cash, ebitda), stored in NUMERIC(15,2) columns (max abs value < 10^13). Foreign
# filers reporting in local currency (e.g. VND/KRW) can overflow this column if a value
# isn't converted to USD before reaching this file, which would abort the entire 3-table
# write transaction for that symbol - mark implausible values unavailable instead of
# crashing on them, as a safety net independent of any particular currency-conversion bug.
MAX_ABSOLUTE_DOLLAR_VALUE = 1_000_000_000_000.0  # $1 trillion - no real company in this universe exceeds this for any single one of these fields

# Computed once in _compute_quality_metrics (needs balance-sheet data _compute_growth_metrics
# doesn't have), then mirrored into growth_dict in fetch_incremental - see that call site for
# why quality_metrics and growth_metrics each carry their own copy of the same values.
# These are computed from quarterly data in _compute_quarterly_metrics() (which is called
# from _compute_quality_metrics), and must be propagated to growth_metrics via this list
# to avoid dropping quarterly-derived metrics that growth_metrics doesn't compute on its own.
_SHARED_TREND_FIELDS = (
    "net_income_growth_yoy",
    "operating_income_growth_yoy",
    "gross_margin_trend",
    "operating_margin_trend",
    "net_margin_trend",
    "roe_trend",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy",
    "consecutive_positive_quarters",
    "earnings_growth_4q_avg",
    "eps_growth_stability",
    "earnings_surprise_avg",
    "earnings_beat_rate",
)
