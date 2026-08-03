#!/usr/bin/env python3
"""Regression test: a real, sustained price move that fails the sequence/gap check must
not permanently deadlock a symbol's price feed.

PriceTransformer._process_row only advanced prior_close_by_symbol on accepted rows. A
genuine large single-day move that doesn't match a clean split ratio (e.g. an earnings
crash) gets correctly rejected as an unconfirmed anomaly and not written to price_daily -
but without this fix, prior_close_by_symbol stayed frozen at the pre-move price forever,
so every subsequent day was also compared against that stale reference and also rejected,
with no recovery path. This test locks in that the day after a rejected anomaly - once the
new price level is confirmed by another day's data - is accepted and inserted normally.
"""

from loaders.price_transformer import PriceTransformer


class TestSequenceCheckRecoversAfterRealCrash:
    def test_day_after_rejected_crash_is_accepted(self):
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            # Normal trading day - establishes the baseline.
            {
                "symbol": "MYGN",
                "date": "2026-07-30",
                "open": 5.07,
                "high": 5.38,
                "low": 5.03,
                "close": 5.37,
                "volume": 2156200,
            },
            # Genuine crash day (-46.7%, doesn't match any clean split ratio) - must still
            # be rejected as an unconfirmed anomaly and NOT written to price_daily.
            {
                "symbol": "MYGN",
                "date": "2026-07-31",
                "open": 3.10,
                "high": 3.26,
                "low": 2.81,
                "close": 2.86,
                "volume": 15104600,
            },
            # Next trading day confirms the new (post-crash) price level - must be
            # accepted, not rejected against the stale pre-crash baseline.
            {
                "symbol": "MYGN",
                "date": "2026-08-03",
                "open": 2.90,
                "high": 2.95,
                "low": 2.80,
                "close": 2.90,
                "volume": 8000000,
            },
        ]

        valid_rows = transformer.validate_and_transform(rows)
        valid_dates = {r["date"] for r in valid_rows}

        assert "2026-07-30" in valid_dates
        assert "2026-07-31" not in valid_dates, "the anomalous crash day itself must still be rejected"
        assert "2026-08-03" in valid_dates, (
            "the day after a rejected crash must recover once the new price level is "
            "confirmed - not stay deadlocked against the stale pre-crash reference forever"
        )

    def test_symbol_never_recovers_without_the_fix_would_fail_indefinitely(self):
        """Sanity check: a THIRD day at the same post-crash level must also pass, proving
        prior_close tracks the real recent price rather than resetting per-row."""
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "MYGN",
                "date": "2026-07-30",
                "open": 5.07,
                "high": 5.38,
                "low": 5.03,
                "close": 5.37,
                "volume": 2156200,
            },
            {
                "symbol": "MYGN",
                "date": "2026-07-31",
                "open": 3.10,
                "high": 3.26,
                "low": 2.81,
                "close": 2.86,
                "volume": 15104600,
            },
            {
                "symbol": "MYGN",
                "date": "2026-08-03",
                "open": 2.90,
                "high": 2.95,
                "low": 2.80,
                "close": 2.90,
                "volume": 8000000,
            },
            {
                "symbol": "MYGN",
                "date": "2026-08-04",
                "open": 2.88,
                "high": 2.96,
                "low": 2.85,
                "close": 2.92,
                "volume": 6000000,
            },
        ]

        valid_rows = transformer.validate_and_transform(rows)
        valid_dates = {r["date"] for r in valid_rows}

        assert valid_dates == {"2026-07-30", "2026-08-03", "2026-08-04"}
