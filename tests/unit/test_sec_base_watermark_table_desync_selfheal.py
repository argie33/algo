"""Regression test for the 2026-08-10 fix: SecLoaderBase.fetch_incremental() trusted the
loader_watermarks table blindly, even when it desyncs from the actual data table.

Live-reproduced 2026-08-10: BFS/UDR's `financial_statements_income_annual` watermark
claimed data already loaded through fiscal_year 2026 (rows_loaded=112/114), but
`annual_income_statement` had ZERO real rows for either symbol (the table was
truncated/reset without resetting the watermark - loader_watermarks advances via
bulk_insert_manager's advance_watermark(in_transaction=False), a write independent of the
row INSERT's own transaction). Since fetch_incremental filters fetched rows to
`fiscal_year > since.year`, a watermark stuck in the future silently and permanently
starves that symbol of ever being re-fetched - every run reports "no new data" even
though the table is empty.

Fix: before trusting a non-None `since`, verify the symbol actually has at least one row
in the target table. If not, the watermark is provably wrong (a symbol with a "later than
now" watermark and zero real rows cannot possibly be caught up) - ignore it and fetch the
full history.
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


def _fake_db_context(fetchone_result):
    def factory(mode, **kwargs):
        ctx = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = fetchone_result
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    return factory


class TestWatermarkTableDesyncSelfHeal:
    def test_ignores_watermark_when_table_has_zero_rows_for_symbol(self):
        loader = _make_loader()
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "BFS", "fiscal_year": 2025, "revenues": 289_800_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(fetchone_result=None),  # zero rows for this symbol
        ):
            rows = loader.fetch_incremental("BFS", since=date(2026, 12, 31))

        # Without the fix, since_year=2026 would filter out the FY2025 row entirely.
        assert len(rows) == 1
        assert rows[0]["fiscal_year"] == 2025

    def test_respects_watermark_when_table_has_real_rows_for_symbol(self):
        loader = _make_loader()
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "AAPL", "fiscal_year": 2025, "revenues": 400_000_000_000},
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=_fake_db_context(fetchone_result=(1,)),  # symbol has real rows
        ):
            rows = loader.fetch_incremental("AAPL", since=date(2026, 12, 31))

        # since_year=2026 correctly filters out the FY2025 row - watermark is trusted
        # because the table backs up its claim.
        assert rows == []

    def test_no_watermark_skips_the_table_check_entirely(self):
        loader = _make_loader()
        loader._sec_client.get_income_statement.return_value = [
            {"symbol": "NEWCO", "fiscal_year": 2025, "revenues": 1_000_000},
        ]

        with patch("utils.db.context.DatabaseContext") as mock_ctx:
            rows = loader.fetch_incremental("NEWCO", since=None)

        mock_ctx.assert_not_called()
        assert len(rows) == 1
