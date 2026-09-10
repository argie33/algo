"""Regression test for the 2026-09-10 fix: all of ConsolidatedFinancialStatementsLoader's
custom-XBRL-extension fallbacks (CUSTOM_REVENUE_CONCEPTS, CUSTOM_INCOME_DIMENSIONED_CONCEPTS,
CUSTOM_CAPEX_CONCEPTS, CUSTOM_CAPEX_DIMENSIONED_CONCEPTS, CUSTOM_DIVIDEND_CONCEPTS,
CUSTOM_DEBT_CONCEPTS, CUSTOM_DEBT_LONGTERM_CONCEPTS, CUSTOM_DEBT_SHORTTERM_CONCEPTS) fetch a
value from the symbol's LATEST ANNUAL FILING ONLY (confirmed via each fetch_custom_*()
function's own docstring in utils/external/sec_custom_xbrl_concepts.py), but were applied to
every row sharing a fiscal_year with no period check at all.

Live-caught via APA (registered in CUSTOM_REVENUE_CONCEPTS): its FY2025 quarterly_income_
statement rows for Q1-Q4 all showed revenue identically equal to the FY2025 annual total
($8.951B in every quarter) - flagged by DataPatrol's quarterly_revenue_annual_duplicate check.
Two prior sessions "fixed" this via a one-off DB UPDATE (nulling the bad rows) without finding
this code path; a normal reload reproduced the identical bug within 2 days both times, since
the actual root cause was never touched. This is the real, durable fix: gate every one of
these fallback loops to annual rows only.

IMPORTANT (own mistake, corrected before landing): the first version of both the fix and this
test file gated on a "fiscal_quarter" key - that key does NOT exist on fetch_incremental()'s
raw pre-transform rows (confirmed via a live fetch_incremental('APA') call: the actual key at
this stage is "fiscal_period", string-valued 'Q1'-'Q4' for quarterly rows and 'FY' for annual
rows - "fiscal_quarter" only exists on the POST-transform row shape used later in the
pipeline). The mocked rows below use "fiscal_period" for exactly this reason; a test built on
"fiscal_quarter" mocks would pass against the broken fix too since both were consistently
wrong together - always verify a mocked field name against a real fetch_incremental() call
when the field isn't already used elsewhere in the same test file.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import (
    ConsolidatedFinancialStatementsLoader,
    get_balance_sheet_config,
    get_income_statement_config,
)


def _make_loader(statement_type: str, period: str) -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config(period) if statement_type == "income" else get_balance_sheet_config(period)
    loader.table_name = config["table_name"]
    loader.period = period
    loader.statement_type = statement_type
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._fallback_only_fields = config["fallback_only_fields"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001841666"
    return loader


class TestCustomRevenueSkipsQuarterlyRows:
    def test_annual_row_gets_custom_revenue_quarterly_rows_do_not(self):
        loader = _make_loader("income", "quarterly")
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "APA", "fiscal_year": 2025, "fiscal_period": "Q1", "revenue": None},
                    {"symbol": "APA", "fiscal_year": 2025, "fiscal_period": "Q2", "revenue": None},
                    {"symbol": "APA", "fiscal_year": 2025, "fiscal_period": "Q3", "revenue": None},
                    {"symbol": "APA", "fiscal_year": 2025, "fiscal_period": "Q4", "revenue": None},
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_revenue",
                return_value={2025: 8_951_000_000.0},
            ),
        ):
            rows = loader.fetch_incremental("APA", since=None)

        assert all("custom_extension_revenue" not in row for row in rows), (
            "custom_extension_revenue (an ANNUAL-only fallback) must never be injected into "
            "quarterly rows - this is exactly the APA duplicate-revenue bug"
        )

    def test_annual_statement_type_still_gets_custom_revenue(self):
        loader = _make_loader("income", "annual")
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "APA", "fiscal_year": 2025, "fiscal_period": "FY", "revenue": None}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_revenue",
                return_value={2025: 8_951_000_000.0},
            ),
        ):
            rows = loader.fetch_incremental("APA", since=None)

        assert rows[0]["custom_extension_revenue"] == 8_951_000_000.0

    def test_row_without_fiscal_period_key_never_gets_custom_revenue(self):
        """A row missing the fiscal_period key entirely is NOT an annual row by this gate's
        rule (== "FY" fails for None too) - fail-safe: don't guess, skip the fallback."""
        loader = _make_loader("income", "annual")
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "APA", "fiscal_year": 2025, "revenue": None}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_revenue",
                return_value={2025: 8_951_000_000.0},
            ),
        ):
            rows = loader.fetch_incremental("APA", since=None)

        assert "custom_extension_revenue" not in rows[0]


class TestCustomDebtExtensionsSkipQuarterlyRows:
    def test_quarterly_balance_sheet_rows_never_get_custom_debt(self):
        loader = _make_loader("balance", "quarterly")
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "BRK.B", "fiscal_year": 2025, "fiscal_period": "Q1", "total_assets": 1},
                    {"symbol": "BRK.B", "fiscal_year": 2025, "fiscal_period": "Q2", "total_assets": 1},
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_debt",
                return_value={2025: 129_081_000_000.0},
            ),
        ):
            rows = loader.fetch_incremental("BRK.B", since=None)

        assert all("custom_extension_total_debt" not in row for row in rows)

    def test_annual_balance_sheet_rows_still_get_custom_debt(self):
        loader = _make_loader("balance", "annual")
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "BRK.B", "fiscal_year": 2025, "fiscal_period": "FY", "total_assets": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_debt",
                return_value={2025: 129_081_000_000.0},
            ),
        ):
            rows = loader.fetch_incremental("BRK.B", since=None)

        assert rows[0]["custom_extension_total_debt"] == 129_081_000_000.0
