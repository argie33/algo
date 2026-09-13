"""Cross-concept period-consistency guard for synthesized FY rows, extracted from
_aggregate_concepts (sec_statements_aggregate.py) to keep that function under the
complexity/size ratchets - body is new logic added 2026-09-13, not a mechanical move.

FIXED 2026-09-13 (goal: XBRL data-integrity audit, PROK live-confirmed via peer session's
redeemable_nci_temp_equity_fix_and_fy_period_mismatch_found_20260913): an annual ("FY") row
not anchored to a real 10-K/20-F/40-F (i.e. synthesized from whichever 10-Q instant snapshot
happened to be latest available per concept, the has_annual_report_form==False fallback path
in _aggregate_concepts_build_unit_context) can end up with different instant-fact columns
sourced from DIFFERENT 10-Q period end-dates - e.g. PROK's stockholders_equity taken from its
Q1-2026 10-Q while total_assets/total_liabilities in the SAME nominal fiscal_year=2026 row
came from its Q2-2026 10-Q, even though the company was never in that combined state at any
single point in time. Each per-concept "latest available" tiebreak upstream is correct in
isolation; nothing previously checked that a synthesized FY row's instant facts actually agree
with each other on WHEN they were measured.
"""

from typing import Any

from utils.external.sec_statements_shared import _ANNUAL_REPORT_FORMS


def apply_fy_stub_period_guard(rows: dict[Any, dict[str, Any]], period: str, symbol: str, logger: Any) -> None:
    """Run `_drop_period_mismatched_instant_columns` over every row when `period == "annual"`.

    Extracted as its own entry point (rather than inlining the `if`/`for` in
    _aggregate_concepts) purely to keep that function's own cyclomatic complexity under
    the repo's ruff C901 ratchet - no behavior difference from inlining it.
    """
    if period != "annual":
        return
    for row in rows.values():
        _drop_period_mismatched_instant_columns(row, symbol, logger)


def _drop_period_mismatched_instant_columns(row: dict[str, Any], symbol: str, logger: Any) -> None:
    """Null out minority-period instant-fact columns on a non-10-K-anchored FY row.

    Detect via the `_end_{col}`/`_is_instant_{col}` bookkeeping
    _aggregate_concepts_apply_entry_value already tracks: if such a row's instant-fact
    columns disagree on end date, keep only the columns sharing the MAJORITY end date and
    null the minority ones - never guess which value is "right", just refuse to let
    mismatched-period facts silently coexist in one row. A row anchored to a real
    annual-report form is by construction one filing's own statement and is never
    touched here.
    """
    if row.get("fiscal_period") != "FY" or row.get("form") in _ANNUAL_REPORT_FORMS:
        return
    end_by_col = {
        key[len("_end_") :]: val
        for key, val in row.items()
        if key.startswith("_end_") and val and row.get(f"_is_instant_{key[len('_end_') :]}")
    }
    if len({*end_by_col.values()}) <= 1:
        return
    counts: dict[Any, int] = {}
    for end in end_by_col.values():
        counts[end] = counts.get(end, 0) + 1
    majority_end = max(counts.items(), key=lambda kv: kv[1])[0]
    dropped = [col for col, end in end_by_col.items() if end != majority_end]
    for col in dropped:
        row[col] = None
    logger.warning(
        "[_aggregate_concepts] %s FY%s: dropped instant-fact column(s) %s - period-end "
        "mismatch within one synthesized (non-10-K) annual row (end dates: %s)",
        symbol,
        row.get("fiscal_year"),
        dropped,
        dict(counts),
    )
