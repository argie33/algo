"""Regression test: scripts/run_loader.py --limit must truncate the symbols list, not pass
limit as a kwarg to loader.run().

Bug (found 2026-08-10): run_loader_generic()'s default branch (and the value/quality/growth
and technical_data_daily branches) passed `limit` straight through as `kwargs["limit"]` into
`loader.run(**kwargs)`. No loader's run() - not OptimalLoader's base signature, nor any
subclass override, including StockScoresLoader (the loader this module's own top-of-file
usage docstring gives as the "--limit 100" example) - actually accepts a `limit` keyword
argument. Every single `--limit` invocation crashed with "unexpected keyword argument
'limit'", including the documented example. Live-reproduced: `python scripts/run_loader.py
company_info --limit 10` and `python scripts/run_loader.py load_stock_scores --limit 5` both
crashed before the fix.

Fixed by truncating the symbols list to `limit` before calling loader.run(), instead of
forwarding `limit` itself.
"""

from unittest.mock import MagicMock

from scripts.run_loader import run_loader_generic


def _make_loader_class(table_name: str):
    captured = {}

    class _FakeLoader:
        def __init__(self):
            self.table_name = table_name

        def run(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"symbols_processed": len(kwargs.get("symbols", []))}

    return _FakeLoader, captured


class TestLimitTruncatesSymbolsInsteadOfBeingForwarded:
    def test_default_branch_truncates_symbols_and_never_passes_limit_kwarg(self):
        loader_class, captured = _make_loader_class("some_generic_table")
        symbols = [f"SYM{i}" for i in range(20)]

        run_loader_generic(loader_class, "load_some_generic_table.py", symbols=symbols, limit=5)

        assert captured["kwargs"]["symbols"] == symbols[:5]
        assert "limit" not in captured["kwargs"], (
            "run() was called with a 'limit' kwarg - no loader class actually accepts this, "
            "so this would raise TypeError in production"
        )

    def test_technical_data_daily_branch_truncates_symbols(self):
        loader_class, captured = _make_loader_class("technical_data_daily")
        symbols = [f"SYM{i}" for i in range(20)]

        run_loader_generic(loader_class, "load_technical_indicators.py", symbols=symbols, limit=3)

        assert captured["kwargs"]["symbols"] == symbols[:3]
        assert "limit" not in captured["kwargs"]

    def test_value_quality_growth_branch_truncates_symbols(self):
        loader_class, captured = _make_loader_class("quality_metrics")
        symbols = [f"SYM{i}" for i in range(20)]

        run_loader_generic(loader_class, "load_value_quality_growth_metrics.py", symbols=symbols, limit=4)

        assert captured["kwargs"]["symbols"] == symbols[:4]
        assert "limit" not in captured["kwargs"]

    def test_no_limit_passes_symbols_unchanged(self):
        loader_class, captured = _make_loader_class("some_generic_table")
        symbols = ["AAPL", "MSFT"]

        run_loader_generic(loader_class, "load_some_generic_table.py", symbols=symbols, limit=None)

        assert captured["kwargs"]["symbols"] == symbols
