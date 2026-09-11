"""Regression test (2026-09-11, goal: "under 300" push): the full-history "never tagged debt"
gates in vqg_symbol_gates.py used `COUNT(long_term_debt) = 0` to mean "no borrowed debt ever
reported" - but COUNT counts non-null rows regardless of value, so a symbol that explicitly
reports a confirmed real 0 (e.g. CMG's long_term_debt = 0 every fiscal year since FY2019,
alongside a real, large operating_lease_liability) failed the "=0" bar exactly like a symbol
with a real nonzero balance would, and fell through to the generic "interest_expense_not_itemized"
("Missing SEC/XBRL data") label instead of the correct "no_debt_no_interest_expense"
("Legitimate / not applicable") one.

Live-confirmed via CMG's real annual_balance_sheet history and companyfacts JSON: no
InterestExpense* concept anywhere in CMG's filings (Chipotle carries no borrowed debt, only
lease liabilities) - this is a real "not applicable" fact, not a loader gap.

Fixed by switching to `COALESCE(MAX(...), 0) = 0`, which treats "never reported" and "always
reported as exactly zero" as the same "no debt" fact, while a symbol with a real nonzero value
in ANY fiscal year (e.g. DNUT: 0 -> $739M -> $911M) still correctly fails the gate.
"""

import re
from pathlib import Path

_SOURCE = Path("loaders/helpers/vqg_symbol_gates.py").read_text(encoding="utf-8")

GATE_NAMES = [
    "_get_never_tagged_debt_components_symbols",
    "_get_never_tagged_borrowed_debt_symbols",
]


def _function_source(name: str) -> str:
    match = re.search(rf"    def {re.escape(name)}\(self\).*?(?=\n    @_cached_symbols|\n    def |\Z)", _SOURCE, re.S)
    assert match is not None, f"could not locate {name} in vqg_symbol_gates.py"
    return match.group(0)


class TestNeverTaggedDebtGatesUseMaxNotCount:
    def test_debt_component_gates_treat_confirmed_zero_as_no_debt(self):
        for name in GATE_NAMES:
            src = _function_source(name)
            assert "COALESCE(MAX(CASE WHEN data_unavailable THEN NULL ELSE long_term_debt END), 0) = 0" in src, (
                f"{name} must use MAX(...)=0 (not COUNT(...)=0) for long_term_debt so a "
                "confirmed real zero counts as 'no debt', same as never being tagged at all"
            )
            assert "COALESCE(MAX(CASE WHEN data_unavailable THEN NULL ELSE short_term_debt END), 0) = 0" in src, (
                f"{name} must use MAX(...)=0 (not COUNT(...)=0) for short_term_debt"
            )
            assert "COUNT(CASE WHEN data_unavailable THEN NULL ELSE long_term_debt END) = 0" not in src
            assert "COUNT(CASE WHEN data_unavailable THEN NULL ELSE short_term_debt END) = 0" not in src
