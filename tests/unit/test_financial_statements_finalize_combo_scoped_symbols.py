"""Regression test: load_financial_statements._finalize_combo()/_finalize_all() must pass
the actual requested `symbols` list through to OptimalLoader._update_final_status(), not
just the count.

Before this fix, _finalize_combo called `loader._update_final_status(symbol_count)` with no
symbols list. Per the 2026-08-03 scoping fix (test_optimal_loader_scoped_symbols_completion.py),
omitting `symbols` makes _update_final_status fall back to an UNSCOPED
`COUNT(DISTINCT symbol) FROM {table_name}` over the table's ENTIRE population, instead of just
the symbols this run actually requested.

This silently masked real failures on scoped runs (e.g. a watermark-reset re-fetch of a
handful of REIT symbols after fixing their revenue extraction): the unscoped count returned
the table's full historical symbol population (thousands), which is >= expected_symbols, so
completion_pct got capped to 100% and the loader was marked COMPLETED even if every single
requested symbol failed to load - exactly the "REIT revenue still wrong after loader
'succeeded'" symptom under investigation 2026-08-09.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import _finalize_all, _finalize_combo


class _FakeStats:
    def __init__(self, symbols_failed=0):
        self._data = {"symbols_failed": symbols_failed}

    def set(self, key, value):
        self._data[key] = value

    def to_dict(self):
        return dict(self._data)


class _FakeLoader:
    table_name = "annual_income_statement"
    max_fail_rate = 15.0

    def __init__(self, symbols_failed=0):
        self._stats = _FakeStats(symbols_failed=symbols_failed)
        self.update_final_status_calls = []
        self.history_calls = []

    def _update_final_status(self, expected_symbols, symbols=None):
        self.update_final_status_calls.append((expected_symbols, symbols))

    def _log_execution_history(self, status, message=None):
        self.history_calls.append((status, message))

    def _invalidate_cache(self):
        pass


class TestFinalizeComboPassesScopedSymbols:
    def test_finalize_combo_forwards_symbols_list(self):
        loader = _FakeLoader()
        symbols = ["UDR", "BFS", "HR"]

        with patch("algo.reporting.metrics.MetricsPublisher") as mock_publisher:
            mock_publisher.return_value.__enter__.return_value = MagicMock()
            ok = _finalize_combo(loader, symbol_count=len(symbols), duration_sec=1.0, symbols=symbols)

        assert ok is True
        assert loader.update_final_status_calls == [(3, symbols)]

    def test_finalize_all_forwards_symbols_to_every_combo(self):
        loaders = [_FakeLoader(), _FakeLoader()]
        symbols = ["UDR", "BFS", "HR"]

        with patch("algo.reporting.metrics.MetricsPublisher") as mock_publisher:
            mock_publisher.return_value.__enter__.return_value = MagicMock()
            result = _finalize_all(
                loaders, total_combos=2, symbol_count=len(symbols), duration_sec=1.0, symbols=symbols
            )

        assert result == 0
        for loader in loaders:
            assert loader.update_final_status_calls == [(3, symbols)]
