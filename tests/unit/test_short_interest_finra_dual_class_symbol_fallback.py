"""Regression test for the 2026-08-18 FINRA dual-class symbol fallback fix.

FINRA's Consolidated Short Interest API strips class-share separators entirely from its
symbolCode - Berkshire Hathaway Class B is reported as "BRKB", not "BRK.B" (live-confirmed
via the real FINRA API, also verified for BF.B->"BFB", HEI.A->"HEIA", TAP.A->"TAPA"). A
plain dict lookup on our canonical "BRK.B"-style symbol always missed, marking all 23
dot-suffix dual/multi-class tickers in the universe finra_data_unavailable despite FINRA
reporting real short-interest data for every one of them.
"""

from loaders.load_short_interest_finra import _lookup_finra_row


class TestFinraDualClassSymbolFallback:
    def test_falls_back_to_separator_stripped_symbol(self) -> None:
        finra_data = {"BRKB": {"short_shares": 17_478_790, "days_to_cover": 2.42, "avg_daily_volume": 7_227_045}}

        row = _lookup_finra_row(finra_data, "BRK.B")

        assert row is not None
        assert row["short_shares"] == 17_478_790

    def test_prefers_exact_match_over_stripped_fallback(self) -> None:
        # A filer that genuinely reports under the literal dotted symbol should never be
        # shadowed by a coincidental stripped-form match for a different row.
        finra_data = {
            "BRK.B": {"short_shares": 111, "days_to_cover": 1.0, "avg_daily_volume": 1},
            "BRKB": {"short_shares": 999, "days_to_cover": 2.0, "avg_daily_volume": 2},
        }

        row = _lookup_finra_row(finra_data, "BRK.B")

        assert row is not None
        assert row["short_shares"] == 111

    def test_no_dot_symbol_not_stripped(self) -> None:
        finra_data = {"AAPL": {"short_shares": 42, "days_to_cover": 1.0, "avg_daily_volume": 1}}

        row = _lookup_finra_row(finra_data, "AAPL")

        assert row is not None
        assert row["short_shares"] == 42

    def test_missing_symbol_returns_none(self) -> None:
        assert _lookup_finra_row({}, "BRK.B") is None
