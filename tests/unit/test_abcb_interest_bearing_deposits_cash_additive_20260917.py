"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up, cash_and_equivalents cluster): ABCB (Ameris Bancorp, CIK 0000351569) live-confirmed
via real SEC companyfacts JSON - "CashAndDueFromBanks" (a bank's non-interest-bearing
vault/till cash) and "InterestBearingDepositsInBanks" (its interest-bearing deposits at other
banks) are two genuinely distinct, simultaneously-real components of a bank's total cash, not
alternates:

FY2022: CashAndDueFromBanks $284,567,000 + InterestBearingDepositsInBanks $833,565,000 =
$1,118,132,000, an EXACT match to both yfinance's flagged value and ABCB's own
CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents fact for the same period.

Before this fix, InterestBearingDepositsInBanks was never fetched at all, so our stored
cash_and_equivalents for every fiscal year was exactly CashAndDueFromBanks alone.
"""

from loaders.helpers.financial_statements_balance_config import get_balance_sheet_config
from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.helpers.sec_zero_component_guards import ADDITIVE_CONCEPT_PAIRS


class TestAbcbInterestBearingDepositsCashAdditive:
    def _make_loader(self) -> SecEdgarStatementLoader:
        cfg = get_balance_sheet_config("annual")
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "cash_and_equivalents", "data_unavailable", "reason"})
        loader._field_mapping = cfg["field_mapping"]
        loader._fallback_only_fields = cfg.get("fallback_only_fields", frozenset())
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_field_mapping_wired(self) -> None:
        cfg = get_balance_sheet_config("annual")
        assert cfg["field_mapping"]["interest_bearing_deposits_in_banks"] == "cash_and_equivalents"

    def test_pair_registered(self) -> None:
        assert ("cash_and_equivalents", "interest_bearing_deposits_in_banks") in ADDITIVE_CONCEPT_PAIRS

    def test_abcb_style_interest_bearing_deposits_summed_not_overwritten(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches the concept-list order (cash_and_due_from_banks listed
        # before interest_bearing_deposits_in_banks): it's processed first, then
        # interest_bearing_deposits_in_banks triggers the sum rather than overwriting it.
        row = {
            "symbol": "ABCB",
            "fiscal_year": 2022,
            "cash_and_due_from_banks": 284_567_000.0,
            "interest_bearing_deposits_in_banks": 833_565_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cash_and_equivalents"] == 1_118_132_000.0

    def test_solo_interest_bearing_deposits_still_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "SOMEBANK", "fiscal_year": 2025, "interest_bearing_deposits_in_banks": 5_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["cash_and_equivalents"] == 5_000.0
