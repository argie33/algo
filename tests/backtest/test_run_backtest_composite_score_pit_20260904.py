"""Regression test for the 2026-09-04 real-money-readiness financial-calculation-integrity
fix: run_backtest.py could not actually test live Phase 7's real ranking mechanism
(composite_score-primary since 2026-08-27) without reintroducing look-ahead bias, because its
only composite_score source (`stock_scores`) has no date dimension - always TODAY's value.
`_get_daily_buy_signals(..., rank_by="composite_score_pit")` closes this by asof-joining
`stock_scores_history` (symbol, score_date<=signal_date) instead. See run_backtest.py's module
docstring and `_get_daily_buy_signals()`'s own docstring for the full writeup.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from algo.backtest.run_backtest import _get_daily_buy_signals


class TestRankByValidation:
    def test_invalid_rank_by_raises(self):
        with pytest.raises(ValueError, match="Invalid rank_by"):
            _get_daily_buy_signals(date(2026, 9, 3), min_composite=50.0, rank_by="not_a_real_mode")


class TestCompositeScorePitJoinsPointInTimeHistory:
    def test_composite_score_pit_queries_stock_scores_history_not_stock_scores(self):
        """The point-in-time mode must source composite_score from stock_scores_history (which
        has a score_date dimension), never from stock_scores (always-current, would be
        look-ahead bias against a historical signal_date) - this is the entire point of the
        fix, so pin the actual SQL text rather than just the returned shape."""
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = [
            ("AAPL", 150.0, 152.0, 148.0, 145.0, 1.5, 149.0, 140.0, 80.0, 75.0, 88.5, 90.0),
        ]
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_cursor
        fake_ctx.__exit__.return_value = False

        with patch("algo.backtest.run_backtest.DatabaseContext", return_value=fake_ctx) as mock_db:
            signals = _get_daily_buy_signals(date(2026, 9, 3), min_composite=50.0, rank_by="composite_score_pit")

        mock_db.assert_called_once_with("read")
        executed_sql = fake_cursor.execute.call_args[0][0]
        assert "stock_scores_history" in executed_sql
        assert "LATERAL" in executed_sql
        assert "score_date <= " in executed_sql
        # min_composite must be a real filter in this mode (unlike the default mode, where
        # it's accepted but unused) - confirm it's actually bound as a query parameter.
        params = fake_cursor.execute.call_args[0][1]
        assert 50.0 in params
        assert len(signals) == 1
        assert signals[0]["composite_score"] == 88.5

    def test_default_mode_still_queries_stock_scores_by_symbol_only(self):
        """Confirms the fix didn't change default-mode behavior (backward compatibility) -
        the default ranking key stays signal_quality_score, sourced from the symbol-only
        stock_scores join, unaffected by this change."""
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_cursor
        fake_ctx.__exit__.return_value = False

        with patch("algo.backtest.run_backtest.DatabaseContext", return_value=fake_ctx):
            _get_daily_buy_signals(date(2026, 9, 3), min_composite=50.0)

        executed_sql = fake_cursor.execute.call_args[0][0]
        assert "stock_scores_history" not in executed_sql
        assert "LEFT JOIN stock_scores s ON s.symbol = b.symbol" in executed_sql
        assert "ORDER BY b.signal_quality_score DESC" in executed_sql
