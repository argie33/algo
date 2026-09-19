"""Regression test for the 2026-09-18 fix: MS (Morgan Stanley) live-confirmed via real SEC
companyfacts JSON - MS has no annual plain "InterestExpense" fact, but DOES have a real,
correct "InterestExpenseOperating" fact ($45,524,000,000 FY2024, exactly matching yfinance).
Before this fix, _backfill_interest_expense_from_net_concept()'s target_rows filter only
checked the literal raw "interest_expense" key (the plain concept), not any of the other
concept-alias keys (interest_expense_operating, interest_expense_nonoperating, ...) that
transform()'s field_mapping later collapses onto the same "interest_expense" db column - so it
fired anyway, found MS's small, unrelated "InterestIncomeExpenseNonoperatingNet" fact
(-$92,000,000) and overwrote the correct $45.5B value with $92M. See
_backfill_interest_expense_from_net_concept()'s own updated docstring/
_INTEREST_EXPENSE_ALIAS_RAW_KEYS for the full alias set now checked.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config


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
    loader._sec_client.symbol_to_cik.return_value = "0000895421"
    loader._backfill_days = 0
    loader._fpi_symbol_cache = {}
    return loader


def _companyfacts(concept: str, entries: list[dict]) -> dict:
    return {"facts": {"us-gaap": {concept: {"units": {"USD": entries}}}}}


def _fy_entry(fy: int, val: float, start: str, end: str, form: str = "10-K") -> dict:
    return {"fy": fy, "fp": "FY", "val": val, "start": start, "end": end, "form": form}


class TestInterestExpenseNetBackfillSkipsWhenAliasPresent:
    def test_interest_expense_operating_alias_present_blocks_net_backfill(self):
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.return_value = _companyfacts(
            "InterestIncomeExpenseNonoperatingNet",
            [_fy_entry(2024, -92_000_000.0, "2024-01-01", "2024-12-31")],
        )
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[
                {
                    "symbol": "MS",
                    "fiscal_year": 2024,
                    "interest_expense": None,
                    "interest_expense_operating": 45_524_000_000.0,
                }
            ],
        ):
            rows = loader.fetch_incremental("MS", since=None)

        loader._sec_client.get_company_facts.assert_not_called()
        assert rows[0]["interest_expense_operating"] == 45_524_000_000.0
        assert rows[0]["interest_expense"] is None

    def test_other_alias_fields_also_block_net_backfill(self):
        for alias in (
            "interest_expense_nonoperating",
            "interest_expense_debt",
            "interest_and_debt_expense",
            "financing_interest_expense",
            "interest_expense_other",
            "interest_paid_net",
            "interest_paid",
        ):
            loader = _make_income_loader()
            with patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "X", "fiscal_year": 2024, "interest_expense": None, alias: 1_000_000.0}],
            ):
                loader.fetch_incremental("X", since=None)

            loader._sec_client.get_company_facts.assert_not_called()

    def test_no_alias_present_still_backfills_as_before(self):
        """PKG-style case (see test_financial_statements_interest_expense_net_fallback_20260903.py)
        must keep working - the fix narrows the trigger, it doesn't disable it."""
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.return_value = _companyfacts(
            "InterestIncomeExpenseNet",
            [_fy_entry(2024, -41_400_000.0, "2024-01-01", "2024-12-31")],
        )
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "PKG", "fiscal_year": 2024, "interest_expense": None}],
        ):
            rows = loader.fetch_incremental("PKG", since=None)

        assert rows[0]["interest_expense"] == 41_400_000.0
