"""Regression test for a 2026-09-10 fix (goal: "SEC/XBRL missing data under 300" push,
shares_outstanding_scale_mismatch bucket) to load_sec_valuations.py's
YFINANCE_STALE_SHARES_TRUST_SEC_SYMBOLS/_sanity_check_market_cap.

BIAF (BioAffinity Technologies): SEC's own dei:EntityCommonStockSharesOutstanding history shows
a real, filed-on-cover-page share count climbing 4,498,675 -> 4,534,906 -> 8,101,725 (most
recent 10-Q, filed 2026-08-03) from a real dilutive capital raise. Live yfinance still reports
sharesOutstanding=600,736 - neither today's count nor either of the two prior real quarters, and
no filed reverse split explains a further ~13x drop from the confirmed-current figure. yfinance's
own field is stale for this illiquid microcap, same failure class as the AMRN frozen-snapshot
case but hitting the live API's sharesOutstanding field itself (not just marketCap), so the
existing shares_ratio<=3 rescue in _sanity_check_market_cap can't catch it.
"""

from typing import Any

from loaders.load_sec_valuations import YFINANCE_STALE_SHARES_TRUST_SEC_SYMBOLS, SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestYfinanceStaleSharesTrustSecRegistry:
    def test_registry_contains_confirmed_symbol(self) -> None:
        assert YFINANCE_STALE_SHARES_TRUST_SEC_SYMBOLS == frozenset({"BIAF"})


class TestSanityCheckMarketCapSkipsRegisteredSymbols:
    def test_biaf_skips_the_ratio_check_despite_gross_mismatch(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {
            "market_cap": 76_075_197.75,
            "pb_ratio": 5.0,
            "ps_ratio": 3.0,
        }
        # yfinance's stale sharesOutstanding-derived ~$5.6M vs our real $76.1M is a >10x gap
        # that would normally trigger rejection.
        loader._sanity_check_market_cap("BIAF", result, yf_market_cap=5_640_911.0, yf_market_cap_is_live=True)

        assert result["market_cap"] == 76_075_197.75
        assert result["pb_ratio"] == 5.0
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
