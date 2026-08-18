"""Regression test for the 2026-08-18 fix: fetch_incremental()'s `fiscal_year > since_year`
filter permanently excluded any fiscal year the watermark had advanced past, even one still
marked data_unavailable in the DB that a later concept-list fix might now be able to fill.

The 2026-08-10 fix (see test_sec_base_watermark_excludes_unavailable_rows.py) stops the
watermark from advancing TO an unavailable fiscal year, but does nothing once a LATER year
succeeds and advances the watermark past it - this is the complementary gap. Live-confirmed:
NVO's 2015-2021 annual_income_statement rows had real revenue/net_income already stored (from
an earlier successful fetch) yet stayed data_unavailable=TRUE forever once FY2022+ advanced
the watermark past them - 486 rows across all 6 statement tables found in this same
contradictory state system-wide.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
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
    return loader


def _fake_db_context(has_rows_for_symbol: bool, unavailable_years: list):
    """Dispatches by query text: the desync-guard's `SELECT 1 ... LIMIT 1` (fetchone) vs.
    the new `SELECT fiscal_year ... WHERE data_unavailable = TRUE` (fetchall)."""

    def factory(mode, **kwargs):
        ctx = MagicMock()
        cur = MagicMock()

        def execute(query, params=None):
            cur._query = query

        def fetchone():
            return (1,) if has_rows_for_symbol else None

        def fetchall():
            return [(y,) for y in unavailable_years]

        cur.execute.side_effect = execute
        cur.fetchone.side_effect = fetchone
        cur.fetchall.side_effect = fetchall
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    return factory


class TestRetriesUnavailableYearsPastWatermark:
    def test_retries_fiscal_year_still_marked_unavailable_despite_watermark(self):
        loader = _make_loader()
        # Full refetched history from SEC - both an old, still-unavailable year and the
        # current year that already advanced the watermark past it.
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "NVO", "fiscal_year": 2025, "revenues": 309_064_000_000},
            {"symbol": "NVO", "fiscal_year": 2021, "revenues": 140_800_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[2021]),
        ):
            rows = loader.fetch_incremental("NVO", since=date(2024, 12, 31))

        # Without the fix, since_year=2024 would silently drop the FY2021 row forever,
        # even though it's still marked unavailable and the real value is right there.
        fiscal_years = {r["fiscal_year"] for r in rows}
        assert fiscal_years == {2025, 2021}

    def test_does_not_retry_years_not_marked_unavailable(self):
        loader = _make_loader()
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "AAPL", "fiscal_year": 2025, "revenues": 400_000_000_000},
            {"symbol": "AAPL", "fiscal_year": 2020, "revenues": 275_000_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(has_rows_for_symbol=True, unavailable_years=[]),
        ):
            rows = loader.fetch_incremental("AAPL", since=date(2024, 12, 31))

        # Normal incremental behavior preserved: no unavailable years on file, so only
        # the fiscal year newer than the watermark comes through.
        assert {r["fiscal_year"] for r in rows} == {2025}

    def test_no_watermark_skips_the_unavailable_years_query_entirely(self):
        loader = _make_loader()
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "NEWCO", "fiscal_year": 2025, "revenues": 1_000_000},
        ]

        with patch("utils.db.context.DatabaseContext") as mock_ctx:
            rows = loader.fetch_incremental("NEWCO", since=None)

        mock_ctx.assert_not_called()
        assert len(rows) == 1
