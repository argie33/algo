"""Regression test for the 2026-09-03 fix: quality_metrics.interest_coverage's
"interest_expense_not_itemized" bucket was 81% (301/373) real borrowers with substantial
total_debt on file, not genuinely debt-free companies - live-confirmed via PKG (Packaging
Corp, $4.39B debt), whose companyfacts JSON has no "InterestExpense"/
"InterestExpenseNonoperating"/"InterestExpenseDebt"/"InterestAndDebtExpense" fact at all, but
does report real values under "InterestIncomeExpenseNet" every year (FY2023 -$53.3M, FY2024
-$41.4M, FY2025 -$79.1M) - PKG nets interest income against interest expense into one line
instead of itemizing it. ConsolidatedFinancialStatementsLoader.fetch_incremental() now backfills
interest_expense from this net concept, but only when it unambiguously means "expense
dominates" (a negative net value) - see
_backfill_interest_expense_from_net_concept()'s own docstring for why a positive net value
(net interest income) is deliberately left alone.
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
    loader._sec_client.symbol_to_cik.return_value = "0000075677"
    loader._backfill_days = 0
    loader._fpi_symbol_cache = {}
    return loader


def _companyfacts(concept: str, entries: list[dict]) -> dict:
    return {"facts": {"us-gaap": {concept: {"units": {"USD": entries}}}}}


def _fy_entry(fy: int, val: float, start: str, end: str, form: str = "10-K") -> dict:
    return {"fy": fy, "fp": "FY", "val": val, "start": start, "end": end, "form": form}


class TestInterestExpenseNetFallback:
    def test_negative_net_value_backfills_interest_expense_as_magnitude(self):
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.return_value = _companyfacts(
            "InterestIncomeExpenseNet",
            [
                _fy_entry(2025, -79_100_000.0, "2025-01-01", "2025-12-31"),
                _fy_entry(2024, -41_400_000.0, "2024-01-01", "2024-12-31"),
            ],
        )
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[
                {"symbol": "PKG", "fiscal_year": 2025, "revenue": 1, "interest_expense": None},
                {"symbol": "PKG", "fiscal_year": 2024, "revenue": 1, "interest_expense": None},
            ],
        ):
            rows = loader.fetch_incremental("PKG", since=None)

        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["interest_expense"] == 79_100_000.0
        assert by_year[2024]["interest_expense"] == 41_400_000.0

    def test_positive_net_value_left_unfetched(self):
        """A positive net figure means interest income exceeds interest expense - the sign
        is ambiguous for a gross expense figure, so this must stay None rather than guess."""
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.return_value = _companyfacts(
            "InterestIncomeExpenseNet",
            [_fy_entry(2025, 12_000_000.0, "2025-01-01", "2025-12-31")],
        )
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "CASHCO", "fiscal_year": 2025, "revenue": 1, "interest_expense": None}],
        ):
            rows = loader.fetch_incremental("CASHCO", since=None)

        assert rows[0]["interest_expense"] is None

    def test_short_duration_fact_ignored(self):
        """A quarterly-duration fact mislabeled fp='FY' must not pass the span guard - same
        discipline as sec_statements.py's own annual-duration span check elsewhere."""
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.return_value = _companyfacts(
            "InterestIncomeExpenseNet",
            [_fy_entry(2025, -1_000_000.0, "2025-10-01", "2025-12-31")],  # ~91 days
        )
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "QCO", "fiscal_year": 2025, "revenue": 1, "interest_expense": None}],
        ):
            rows = loader.fetch_incremental("QCO", since=None)

        assert rows[0]["interest_expense"] is None

    def test_row_with_real_interest_expense_already_present_is_untouched_and_no_fetch(self):
        loader = _make_income_loader()
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "interest_expense": 3_900_000_000.0}],
        ):
            rows = loader.fetch_incremental("AAPL", since=None)

        loader._sec_client.get_company_facts.assert_not_called()
        assert rows[0]["interest_expense"] == 3_900_000_000.0

    def test_data_unavailable_row_never_triggers_fetch(self):
        loader = _make_income_loader()
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "SPAC1", "fiscal_year": 2025, "data_unavailable": True, "interest_expense": None}],
        ):
            loader.fetch_incremental("SPAC1", since=None)

        loader._sec_client.get_company_facts.assert_not_called()

    def test_balance_statement_type_never_invokes_fallback(self):
        loader = _make_income_loader()
        loader.statement_type = "balance"
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "PKG", "fiscal_year": 2025, "interest_expense": None}],
        ):
            loader.fetch_incremental("PKG", since=None)

        loader._sec_client.get_company_facts.assert_not_called()

    def test_quarterly_period_never_invokes_fallback(self):
        loader = _make_income_loader()
        loader.period = "quarterly"
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "PKG", "fiscal_year": 2025, "interest_expense": None}],
        ):
            loader.fetch_incremental("PKG", since=None)

        loader._sec_client.get_company_facts.assert_not_called()

    def test_get_company_facts_exception_is_soft_failure(self):
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.side_effect = RuntimeError("boom")
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "PKG", "fiscal_year": 2025, "interest_expense": None}],
        ):
            rows = loader.fetch_incremental("PKG", since=None)

        assert rows[0]["interest_expense"] is None

    def test_nonoperating_net_alias_concept_also_used(self):
        loader = _make_income_loader()
        loader._sec_client.get_company_facts.return_value = _companyfacts(
            "InterestIncomeExpenseNonoperatingNet",
            [_fy_entry(2025, -10_000_000.0, "2025-01-01", "2025-12-31")],
        )
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[{"symbol": "JNJ2", "fiscal_year": 2025, "interest_expense": None}],
        ):
            rows = loader.fetch_incremental("JNJ2", since=None)

        assert rows[0]["interest_expense"] == 10_000_000.0
