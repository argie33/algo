"""Regression test for the 2026-08-23 fix: _reject_implausible_eps()/
_reject_implausible_shares_outstanding() logged "Rejecting" and set row[field]=None in
transform(), but that None was silently discarded by preserve_on_missing_fields' ON CONFLICT
clause - `COALESCE(EXCLUDED.col, table.col)` (utils/bulk_insert_manager.py) can't distinguish
"this run's fetch didn't produce a value for this optional concept" (the legitimate case
preserve_on_missing_fields exists for) from "this run fetched a value and deliberately
rejected it as implausible" - both look identical to COALESCE (EXCLUDED.col is NULL either
way), so the stale bad value silently survived on any row that already existed.

Live-confirmed via a real remediation re-fetch: OLOX FY2024/PACK FY2017-2018/RAYA
FY2020+2023/STSS FY2024 all still showed their exact pre-rejection garbage EPS in the DB
after a live re-fetch that logged each one as "Rejecting rather than storing a
confidently-wrong per-share value." 159 corrupted annual rows / 101 symbols barely moved
(153/99) despite every one being logged as rejected that run.

Fix: record every (primary key, field) the two reject_implausible_* methods null out into
self._explicit_null_rejections, then post_run() force-nulls those exact cells directly via
UPDATE ... WHERE <pk> = ... AND <field> IS NOT NULL - bypassing bulk_insert_manager's COALESCE
entirely, since that's the only way to actually overwrite a stale bad value it would
otherwise protect. Wired into both the single-combo path (runner.py's existing post_run hook)
and ALL MODE's _finalize_combo() (which never went through runner.py at all).

FOLLOW-UP FIX (2026-08-24, real-money-readiness goal session): the explicit-rejection path
above can only force-null a cell if THIS run's fetch actually returned a value for that
(symbol, fiscal_year, field) - live-confirmed a scoped 38-symbol remediation re-fetch only
cleared 5 of 85 known-bad rows, because the other 80 are older fiscal years SEC's live
companyfacts API no longer serves fresh data for, so _reject_implausible_eps() never even
sees them. post_run() now also calls _sweep_stale_implausible_eps() (income-statement tables
only), which applies the identical abs(net_income/eps) < 10,000 rule as a table-wide UPDATE
independent of what this run fetched, so every test below that exercises post_run() now sees
one extra DatabaseContext/execute call for the sweep.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestExplicitNullRejectionRecorded:
    def test_eps_rejection_records_symbol_and_fiscal_year(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "GIBO",
                "fiscal_year": 2024,
                "revenue": Decimal("30000000"),
                "net_income": Decimal("-24852333"),
                "earnings_per_share": Decimal("-24852333"),
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert ({"symbol": "GIBO", "fiscal_year": 2024}, "earnings_per_share") in loader._explicit_null_rejections

    def test_shares_outstanding_absolute_floor_rejection_records(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "PACK",
                "fiscal_year": 2017,
                "revenue": Decimal("50000000"),
                "net_income": Decimal("27700000"),
                "shares_outstanding_basic": Decimal("995"),
                "shares_outstanding_diluted": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert (
            {"symbol": "PACK", "fiscal_year": 2017},
            "shares_outstanding_basic",
        ) in loader._explicit_null_rejections

    def test_no_rejection_leaves_list_empty(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "revenue": Decimal("400000000000"),
                "net_income": Decimal("100000000000"),
                "earnings_per_share": Decimal("6.50"),
                "diluted_eps": Decimal("6.48"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []

    def test_quarterly_primary_key_includes_fiscal_quarter(self) -> None:
        loader = _make_loader(period="quarterly")
        rows = [
            {
                "symbol": "HAL",
                "fiscal_year": 2021,
                "fiscal_quarter": 2,
                "revenue": Decimal("3200000000"),
                "net_income": Decimal("-158000000"),
                "earnings_per_share": Decimal("-158000000"),
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        pk, field = loader._explicit_null_rejections[0]
        assert pk == {"symbol": "HAL", "fiscal_year": 2021, "fiscal_quarter": 2}
        assert field == "earnings_per_share"


class TestPostRunForcesNull:
    def test_post_run_issues_update_for_each_recorded_rejection(self) -> None:
        loader = _make_loader()
        loader._explicit_null_rejections = [
            ({"symbol": "OLOX", "fiscal_year": 2024}, "earnings_per_share"),
            ({"symbol": "OLOX", "fiscal_year": 2024}, "diluted_eps"),
        ]
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        # 2 explicit-rejection UPDATEs + 1 table-wide sweep UPDATE
        assert mock_cur.execute.call_count == 3
        queries = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any("earnings_per_share = NULL" in q and "symbol = %s AND fiscal_year = %s" in q for q in queries)
        assert any("diluted_eps = NULL" in q for q in queries)
        assert any("abs(net_income / earnings_per_share) < 10000" in q for q in queries)

    def test_post_run_no_op_when_nothing_rejected(self) -> None:
        """No per-row explicit rejections this run, but the table-wide sweep still runs -
        it's independent of what this run fetched."""
        loader = _make_loader()
        assert loader._explicit_null_rejections == []
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx) as mock_dc:
            loader.post_run()
        mock_dc.assert_called_once()
        assert mock_cur.execute.call_count == 1
        assert "abs(net_income / earnings_per_share) < 10000" in mock_cur.execute.call_args.args[0]

    def test_post_run_dedupes_identical_rejections(self) -> None:
        """Same (row, field) recorded twice (e.g. both reject_implausible_* methods happened
        to touch the same cell) must only issue one UPDATE for the explicit-rejection path
        (plus the always-on table-wide sweep)."""
        loader = _make_loader()
        loader._explicit_null_rejections = [
            ({"symbol": "PACK", "fiscal_year": 2017}, "shares_outstanding_basic"),
            ({"symbol": "PACK", "fiscal_year": 2017}, "shares_outstanding_basic"),
        ]
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        assert mock_cur.execute.call_count == 2

    def test_post_run_skips_rejection_with_missing_pk_value(self) -> None:
        """Defensive: a row missing a primary-key value (shouldn't happen for a real fetched
        row) must not produce a malformed UPDATE with a NULL in the WHERE clause. The
        table-wide sweep still runs regardless."""
        loader = _make_loader()
        loader._explicit_null_rejections = [({"symbol": "ZZZZ", "fiscal_year": None}, "earnings_per_share")]
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        assert mock_cur.execute.call_count == 1
        assert "abs(net_income / earnings_per_share) < 10000" in mock_cur.execute.call_args.args[0]

    def test_post_run_uses_quarterly_primary_key_in_where_clause(self) -> None:
        loader = _make_loader(period="quarterly")
        loader._explicit_null_rejections = [
            ({"symbol": "HAL", "fiscal_year": 2021, "fiscal_quarter": 2}, "earnings_per_share"),
        ]
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        # First call is the explicit-rejection UPDATE; second is the table-wide sweep (no params).
        query, params = mock_cur.execute.call_args_list[0].args
        assert "fiscal_quarter = %s" in query
        assert params == ("HAL", 2021, 2)


class TestFinalizeComboCallsPostRun:
    def test_all_mode_finalize_combo_invokes_post_run(self) -> None:
        """ALL MODE (_finalize_combo) never went through runner.py's own post_run hook -
        must call it directly so the force-null fix actually reaches production's real
        invocation path, not just single-combo/run_loader() mode."""
        from loaders.load_financial_statements import _finalize_combo

        loader = _make_loader()
        loader._explicit_null_rejections = [({"symbol": "OLOX", "fiscal_year": 2024}, "earnings_per_share")]
        loader._stats.set("symbols_failed", 0)
        loader._update_final_status = MagicMock()
        loader._log_execution_history = MagicMock()

        mock_ctx, mock_cur = _mock_write_context()
        with (
            patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx),
            patch("algo.reporting.metrics.MetricsPublisher") as mock_metrics,
        ):
            mock_metrics.return_value.__enter__.return_value = MagicMock()
            ok = _finalize_combo(loader, symbol_count=1, duration_sec=1.0, symbols=["OLOX"])

        assert ok is True
        # 1 explicit-rejection UPDATE + 1 table-wide sweep UPDATE
        assert mock_cur.execute.call_count == 2
        loader._log_execution_history.assert_called_once_with("success")
