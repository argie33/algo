"""Regression test: loaders/runner.py's run_loader() always passed symbols to loader.run()
in get_active_symbols()'s fixed `ORDER BY symbol` (alphabetical) order. For a loader whose
per-symbol latency * universe size exceeds its own timeout, this is a structural coverage
gap, not a transient stall - every run starts over from 'A' and the timeout always cuts it
off at the same point, so symbols past that point are never reached, run after run.

Live-confirmed for current_reports_8k (loaders/load_current_reports_8k.py): a 120-minute SEC
EDGAR loader with ~10s/symbol latency against a 4,922-symbol universe only ever reached ~886
symbols (through 'COCP') - DB query confirmed zero rows, ever, for symbols past that point.
sec_segment_info hits the same fixed-order gap via a hard process crash instead of a timeout.

Fixed by an opt-in `rotate_symbols_daily` class attribute: when set, run_loader() rotates the
symbol list by a day-of-year-derived offset before calling loader.run(), so the covered window
shifts daily instead of the same prefix being processed forever. Loaders that already complete
a full pass within their timeout do not set this flag and are unaffected (test asserts
alphabetical order is preserved when the flag is absent).
"""

from datetime import date
from unittest.mock import patch

from utils.optimal_loader import OptimalLoader


class _RecordingLoader(OptimalLoader):
    table_name = "some_table"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 15.0
    exclude_etfs_from_symbols = False
    rotate_symbols_daily = False

    def __init__(self):
        self.received_symbols = None

    def run(self, symbols, parallelism=1, backfill_days=None):
        self.received_symbols = list(symbols)
        return {
            "symbols_failed": 0,
            "symbols_loaded": len(symbols),
            "execution_duration_sec": 1.0,
            "retry_count": 0,
        }

    def close(self):
        pass


class _RotatingLoader(_RecordingLoader):
    rotate_symbols_daily = True


class _NullStatusManager:
    def __init__(self, table_name):
        pass

    def mark_completed(self, **kwargs):
        pass

    def mark_failed(self, **kwargs):
        pass


def _run(monkeypatch, loader_class, symbols):
    import sys

    from loaders import runner

    monkeypatch.setattr(sys, "argv", ["run_loader.py"])
    instances = []
    original_init = loader_class.__init__

    def _tracking_init(self):
        original_init(self)
        instances.append(self)

    with (
        patch("loaders.runner.get_active_symbols", return_value=list(symbols)),
        patch("utils.loaders.status_manager.LoaderStatusManager", _NullStatusManager),
        patch.object(loader_class, "__init__", _tracking_init),
    ):
        runner.run_loader(loader_class)

    return instances[-1].received_symbols


def test_run_loader_preserves_alphabetical_order_when_rotation_disabled(monkeypatch):
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    received = _run(monkeypatch, _RecordingLoader, symbols)
    assert received == symbols


def test_run_loader_rotates_symbol_order_when_enabled(monkeypatch):
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    received = _run(monkeypatch, _RotatingLoader, symbols)

    expected_offset = date.today().toordinal() % len(symbols)
    expected = symbols[expected_offset:] + symbols[:expected_offset]

    assert received == expected
    assert sorted(received) == sorted(symbols), "rotation must not drop or duplicate symbols"
