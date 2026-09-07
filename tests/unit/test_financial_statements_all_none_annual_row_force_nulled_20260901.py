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

from typing import Any
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
        missing' case preserve_on_missing_fields exists for) must never trigger this.

        Uses a raw pre-transform concept key ("revenue_from_contract_with_customer_
        excluding_assessed_tax"), not the canonical "revenue" column name - fetch_incremental's
        `rows` here are pre-transform (see the 2026-09-07 fix comment in fetch_incremental for
        the CELH/DXCM/SHOP/NU regression this distinguishes from: a fixture keyed by the
        canonical name would pass even with that bug present, since real raw rows never carry
        a literal "revenue"/"net_income" key at all).
        """
        loader = _make_loader()
        partial_row = {
            "symbol": "AAPL",
            "fiscal_year": 2024,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 391_035_000_000,
            "net_income_loss": None,
        }
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


def _mock_read_context(fetchall_result: list[tuple[Any, ...]]) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fetchall_result
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestExistingRealDataProtectedFromTransientFetchGap:
    """Regression test for the 2026-09-07 fix: the 2026-09-06 guard above force-nulled a row
    the instant THIS run's fetch came back with no required fields, with no check against
    what's already stored - live-confirmed to have wiped real annual_income_statement data
    (revenue/net_income) for 3,013 of 5,015 symbols in one run on 2026-09-07, including AAPL
    FY2024/FY2025 (real net_income $93.7B/$112.0B), because a single run's fetch transiently
    missed the required fields even though a direct fetch_incremental()+transform() call
    immediately afterward reproduced the correct values. A row that already has confirmed
    real required-field data on file must not be force-nulled just because one run's fetch
    came back empty - only a row that NEVER had real data on file should be.
    """

    def test_existing_real_data_blocks_force_null_on_transient_empty_fetch(self) -> None:
        loader = _make_loader()
        all_none_row = {
            "symbol": "AAPL",
            "fiscal_year": 2024,
            "fiscal_quarter": None,
            "revenue": None,
            "net_income": None,
        }
        # DB already has real revenue/net_income on file for AAPL FY2024 - this run's fetch
        # came back empty (transient), so the existing real data must win.
        read_ctx = _mock_read_context([("AAPL", 2024, 93_736_000_000, 391_035_000_000)])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[all_none_row],
            ),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=read_ctx),
        ):
            result = loader.fetch_incremental("AAPL", None)
        assert result == [all_none_row]
        assert loader._explicit_null_rejections == []

    def test_no_existing_real_data_still_force_nulls(self) -> None:
        """A fiscal year the DB has never had real required-field data for (the guard's
        original ALMR/MRLN-class target) must still be force-nulled - this fix only protects
        rows that already have confirmed real data on file."""
        loader = _make_loader()
        all_none_row = {
            "symbol": "OFRM",
            "fiscal_year": 2026,
            "fiscal_quarter": None,
            "revenue": None,
            "net_income": None,
        }
        read_ctx = _mock_read_context([])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[all_none_row],
            ),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=read_ctx),
        ):
            result = loader.fetch_incremental("OFRM", None)
        assert result == [all_none_row]
        for field in loader._bulk_insert_mgr.preserve_on_missing_fields:
            assert ({"symbol": "OFRM", "fiscal_year": 2026}, field) in loader._explicit_null_rejections


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
