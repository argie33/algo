"""Regression tests for the 2026-09-19 PRG depreciation_expense fix: PRG (PROG Holdings)
tags its dominant depreciation line - depreciation of its rental-fleet lease merchandise -
under a filer-specific custom XBRL extension concept (prg:DepreciationOfLeaseMerchandise),
invisible to SEC's companyfacts/companyconcept APIs (same structural gap CUSTOM_CAPEX_
CONCEPTS' module docstring documents for DHT/CMRE). Unlike every other custom-extension
field, this one is ADDITIVE to the base us-gaap depreciation_expense PRG's normal
concept extraction already finds (a real but tiny corporate-PP&E figure), not fallback-only.

Fixture XML values (FY2023/2024/2025) match the real filed XBRL instance document,
verified live 2026-09-19 (accession 0001808834-26-000012).
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config
from utils.external.sec_custom_xbrl_concepts import (
    CUSTOM_DEPRECIATION_CONCEPTS,
    extract_custom_depreciation_from_xbrl_xml,
)

_PRG_XML = """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:prg="http://progleasing.com/20251231">
  <context id="c-13">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001808834</identifier></entity>
    <period><startDate>2023-01-01</startDate><endDate>2023-12-31</endDate></period>
  </context>
  <context id="c-12">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001808834</identifier></entity>
    <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
  </context>
  <context id="c-1">
    <entity><identifier scheme="http://www.sec.gov/CIK">0001808834</identifier></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <prg:DepreciationOfLeaseMerchandise contextRef="c-13" unitRef="usd" decimals="-3">1576303000</prg:DepreciationOfLeaseMerchandise>
  <prg:DepreciationOfLeaseMerchandise contextRef="c-12" unitRef="usd" decimals="-3">1621101000</prg:DepreciationOfLeaseMerchandise>
  <prg:DepreciationOfLeaseMerchandise contextRef="c-1" unitRef="usd" decimals="-3">1590240000</prg:DepreciationOfLeaseMerchandise>
</xbrl>
"""


class TestExtractCustomDepreciationFromXbrlXml:
    def test_extracts_all_three_fiscal_years(self):
        values = extract_custom_depreciation_from_xbrl_xml(_PRG_XML, "PRG")
        assert values == {2023: 1_576_303_000.0, 2024: 1_621_101_000.0, 2025: 1_590_240_000.0}

    def test_unregistered_symbol_returns_empty(self):
        assert extract_custom_depreciation_from_xbrl_xml(_PRG_XML, "AAPL") == {}


class TestPrgRegisteredInCustomDepreciationConcepts:
    def test_prg_registered(self):
        assert "PRG" in CUSTOM_DEPRECIATION_CONCEPTS


def _make_income_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "income"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._fallback_only_fields = config["fallback_only_fields"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001808834"
    return loader


class TestApplyCustomIncomeExtensionsStagesDepreciationKey:
    """apply_custom_income_extensions() runs on fetch_incremental()'s raw, pre-transform
    output (transform() is a separate later pipeline stage - see optimal_loader.py's
    fetch_incremental()-then-transform() call sequence), so depreciation_expense itself
    isn't populated on `row` yet at this point. It stages the custom value onto
    custom_extension_lease_merchandise_depreciation instead, same convention as every
    other custom-extension field - transform() (tested separately below) is what actually
    sums it into depreciation_expense.
    """

    def test_custom_depreciation_staged_for_matching_fiscal_years(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "PRG", "fiscal_year": 2024, "fiscal_period": "FY", "depreciation": 8_400_000.0},
                    {"symbol": "PRG", "fiscal_year": 2023, "fiscal_period": "FY", "depreciation": 8_500_000.0},
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_depreciation",
                return_value={2024: 1_621_101_000.0, 2023: 1_576_303_000.0},
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("PRG", since=None)

        mock_fetch.assert_called_once_with("PRG", loader._sec_client)
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["custom_extension_lease_merchandise_depreciation"] == 1_621_101_000.0
        assert by_year[2023]["custom_extension_lease_merchandise_depreciation"] == 1_576_303_000.0

    def test_fiscal_year_with_no_custom_data_is_left_unmodified(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "PRG", "fiscal_year": 2010, "fiscal_period": "FY", "depreciation": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_depreciation",
                return_value={2024: 1_621_101_000.0},  # No entry for 2010
            ),
        ):
            rows = loader.fetch_incremental("PRG", since=None)

        assert "custom_extension_lease_merchandise_depreciation" not in rows[0]

    def test_unregistered_symbol_never_calls_fetch_custom_depreciation(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "fiscal_period": "FY", "depreciation": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_depreciation"
            ) as mock_fetch,
        ):
            loader.fetch_incremental("AAPL", since=None)

        mock_fetch.assert_not_called()

    def test_balance_statement_type_never_calls_fetch_custom_depreciation(self):
        loader = _make_income_loader()
        loader.statement_type = "balance"
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "PRG", "fiscal_year": 2024, "fiscal_period": "FY", "total_assets": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_depreciation"
            ) as mock_fetch,
        ):
            loader.fetch_incremental("PRG", since=None)

        mock_fetch.assert_not_called()


class TestTransformSumsCustomDepreciationIntoDepreciationExpense:
    """End-to-end through the real SecEdgarStatementLoader.transform() (sec_base.py) -
    exercises the actual ADDITIVE_CONCEPT_PAIRS/is_fallback_only_write_permitted_by_
    documented_override wiring, not just apply_custom_income_extensions() in isolation.
    """

    def test_real_transform_sums_base_and_custom_depreciation(self):
        loader = _make_income_loader()
        raw_rows = [
            {
                "symbol": "PRG",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "depreciation": 8_400_000.0,
                "custom_extension_lease_merchandise_depreciation": 1_621_101_000.0,
            }
        ]
        transformed = loader.transform(raw_rows)
        assert transformed[0]["depreciation_expense"] == 8_400_000.0 + 1_621_101_000.0

    def test_real_transform_never_overwrites_when_custom_value_absent(self):
        loader = _make_income_loader()
        raw_rows = [{"symbol": "AAPL", "fiscal_year": 2024, "fiscal_period": "FY", "depreciation": 500_000_000.0}]
        transformed = loader.transform(raw_rows)
        assert transformed[0]["depreciation_expense"] == 500_000_000.0
