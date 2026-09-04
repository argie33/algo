"""Regression test for a 2026-09-03 fix (goal session continuation) to
load_sec_valuations.py's DOMESTIC_FILER_ADS_RATIO_OVERRIDES/FPI_EPS_ADS_RATIO_OVERRIDES ONC
entries.

ONC (BeOne Medicines Ltd, formerly BeiGene) is is_foreign_private_issuer=False in our DB
(Cayman-incorporated but files as a large accelerated DOMESTIC filer), so none of this file's
FPI-specific ADS-unit-mismatch guards apply - the same class of gap DOMESTIC_FILER_ADS_RATIO_OVERRIDES
exists for (AMRN). SEC filings (424B7, Form 4 insider-trading reports) confirm 1 ADS = 13
ordinary shares. Needs BOTH registries: shares_out is on ordinary-share basis (raw
1,417,803,727 vs a real ADS-equivalent ~109M) AND EPS is on ordinary-share basis (unadjusted
FY2025 EPS=0.20 against a $362.68 ADS price gives an implausible ~1813x PE).

Cross-validated via a live yfinance market cap fetch, independent of both registries:
shares_out/13 * price = $39.55B vs live $41.03B, within 3.6%.
"""

import pytest

from loaders.load_sec_valuations import (
    DOMESTIC_FILER_ADS_RATIO_OVERRIDES,
    FPI_EPS_ADS_RATIO_OVERRIDES,
    _fpi_ads_adjusted_eps,
)


class TestOncDualAdsRegistryEntries:
    def test_onc_registered_in_shares_out_override(self) -> None:
        assert DOMESTIC_FILER_ADS_RATIO_OVERRIDES["ONC"] == 13.0

    def test_onc_registered_in_eps_override(self) -> None:
        ratio, effective_date = FPI_EPS_ADS_RATIO_OVERRIDES["ONC"]
        assert ratio == 13.0
        assert effective_date is None

    def test_onc_eps_multiplied_by_ratio(self) -> None:
        assert _fpi_ads_adjusted_eps("ONC", 0.20, 2025) == pytest.approx(0.20 * 13.0)

    def test_shares_out_and_eps_adjustments_produce_plausible_pe(self) -> None:
        raw_shares = 1_417_803_727.0
        raw_eps = 0.20
        price = 362.68
        adj_shares = raw_shares / DOMESTIC_FILER_ADS_RATIO_OVERRIDES["ONC"]
        adj_eps = _fpi_ads_adjusted_eps("ONC", raw_eps, 2025)

        unadjusted_pe = price / raw_eps
        adjusted_pe = price / adj_eps
        adjusted_market_cap = price * adj_shares

        # Unadjusted PE is wildly implausible; adjusted PE lands in a sane biotech range.
        assert unadjusted_pe > 1000
        assert 50 < adjusted_pe < 300
        # Adjusted market cap should land within the same order of magnitude as the live
        # cross-check ($41.03B).
        assert 30_000_000_000 < adjusted_market_cap < 50_000_000_000
