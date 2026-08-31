"""Coverage test for algo/orchestrator/phase8_entry_execution.py's
_persist_signals_to_database() - found 2026-08-31 via an objective coverage-analysis pass
(the same one that found quote_fetcher.py/liquidity_checks.py completely untested) to have
zero dedicated tests anywhere in the suite, despite being the function responsible for writing
every generated trading signal to algo_signals for dashboard visibility and audit trail. Its
own docstring documents the exact bug it was written to fix: "Signals were being generated but
never saved, causing: Dashboard to show no signals... No signal audit trail" - a regression
here would silently reintroduce that exact failure mode.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.orchestrator.phase8_entry_execution import _persist_signals_to_database

RUN_DATE = date(2026, 1, 15)


def _good_signal(symbol="AAPL", **overrides):
    signal = {
        "symbol": symbol,
        "entry_price": 100.0,
        "composite_score": 75.0,
        "risk_score": 20.0,
    }
    signal.update(overrides)
    return signal


def _mock_cursor(rowcount=1):
    cur = MagicMock()
    cur.rowcount = rowcount
    return cur


class TestPersistSignalsEmptyInput:
    def test_empty_list_returns_zero_without_touching_db(self):
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            result = _persist_signals_to_database([], RUN_DATE, dry_run=False)
        assert result == 0
        MockDB.assert_not_called()


class TestPersistSignalsHappyPath:
    def test_inserts_one_valid_signal(self):
        cur = _mock_cursor(rowcount=1)
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([_good_signal()], RUN_DATE, dry_run=False)
        assert result == 1
        cur.execute.assert_called_once()

    def test_inserts_multiple_valid_signals(self):
        cur = _mock_cursor(rowcount=1)
        signals = [_good_signal("AAPL"), _good_signal("MSFT"), _good_signal("GOOG")]
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database(signals, RUN_DATE, dry_run=False)
        assert result == 3
        assert cur.execute.call_count == 3

    def test_uses_signal_quality_score_field_when_composite_score_absent(self):
        cur = _mock_cursor(rowcount=1)
        signal = _good_signal(composite_score=None)
        del signal["composite_score"]
        signal["signal_quality_score"] = 82.0
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([signal], RUN_DATE, dry_run=False)
        assert result == 1


class TestPersistSignalsValidationSkips:
    """Every one of these must be SKIPPED (not raise, not corrupt the batch) - a single bad
    signal must not prevent the rest of the batch from persisting."""

    def test_skips_signal_with_no_symbol(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal(symbol=None)
        good = _good_signal("MSFT")
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad, good], RUN_DATE, dry_run=False)
        assert result == 1
        assert cur.execute.call_count == 1

    def test_skips_signal_with_missing_entry_price(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal()
        del bad["entry_price"]
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_zero_entry_price(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal(entry_price=0)
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_negative_entry_price(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal(entry_price=-5.0)
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_nan_entry_price(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal(entry_price=float("nan"))
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_no_quality_score_at_all(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal()
        del bad["composite_score"]
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_invalid_composite_score(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal(composite_score="not-a-number")
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_missing_risk_score(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal()
        del bad["risk_score"]
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_skips_signal_with_invalid_risk_score(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal(risk_score=float("inf"))
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([bad], RUN_DATE, dry_run=False)
        assert result == 0

    def test_one_bad_signal_does_not_block_the_rest_of_the_batch(self):
        cur = _mock_cursor(rowcount=1)
        bad = _good_signal("BAD", entry_price=None)
        del bad["entry_price"]
        good1 = _good_signal("AAPL")
        good2 = _good_signal("MSFT")
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _persist_signals_to_database([good1, bad, good2], RUN_DATE, dry_run=False)
        assert result == 2
        assert cur.execute.call_count == 2


class TestPersistSignalsDatabaseErrors:
    def test_raises_runtime_error_on_database_error(self):
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.DatabaseError("connection lost")
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            with pytest.raises(RuntimeError, match="Failed to persist"):
                _persist_signals_to_database([_good_signal()], RUN_DATE, dry_run=False)

    def test_raises_when_insert_reports_zero_rowcount(self):
        """A silent 0-row INSERT (no exception, but nothing actually written) must not be
        reported as success - this is the exact 'signals generated but never saved' bug class
        this function's own docstring documents fixing."""
        cur = _mock_cursor(rowcount=0)
        with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            with pytest.raises(RuntimeError, match="no rows"):
                _persist_signals_to_database([_good_signal()], RUN_DATE, dry_run=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
