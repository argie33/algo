"""Regression test for the 2026-08-17 fix to load_financial_statements.py's crash-handler.

main()'s except-block used to write a placeholder row (symbol, data_unavailable=TRUE,
reason='loader_crash:...') into whatever statement table was active, omitting fiscal_year
(defaulting it to NULL) and relying on "ON CONFLICT (symbol, fiscal_year) DO NOTHING" to dedupe
repeat crashes. That never worked: SQL NULL never equals NULL, so ON CONFLICT's uniqueness
check never matched and every crash appended a fresh full-universe batch of NULL-keyed rows.

Live-confirmed 2026-08-17: a single crashed run wrote 4,948 NULL-fiscal_year rows into
annual_balance_sheet in one pass. Because Postgres's DESC ordering defaults to NULLS FIRST,
those rows then silently outranked real data in every "ORDER BY fiscal_year DESC LIMIT 1"
query elsewhere (load_sec_valuations.py's book_value/cash_row/debt_row lookups), making AAPL/
MSFT/GOOGL/F all report "book value missing" despite having real, freshly-loaded balance
sheets.

Fixed: when the primary key requires more than 'symbol' (true for every one of this loader's
9 output tables), skip the placeholder write entirely instead of writing an unrecoverable
NULL-keyed row.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import main


class TestCrashMarkerSkipsNullKeyedWrite:
    def test_balance_annual_crash_does_not_write_null_fiscal_year_row(self, monkeypatch):
        monkeypatch.setenv("LOADER_STATEMENT_TYPE", "balance")
        monkeypatch.setenv("LOADER_PERIOD", "annual")

        fake_db_context = MagicMock()

        with (
            patch("loaders.load_financial_statements.run_loader", side_effect=RuntimeError("boom")),
            patch("loaders.load_financial_statements.DatabaseContext", fake_db_context),
        ):
            result = main()

        assert result == 1
        # The old buggy path opened a DatabaseContext("write") cursor and looped INSERTs
        # over every active symbol with fiscal_year omitted (NULL). The fix returns before
        # ever touching the DB for a fiscal_year-keyed table's crash marker.
        fake_db_context.assert_not_called()

    def test_income_quarterly_crash_does_not_write_null_keyed_row(self, monkeypatch):
        monkeypatch.setenv("LOADER_STATEMENT_TYPE", "income")
        monkeypatch.setenv("LOADER_PERIOD", "quarterly")

        fake_db_context = MagicMock()

        with (
            patch("loaders.load_financial_statements.run_loader", side_effect=RuntimeError("boom")),
            patch("loaders.load_financial_statements.DatabaseContext", fake_db_context),
        ):
            result = main()

        assert result == 1
        fake_db_context.assert_not_called()
