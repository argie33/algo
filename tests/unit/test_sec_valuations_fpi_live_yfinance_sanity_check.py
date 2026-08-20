"""Regression test for the 2026-08-20 fix (goal: finance-accuracy audit, part 2):
_sanity_check_market_cap/_sanity_check_pe_ratio read yfinance_snapshot, a table with no live
writer since Session 275 (39 days stale, live-confirmed via direct query, covering 4,522/5,210
of the active universe). For domestic filers this is redundant defense-in-depth (the
company_info_sec cross-check + MAX_PLAUSIBLE_SHARES_OUTSTANDING ceiling are both fresh and
SEC-native), but for foreign private issuers it's the PRIMARY defense - company_info_sec is
deliberately skipped for FPIs (same home-market-vs-ADS unit-mismatch risk as the primary data,
per the TSM $10.7T incident) - so a stale comparison baseline there is a real gap.

Fix: for FPI symbols specifically, fetch live via _fetch_live_fpi_yfinance_check_values()
instead of trusting the frozen table. Never a value source for pe_ratio/market_cap themselves
(those stay 100% SEC-derived) - only used to validate/reject an already-computed value, same
as the existing yfinance_snapshot-based check.

Only covers the case where an FPI's shares_outstanding DID resolve (via a domestic-form-guarded
tier like company_info_sec.shares_outstanding_dei) - a pure FPI with zero domestic-form data
(the SAP/MFC/NGG live-observed case) hits the earlier `if not shares_out` unavailable-marker
return and never reaches this code at all; that's a separate, deliberately-not-fixed gap (see
this session's memory: fixing it would mean using yfinance as a VALUE source, which conflicts
with this file's explicit "SEC data only" policy and GOVERNANCE.md's fail-fast/no-fallback
principle).
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# FPI-flagged (last element True), but shares_outstanding_basic present so the derived tiers
# get a value via the domestic-form-guarded company_info_sec tier below (fetchone_results[2]).
_FPI_WITH_RESOLVED_SHARES_INCOME_ROWS = [
    (2024, 1_500_000_000.0, 227_000_000.0, 2.7, None, None, None, None, None, None, True),
]


class TestFpiLiveYfinanceSanityCheck:
    def test_fpi_uses_live_fetch_not_stale_table(self) -> None:
        fetchone_results = [
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            (1_417_000_000.0,),  # company_info_sec shares_outstanding_dei (domestic-guarded tier)
            (376.86,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (999_999_999_999.0, 999.0),  # yfinance_snapshot (stale) - would NOT trigger mismatch if trusted
        ]

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_fpi_yfinance_check_values",
            return_value=(30_990_489_600.0, None),  # live, fresh, real ~10x-mismatched value
        ) as mock_live_fetch:
            result = _run_fetch_incremental("FPICO", _FPI_WITH_RESOLVED_SHARES_INCOME_ROWS, fetchone_results)

        mock_live_fetch.assert_called_once_with("FPICO")
        row = result[0]
        # The live (fresh) value triggered the scale-mismatch guard - proves the live fetch's
        # result was actually used, not the stale yfinance_snapshot row that would have hidden it.
        assert row["market_cap"] is None
        assert row["reason"] == "shares_outstanding_scale_mismatch"

    def test_fpi_live_fetch_failure_falls_back_to_stale_table_without_crashing(self) -> None:
        fetchone_results = [
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            (1_417_000_000.0,),
            (376.86,),
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (None, None),  # yfinance_snapshot has nothing either - both sources empty
        ]

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_fpi_yfinance_check_values",
            return_value=(None, None),
        ):
            result = _run_fetch_incremental("FPICO2", _FPI_WITH_RESOLVED_SHARES_INCOME_ROWS, fetchone_results)

        row = result[0]
        # No comparison data available anywhere - sanity check must be a no-op, not a crash.
        assert row["market_cap"] == pytest.approx(376.86 * 1_417_000_000.0, rel=1e-9)

    def test_domestic_filer_never_calls_live_fpi_fetch(self) -> None:
        income_rows = [
            (2024, 1_500_000_000.0, 227_000_000.0, 2.7, None, None, None, None, 1_417_803_727.0, None, False),
        ]
        fetchone_results = [
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            (1_417_000_000.0,),
            (376.86,),
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (450_000_000_000.0, None),
        ]

        with patch.object(SecValuationsLoader, "_fetch_live_fpi_yfinance_check_values") as mock_live_fetch:
            _run_fetch_incremental("DOMESTICCO", income_rows, fetchone_results)

        mock_live_fetch.assert_not_called()
