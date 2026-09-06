"""Regression test: the "never tagged" full-history sibling gates in vqg_symbol_gates.py must
not silently exclude a symbol whose ENTIRE fiscal-year history happens to be marked
data_unavailable=True.

Found 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit). 11 of these gates'
queries filtered `WHERE data_unavailable = FALSE`, requiring at least one real (non-unavailable)
row before the `COUNT(*) >= 1` guard could even fire - a symbol with real fiscal-year rows on
file, every one of them explicitly marked unavailable (not "never filed", just "SEC's own data
for this year didn't parse/isn't usable"), was invisible to the gate entirely and fell through
to the generic "missing_sec_data" label instead of the specific one (e.g.
"net_income_not_reported"). _get_never_tagged_pretax_income_symbols() had already been fixed
this way (`WHERE fiscal_year > 0` replaces `data_unavailable = FALSE`, same fix
_get_no_recent_*_symbols()'s windowed siblings already use) - this just wasn't mirrored to the
other 10 never-tagged gates. Live-confirmed AVEX/ADBT/DPC (quality_metrics.roa): real
annual_income_statement rows on file every year, all marked data_unavailable, net_income NULL
throughout - came back "missing_sec_data" pre-fix, "net_income_not_reported" post-fix.

Same-day follow-up: _get_never_tagged_revenue_symbols() used `WHERE data_unavailable IS NOT
TRUE` instead of `= FALSE` - semantically identical for excluding a data_unavailable=TRUE row
(`TRUE IS NOT TRUE` is just as false as `TRUE = FALSE`), so it was mistakenly treated as
"already fixed" on first pass and missed from the batch above. Live-confirmed ADBT/SSMR/KARD/
AVEX (quality_metrics.asset_turnover): real annual_balance_sheet total_assets on file, revenue
NULL/data_unavailable=TRUE in every annual_income_statement row - came back "missing_sec_data"
pre-fix, "no_revenue_reported" post-fix.
"""

import re
from pathlib import Path

_SOURCE = Path("loaders/helpers/vqg_symbol_gates.py").read_text(encoding="utf-8")

FIXED_GATE_NAMES = [
    "_get_never_tagged_interest_expense_symbols",
    "_get_never_tagged_debt_components_symbols",
    "_get_never_tagged_total_assets_symbols",
    "_get_never_tagged_current_assets_symbols",
    "_get_never_tagged_current_liabilities_symbols",
    "_get_never_tagged_cash_symbols",
    "_get_never_tagged_net_income_symbols",
    "_get_never_tagged_operating_income_symbols",
    "_get_never_tagged_total_liabilities_symbols",
    "_get_never_tagged_free_cash_flow_symbols",
    "_get_never_tagged_stockholders_equity_symbols",
]


def _function_source(name: str) -> str:
    match = re.search(rf"    def {re.escape(name)}\(self\).*?(?=\n    @_cached_symbols|\n    def |\Z)", _SOURCE, re.S)
    assert match is not None, f"could not locate {name} in vqg_symbol_gates.py"
    return match.group(0)


class TestNeverTaggedGatesDontRequireANonUnavailableRow:
    def test_all_never_tagged_gates_filter_on_fiscal_year_not_data_unavailable(self):
        for name in FIXED_GATE_NAMES:
            source = _function_source(name)
            assert "WHERE fiscal_year > 0" in source, (
                f"{name} still gates on `data_unavailable = FALSE` (or similar) instead of "
                "`fiscal_year > 0` - a symbol whose entire history is marked data_unavailable "
                "is invisible to it, same bug class as the pretax_income sibling fixed earlier."
            )
            assert "WHERE data_unavailable = FALSE" not in source, (
                f"{name} still has an unfixed `WHERE data_unavailable = FALSE` filter."
            )

    def test_never_tagged_revenue_symbols_filters_on_fiscal_year_not_data_unavailable(self):
        # Same bug, different (semantically equivalent) spelling: `IS NOT TRUE` excludes a
        # data_unavailable=TRUE row exactly as thoroughly as `= FALSE` does.
        source = _function_source("_get_never_tagged_revenue_symbols")
        assert "WHERE fiscal_year > 0" in source
        assert "WHERE data_unavailable IS NOT TRUE" not in source
