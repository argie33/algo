"""Regression test: _score_momentum must not warn about a "legacy 'macd' field" - that
field is the only one ever populated, not a rare backward-compat fallback.

Bug (found 2026-08-18, loader-health review): _prepare_batch_context()'s technical_data_daily
cache query (loaders/load_stock_scores.py) selects "rsi_14, macd, sma_50, sma_200, close" and
nothing else - "macd_line" is not a column on that table at all (a same-named column exists
only on the unrelated momentum_metrics table, migration 119, never queried here). A prior
commit speculatively preferred metrics.get("macd_line") with a warning-logged fallback to
"macd" - since macd_line was provably always None, this fired on ~4926/4930 symbols every
single stock_scores run: pure log noise with zero effect on the actual computed score (macd
was already the only value ever used).
"""

import logging

from loaders.load_stock_scores import StockScoresLoader


class TestMacdLineDeadFieldLogNoise:
    def test_macd_present_no_macd_line_does_not_warn(self, caplog) -> None:
        loader = StockScoresLoader()
        metrics = {
            "momentum_1m": 0.0,
            "momentum_3m": 0.0,
            "momentum_6m": 0.0,
            "momentum_12m": 0.0,
            "rsi_14": 50.0,
            "macd": 1.5,
        }

        with caplog.at_level(logging.WARNING):
            loader._score_momentum(metrics, "TEST")

        assert not any("legacy" in r.message.lower() for r in caplog.records), (
            "macd is the only field this loader ever populates - it must not be logged "
            "as a 'legacy' fallback on every symbol, every run"
        )

    def test_macd_sign_still_drives_the_score(self) -> None:
        """STALE FIXTURE FIXED 2026-09-08 (goal session score-sanity sweep): all-zero
        momentum_1m/3m/6m/12m fall inside _pct_to_score's +/-3% "weak momentum" deadzone
        (score=None, contributes no weight), and RSI+MACD alone (0.37 combined weight) sits
        below MOMENTUM_MIN_WEIGHT=0.40 (loaders/stock_scores/momentum_scoring.py) - a gate
        added after this test was written. With only that 0.37 of weight available,
        _score_momentum now correctly returns the {"data_unavailable": True, ...} thin-sample
        marker dict instead of a float, so `bullish > bearish` below raised
        `TypeError: '>' not supported between instances of 'dict' and 'dict'` rather than
        testing MACD sign at all. Giving momentum_3m a real (non-deadzone) return adds its own
        weight, clearing the 0.40 floor and restoring a genuine float-vs-float comparison.

        UPDATED AGAIN 2026-09-14 (industry-consensus Momentum reweight - see
        momentum_scoring.py's "MOM_12_1 RE-EMPHASIZED, TECH_TREND DEMOTED" docstring note):
        tech_trend's own weight dropped 25%->15%, so momentum_3m's 20% alone (0.20+0.15=0.35)
        no longer clears the 0.40 floor by itself either. momentum_1m/momentum_12m now also
        get real (non-deadzone) values so mom_12_1 (45% weight, the dominant slot now)
        contributes too - 0.20+0.45+0.15=0.80, comfortably above the floor.
        """
        loader = StockScoresLoader()
        base = {
            "momentum_1m": 2.0,
            "momentum_3m": 10.0,
            "momentum_6m": 0.0,
            "momentum_12m": 20.0,
            "rsi_14": 50.0,
        }
        bullish = loader._score_momentum(dict(base, macd=2.0), "BULL")
        bearish = loader._score_momentum(dict(base, macd=-2.0), "BEAR")

        assert isinstance(bullish, float) and isinstance(bearish, float), (
            "expected a real score, not the thin-sample data_unavailable marker dict - "
            f"bullish={bullish!r} bearish={bearish!r}"
        )
        assert bullish > bearish, "positive MACD must score higher than negative MACD"
