"""Regression test for the 2026-09-02 fix: post_run()'s force-null UPDATE (used by
_reject_stale_fpi_currency_data/_reject_implausible_eps/_reject_implausible_shares_outstanding
via _explicit_null_rejections) only ever touched the value column it was told to null - it
never revisited data_unavailable/reason, which stayed at whatever a PRIOR successful run last
wrote (typically data_unavailable=FALSE/reason=NULL, from when the row genuinely had real
data).

Live-confirmed: CIG/GGB/STNE/XP/SUZ/ABEV/VIV/PAGS and ~50 more FPI symbols had
annual_balance_sheet rows with EVERY column NULL (total_assets, stockholders_equity, etc, all
force-nulled by _reject_stale_fpi_currency_data as stale unconvertible-currency values) but
data_unavailable=FALSE/reason=NULL - a strictly worse state than "missing", since any
downstream query filtering `WHERE data_unavailable = FALSE` (the normal "give me real rows"
filter used throughout the codebase) silently got NULLs back instead of skipping the row.
BMA/LOMA/CEPU had already self-corrected to data_unavailable=TRUE because a later run happened
to re-fetch and re-transform() those exact fiscal years (transform() has its own, correct
required-field check), proving this is a real, reachable state, not a hypothetical.

Fix: post_run() now tracks which primary keys had a REQUIRED field (per statement type -
revenue/net_income for income, total_assets/stockholders_equity for balance,
operating_cash_flow for cashflow) force-nulled, and for exactly those rows, issues a follow-up
UPDATE setting data_unavailable=TRUE/reason='fpi_currency_data_rejected' - but only when every
required field is still NULL after the force-null (a row that still has SOME required data must
not be marked unavailable). Rows where only an OPTIONAL field (eps, diluted_eps,
shares_outstanding_basic - the _reject_implausible_* rejections) was force-nulled are
deliberately excluded from this check, since nulling an optional field can never make a row
"required-data-empty" and checking anyway would be a pointless extra query on the far more
common eps/shares rejection path.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "balance", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


class _FakeCursor:
    """Mimics psycopg2 cursor.rowcount per-call via a queue, since real force-null UPDATEs
    and the flag-sync follow-up UPDATE need different rowcount outcomes within one test."""

    def __init__(self, rowcounts: list[int]) -> None:
        self._rowcounts = list(rowcounts)
        self.execute_calls: list[tuple[str, Any]] = []
        self.rowcount = 0

    def execute(self, query: str, params: Any = None) -> None:
        self.execute_calls.append((query, params))
        self.rowcount = self._rowcounts.pop(0) if self._rowcounts else 0


def _mock_write_context(rowcounts: list[int]) -> tuple[MagicMock, _FakeCursor]:
    fake_cur = _FakeCursor(rowcounts)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = fake_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, fake_cur


class TestPostRunFlagsRequiredFieldForceNulls:
    def test_balance_sheet_required_field_null_flips_data_unavailable(self) -> None:
        """total_assets/stockholders_equity are the balance sheet's required fields - both
        force-nulled for the same pk must trigger exactly one flag-sync UPDATE."""
        loader = _make_loader(statement_type="balance")
        loader._explicit_null_rejections = [
            ({"symbol": "GGB", "fiscal_year": 2024}, "total_assets"),
            ({"symbol": "GGB", "fiscal_year": 2024}, "stockholders_equity"),
        ]
        # rowcount=1 for each of the 2 force-null UPDATEs, then rowcount=1 for the 1 flag-sync UPDATE
        mock_ctx, fake_cur = _mock_write_context([1, 1, 1])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        assert len(fake_cur.execute_calls) == 3
        flag_query, flag_params = fake_cur.execute_calls[2]
        assert "data_unavailable = TRUE" in flag_query
        # FIXED 2026-09-03: reason is now a bound parameter, not a hardcoded literal, so
        # every rejection cause gets its own real reason instead of always
        # 'fpi_currency_data_rejected' (see _record_explicit_null_rejection). These tests
        # pre-seed _explicit_null_rejections directly, bypassing _rejection_reasons, so
        # post_run() falls back to 'fpi_currency_data_rejected' - same value as before,
        # just passed as a parameter now.
        assert "reason = %s" in flag_query
        assert "total_assets IS NULL" in flag_query
        assert "stockholders_equity IS NULL" in flag_query
        assert "data_unavailable = FALSE" in flag_query
        assert flag_params == ("fpi_currency_data_rejected", "GGB", 2024)

    def test_optional_field_only_rejection_never_triggers_flag_sync(self) -> None:
        """eps/shares_outstanding rejections (income/other optional fields) must not trigger
        the flag-sync query at all - only a REQUIRED field being nulled can."""
        loader = _make_loader(statement_type="income")
        loader._explicit_null_rejections = [
            ({"symbol": "OLOX", "fiscal_year": 2024}, "earnings_per_share"),
        ]
        mock_ctx, fake_cur = _mock_write_context([1])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            with patch.object(loader, "_sweep_stale_implausible_eps"):
                loader.post_run()
        assert len(fake_cur.execute_calls) == 1
        assert "data_unavailable" not in fake_cur.execute_calls[0][0]

    def test_required_field_still_has_a_value_does_not_flag(self) -> None:
        """Only revenue was force-nulled, but net_income (the sibling required field) still
        has a real value in the DB - the flag-sync UPDATE's own WHERE clause must not flip
        data_unavailable for a row that still has usable required data."""
        loader = _make_loader(statement_type="income")
        loader._explicit_null_rejections = [
            ({"symbol": "PARTIAL", "fiscal_year": 2023}, "revenue"),
        ]
        # force-null UPDATE affects 1 row; flag-sync UPDATE's WHERE (... AND net_income IS
        # NULL) matches nothing since net_income is real, so rowcount=0.
        mock_ctx, fake_cur = _mock_write_context([1, 0])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            with patch.object(loader, "_sweep_stale_implausible_eps"):
                loader.post_run()
        assert len(fake_cur.execute_calls) == 2
        flag_query, flag_params = fake_cur.execute_calls[1]
        assert "revenue IS NULL" in flag_query
        assert "net_income IS NULL" in flag_query
        assert flag_params == ("fpi_currency_data_rejected", "PARTIAL", 2023)

    def test_force_null_no_rows_matched_skips_flag_sync(self) -> None:
        """If the force-null UPDATE itself matched zero rows (field was already NULL), the
        pk must not be queued for a flag-sync check at all."""
        loader = _make_loader(statement_type="balance")
        loader._explicit_null_rejections = [
            ({"symbol": "ALREADY", "fiscal_year": 2022}, "total_assets"),
        ]
        mock_ctx, fake_cur = _mock_write_context([0])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        assert len(fake_cur.execute_calls) == 1

    def test_cashflow_required_field_uses_operating_cash_flow(self) -> None:
        # A cashflow-type run also triggers the 2026-09-03 free_cash_flow recompute sweep
        # (see test_financial_statements_free_cash_flow_sweep_20260903.py) - one extra
        # execute() call beyond the force-null + flag-sync pair this test itself covers.
        loader = _make_loader(statement_type="cashflow")
        loader._explicit_null_rejections = [
            ({"symbol": "FXE", "fiscal_year": 2021}, "operating_cash_flow"),
        ]
        mock_ctx, fake_cur = _mock_write_context([1, 1, 0])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        assert len(fake_cur.execute_calls) == 3
        flag_query, _ = fake_cur.execute_calls[1]
        assert "operating_cash_flow IS NULL" in flag_query
        assert "UPDATE annual_cash_flow" in fake_cur.execute_calls[2][0]
        assert "free_cash_flow = operating_cash_flow - capex" in fake_cur.execute_calls[2][0]

    def test_no_rejections_never_touches_flag_sync(self) -> None:
        loader = _make_loader(statement_type="balance")
        assert loader._explicit_null_rejections == []
        mock_ctx, fake_cur = _mock_write_context([])
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx) as mock_dc:
            loader.post_run()
        mock_dc.assert_not_called()
        assert fake_cur.execute_calls == []
