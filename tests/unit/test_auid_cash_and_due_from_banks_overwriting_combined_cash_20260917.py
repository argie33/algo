"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up, cash_and_equivalents cluster): AUID (authID Inc., CIK 0001534154) FY2023/FY2024
live-confirmed via real SEC companyfacts JSON - tags a real, immaterial "CashAndDueFromBanks"
fact ($700 / $600 - not a bank, this looks like a stray escrow/petty-cash line the filer
mis-tagged under a bank-specific concept) alongside a real, dramatically larger
"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents" combined-cash fact
($10,177,099 / $8,471,561, exact yfinance match for both years).

Root cause (confirmed empirically via SecEdgarStatementLoader.transform() called directly on
AUID's real raw row, see loaders/helpers/sec_zero_component_guards.py's
is_narrow_cash_due_from_banks_overwriting_combined_cash docstring for full detail):
sec_base.py's transform() processes raw concepts in the RAW ROW's own key order (from
_aggregate_concepts, i.e. sec_balance_sheet.py's concept-fetch list order), not
field_mapping's dict order. Since the combined concept is listed BEFORE "CashAndDueFromBanks"
in that fetch list (intentionally, to keep it "least preferred"/overridable), and
"CashAndDueFromBanks" is a plain, non-fallback-gated concept, it unconditionally overwrote
the earlier-processed, correct combined-cash total via ordinary last-processed-wins.
"""

from loaders.helpers.financial_statements_balance_config import get_balance_sheet_config
from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.helpers.sec_zero_component_guards import (
    _CASH_DUE_FROM_BANKS_MIN_MULTIPLE,
    is_narrow_cash_due_from_banks_overwriting_combined_cash,
)


def _make_loader() -> SecEdgarStatementLoader:
    cfg = get_balance_sheet_config("annual")
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_balance_sheet"
    loader.period = "annual"
    loader.statement_type = "balance"
    loader._schema_cols = frozenset(
        {
            "symbol",
            "fiscal_year",
            "cash_and_equivalents",
            "cash_and_restricted_cash_combined",
            "data_unavailable",
            "reason",
        }
    )
    loader._field_mapping = cfg["field_mapping"]
    loader._fallback_only_fields = cfg.get("fallback_only_fields", frozenset())
    loader._reit_only_fallback_fields = frozenset()
    loader._reit_exclusive_fields = frozenset()
    loader._reit_symbols = frozenset()
    return loader


class TestIsNarrowCashDueFromBanksOverwritingCombinedCash:
    def test_auid_fy2023_fires(self) -> None:
        assert (
            is_narrow_cash_due_from_banks_overwriting_combined_cash(
                "cash_and_equivalents",
                "cash_and_due_from_banks",
                10_177_099.0,
                700.0,
                "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents",
            )
            is True
        )

    def test_auid_fy2024_fires(self) -> None:
        assert (
            is_narrow_cash_due_from_banks_overwriting_combined_cash(
                "cash_and_equivalents",
                "cash_and_due_from_banks",
                8_471_561.0,
                600.0,
                "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents",
            )
            is True
        )

    def test_does_not_fire_when_existing_source_is_not_the_combined_concept(self) -> None:
        # A modest existing value from some OTHER concept must never be treated as this bug -
        # this guard is only about protecting the specific combined-cash concept's total.
        assert (
            is_narrow_cash_due_from_banks_overwriting_combined_cash(
                "cash_and_equivalents",
                "cash_and_due_from_banks",
                10_177_099.0,
                700.0,
                "cash_and_cash_equivalents_at_carrying_value",
            )
            is False
        )

    def test_does_not_fire_below_magnitude_threshold(self) -> None:
        existing = 100_000.0
        value = existing / (_CASH_DUE_FROM_BANKS_MIN_MULTIPLE - 1)
        assert (
            is_narrow_cash_due_from_banks_overwriting_combined_cash(
                "cash_and_equivalents",
                "cash_and_due_from_banks",
                existing,
                value,
                "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents",
            )
            is False
        )

    def test_zion_class_real_bank_total_is_not_narrow(self) -> None:
        # ZION's own real CashAndDueFromBanks IS the authoritative total for a bank - this
        # must never be mistaken for AUID's shape.
        assert (
            is_narrow_cash_due_from_banks_overwriting_combined_cash(
                "cash_and_equivalents",
                "cash_and_due_from_banks",
                500_000_000.0,
                600_000_000.0,
                "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents",
            )
            is False
        )

    def test_does_not_fire_for_other_db_fields(self) -> None:
        assert (
            is_narrow_cash_due_from_banks_overwriting_combined_cash(
                "long_term_debt",
                "cash_and_due_from_banks",
                10_177_099.0,
                700.0,
                "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents",
            )
            is False
        )


class TestTransformAuidIntegration:
    def test_auid_style_row_keeps_combined_cash_total(self) -> None:
        loader = _make_loader()
        row = {
            "symbol": "AUID",
            "fiscal_year": 2023,
            "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": 10_177_099,
            "_rank_cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": 2,
            "cash_and_due_from_banks": 700,
            "_rank_cash_and_due_from_banks": 2,
            "cash_and_restricted_cash_combined": 10_177_099,
        }
        transformed = loader.transform([row])
        assert transformed[0]["cash_and_equivalents"] == 10_177_099

    def test_zion_style_bank_only_concept_still_writes_normally(self) -> None:
        loader = _make_loader()
        row = {
            "symbol": "ZION",
            "fiscal_year": 2024,
            "cash_and_due_from_banks": 500_000_000,
            "_rank_cash_and_due_from_banks": 2,
        }
        transformed = loader.transform([row])
        assert transformed[0]["cash_and_equivalents"] == 500_000_000
