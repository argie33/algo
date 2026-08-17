"""Regression test for the 2026-08-17 SBC/buyback fallback concepts (loader-review goal
continuation, migration 1206 follow-up).

Live-confirmed via real SEC companyfacts JSON across a random sample of ~80 symbols with
real cash-flow data: FIP/DC/CNA report non-cash SBC expense only under
"AllocatedShareBasedCompensationExpense" (never "ShareBasedCompensation"), and SPWH
reports buybacks only under "PaymentsForRepurchaseOfEquity" (never
"PaymentsForRepurchaseOfCommonStock"). Added as fallback-only fields (same "don't clobber
a real total" mechanism already used for the long-term-debt fallbacks - see
test_sec_debt_fallback_concepts_not_overwriting.py) so a filer that DOES report the
standard concept always keeps that value; these only fill genuinely empty years.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _to_snake


class TestSbcBuybackFallbackConceptMappings:
    def test_fallback_concepts_map_to_expected_columns(self) -> None:
        assert (
            _CASHFLOW_FIELD_MAPPING[_to_snake("AllocatedShareBasedCompensationExpense")] == "stock_based_compensation"
        )
        assert _CASHFLOW_FIELD_MAPPING[_to_snake("PaymentsForRepurchaseOfEquity")] == "common_stock_repurchased"
        assert _to_snake("AllocatedShareBasedCompensationExpense") in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        assert _to_snake("PaymentsForRepurchaseOfEquity") in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_standard_concepts_still_map_directly_and_are_not_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["share_based_compensation"] == "stock_based_compensation"
        assert _CASHFLOW_FIELD_MAPPING["payments_for_repurchase_of_common_stock"] == "common_stock_repurchased"
        assert "share_based_compensation" not in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        assert "payments_for_repurchase_of_common_stock" not in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestSbcBuybackFallbackNotOverwritingRealValue:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset(
            {
                "symbol",
                "fiscal_year",
                "stock_based_compensation",
                "common_stock_repurchased",
                "data_unavailable",
                "reason",
            }
        )
        loader._field_mapping = {
            "share_based_compensation": "stock_based_compensation",
            "allocated_share_based_compensation_expense": "stock_based_compensation",
            "payments_for_repurchase_of_common_stock": "common_stock_repurchased",
            "payments_for_repurchase_of_equity": "common_stock_repurchased",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = _SBC_BUYBACK_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_sbc_not_overwritten_by_fallback_concept(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "share_based_compensation": 12_500_000_000.0,
            "allocated_share_based_compensation_expense": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stock_based_compensation"] == 12_500_000_000.0

    def test_fallback_concept_populates_sbc_when_standard_concept_absent(self) -> None:
        # FIP/DC/CNA-style filer: never tags "ShareBasedCompensation", only
        # "AllocatedShareBasedCompensationExpense" - previously silently dropped.
        loader = self._make_loader()
        row = {
            "symbol": "FIP",
            "fiscal_year": 2025,
            "allocated_share_based_compensation_expense": 11_076_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stock_based_compensation"] == 11_076_000.0

    def test_fallback_concept_populates_buyback_when_standard_concept_absent(self) -> None:
        # SPWH-style filer: never tags "PaymentsForRepurchaseOfCommonStock", only
        # "PaymentsForRepurchaseOfEquity" - previously silently dropped.
        loader = self._make_loader()
        row = {
            "symbol": "SPWH",
            "fiscal_year": 2023,
            "payments_for_repurchase_of_equity": 2_748_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["common_stock_repurchased"] == 2_748_000.0
