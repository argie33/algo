"""Regression test (goal session 2026-09-06, SEC/XBRL missing-data campaign) for six of
vqg_symbol_gates.py's "never tagged" full-history gates that counted a disclaimed row's stray
non-NULL value as if it were a real, tagged one.

Each `_get_never_tagged_*_symbols()` gate answers "does this symbol have at least one real
fiscal-year row, none of which ever carry a real value for this field" - used to label a symbol's
missing metric as a specific, structural "field never reported" reason instead of the generic
"missing_sec_data" bucket. Its sibling gates (interest_expense, debt_components, revenue,
operating_income, cash, free_cash_flow, pretax_income) all already guard the COUNT/FILTER
expression against data_unavailable=TRUE rows (either via a CASE WHEN that nulls the value first,
or an explicit `data_unavailable IS NOT TRUE` inside the FILTER clause) - six gates
(total_assets, current_assets, current_liabilities, net_income, total_liabilities,
stockholders_equity) did not, so a data_unavailable=TRUE row carrying a leftover stray non-NULL
value (the same bug class fixed across the rest of this cascade, see
sec_xbrl_anchor_query_disclaimed_row_wrong_values_fixed_20260905 in MEMORY.md) would make
COUNT(field) (or the FILTER's WHERE) count it as present, so the gate wrongly concluded "this
symbol reports the field" and the specific reason label was lost - falling back to the generic
"missing_sec_data" bucket instead. This is the opposite direction from the
2026-09-05 all-unavailable-history fix (test_never_tagged_gates_all_unavailable_history_20260905.py):
that one fixed a false EXCLUSION at the WHERE level; this fixes a false INCLUSION at the
COUNT/FILTER level.

A mocked cursor can't exercise real Postgres WHERE/HAVING evaluation, so - matching the sibling
tests' approach - this asserts the query text itself guards against data_unavailable, guarding
against a future edit reverting it.
"""

import re
from pathlib import Path

_SOURCE = Path("loaders/helpers/vqg_symbol_gates.py").read_text(encoding="utf-8")

FIXED_GATE_NAMES = [
    "_get_never_tagged_total_assets_symbols",
    "_get_never_tagged_current_assets_symbols",
    "_get_never_tagged_current_liabilities_symbols",
    "_get_never_tagged_net_income_symbols",
    "_get_never_tagged_total_liabilities_symbols",
    "_get_never_tagged_stockholders_equity_symbols",
]


def _function_source(name: str) -> str:
    match = re.search(rf"    def {re.escape(name)}\(self\).*?(?=\n    @_cached_symbols|\n    def |\Z)", _SOURCE, re.S)
    assert match is not None, f"could not locate {name} in vqg_symbol_gates.py"
    return match.group(0)


class TestNeverTaggedGatesExcludeDisclaimedRowStrayValues:
    def test_all_six_gates_guard_their_count_against_data_unavailable_rows(self) -> None:
        for name in FIXED_GATE_NAMES:
            source = _function_source(name)
            assert "data_unavailable" in source, (
                f"{name}'s COUNT/FILTER no longer references data_unavailable at all - a "
                "disclaimed row's stray non-NULL value would be counted as real, tagged data "
                "again, same bug class as the sibling gates already guard against."
            )
