"""Regression test for the 2026-08-18 fix: fetch_incremental()'s retry-set only covered
fiscal years marked `data_unavailable = TRUE` (test_sec_base_retries_unavailable_years_
past_watermark.py) - it did nothing for the DIFFERENT, more common shape of the same bug:
a row written successfully (data_unavailable = FALSE) but missing this statement's one
load-bearing field because of an extraction gap that a later fix might now close.

Live-confirmed on AVAV: annual_balance_sheet FY2024-2026 rows have real total_assets on
file, data_unavailable=FALSE, yet stockholders_equity NULL every year. The 2026-08-18
mid-year-10-Q-stub fix (d36598a2d) landed and a fresh full pipeline pass ran afterward,
but AVAV's watermark had already advanced past FY2026 from an earlier run, so
`fiscal_year > since_year` silently discarded these rows before the fix could ever reach
them - same root mechanism, just never marked data_unavailable=TRUE in the first place
because total_assets DID extract fine that year.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_balance_sheet_config


def _make_balance_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_balance_sheet_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "balance"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001234567"
    return loader


def _fake_db_context(has_rows_for_symbol: bool, unavailable_years: list, incomplete_years: list):
    """Dispatches by query text: the desync-guard's `SELECT 1 ... LIMIT 1`, the
    data_unavailable=TRUE retry query, and the new data_unavailable=FALSE + core-field-
    NULL retry query each return a different fixed result."""

    def factory(mode, **kwargs):
        ctx = MagicMock()
        cur = MagicMock()
        state = {"query": None}

        def execute(query, params=None):
            state["query"] = query

        def fetchone():
            return (1,) if has_rows_for_symbol else None

        def fetchall():
            if "data_unavailable = TRUE" in state["query"]:
                return [(y,) for y in unavailable_years]
            if "data_unavailable = FALSE" in state["query"]:
                return [(y,) for y in incomplete_years]
            raise AssertionError(f"Unexpected query: {state['query']}")

        cur.execute.side_effect = execute
        cur.fetchone.side_effect = fetchone
        cur.fetchall.side_effect = fetchall
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    return factory


class TestRetriesIncompleteAvailableYearsPastWatermark:
    def test_retries_fiscal_year_available_but_missing_core_field(self):
        loader = _make_balance_loader()
        # Full refetched history from SEC - both the current year (already past the
        # watermark) and an older year that IS on file (data_unavailable=FALSE) but
        # missing stockholders_equity specifically, same as AVAV's real state.
        loader._sec_client.get_balance_sheet.return_value = [
            {"symbol": "AVAV", "fiscal_year": 2026, "total_assets": 5_716_742_000, "stockholders_equity": 900_000_000},
            {"symbol": "AVAV", "fiscal_year": 2024, "total_assets": 1_015_860_000, "stockholders_equity": 700_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[2024]),
        ):
            rows = loader.fetch_incremental("AVAV", since=date(2025, 12, 31))

        # Without the fix, since_year=2025 would silently drop the FY2024 row forever,
        # even though stockholders_equity is now extractable and right there in the
        # freshly refetched data.
        fiscal_years = {r["fiscal_year"] for r in rows}
        assert fiscal_years == {2026, 2024}

    def test_does_not_retry_years_with_core_field_already_populated(self):
        loader = _make_balance_loader()
        loader._sec_client.get_balance_sheet.return_value = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "total_assets": 400_000_000_000,
                "stockholders_equity": 60_000_000_000,
            },
            {
                "symbol": "AAPL",
                "fiscal_year": 2020,
                "total_assets": 275_000_000_000,
                "stockholders_equity": 65_000_000_000,
            },
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[], incomplete_years=[]),
        ):
            rows = loader.fetch_incremental("AAPL", since=date(2024, 12, 31))

        # Normal incremental behavior preserved: no incomplete years on file, so only
        # the fiscal year newer than the watermark comes through.
        assert {r["fiscal_year"] for r in rows} == {2025}

    def test_income_statement_uses_net_income_as_core_field(self):
        """Different statement_type -> different core field (_CORE_FIELD_BY_STATEMENT_TYPE)."""
        from loaders.load_financial_statements import get_income_statement_config

        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_income_statement_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "income"
        loader.is_symbol_based = True
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._sec_client = MagicMock()
        loader._sec_client.symbol_to_cik.return_value = "0001234567"
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "XYZ", "fiscal_year": 2025, "revenues": 100},
            {"symbol": "XYZ", "fiscal_year": 2023, "revenues": 90},
        ]

        captured_queries = []

        def factory(mode, **kwargs):
            ctx = MagicMock()
            cur = MagicMock()

            def execute(query, params=None):
                captured_queries.append(query)

            cur.execute.side_effect = execute
            cur.fetchone.side_effect = lambda: (1,)
            cur.fetchall.side_effect = list
            ctx.__enter__.return_value = cur
            ctx.__exit__.return_value = False
            return ctx

        with patch("utils.db.context.DatabaseContext", side_effect=factory):
            loader.fetch_incremental("XYZ", since=date(2024, 12, 31))

        assert any("net_income IS NULL" in q for q in captured_queries)
