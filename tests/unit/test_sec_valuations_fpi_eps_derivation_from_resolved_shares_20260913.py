"""Regression test (2026-09-13, goal: "question our own assumptions" audit).

BP/AZUL/FMX/BIPC/etc. (the eps_never_tagged_in_filings bucket's foreign private issuers)
never tag any EPS concept in their SEC XBRL filings, but have real net_income and a real,
already-resolved shares_out (via the yfinance FPI fallback tier in
SharesOutstandingResolutionMixin._resolve_shares_outstanding). SecValuationsLoader.
_derive_fpi_eps_from_resolved_shares computes ttm_eps_basic = net_income / shares_out for
exactly this case, called from fetch_incremental right after shares_out is confirmed
resolved (non-null, positive).

This supersedes an earlier same-day attempt to do this inside
IncomeStatementContextMixin._fetch_income_statement_context using
company_info_sec.shares_outstanding, cross-checked against yfinance - live-tested against a
real BP loader run and found ineffective: company_info_sec.shares_outstanding is NULL for
BP (a domestic-forms-only field, empty for exactly this population by construction - see
test_sec_valuations_derived_eps_from_net_income_shares_20260910.py's own updated docstring).
shares_out is the right basis instead: every SEC-sourced tier in
_resolve_shares_outstanding is gated off for FPIs, so for is_foreign_private_issuer=True,
a resolved shares_out can only have come from the already-yfinance-verified tier - no
second cross-check needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


class TestDeriveFpiEpsFromResolvedShares:
    def test_fpi_with_net_income_and_resolved_shares_derives_eps(self) -> None:
        result = SecValuationsLoader._derive_fpi_eps_from_resolved_shares(
            ttm_eps_basic=None,
            is_foreign_private_issuer=True,
            ttm_net_income=1_295_000_000.0,
            shares_out=2_575_404_456.0,
        )
        assert result == 1_295_000_000.0 / 2_575_404_456.0

    def test_domestic_filer_not_touched(self) -> None:
        """This helper is FPI-only - a domestic filer's ttm_eps_basic (already resolved or
        still None) must pass through unchanged; the domestic derivation tier lives
        entirely in IncomeStatementContextMixin, upstream of this call."""
        result = SecValuationsLoader._derive_fpi_eps_from_resolved_shares(
            ttm_eps_basic=None,
            is_foreign_private_issuer=False,
            ttm_net_income=1_000_000.0,
            shares_out=500_000.0,
        )
        assert result is None

    def test_real_tagged_eps_wins_over_derivation(self) -> None:
        result = SecValuationsLoader._derive_fpi_eps_from_resolved_shares(
            ttm_eps_basic=0.52,
            is_foreign_private_issuer=True,
            ttm_net_income=1_295_000_000.0,
            shares_out=2_575_404_456.0,
        )
        assert result == 0.52

    def test_no_net_income_not_derived(self) -> None:
        result = SecValuationsLoader._derive_fpi_eps_from_resolved_shares(
            ttm_eps_basic=None,
            is_foreign_private_issuer=True,
            ttm_net_income=None,
            shares_out=2_575_404_456.0,
        )
        assert result is None


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone/fetchall stand-in - see the sibling FPI shares-gate tests'
    _FakeCursor docstrings for why fetchall() must be sequential (income_rows first, then
    the DCF 3-year-average-FCF fallback's cash_rows)."""

    def __init__(self, income_rows, fetchone_results) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self):
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self):
        if self._fetchone_idx >= len(self._fetchone_results):
            return None
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


class TestFpiEpsDerivationIntegration:
    def test_bp_shaped_fpi_gets_real_pe_ratio(self) -> None:
        """End-to-end: an FPI with real net_income every year, no tagged EPS ever, and a
        real yfinance-resolved shares_out must come out with a real pe_ratio - not
        data_unavailable, not eps_never_tagged_in_filings."""
        income_rows = [
            (
                2025,
                192_549_000_000.0,
                1_295_000_000.0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                True,
                2911,
                None,
                None,
            ),
        ]
        fetchone_results = [
            None,  # entity_type exemption gate check - not exempt
            (30_000_000_000.0,),  # cash_and_equivalents
            (72_529_000_000.0, None, None, None),  # debt_row
            # company_info_sec/dei fallback tiers are gated off for FPI - no fetchone entries
            (46.10,),  # price_daily.close
            (200_000_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check
        ]

        loader = _make_loader()
        fake_cursor = _FakeCursor(income_rows, fetchone_results)
        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with (
            patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx),
            patch.object(
                SecValuationsLoader, "_fetch_live_fpi_shares_outstanding_yfinance", return_value=2_575_404_456.0
            ),
            patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
        ):
            result = loader.fetch_incremental("BP", None)

        row = result[0]
        assert not row.get("data_unavailable")
        assert row.get("pe_ratio") == pytest.approx(46.10 / (1_295_000_000.0 / 2_575_404_456.0), abs=0.01)
