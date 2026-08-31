"""Regression test for a 2026-08-31 fix (goal: data-coverage sweep) to load_sec_valuations.py.

yfinance_snapshot has had no active writer since Session 275 - live-confirmed 100% of its
4,683 rows are frozen at 2026-07-04/07-12 (7-8 weeks stale as of this fix), yet
_sanity_check_market_cap/_sanity_check_pe_ratio treated it as live ground truth and rejected
any SEC-derived value disagreeing >10x against it. An 8-week-old market_cap/pe_ratio easily
drifts >10x from the real current value for a volatile small/mid-cap purely from normal price
movement - not evidence of a mis-scaled shares_outstanding/EPS. Live-confirmed via AMRN
(Amarin): SEC-derived market_cap=$5.86B (price $13.97 x 419.5M shares, both independently
correct per company_info_sec and annual_income_statement) was rejected against the frozen
table's $312M (implying $0.74/share) - AMRN's real market cap is ~$6.00B per live external
quotes. This hit 66 active symbols, including liquid non-micro-caps like FUBO and GENI, not
just illiquid shells.

Fix: before finalizing a rejection sourced from the (guaranteed-stale) table value, both sanity
checks now try one bounded live yfinance re-check (the same helper the FPI/>$50B tiers already
use) and re-evaluate the ratio against that fresher number first. Only symbols already heading
toward rejection pay the extra live-fetch cost - not the whole universe. When the value passed
in already came from a live fetch (yf_*_is_live=True), no redundant second fetch happens.
"""

from typing import Any
from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestStaleYfinanceSnapshotLiveRecheck:
    def test_market_cap_stale_mismatch_rescued_by_live_recheck(self) -> None:
        """AMRN-shaped: SEC-derived market_cap disagrees >10x with the frozen table value, but
        a live re-check agrees within tolerance - the row must NOT be nulled."""
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 5_860_000_000.0,
            "pb_ratio": 3.1,
            "ps_ratio": 2.0,
            "fcf_yield": 0.05,
            "reason": None,
        }
        with patch.object(loader, "_fetch_live_fpi_yfinance_check_values", return_value=(6_000_000_000.0, None)):
            loader._sanity_check_market_cap("AMRN", result, 312_020_320.0, yf_market_cap_is_live=False)

        assert result["market_cap"] == 5_860_000_000.0
        assert result["pb_ratio"] == 3.1
        assert result["reason"] is None

    def test_market_cap_still_mismatched_after_live_recheck_is_nulled(self) -> None:
        """If the live re-check itself still disagrees >10x, the rejection must still fire -
        this fix must not turn genuine scale mismatches into false accepts."""
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 5_860_000_000.0,
            "pb_ratio": 3.1,
            "ps_ratio": 2.0,
            "fcf_yield": 0.05,
            "reason": None,
        }
        with patch.object(loader, "_fetch_live_fpi_yfinance_check_values", return_value=(5_000_000.0, None)):
            loader._sanity_check_market_cap("BADCO", result, 312_020_320.0, yf_market_cap_is_live=False)

        assert result["market_cap"] is None
        assert result["reason"] == "shares_outstanding_scale_mismatch"

    def test_market_cap_live_fetch_failure_falls_back_to_stale_table_rejection(self) -> None:
        """When the live re-check itself fails (fails open, returns None), behavior must match
        the pre-fix path exactly - no regression when live data is unavailable."""
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 5_860_000_000.0,
            "pb_ratio": 3.1,
            "ps_ratio": 2.0,
            "fcf_yield": 0.05,
            "reason": None,
        }
        with patch.object(loader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None)) as mock_fetch:
            loader._sanity_check_market_cap("AMRN", result, 312_020_320.0, yf_market_cap_is_live=False)

        mock_fetch.assert_called_once()
        assert result["market_cap"] is None
        assert result["reason"] == "shares_outstanding_scale_mismatch"

    def test_already_live_value_does_not_trigger_a_second_fetch(self) -> None:
        """yf_market_cap_is_live=True (FPI / >$50B-ceiling tiers) means the comparison value
        is already the best available live number - no redundant second live fetch."""
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 5_860_000_000.0,
            "pb_ratio": 3.1,
            "ps_ratio": 2.0,
            "fcf_yield": 0.05,
            "reason": None,
        }
        with patch.object(loader, "_fetch_live_fpi_yfinance_check_values") as mock_fetch:
            loader._sanity_check_market_cap("FPICO", result, 5_000_000.0, yf_market_cap_is_live=True)

        mock_fetch.assert_not_called()
        assert result["market_cap"] is None

    def test_pe_ratio_stale_mismatch_rescued_by_live_recheck(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"pe_ratio": 500.0, "peg_ratio": 5.0, "pb_ratio": 3.1, "reason": None}
        with patch.object(loader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, 60.0)):
            loader._sanity_check_pe_ratio("ONC", result, 1.0, yf_value_is_live=False)

        assert result["pe_ratio"] == 500.0
        assert result["reason"] is None

    def test_pe_ratio_live_fetch_failure_falls_back_to_stale_table_rejection(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"pe_ratio": 1884.30, "peg_ratio": 5.0, "pb_ratio": 3.1, "reason": None}
        with patch.object(loader, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None)):
            loader._sanity_check_pe_ratio("ONC", result, 1.0, yf_value_is_live=False)

        assert result["pe_ratio"] is None
        assert result["reason"] == "eps_scale_mismatch"
