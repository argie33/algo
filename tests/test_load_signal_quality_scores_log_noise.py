#!/usr/bin/env python3
"""Regression test: a symbol with no active buy/sell signal must not be logged at ERROR.

load_signal_quality_scores.py's fetch_incremental() previously logged every symbol with
no buy_sell_daily rows in the lookback window via a bare `except Exception` at ERROR
level - the ordinary, expected outcome for the large majority of ~10k symbols on any
given day. A single dry-run against one trading day produced 720 such ERROR lines,
making any genuinely rare failure invisible in the noise. Fixed by raising a dedicated
_NoBuySellSignalsError for the no-signals case and logging it at DEBUG, while genuine
exceptions still log at ERROR.
"""

import logging
from datetime import date
from unittest.mock import patch

from loaders.load_signal_quality_scores import SignalQualityScoresLoader


def _loader_with_batch_context():
    loader = SignalQualityScoresLoader.__new__(SignalQualityScoresLoader)
    loader._batch_context = {
        "end_date": date(2026, 7, 24),
        "bs_signal_count": 1000,  # comfortably above both warning thresholds
        "watermarks": {},
    }
    return loader


def test_no_signals_case_logs_debug_not_error(caplog):
    loader = _loader_with_batch_context()

    with patch.object(loader, "_fetch_buy_sell_signals", return_value=[]):
        with caplog.at_level(logging.DEBUG, logger="loaders.load_signal_quality_scores"):
            result = loader.fetch_incremental("ZZZZ", since=date(2026, 7, 1))

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not error_records, f"No-signals case must not log at ERROR, got: {error_records}"

    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("SIGNAL_QUALITY_SKIP" in m for m in debug_messages)

    # Behavior (data_unavailable marker records) must be unchanged - only the log level moved.
    assert result is not None
    assert len(result) > 0
    assert all(r["data_unavailable"] is True for r in result)


def test_genuine_exception_still_logs_error(caplog):
    loader = _loader_with_batch_context()

    with patch.object(loader, "_fetch_buy_sell_signals", side_effect=RuntimeError("db connection lost")):
        with caplog.at_level(logging.DEBUG, logger="loaders.load_signal_quality_scores"):
            result = loader.fetch_incremental("ZZZZ", since=date(2026, 7, 1))

    error_messages = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("SIGNAL_QUALITY_ERROR" in m and "db connection lost" in m for m in error_messages), (
        f"Genuine exceptions must still log at ERROR, got: {error_messages}"
    )
    assert result is not None
    assert all(r["data_unavailable"] is True for r in result)
