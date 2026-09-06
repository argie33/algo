"""Regression test for a 2026-09-03 fix (goal session continuation, DDI-discovered) to
load_sec_valuations.py's FPI_EPS_ADS_RATIO_OVERRIDES/_fpi_ads_adjusted_eps.

Live-confirmed via DDI (DoubleDown Interactive Co., Ltd.): a genuine foreign private issuer
whose shares_out is already corrected to an ADS-equivalent basis elsewhere in this file (the
FPI yfinance shares_outstanding fallback - yfinance queries per-listing/ADS-ticker), but whose
SEC-tagged earnings_per_share is reported per ordinary (home-market) share and was never
converted at all. SEC's own 424B4 prospectus and Schedule 13G ADS-count filings confirm 20 ADS
= 1 ordinary share. FY2025 SEC-tagged earnings_per_share=$41.37 (per ordinary share) against a
live ADS price of $12.97 computed an implausible PE of ~0.31 - correctly rejected by the
existing >10x sanity check as eps_scale_mismatch, but for the wrong reason: the EPS wasn't
genuinely missing/bad, it was on the wrong share-count basis. Dividing by the confirmed ADS
ratio before the sanity check runs resolves a real, plausible pe_ratio (~6.3x) instead of
leaving it permanently null.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader, _fpi_ads_adjusted_eps


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed_sql: list[str] = []
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

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
) -> tuple[list[dict[str, Any]], _RecordingCursor]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        result = loader.fetch_incremental(symbol, None)
    return result, fake_cursor


class TestFpiAdsAdjustedEpsHelper:
    def test_divide_direction_symbol(self) -> None:
        # DDI: 20 ADS = 1 ordinary share -> divide.
        assert _fpi_ads_adjusted_eps("DDI", 41.37, 2025) == pytest.approx(41.37 / 20.0)

    def test_multiply_direction_symbol(self) -> None:
        # GDS: 1 ADS = 8 ordinary shares -> multiply.
        assert _fpi_ads_adjusted_eps("GDS", 0.3110, 2024) == pytest.approx(0.3110 * 8.0)

    def test_cx_resolved_cpo_ambiguity_uses_30x(self) -> None:
        # CX: 1 ADS = 10 CPOs = 30 ordinary shares - resolved via net_income/market_cap
        # cross-check to be the per-ordinary-share (x30) basis, not per-CPO (x10).
        assert _fpi_ads_adjusted_eps("CX", 0.0217, 2024) == pytest.approx(0.0217 * 30.0)

    def test_unregistered_symbol_untouched(self) -> None:
        # NOTE: "ONC" is no longer a valid placeholder for "unregistered" - a 2026-09-03 fix
        # added it to FPI_EPS_ADS_RATIO_OVERRIDES (see
        # test_sec_valuations_onc_dual_ads_registry_20260903.py).
        assert _fpi_ads_adjusted_eps("NOTREGISTERED", 41.37, 2025) == 41.37

    def test_none_eps_passthrough(self) -> None:
        assert _fpi_ads_adjusted_eps("DDI", None, 2025) is None

    def test_stable_ratio_applies_regardless_of_fiscal_year(self) -> None:
        # No effective_date registered for DDI -> applies even to an old fiscal year.
        assert _fpi_ads_adjusted_eps("DDI", 41.37, 2015) == pytest.approx(41.37 / 20.0)

    def test_ratio_change_gated_by_effective_date(self) -> None:
        # TOUR's 1:30 ratio only took effect 2026-04-22 - a fiscal year ending before that
        # used a different, unresearched ratio and must be left unadjusted.
        assert _fpi_ads_adjusted_eps("TOUR", 0.10, 2025) == 0.10
        assert _fpi_ads_adjusted_eps("TOUR", 0.10, 2026) == pytest.approx(0.10 * 30.0)

    def test_ratio_change_gated_with_none_fiscal_year(self) -> None:
        # An unknown fiscal year for a date-gated symbol must not be guessed as post-change.
        assert _fpi_ads_adjusted_eps("TOUR", 0.10, None) == 0.10


# DDI-shaped: FY2025 SEC-tagged EPS=41.37 (per ordinary share), current_price=12.97 (ADS, live).
# Columns match the ais/cis join in fetch_incremental: fiscal_year, revenue, net_income,
# earnings_per_share, operating_income, pretax_income, depreciation_expense,
# amortization_expense, shares_outstanding_basic, income_tax_expense,
# is_foreign_private_issuer, sic_code.
_DDI_EPS_SHAPED_INCOME_ROWS = [
    (2025, 200_000_000.0, 100_000_000.0, 41.37, None, None, None, None, None, 40_000_000.0, True, "7372"),
]


class TestDdiFpiAdsRatioResolvesPeRatio:
    def test_fpi_eps_adjusted_produces_plausible_pe_ratio(self) -> None:
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            (12.97,),  # price_daily.close (live, ADS)
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check - no adjacent-year debt data
            None,  # yfinance_snapshot market_cap/pe_ratio table lookup - no row
        ]

        with (
            patch(
                "loaders.load_sec_valuations.SecValuationsLoader._fetch_live_fpi_shares_outstanding_yfinance",
                return_value=49_553_440.0,
            ),
            patch(
                "loaders.load_sec_valuations.SecValuationsLoader._fetch_live_fpi_yfinance_check_values",
                return_value=(None, None),
            ),
        ):
            result, _ = _run_fetch_incremental("DDI", _DDI_EPS_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        expected_eps = 41.37 / 20.0
        assert row.get("reason") != "eps_scale_mismatch"
        assert row["pe_ratio"] == pytest.approx(12.97 / expected_eps, abs=0.5)
