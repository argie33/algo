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
        loader = StockScoresLoader()
        base = {
            "momentum_1m": 0.0,
            "momentum_3m": 0.0,
            "momentum_6m": 0.0,
            "momentum_12m": 0.0,
            "rsi_14": 50.0,
        }
        bullish = loader._score_momentum(dict(base, macd=2.0), "BULL")
        bearish = loader._score_momentum(dict(base, macd=-2.0), "BEAR")

        assert bullish > bearish, "positive MACD must score higher than negative MACD"
