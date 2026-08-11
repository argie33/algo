"""Regression test for the 2026-08-11 fix: SpecializedChecker.check_sentiment_aggregate()
queried a table "sentiment_aggregate" with columns "aggregate_sentiment"/"aaii_bullish"/
"naaim_bullish" that have never existed anywhere in this schema (confirmed against
information_schema.tables). Because information_schema queries against a nonexistent table
name return zero rows rather than raising, this silently logged "Missing columns" as an ERROR
on every single run instead of ever validating real data. The real, live table for this
concept is `market_sentiment` (VIX, put/call, fear/greed, bullish/bearish/neutral %,
sentiment_score - actively written, not monitored anywhere else in data_patrol).
"""

import inspect

from algo.monitoring.data_patrol.checks.specialized import SpecializedChecker


class TestSentimentAggregateNonexistentTable:
    @staticmethod
    def _code_only(source: str) -> str:
        """Strip the leading module/method docstring so assertions check the actual
        implementation, not the explanatory prose describing the bug that was fixed."""
        doc_end = source.index('"""', source.index('"""') + 3) + 3
        return source[doc_end:]

    def test_check_sentiment_aggregate_uses_real_table_name(self):
        source = self._code_only(inspect.getsource(SpecializedChecker.check_sentiment_aggregate))

        assert "'sentiment_aggregate'" not in source, (
            "sentiment_aggregate has never been a real table - information_schema silently "
            "returns zero columns for it instead of erroring, masking this as a permanent "
            "false 'Missing columns' ERROR"
        )
        assert "'market_sentiment'" in source, (
            "the real, live sentiment table (market_sentiment) must be checked instead"
        )
        assert "aggregate_sentiment" not in source
        assert "naaim_bullish" not in source
        assert "aaii_bullish" not in source

    def test_check_sentiment_aggregate_uses_real_columns(self):
        source = self._code_only(inspect.getsource(SpecializedChecker.check_sentiment_aggregate))
        for real_col in ("sentiment_score", "bullish_pct", "bearish_pct"):
            assert real_col in source, f"required_cols must reference market_sentiment's real column {real_col}"
