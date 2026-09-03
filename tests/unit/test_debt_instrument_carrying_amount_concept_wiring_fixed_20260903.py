"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep): the 2026-08-18 ADC/net-lease-REIT fix added "debt_instrument_carrying_amount" to
load_financial_statements.py's _BALANCE_FIELD_MAPPING/_DEBT_FALLBACK_ONLY_FIELDS (and a
regression test for the mapping) but never added the matching XBRL concept string to
sec_statements.py's get_balance_sheet() concept-fetch list - the exact "wiring half-landed"
bug class documented one entry above this one in that same file (LongTermDebtNoncurrent/
LongTermDebtAndCapitalLeaseObligations), which somehow didn't stop a second instance of it.

Live-reverified 2026-09-03: ADC itself (the symbol the original fix targeted) was still NULL
for long_term_debt across FY2023-2025 despite real DebtInstrumentCarryingAmount values in its
companyfacts JSON; DLR (Digital Realty) was NULL for its entire history despite a real,
undimensioned $17,537,652,000 FY2023 fact under the same concept. The fallback had never
fired for any symbol since it was written.
"""

import inspect

from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS
from utils.external import sec_statements


class TestDebtInstrumentCarryingAmountConceptWiringFixed:
    def test_field_mapping_wires_debt_instrument_carrying_amount_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["debt_instrument_carrying_amount"] == "long_term_debt"
        assert "debt_instrument_carrying_amount" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_debt_instrument_carrying_amount_concept_is_actually_fetched(self) -> None:
        # A field_mapping entry alone is not enough - get_balance_sheet()'s concept list
        # must actually request the concept from SEC or the mapping never fires. This is
        # the exact gap that let the ADC fix silently do nothing for over 2 weeks.
        source = inspect.getsource(sec_statements.get_balance_sheet)
        assert "DebtInstrumentCarryingAmount" in source
