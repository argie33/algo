#!/usr/bin/env python3
"""Regression test: _compute_stock_score's success-path result dict must always include
"reason_type" (added 2026-09-01, /goal session).

BUG: only fetch_incremental's two exception-handling branches set reason_type (to
"loader_failed"). Since BulkInsertManager derives each row's UPSERT column list from that row's
own dict keys, a symbol that failed once (reason_type='loader_failed' persisted) and later
recovered never had reason_type in its column list on the recovery write - the stale
'loader_failed' value was silently carried forward FOREVER, untouched by every subsequent
successful re-score. Live-confirmed 2026-09-01: 80 symbols (incl. NVDA, BRK.A, BRK.B) sat at
reason_type='loader_failed' despite full completeness and real scored pillars.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader


class TestReasonTypeAlwaysWrittenOnSuccessPath:
    def _compute(self) -> dict:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        loader._min_completeness_threshold = 70.0

        with (
            patch("loaders.load_stock_scores.DatabaseContext") as mock_db_ctx,
            patch.object(loader, "_get_quality_metrics", return_value={}),
            patch.object(loader, "_get_growth_metrics", return_value={}),
            patch.object(loader, "_get_value_metrics", return_value={}),
            patch.object(loader, "_get_stability_metrics", return_value={}),
            patch.object(loader, "_get_momentum_metrics", return_value={}),
            patch.object(loader, "_score_quality", return_value=80.0),
            patch.object(loader, "_score_growth", return_value=70.0),
            patch.object(loader, "_score_value", return_value=60.0),
            patch.object(loader, "_score_risk", return_value=50.0),
            patch.object(loader, "_score_momentum", return_value=90.0),
        ):
            mock_db_ctx.return_value.__enter__.return_value = MagicMock()
            return loader._compute_stock_score("TEST")

    def test_success_path_writes_reason_type_unknown(self) -> None:
        """Matches the column's own DEFAULT and every other successful row - and, critically,
        actively RESETS a stale 'loader_failed' carried over from a prior failed attempt,
        since BulkInsertManager only clears/overwrites columns present in the row dict."""
        result = self._compute()
        assert "reason_type" in result
        assert result["reason_type"] == "unknown"

    def test_reason_type_present_even_though_reason_text_is_none(self) -> None:
        """Full-completeness case (reason_text is None, no missing-metrics message) must
        still carry reason_type - it's not conditioned on reason_text being set."""
        result = self._compute()
        assert result["reason"] is None
        assert result["reason_type"] == "unknown"


class TestReasonTypeOnFailurePaths:
    """fetch_incremental's own two exception branches - unchanged by this fix, confirmed
    still correctly set to 'loader_failed' for genuine failures."""

    def _loader(self) -> StockScoresLoader:
        loader = StockScoresLoader.__new__(StockScoresLoader)
        loader._quality_cache = {}
        return loader

    def test_runtime_error_from_compute_marks_loader_failed(self) -> None:
        loader = self._loader()
        with patch.object(loader, "_compute_stock_score", side_effect=RuntimeError("no data")):
            rows = loader.fetch_incremental("TEST", None)
        assert rows[0]["reason_type"] == "loader_failed"
        assert rows[0]["data_unavailable"] is True

    def test_unexpected_none_return_marks_loader_failed(self) -> None:
        loader = self._loader()
        with patch.object(loader, "_compute_stock_score", return_value=None):
            rows = loader.fetch_incremental("TEST", None)
        assert rows[0]["reason_type"] == "loader_failed"
        assert rows[0]["data_unavailable"] is True
