"""Cumulative-YTD-to-discrete-quarter derivation, extracted from _aggregate_concepts
(sec_statements_aggregate.py) to keep that function under the complexity/size ratchets - body
is new logic added 2026-09-13, not a mechanical move.

FIXED 2026-09-13 (goal: keep finding data-quality issues, RITM live-confirmed - see memory
quarterly_cashflow_cumulative_ytd_stored_as_discrete_20260913 for the full investigation):
for concepts that never get a genuine ~90-day discrete-quarter fact filed at all (common for
non-headline cash-flow-statement line items - stock_based_compensation/capex/
common_stock_repurchased/financing_cash_flow/investing_cash_flow/dividends_paid, less
common for revenue/net_income, which almost always DO get a real discrete fact),
`_aggregate_concepts_resolve_entry_period`/`_aggregate_concepts_should_replace_entry` already
correctly prefer a genuine discrete fact over a same-fiscal-year cumulative echo WHEN BOTH
EXIST for a quarter - but when no discrete fact exists at all, the lone cumulative fact was
previously stored as-is under Q2/Q3, silently inflating those quarters to the year-to-date
total instead of the true discrete amount. Live-confirmed via RITM's real SEC companyfacts
JSON (CIK 0001556593): AllocatedShareBasedCompensationExpense's 2018 Q2 fact is
start=2018-01-01/end=2018-06-30/val=1,019,000 and its Q3 fact is start=2018-01-01/
end=2018-09-30/val=1,019,000 - both raw YTD-cumulative, no discrete fact ever filed for
either quarter. Downstream Q4 derivation (FY_total - stored Q1+Q2+Q3, see
loaders/helpers/financial_statements_q4_sweeps.py) then massively over-subtracts the
cumulative overlap, corrupting Q4 too - this fix makes that sweep's input correct instead of
patching its output.

Q1 needs no correction: a fiscal year's Q1 cumulative fact and its true discrete value are the
same fact (both start at the fiscal-year start), so Q1's own span always looks like a genuine
single quarter already, whether or not a distinct discrete fact was ever filed.
"""

from typing import Any

_META_ROW_KEYS = frozenset({"symbol", "fiscal_year", "fiscal_period", "period_end", "filed", "form"})

# A genuine discrete quarter's own start-to-end span is ~89-92 days (see the 80-100 day window
# _aggregate_concepts_resolve_entry_period/_aggregate_concepts_should_replace_entry already
# trust for the same distinction elsewhere in this file's sibling module). A same-fiscal-year
# cumulative echo is unambiguously longer - ~181-191 days for H1 (Q2 bucket), ~272-282 days for
# 9mo (Q3 bucket) - so a wide margin above the real-quarter ceiling cleanly separates the two
# without risking a false hit on a merely slightly-long real quarter (e.g. a 92-day Q2).
_CUMULATIVE_SPAN_THRESHOLD_DAYS = 130


def apply_cumulative_quarter_derivation(rows: dict[Any, dict[str, Any]], period: str) -> None:
    """Convert a lone cumulative-YTD fact stored under Q2/Q3 into its true discrete value.

    Extracted as its own entry point (rather than inlining the loop in _aggregate_concepts)
    purely to keep that function's own cyclomatic complexity under the repo's ruff C901
    ratchet - same rationale as apply_fy_stub_period_guard. No-op for `period == "annual"`
    (annual rows carry no `_span_` bookkeeping at all - see
    _aggregate_concepts_apply_entry_value) and for any (fiscal_year, column) pair whose Q2/Q3
    value already came from a genuine discrete fact (span within the real-quarter window), so
    this can only ever correct an already-wrong cumulative value, never touch a right one.
    """
    if period != "quarterly":
        return
    fiscal_years = {key[0] for key in rows}
    for fiscal_year in fiscal_years:
        row_q1 = rows.get((fiscal_year, "Q1"))
        row_q2 = rows.get((fiscal_year, "Q2"))
        row_q3 = rows.get((fiscal_year, "Q3"))
        if row_q2 is None and row_q3 is None:
            continue
        # Snapshot Q2's raw (possibly still-cumulative) values before any correction below -
        # Q3's derivation needs the RAW cumulative Q2 value to subtract, not Q2's own
        # already-corrected discrete value, or the arithmetic double-subtracts Q1's overlap.
        raw_q2_values = {k: v for k, v in (row_q2 or {}).items() if not k.startswith("_") and k not in _META_ROW_KEYS}

        if row_q1 is not None and row_q2 is not None:
            _derive_discrete_quarter(row_q2, row_q1)
        if row_q3 is not None and raw_q2_values:
            _derive_discrete_quarter(row_q3, raw_q2_values)


def _derive_discrete_quarter(quarter_row: dict[str, Any], prior_cumulative_values: dict[str, Any]) -> None:
    """Subtract the prior quarter's cumulative value from each cumulative-shaped column."""
    for col in list(quarter_row.keys()):
        if col.startswith("_") or col in _META_ROW_KEYS:
            continue
        span = quarter_row.get(f"_span_{col}")
        if span is None or span <= _CUMULATIVE_SPAN_THRESHOLD_DAYS:
            continue
        prior_val = prior_cumulative_values.get(col)
        entry_val = quarter_row.get(col)
        if isinstance(prior_val, int | float) and isinstance(entry_val, int | float):
            quarter_row[col] = entry_val - prior_val
