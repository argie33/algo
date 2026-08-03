"""Regression test: loaders/runner.py's run_loader() used `loader_class.table_name` (the
CLASS attribute) instead of `loader.table_name` (the actual instantiated loader) when writing
to data_loader_status. This is silently wrong for any OptimalLoader subclass that only sets
table_name inside __init__ as an instance attribute rather than as a class-level attribute -
which is exactly how ConsolidatedFinancialStatementsLoader (loaders/load_financial_statements.py)
works, since it manages 6 different destination tables (annual/quarterly/ttm x
income/balance/cashflow) and sets self.table_name per-combo, never at class level.

`loader_class.table_name` on such a class resolves via MRO straight to OptimalLoader's own
base-class default (`table_name: str = ""`), so every run_loader() call for this loader wrote
its final status under table_name="" - live-confirmed via a real data_loader_status row:
table_name='', error_message='Incomplete load: only None/None symbols loaded (0.00%)',
consecutive_failures climbing on every run. Fixed by using `loader.table_name` (the real
instance, populated by __init__) at every post-instantiation call site.
"""

from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


class _NoClassLevelTableNameLoader(OptimalLoader):
    """Mirrors ConsolidatedFinancialStatementsLoader's shape: table_name is only ever set as
    an instance attribute inside __init__, never declared at class level."""

    def __init__(self):
        self.table_name = "quarterly_cash_flow"
        self.primary_key = ("symbol",)
        self.watermark_field = "updated_at"
        self.max_fail_rate = 15.0
        self.exclude_etfs_from_symbols = False

    def run(self, symbols, parallelism=1, backfill_days=None):
        return {
            "symbols_failed": 0,
            "symbols_loaded": len(symbols),
            "execution_duration_sec": 1.0,
            "retry_count": 0,
        }

    def close(self):
        pass


def test_run_loader_writes_status_under_instance_table_name(monkeypatch):
    import sys

    from loaders import runner

    assert "table_name" not in _NoClassLevelTableNameLoader.__dict__, (
        "test fixture must not declare table_name at class level - "
        "that's the exact condition this regression guards against"
    )

    monkeypatch.setattr(sys, "argv", ["run_loader.py", "--symbols", "AAPL,MSFT"])

    captured_table_names = []

    class _RecordingStatusManager:
        def __init__(self, table_name):
            captured_table_names.append(table_name)

        def mark_completed(self, **kwargs):
            pass

        def mark_failed(self, **kwargs):
            pass

    with patch("utils.loaders.status_manager.LoaderStatusManager", _RecordingStatusManager):
        exit_code = runner.run_loader(_NoClassLevelTableNameLoader)

    assert exit_code == 0
    assert captured_table_names, "LoaderStatusManager was never constructed"
    assert captured_table_names[-1] == "quarterly_cash_flow", (
        f"expected the real instance table_name, got {captured_table_names[-1]!r} - "
        "run_loader() is reading loader_class.table_name (class attribute) instead of "
        "loader.table_name (the actual instance)"
    )
