"""Regression test for the 2026-09-05 fix: shares_outstanding_unavailable_reason being in
preserve_on_missing_fields (2026-09-04 fix) can protect a CORRECT reason from being wrongly
overwritten, but it can never CLEAR a stale one - COALESCE(EXCLUDED.col, existing.col) has no
way to write NULL over a non-NULL existing value, so once a symbol's reason gets set to
"shares_outstanding_not_in_xbrl_or_filing_text" by an old run, it stays there forever even
after a later code fix (dual-class resolution, WeightedAverage fallback, etc.) teaches the
loader to find a real shares_outstanding value for it.

Live-confirmed 67 active-universe rows this way (AMH, DDS, ARTNA, F, SF, BBBY among them):
real, current shares_outstanding sitting next to a stale "not found" reason, still counting
as a live "Missing SEC/XBRL data" gap on the coverage dashboard.

Fix: CompanyInfoSECLoader.post_run() delegates to
loaders/helpers/company_info_sec_reason_cleanup.py's clear_stale_shares_outstanding_reason(),
which issues a direct UPDATE clearing shares_outstanding_unavailable_reason wherever
shares_outstanding is already non-NULL - the only way to actually clear it, since the normal
per-symbol upsert path structurally cannot.
"""

from unittest.mock import MagicMock, patch

from loaders.helpers.company_info_sec_reason_cleanup import (
    clear_stale_shares_outstanding_reason,
    reclassify_stale_registered_investment_company_reason,
)
from loaders.load_company_info_sec import CompanyInfoSECLoader


class _FakeCursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.execute_calls: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.execute_calls.append((query, params))


def _mock_write_context(rowcount: int) -> tuple[MagicMock, _FakeCursor]:
    fake_cur = _FakeCursor(rowcount)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = fake_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, fake_cur


class TestStaleSharesOutstandingReasonClearedOnRecovery:
    def test_clears_reason_where_shares_outstanding_is_real(self) -> None:
        mock_ctx, fake_cur = _mock_write_context(rowcount=67)

        with patch(
            "loaders.helpers.company_info_sec_reason_cleanup.DatabaseContext",
            return_value=mock_ctx,
        ):
            clear_stale_shares_outstanding_reason()

        assert len(fake_cur.execute_calls) == 1
        query, params = fake_cur.execute_calls[0]
        assert "UPDATE company_info_sec" in query
        assert "SET shares_outstanding_unavailable_reason = NULL" in query
        assert "shares_outstanding IS NOT NULL" in query
        assert "shares_outstanding_unavailable_reason IS NOT NULL" in query
        assert params is None

    def test_no_op_when_nothing_stale(self) -> None:
        mock_ctx, fake_cur = _mock_write_context(rowcount=0)

        with patch(
            "loaders.helpers.company_info_sec_reason_cleanup.DatabaseContext",
            return_value=mock_ctx,
        ):
            clear_stale_shares_outstanding_reason()

        assert len(fake_cur.execute_calls) == 1

    def test_loader_post_run_delegates_to_cleanup_helper(self) -> None:
        loader = CompanyInfoSECLoader.__new__(CompanyInfoSECLoader)

        with (
            patch("loaders.load_company_info_sec.clear_stale_shares_outstanding_reason") as mock_cleanup,
            patch(
                "loaders.load_company_info_sec.reclassify_stale_registered_investment_company_reason"
            ) as mock_reclassify,
        ):
            loader.post_run()

        mock_cleanup.assert_called_once_with()
        mock_reclassify.assert_called_once_with()


class TestStaleRegisteredInvestmentCompanyReasonReclassified:
    """2026-09-09/10 fix: CompanyInfoSECLoader's exclude_etfs_from_symbols=True means
    get_active_symbols(exclude_etfs=True) never includes a symbol already classified
    entity_type in ('other','investment')/sic_code NULL (the exact CEF/RIC signature) in any
    later run's symbol list - so a symbol correctly classified as a CEF by an old run can
    never reach fetch_incremental() again, and the 2026-09-06 fix that relabels this exact
    shape from the generic "no_annual_report_filing" to "registered_investment_company_
    no_annual_report" can never actually apply to it. This is a companion self-heal:
    relabel directly from the row's own already-known entity_type/sic_code, no live SEC call
    needed."""

    def test_reclassifies_stale_generic_reason_for_cef_signature(self) -> None:
        mock_ctx, fake_cur = _mock_write_context(rowcount=88)

        with patch(
            "loaders.helpers.company_info_sec_reason_cleanup.DatabaseContext",
            return_value=mock_ctx,
        ):
            reclassify_stale_registered_investment_company_reason()

        assert len(fake_cur.execute_calls) == 1
        query, params = fake_cur.execute_calls[0]
        assert "UPDATE company_info_sec" in query
        assert "SET shares_outstanding_unavailable_reason = 'registered_investment_company_no_annual_report'" in query
        assert "shares_outstanding_unavailable_reason = 'no_annual_report_filing'" in query
        assert "entity_type IN ('other', 'investment')" in query
        assert "sic_code IS NULL" in query
        assert params is None

    def test_no_op_when_nothing_matches(self) -> None:
        mock_ctx, fake_cur = _mock_write_context(rowcount=0)

        with patch(
            "loaders.helpers.company_info_sec_reason_cleanup.DatabaseContext",
            return_value=mock_ctx,
        ):
            reclassify_stale_registered_investment_company_reason()

        assert len(fake_cur.execute_calls) == 1
