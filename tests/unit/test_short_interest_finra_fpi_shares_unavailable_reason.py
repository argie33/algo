"""Regression test for the 2026-08-20 FPI shares_outstanding fix.

load_sec_valuations.py's 2026-08-19 fix (commit a123cdb46, migration 1211) correctly stopped
deriving shares_outstanding for foreign private issuers from any tier that reports in
home-market (non-ADS) units - the TSM 5x-market-cap unit-mismatch bug. The side effect: FPIs
now permanently have no valid shares_outstanding source anywhere, live-confirmed 750 of 788
shares_outstanding_unavailable rows for settlement_date 2026-07-31 are FPIs, which pushed
short_interest_finra's fail rate (15.6%) past its max_fail_rate (15%) and failed the loader.

This is a permanent structural gap, not a regression - _classify_availability must tag it with
its own reason (foreign_private_issuer_shares_unavailable) distinct from a domestic filer's
shares_outstanding_unavailable/_invalid, so the fail-rate check (loaders/load_short_interest_finra.py's
run(), which excludes this reason from its numerator) doesn't trip on it every run.
"""

from loaders.load_short_interest_finra import _classify_availability

_FINRA_ROW = {"short_shares": 1_000_000, "days_to_cover": 1.5, "avg_daily_volume": 500_000}


class TestFpiSharesUnavailableReason:
    def test_fpi_with_no_shares_outstanding_gets_specific_reason(self) -> None:
        short_pct, short_shares, data_unavailable, reason = _classify_availability(
            _FINRA_ROW, outstanding=None, is_foreign_private_issuer=True, finra_data_present=True
        )

        assert short_pct is None
        assert short_shares == 1_000_000
        assert data_unavailable is True
        assert reason == "foreign_private_issuer_shares_unavailable"

    def test_domestic_filer_with_no_shares_outstanding_keeps_generic_reason(self) -> None:
        # Control: same missing-outstanding shape, but not an FPI - must not be misattributed
        # to the permanent structural gap.
        _, _, data_unavailable, reason = _classify_availability(
            _FINRA_ROW, outstanding=None, is_foreign_private_issuer=False, finra_data_present=True
        )

        assert data_unavailable is True
        assert reason == "shares_outstanding_unavailable"

    def test_fpi_with_invalid_shares_outstanding_also_gets_specific_reason(self) -> None:
        # outstanding <= 1000 (implausible/placeholder value) hits the same branch as missing.
        _, _, data_unavailable, reason = _classify_availability(
            _FINRA_ROW, outstanding=500, is_foreign_private_issuer=True, finra_data_present=True
        )

        assert data_unavailable is True
        assert reason == "foreign_private_issuer_shares_unavailable"

    def test_fpi_with_valid_shares_outstanding_computes_real_value(self) -> None:
        # FPI status alone must not suppress a real result once shares_outstanding IS available.
        short_pct, short_shares, data_unavailable, reason = _classify_availability(
            _FINRA_ROW, outstanding=10_000_000, is_foreign_private_issuer=True, finra_data_present=True
        )

        assert short_pct == 10.0
        assert short_shares == 1_000_000
        assert data_unavailable is False
        assert reason is None

    def test_no_finra_row_keeps_finra_reason_regardless_of_fpi_status(self) -> None:
        _, short_shares, data_unavailable, reason = _classify_availability(
            None, outstanding=None, is_foreign_private_issuer=True, finra_data_present=True
        )

        assert short_shares is None
        assert data_unavailable is True
        assert reason == "finra_data_unavailable"
