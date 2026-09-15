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

    def test_macd_sign_no_longer_affects_the_score(self) -> None:
        """UPDATED 2026-09-15 (WEIGHTS REBALANCED, see momentum_scoring.py's own docstring):
        MACD (along with RSI and SMA-position) was demoted to informational-only - no
        institutional Momentum factor definition uses technical indicators, and live-
        verifying against fresh MTUM holdings confirmed removing them roughly doubled real-
        fund rank correlation. This test now asserts the opposite of its pre-fix version:
        with identical momentum_1m/3m/6m/12m/rsi inputs, MACD sign must NOT move
        momentum_score at all anymore (this file's other test above already confirms MACD's
        raw value is still correctly wired for display, just not scored)."""
        loader = StockScoresLoader()
        base = {
            "momentum_1m": 2.0,
            "momentum_3m": 10.0,
            "momentum_6m": 5.0,
            "momentum_12m": 20.0,
            "rsi_14": 50.0,
        }
        bullish = loader._score_momentum(dict(base, macd=2.0), "BULL")
        bearish = loader._score_momentum(dict(base, macd=-2.0), "BEAR")

        assert isinstance(bullish, float) and isinstance(bearish, float), (
            "expected a real score, not the thin-sample data_unavailable marker dict - "
            f"bullish={bullish!r} bearish={bearish!r}"
        )
        assert bullish == bearish, "MACD sign must no longer affect momentum_score"
