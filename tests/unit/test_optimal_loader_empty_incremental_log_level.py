#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: OptimalLoader.load_symbol() logged an empty
fetch_incremental result at WARNING, despite its own comment documenting it as expected
("No new data since watermark - expected for incremental loads"). On a full-universe run
(~5000 symbols) this fires for most/all of them - confirmed live: one orchestrator dry-run
logged 4753 of these against price/signal data that legitimately hadn't changed since the
prior close, vs. single digits of every other WARNING/ERROR combined. The aggregate count
is already surfaced via self._stats -> MetricsPublisher.put_loader_result, so nothing is
lost by moving the per-symbol line to DEBUG.
"""

from unittest.mock import patch

from utils.optimal_loader import OptimalLoader


class _TestLoader(OptimalLoader):
    table_name = "stock_scores"  # any real SAFE_TABLES entry - required for __init__ validation

    def fetch_incremental(self, symbol, since):
        return []


class TestEmptyIncrementalResultLogLevel:
    def test_empty_result_logs_at_debug_not_warning(self):
        loader = _TestLoader()
        loader._backfill_days = 1  # avoids a DB watermark lookup in load_symbol

        with patch("utils.optimal_loader.logger") as mock_logger:
            result = loader.load_symbol("AAPL")

        assert result == 0
        mock_logger.warning.assert_not_called()
        debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any("Empty result from fetch_incremental" in c for c in debug_calls), debug_calls
