"""scripts/tiingo_dual_class_gap_backfill.py: dot->dash ticker translation.

Added 2026-09-15 alongside the script itself - live-confirmed against Tiingo's real API that
WSO.B/AKO.A/etc. only resolve as WSO-B/AKO-A (see that script's own module docstring), not
retested here since that's a live network call; this test only locks in the pure translation
function's behavior.
"""

from scripts.tiingo_dual_class_gap_backfill import _to_tiingo_ticker


class TestToTiingoTicker:
    def test_dual_class_dot_becomes_dash(self):
        assert _to_tiingo_ticker("WSO.B") == "WSO-B"
        assert _to_tiingo_ticker("AKO.A") == "AKO-A"
        assert _to_tiingo_ticker("MOG.B") == "MOG-B"

    def test_plain_ticker_unaffected(self):
        assert _to_tiingo_ticker("AAPL") == "AAPL"

    def test_multiple_dots_all_translated(self):
        assert _to_tiingo_ticker("A.B.C") == "A-B-C"
