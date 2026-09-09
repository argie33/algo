#!/usr/bin/env python3
"""Regression test for _batch_fetch_technical_data's sma_50 fallback, found via the
2026-09-09 real-money-readiness audit.

price_daily stores raw/unadjusted prices. sma_50 used to be a flat SQL AVG(close) over the
trailing 50 raw rows, so a real stock split inside that window read as a fake step straight
into sma_50 - which feeds live entry-sizing/technical-gate decisions. Fixed by computing
sma_50 in the same per-symbol pandas loop already used for ATR, running
detect_and_adjust_splits() (the same function the offline technical_data_daily loader uses)
on the trailing-50 window before averaging.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase8_entry_execution import _batch_fetch_technical_data
from loaders.technical_indicators import compute_atr


def _rows_with_split(symbol: str, run_date: date, pre_split_close: float, post_split_close: float) -> list[tuple]:
    """60 days of history: 50 pre-split days at pre_split_close, then a clean 2:1-ratio
    split down to post_split_close for the last 10 days - enough history for both the
    period=14 ATR window and the 50-row SMA window to land entirely post-split-detection."""
    rows = []
    d = run_date - timedelta(days=59)
    for i in range(50):
        rows.append((symbol, d, pre_split_close + 1.0, pre_split_close - 1.0, pre_split_close))
        d += timedelta(days=1)
    for i in range(10):
        rows.append((symbol, d, post_split_close + 0.5, post_split_close - 0.5, post_split_close))
        d += timedelta(days=1)
    return rows


class TestBatchFetchTechnicalDataSma50SplitAdjustment:
    def test_clean_split_in_window_produces_sma50_near_current_price(self):
        """Without split adjustment, sma_50 stays anchored near the pre-split level (~150),
        wildly different from the post-split current price (~75). With adjustment, sma_50
        must land close to the post-split price level instead."""
        run_date = date(2026, 9, 9)
        pre_split_close = 150.0
        post_split_close = 75.3  # ratio 150/75.3 = 1.992, within the 2% split-detection tolerance
        rows = _rows_with_split("SPLITSYM", run_date, pre_split_close, post_split_close)

        with patch("algo.orchestrator.phase8_technical_data.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchall.side_effect = [
                [{"symbol": "SPLITSYM", "close": post_split_close}],
                rows,
            ]
            mock_db.return_value.__enter__.return_value = mock_cur

            result = _batch_fetch_technical_data(
                {"SPLITSYM": {"sma_50": None, "atr_14": None, "close": None}}, run_date
            )

        assert "SPLITSYM" in result
        sma_50 = result["SPLITSYM"]["sma_50"]
        assert sma_50 is not None
        old_unadjusted_sma_50 = (pre_split_close * 50 + post_split_close * 10) / 60
        assert abs(sma_50 - post_split_close) < abs(sma_50 - old_unadjusted_sma_50), (
            f"split-adjusted sma_50 ({sma_50}) should land much closer to the post-split "
            f"current price ({post_split_close}) than to the old unadjusted average "
            f"({old_unadjusted_sma_50})"
        )
        assert 60.0 < sma_50 < 90.0

    def test_no_split_sma50_matches_plain_average(self):
        """No split in the window - detect_and_adjust_splits() must be a no-op, so sma_50
        matches a plain average of the trailing 50 closes, same as pre-fix behavior."""
        run_date = date(2026, 9, 9)
        rows = []
        d = run_date - timedelta(days=59)
        closes = []
        for i in range(60):
            c = 100.0 + i * 0.1
            closes.append(c)
            rows.append(("NOSPLITSYM", d, c + 1.0, c - 1.0, c))
            d += timedelta(days=1)
        expected_sma_50 = sum(closes[-50:]) / 50

        with patch("algo.orchestrator.phase8_technical_data.DatabaseContext") as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchall.side_effect = [
                [{"symbol": "NOSPLITSYM", "close": closes[-1]}],
                rows,
            ]
            mock_db.return_value.__enter__.return_value = mock_cur

            result = _batch_fetch_technical_data(
                {"NOSPLITSYM": {"sma_50": None, "atr_14": None, "close": None}}, run_date
            )

        assert result["NOSPLITSYM"]["sma_50"] == pytest.approx(expected_sma_50, rel=1e-9)
