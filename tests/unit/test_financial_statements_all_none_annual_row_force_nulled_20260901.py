"""Regression test for the 2026-09-01 fix: OFRM (Once Upon a Farm, PBC) had
annual_income_statement.revenue/net_income for FY2025 and FY2026 exactly equal to that
fiscal year's real Q1-only quarterly figure (live-confirmed via OFRM's own real SEC
companyfacts JSON: the only revenue tag present has zero entries with a ~365-day span,
only quarterly/6-month-cumulative ones), driving a spurious revenue_growth_1y=43.7% into
the Growth pillar.

utils/external/sec_statements.py's period=="annual" extraction already has a 330-day
minimum-span guard (added 2026-08-09) that correctly rejects a short-duration fact today -
live-verified via a direct call: get_income_statement(client, 'OFRM', period='annual')
returns only {"fiscal_year": 2026, "fiscal_quarter": None, "revenue": None, "net_income":
None} for FY2026 and nothing at all for FY2025. But that correct rejection never reached
the DB: the returned row is non-empty (so `if not rows:` in fetch_incremental never fires,
never triggering the yfinance fallback) and its all-None value fields get silently
preserved (COALESCEd away) by preserve_on_missing_fields instead of overwriting the stale
pre-fix value - the same "correctly rejects now, but the stale value survives forever" bug
class already fixed once for the FPI-currency case (test_financial_statements_stale_fpi_
currency_force_nulled_20260831.py), never extended to this trigger condition.

Fix: fetch_incremental() now queues force-null (via the same _record_explicit_null_
rejection/post_run() path) for any row where EVERY preserve_on_missing_fields column is
None - that specifically means "found nothing usable at all for this fiscal_year" (a
legitimate partial-data case always leaves at least one field populated), scoped to just
that (symbol, fiscal_year), not the whole symbol's history like the FPI case.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader

ALL_NONE_ROW = {"symbol": "OFRM", "fiscal_year": 2026, "fiscal_quarter": None, "revenue": None, "net_income": None}


def _make_loader(period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="income", period=period)


class TestAllNoneAnnualRowForceNulled:
    def test_all_none_annual_row_queues_force_null_for_that_fiscal_year(self) -> None:
        loader = _make_loader()
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[ALL_NONE_ROW],
        ):
            result = loader.fetch_incremental("OFRM", None)
        assert result == [ALL_NONE_ROW]
        for field in loader._bulk_insert_mgr.preserve_on_missing_fields:
            assert ({"symbol": "OFRM", "fiscal_year": 2026}, field) in loader._explicit_null_rejections

    def test_quarterly_period_never_triggers_this_guard(self) -> None:
        """Quarterly period rows legitimately vary a lot - this guard is annual-only."""
        loader = _make_loader(period="quarterly")
        all_none_quarterly = {
            "symbol": "OFRM",
            "fiscal_year": 2026,
            "fiscal_quarter": 3,
            "revenue": None,
            "net_income": None,
        }
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[all_none_quarterly],
        ):
            result = loader.fetch_incremental("OFRM", None)
        assert result == [all_none_quarterly]
        assert loader._explicit_null_rejections == []

    def test_data_unavailable_marker_row_does_not_double_trigger(self) -> None:
        """A data_unavailable=True marker row is handled by the separate FPI-currency
        sweep (which checks `not r.get("data_unavailable")` for has_real_data) - this new
        guard must skip marker rows entirely, not queue a redundant/conflicting rejection."""
        loader = _make_loader()
        marker_row = {"symbol": "OFRM", "fiscal_year": 0, "data_unavailable": True, "reason": "some_reason"}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[marker_row],
        ):
            result = loader.fetch_incremental("OFRM", None)
        assert result == [marker_row]
        assert loader._explicit_null_rejections == []

    def test_partial_data_row_does_not_queue(self) -> None:
        """A row with at least one real field populated (the common 'one optional concept
        missing' case preserve_on_missing_fields exists for) must never trigger this."""
        loader = _make_loader()
        partial_row = {"symbol": "AAPL", "fiscal_year": 2024, "revenue": 391_035_000_000, "net_income": None}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[partial_row],
        ):
            result = loader.fetch_incremental("AAPL", None)
        assert result == [partial_row]
        assert loader._explicit_null_rejections == []

    def test_missing_fiscal_year_key_does_not_queue(self) -> None:
        """A row missing its own primary-key field can't safely target an UPDATE - must be
        skipped, not crash or queue a garbage rejection."""
        loader = _make_loader()
        no_pk_row = {"symbol": "OFRM", "fiscal_year": None, "revenue": None, "net_income": None}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[no_pk_row],
        ):
            result = loader.fetch_incremental("OFRM", None)
        assert result == [no_pk_row]
        assert loader._explicit_null_rejections == []


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestPostRunActuallyNullsTheStaleCell:
    def test_post_run_issues_update_for_queued_rejection(self) -> None:
        loader = _make_loader()
        loader._record_explicit_null_rejection(
            {"symbol": "OFRM", "fiscal_year": 2026}, "revenue", "no_usable_annual_duration_fact"
        )
        write_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=write_ctx):
            loader.post_run()
        # post_run() also runs _sweep_stale_implausible_eps() for statement_type=="income" -
        # this test only asserts the force-null UPDATE this fix adds is among the calls made.
        sql, params = mock_cur.execute.call_args_list[0][0]
        assert "SET revenue = NULL" in sql
        assert "annual_income_statement" in sql
        assert params == ("OFRM", 2026)

    def test_post_run_flag_sync_uses_this_rejections_real_reason(self) -> None:
        """FIXED 2026-09-03: revenue AND net_income are income's required fields, so nulling
        both here also triggers post_run()'s data_unavailable flag-sync - which, before this
        fix, hardcoded 'fpi_currency_data_rejected' for every rejection cause regardless of
        what actually happened. This row was rejected for the Q1-mislabeled-as-annual reason,
        not an FPI-currency issue - the flag-sync UPDATE must say so."""
        loader = _make_loader()
        loader._record_explicit_null_rejection(
            {"symbol": "OFRM", "fiscal_year": 2026}, "revenue", "no_usable_annual_duration_fact"
        )
        loader._record_explicit_null_rejection(
            {"symbol": "OFRM", "fiscal_year": 2026}, "net_income", "no_usable_annual_duration_fact"
        )
        write_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=write_ctx):
            loader.post_run()
        flag_sql, flag_params = mock_cur.execute.call_args_list[2][0]
        assert "data_unavailable = TRUE" in flag_sql
        assert "reason = %s" in flag_sql
        assert flag_params == ("no_usable_annual_duration_fact", "OFRM", 2026)
