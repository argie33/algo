"""Regression test for the 2026-09-16 fix: quarterly_income_statement is keyed on (symbol,
fiscal_year, fiscal_quarter), not (symbol, period_end).
_aggregate_concepts_resolve_entry_period's fiscal_year derivation for a
non-December-FYE filer depends on fye_month, which is re-derived from a symbol's evolving SEC
evidence on every run (not cached) - when a symbol's fye_month confidence flips between two
runs, the same underlying fact (same period_end) can get assigned a different fiscal_year on a
later run. Since that's a different primary key, ON CONFLICT never fires and bulk_insert() adds
a second row instead of correcting the first - live-confirmed DB-wide sweep found 1,000+
symbol/period groups with this exact signature (e.g. AGYS, ACI, MCK, FLEX).

Fix: fetch_incremental() now reconciles this before insert - for each row it's about to write,
if the DB already has a different (fiscal_year, fiscal_quarter) row for the same symbol sharing
that row's period_end, the old one is deleted (this run's fresh resolution is authoritative).

BUGFIX 2026-09-16 (same session, live-caught running the historical backfill this fix was
supposed to enable): the original version of these tests constructed `fresh_row` with an
already-transformed int "fiscal_quarter" key - but _reconcile_stale_fiscal_year_duplicate_period_end
runs INSIDE fetch_incremental(), before transform() has renamed/parsed the raw "fiscal_period"
string ("Q1".."Q4") into the canonical int "fiscal_quarter" column, and before period_end (a
plain ISO string on a raw row) has been coerced to a `date`. Real raw rows never carry an int
"fiscal_quarter" key at this stage, so the original tests exercised a shape the real code path
never produces - masking that the fix was dead code (candidates was always empty against real
rows). Rewritten to use the real raw-row shape: "fiscal_period" (string) + "period_end" (ISO
string), matching what fetch_incremental's superclass actually returns.

BUGFIX 2026-09-16 (same session, live-caught mid-backfill): quarterly_balance_sheet and
quarterly_cash_flow were ALSO listed in _QUARTERLY_TABLES_WITH_FISCAL_QUARTER_PK, but neither
table actually has a period_end column at all (confirmed via information_schema.columns) - the
reconcile query unconditionally selects period_end FROM {self.table_name}, so every quarterly
balance/cashflow loader run crashed with UndefinedColumn instead of skipping harmlessly
(live-reproduced: 879/882 symbols failed on the first real backfill attempt against
quarterly_balance_sheet). Temporarily restricted the set to quarterly_income_statement only.

FIXED 2026-09-16 (same session, follow-up): quarterly_balance_sheet/quarterly_cash_flow carry
the exact same fye_month-flip duplicate-row bug (DB-wide sweep: 1,442/417 groups respectively,
same "same core values, fiscal_year off by exactly one, same fiscal_quarter" signature) - they
just can't be reconciled by period_end since that column doesn't exist for them. Re-added both
to _QUARTERLY_TABLES_WITH_FISCAL_QUARTER_PK, routed through a value-fingerprint variant
(_reconcile_stale_fiscal_year_duplicate_value_fingerprint) that recognizes the same underlying
fact via its core reported values (_VALUE_FINGERPRINT_FIELDS) matching exactly under an
adjacent fiscal_year label instead of via period_end.
test_other_quarterly_tables_never_trigger_this_guard (renamed
test_balance_cashflow_use_value_fingerprint_reconcile below) now pins the new behavior.

BUGFIX 2026-09-16 (same session, follow-up fork - FPI/foreign-currency residual): the
value-fingerprint variant above still compared RAW pre-transform concept values, which don't
reliably equal the canonical value transform() ultimately computes and stores (FX conversion,
IFRS/alternate-concept aliasing, unit-scale normalization all happen downstream of the raw
resolve) - live-confirmed via BABA/MUFG/GGAL real SEC data this made the reconcile match 0 of a
63/29-group balance_sheet/cash_flow residual that skewed heavily toward FPI/ADR filers. Fixed
by running the same rows through self.transform() first and comparing POST-transform values
with a small relative tolerance instead of exact raw equality (live-confirmed: took the
residual to 2/4, a distinct, separately-characterized pattern - see this fix's memory entry).
test_value_fingerprint_uses_transformed_values_not_raw below pins this.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(
    statement_type: str = "income", table_name: str = "quarterly_income_statement"
) -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period="quarterly")
    loader.table_name = table_name
    return loader


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


def _mock_read_context(fetchall_result: list[tuple[Any, ...]]) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fetchall_result
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestStaleFiscalYearDuplicateReconciled:
    def test_stale_row_under_old_fiscal_year_is_deleted(self) -> None:
        """AGYS-shaped case: this run resolved fiscal_year=2023 for period_end 2022-12-31,
        but the DB still has a stale fiscal_year=2022 row for that same period_end (from
        before a fye_month confidence flip) - the stale row must be deleted."""
        loader = _make_loader()
        fresh_row = {
            "symbol": "AGYS",
            "fiscal_year": 2023,
            "fiscal_period": "Q3",
            "period_end": "2022-12-31",
            "revenue": 49_920_000,
        }
        read_ctx = _mock_read_context([(2022, 3, date(2022, 12, 31))])
        write_ctx, mock_cur = _mock_write_context()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[read_ctx, write_ctx],
            ),
        ):
            result = loader.fetch_incremental("AGYS", None)
        assert result == [fresh_row]
        delete_sql, delete_params = mock_cur.execute.call_args_list[0][0]
        assert "DELETE FROM quarterly_income_statement" in delete_sql
        assert delete_params == ("AGYS", 2022, 3)

    def test_matching_existing_row_is_left_alone(self) -> None:
        """The common case - this run's (fiscal_year, fiscal_quarter) for a period_end
        matches what's already in the DB - must not delete anything."""
        loader = _make_loader()
        fresh_row = {
            "symbol": "AAPL",
            "fiscal_year": 2024,
            "fiscal_period": "Q4",
            "period_end": "2024-09-28",
            "revenue": 391_035_000_000,
        }
        read_ctx = _mock_read_context([(2024, 4, date(2024, 9, 28))])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=read_ctx),
        ):
            result = loader.fetch_incremental("AAPL", None)
        assert result == [fresh_row]

    def test_annual_period_never_triggers_this_guard(self) -> None:
        """annual_* tables are keyed on (symbol, fiscal_year) alone - period_end collisions
        there are a different (already-handled) code path, not this one."""
        loader = _make_loader(table_name="annual_income_statement")
        loader.period = "annual"
        fresh_row = {"symbol": "AGYS", "fiscal_year": 2023, "period_end": "2023-03-31", "revenue": 198_065_000}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[fresh_row],
        ):
            result = loader.fetch_incremental("AGYS", None)
        assert result == [fresh_row]

    def test_balance_sheet_stale_value_fingerprint_row_is_deleted(self) -> None:
        """ABAT/ACI-shaped case: same total_assets/total_liabilities/stockholders_equity
        reported for fiscal_quarter=2, but the DB has it under fiscal_year=2025 (stale) while
        this run resolved fiscal_year=2026 (fresh) - the stale row must be deleted."""
        loader = _make_loader(statement_type="balance", table_name="quarterly_balance_sheet")
        # PRE-transform raw SEC concept keys (self._field_mapping), not canonical column
        # names - see this method's own docstring for the dead-code bug this pins.
        fresh_row = {
            "symbol": "ABAT",
            "fiscal_year": 2026,
            "fiscal_period": "Q2",
            "assets": 123_342_477,
            "liabilities": 4_363_822,
            "stockholders_equity": 118_978_655,
        }
        read_ctx = _mock_read_context([(2025, 2, 123_342_477, 4_363_822, 118_978_655)])
        write_ctx, mock_cur = _mock_write_context()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[read_ctx, write_ctx],
            ),
        ):
            result = loader.fetch_incremental("ABAT", None)
        assert result == [fresh_row]
        delete_sql, delete_params = mock_cur.execute.call_args_list[0][0]
        assert "DELETE FROM quarterly_balance_sheet" in delete_sql
        assert delete_params == ("ABAT", 2025, 2)

    def test_cash_flow_stale_value_fingerprint_row_is_deleted(self) -> None:
        loader = _make_loader(statement_type="cashflow", table_name="quarterly_cash_flow")
        fresh_row = {
            "symbol": "AACG",
            "fiscal_year": 2026,
            "fiscal_period": "Q3",
            "net_cash_provided_by_used_in_operating_activities": 1_000_000,
            "net_cash_provided_by_used_in_investing_activities": -200_000,
            "net_cash_provided_by_used_in_financing_activities": -50_000,
        }
        read_ctx = _mock_read_context([(2025, 3, 1_000_000, -200_000, -50_000)])
        write_ctx, mock_cur = _mock_write_context()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[read_ctx, write_ctx],
            ),
        ):
            result = loader.fetch_incremental("AACG", None)
        assert result == [fresh_row]
        delete_sql, delete_params = mock_cur.execute.call_args_list[0][0]
        assert "DELETE FROM quarterly_cash_flow" in delete_sql
        assert delete_params == ("AACG", 2025, 3)

    def test_value_fingerprint_empty_rows_does_not_crash(self) -> None:
        """BUGFIX 2026-09-16 (goal session, XBRL data-check sweep, live-confirmed via CAT
        with a real incremental `since` cutoff): an ordinary incremental fetch with no new
        SEC data returns rows=[] - the normal, common steady-state outcome, not a failure.
        self.transform() doesn't distinguish "0 rows in, 0 rows out" from "N rows in, 0
        valid rows out" and raises the same CRITICAL RuntimeError for both - calling it
        unconditionally here meant this reconcile silently no-op'd (via the broad except)
        on every ordinary no-new-data run. Must return early on empty rows before ever
        calling transform(), not attempt it and rely on the except to paper over it."""
        loader = _make_loader(statement_type="cashflow", table_name="quarterly_cash_flow")
        with patch.object(loader, "transform") as mock_transform:
            loader._reconcile_stale_fiscal_year_duplicate_value_fingerprint("EMPTY", [])
        mock_transform.assert_not_called()

    def test_balance_sheet_non_adjacent_year_match_is_left_alone(self) -> None:
        """Same values but fiscal_year is 2 apart (not the fye-flip's exact off-by-one
        signature) - a coincidental multi-year-stagnant balance sheet must not be deleted."""
        loader = _make_loader(statement_type="balance", table_name="quarterly_balance_sheet")
        fresh_row = {
            "symbol": "FLAT",
            "fiscal_year": 2026,
            "fiscal_period": "Q2",
            "assets": 500_000,
            "liabilities": 100_000,
            "stockholders_equity": 400_000,
        }
        read_ctx = _mock_read_context([(2024, 2, 500_000, 100_000, 400_000)])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=read_ctx),
        ):
            result = loader.fetch_incremental("FLAT", None)
        assert result == [fresh_row]

    def test_value_fingerprint_uses_transformed_values_not_raw(self) -> None:
        """BABA-shaped case: the RAW pre-transform value (e.g. a foreign filer's own local-
        currency fact) does not equal the existing DB row's value, but the POST-transform
        canonical value (what self.transform() actually computes, e.g. after FX conversion)
        does - the reconcile must delete the stale row based on the transformed comparison,
        not the raw one (which would find no match at all and leave the duplicate in place)."""
        loader = _make_loader(statement_type="balance", table_name="quarterly_balance_sheet")
        fresh_row = {
            "symbol": "BABA",
            "fiscal_year": 2021,
            "fiscal_period": "Q2",
            "assets": 1_433_626_000_000,  # raw CNY-denominated fact - must NOT be compared directly
            "liabilities": 900_000_000_000,
            "stockholders_equity": 533_626_000_000,
        }
        # DB already has this exact fact filed under the stale fiscal_year=2020 (USD, post-FX).
        read_ctx = _mock_read_context([(2020, 2, 210_548_685_563.23, 132_000_000_000.00, 78_548_685_563.23)])
        write_ctx, mock_cur = _mock_write_context()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch.object(
                loader,
                "transform",
                return_value=[
                    {
                        "symbol": "BABA",
                        "fiscal_year": 2021,
                        "fiscal_quarter": 2,
                        "total_assets": 210_548_685_563.23,
                        "total_liabilities": 132_000_000_000.00,
                        "stockholders_equity": 78_548_685_563.23,
                    }
                ],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[read_ctx, write_ctx],
            ),
        ):
            result = loader.fetch_incremental("BABA", None)
        assert result == [fresh_row]
        delete_sql, delete_params = mock_cur.execute.call_args_list[0][0]
        assert "DELETE FROM quarterly_balance_sheet" in delete_sql
        assert delete_params == ("BABA", 2020, 2)

    def test_row_missing_period_end_is_skipped(self) -> None:
        """A row without a resolved period_end can't safely be reconciled - must not crash
        or issue a query keyed on nothing."""
        loader = _make_loader()
        fresh_row = {"symbol": "AGYS", "fiscal_year": 2023, "fiscal_period": "Q3", "period_end": None, "revenue": None}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[fresh_row],
        ):
            result = loader.fetch_incremental("AGYS", None)
        assert result == [fresh_row]
