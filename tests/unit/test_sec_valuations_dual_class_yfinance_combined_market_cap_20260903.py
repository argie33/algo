"""Regression test for a 2026-09-03 fix (goal session continuation, KELYB-discovered) to
load_sec_valuations.py's DUAL_CLASS_YFINANCE_COMBINED_MARKET_CAP_SYMBOLS/_sanity_check_market_cap.

For a thin sibling class of a multi-class ticker (KELYB, LBTYB), yfinance's market_cap
reflects the COMBINED-entity share count shared across every class' ticker symbol, not that
class' own float - live-confirmed both via the frozen yfinance_snapshot table and a fresh live
re-fetch (both agree, ruling out staleness as the cause). KELYB's own SEC-derived market_cap
($76.7M off a real 3,295,941-share Class B float) was being rejected against yfinance's
$808M-830M for the same ticker - a false positive, not the genuine mis-scaled-shares bug this
check exists to catch. Confirmed via a sibling-sum cross-check: company_info_sec's
class-specific counts sum correctly across siblings (KELYA 30,915,587 + KELYB 3,295,941 =
34,211,528, matching Kelly Services' real combined ~34.6M shares outstanding) - a genuinely
mis-scaled shares_outstanding bug would NOT sum this cleanly with its siblings.
"""

from typing import Any

from loaders.load_sec_valuations import DUAL_CLASS_YFINANCE_COMBINED_MARKET_CAP_SYMBOLS, SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestDualClassYfinanceCombinedMarketCapRegistry:
    def test_registry_contains_confirmed_symbols(self) -> None:
        assert DUAL_CLASS_YFINANCE_COMBINED_MARKET_CAP_SYMBOLS == frozenset({"KELYB", "LBTYB"})


class TestSanityCheckMarketCapSkipsRegisteredSymbols:
    def test_kelyb_skips_the_ratio_check_despite_gross_mismatch(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 76_700_000.0,
            "pb_ratio": 5.0,
            "ps_ratio": 3.0,
        }
        # yfinance's ~$808M vs our $76.7M is a >10x gap that would normally trigger rejection.
        loader._sanity_check_market_cap("KELYB", result, yf_market_cap=808_038_656.0, yf_market_cap_is_live=True)

        assert result["market_cap"] == 76_700_000.0
        assert result["pb_ratio"] == 5.0
        assert result.get("reason") is None

    def test_lbtyb_skips_the_ratio_check(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"market_cap": 170_500_000.0}
        loader._sanity_check_market_cap("LBTYB", result, yf_market_cap=4_483_595_776.0, yf_market_cap_is_live=True)

        assert result["market_cap"] == 170_500_000.0
        assert result.get("reason") is None

    def test_unregistered_symbol_still_rejected_on_gross_mismatch(self) -> None:
        # Guards against the skip accidentally becoming a global bypass - a genuinely
        # mis-scaled shares_outstanding case (e.g. the already-fixed ONC) must still reject.
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 534_300_000_000.0,
            "pb_ratio": 5.0,
        }
        loader._sanity_check_market_cap("ONC", result, yf_market_cap=31_000_000_000.0, yf_market_cap_is_live=True)

        assert result["market_cap"] is None
        assert result["pb_ratio"] is None
        assert result["reason"] == "shares_outstanding_scale_mismatch"
