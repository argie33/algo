"""Regression test for a 2026-09-07 fix (goal session: leaderboard sanity audit,
ads_ratio_eps_pe_mismatch_foreign_adrs memory finding) adding VIPS/BABA/JD/NTES to
load_sec_valuations.py's FPI_EPS_ADS_RATIO_OVERRIDES.

Each ratio confirmed via SEC filing/press release search (see the registry's own comment for
citations) - live-confirmed via VIPS: FY2025 SEC-tagged diluted_eps=$10.10 (ordinary-share
basis) against a live ADS price of $13.20 computed pe_ratio=1.28, a nonsense "super cheap"
signal that inflated VIPS's value_score to 86.48. Vipshop's real ADS ratio is 5 ADS = 1 ordinary
share (1 ADS = 0.2 ordinary shares), giving EPS-per-ADS = $10.10 * 0.2 = $2.02 and a correct
PE ~6.53 - about 5x higher than the unadjusted figure, matching the disclosed ratio.

WB (Weibo) was investigated the same session and confirmed a genuine 1:1 ADS ratio - correctly
NOT added to the registry (no entry means no adjustment, same as every other 1:1 FPI).
"""

import pytest

from loaders.load_sec_valuations import _fpi_ads_adjusted_eps


class TestChineseAdrAdsRatioOverrides:
    def test_vips_divide_direction(self) -> None:
        # VIPS: 5 ADS = 1 ordinary share -> multiply by 0.2.
        assert _fpi_ads_adjusted_eps("VIPS", 10.10, 2025) == pytest.approx(10.10 * 0.2)

    def test_baba_multiply_direction(self) -> None:
        # BABA: 1 ADS = 8 ordinary shares -> multiply by 8.
        assert _fpi_ads_adjusted_eps("BABA", 0.797, 2026) == pytest.approx(0.797 * 8.0)

    def test_jd_multiply_direction(self) -> None:
        # JD: 1 ADS = 2 Class A ordinary shares -> multiply by 2.
        assert _fpi_ads_adjusted_eps("JD", 0.921, 2025) == pytest.approx(0.921 * 2.0)

    def test_ntes_ratio_change_gated_by_effective_date(self) -> None:
        # NTES's 1:5 ratio only took effect 2020-10-01 (was 1:25 before) - a fiscal year
        # ending before that used the old, unresearched ratio and must be left unadjusted.
        assert _fpi_ads_adjusted_eps("NTES", 1.50, 2019) == 1.50
        assert _fpi_ads_adjusted_eps("NTES", 1.50, 2025) == pytest.approx(1.50 * 5.0)

    def test_tal_not_registered_ratio_confirmed_but_cross_validation_failed(self) -> None:
        # TAL's disclosed ratio (3 ADS = 1 share) is confirmed via SEC filing, but the
        # registry's own live-data cross-check didn't converge (see the registry's own
        # comment) - deliberately excluded rather than shipped on the disclosed ratio alone.
        assert _fpi_ads_adjusted_eps("TAL", 2.75, 2026) == 2.75

    def test_wb_not_registered_confirmed_1to1(self) -> None:
        # Weibo's ADS ratio is confirmed 1:1 - deliberately excluded from the registry.
        assert _fpi_ads_adjusted_eps("WB", 1.70, 2025) == 1.70
